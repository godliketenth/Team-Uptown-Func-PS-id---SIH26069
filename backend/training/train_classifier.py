"""Phase 1.1 — train an event-type classifier on sentence embeddings.

Trains multinomial logistic regression over the ONNX embeddings already used
for deduplication, then exports the weight matrix as a small .npz. Runtime
inference is a single matmul in numpy, so scikit-learn is a training-time
dependency only and never ships in the serving path.

Evaluated two ways, because only the second is informative:

  1. Held-out split of the synthetic corpus — near-circular, since the
     generator embeds the very keywords the rule engine searches for.
  2. A hand-written realistic set (training/eval_realistic.py) with implicit
     phrasing, Hinglish, misspellings and negation traps.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sklearn.linear_model import LogisticRegression          # noqa: E402
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix  # noqa: E402
from sklearn.model_selection import train_test_split          # noqa: E402
from sqlalchemy import text                                   # noqa: E402

from app.db.session import SessionLocal, engine               # noqa: E402
from app.services.pipeline import classify as rules           # noqa: E402
from app.services.pipeline import embeddings as E             # noqa: E402
from training.eval_realistic import REALISTIC_CASES           # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "models" / "event_classifier.npz"
BATCH = 256


async def load_corpus(limit: int = 30000):
    async with SessionLocal() as s:
        rows = (await s.execute(text("""
            SELECT r.normalized_text, e.payload->>'intended_event_type' AS label
            FROM reports r JOIN raw_events e ON e.id = r.raw_event_id
            WHERE e.payload->>'intended_event_type' IS NOT NULL
              AND r.normalized_text IS NOT NULL
              AND length(r.normalized_text) > 8
            LIMIT :lim
        """), {"lim": limit})).all()
    await engine.dispose()
    return [r[0] for r in rows], [r[1] for r in rows]


def embed_all(texts: list[str]) -> np.ndarray:
    out = []
    for i in range(0, len(texts), BATCH):
        chunk = E.embed_many(texts[i : i + BATCH])
        if chunk is None:
            raise SystemExit("embedding model unavailable — run `python fetch_model.py`")
        out.extend(chunk)
        print(f"  embedded {min(i + BATCH, len(texts))}/{len(texts)}", end="\r")
    print()
    return np.asarray(out, dtype=np.float32)


def keyword_predictions(texts: list[str]) -> list[str]:
    return [rules.predict(t)[0] for t in texts]


def main() -> None:
    print("loading labelled corpus …")
    texts, labels = asyncio.run(load_corpus())
    print(f"  {len(texts)} labelled reports across {len(set(labels))} classes")

    print("embedding …")
    X = embed_all(texts)
    y = np.asarray(labels)

    X_tr, X_te, y_tr, y_te, t_tr, t_te = train_test_split(
        X, y, texts, test_size=0.2, random_state=42, stratify=y
    )
    print(f"  train={len(X_tr)}  test={len(X_te)}")

    print("training logistic regression …")
    clf = LogisticRegression(max_iter=2000, C=4.0, class_weight="balanced")
    clf.fit(X_tr, y_tr)

    # ---- Evaluation 1: held-out synthetic split (near-circular) -------------
    ml_pred = clf.predict(X_te)
    kw_pred = keyword_predictions(t_te)
    ml_acc = accuracy_score(y_te, ml_pred)
    kw_acc = accuracy_score(y_te, kw_pred)

    print("\n" + "=" * 72)
    print("EVAL 1 — held-out synthetic split  (near-circular, expect both high)")
    print("=" * 72)
    print(f"  rule-based keywords : {kw_acc:6.2%}")
    print(f"  embedding model     : {ml_acc:6.2%}")
    print("\n" + classification_report(y_te, ml_pred, digits=3, zero_division=0))
    labels_sorted = sorted(set(y))
    print("confusion matrix (rows = true, cols = predicted)")
    print("            " + " ".join(f"{l[:5]:>6s}" for l in labels_sorted))
    for row, l in zip(confusion_matrix(y_te, ml_pred, labels=labels_sorted), labels_sorted):
        print(f"  {l:11s}" + " ".join(f"{v:6d}" for v in row))

    # ---- Evaluation 2: hand-written realistic phrasing ----------------------
    r_texts = [c[0].lower() for c in REALISTIC_CASES]
    r_true = [c[1] for c in REALISTIC_CASES]
    r_ml = clf.predict(embed_all(r_texts))
    r_kw = keyword_predictions(r_texts)

    print("\n" + "=" * 72)
    print("EVAL 2 — hand-written realistic reports  (the informative one)")
    print("=" * 72)
    print(f"  rule-based keywords : {accuracy_score(r_true, r_kw):6.2%}")
    print(f"  embedding model     : {accuracy_score(r_true, r_ml):6.2%}")
    print()
    print(f"  {'true':<13}{'rules':<14}{'model':<14}case")
    for (txt, true, why), k, m in zip(REALISTIC_CASES, r_kw, r_ml):
        mark = lambda p: ("OK " if p == true else "MISS")
        print(f"  {true:<13}{mark(k)+' '+k[:9]:<14}{mark(m)+' '+m[:9]:<14}{why}")

    np.savez(
        OUT,
        coef=clf.coef_.astype(np.float32),
        intercept=clf.intercept_.astype(np.float32),
        classes=np.asarray(clf.classes_),
    )
    print(f"\nsaved → {OUT}  ({OUT.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()

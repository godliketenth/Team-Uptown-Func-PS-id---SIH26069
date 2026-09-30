"""Phase 1.3 — a learned relevance signal for credibility.

**Scope, stated honestly.** There are no human-labelled false weather reports
in this system — zero verifier decisions have been recorded. So this model does
not answer "is this weather claim true?". It answers the narrower question the
available ground truth actually supports: **"is this a weather report at all?"**

That matters because it is the one credibility signal that genuinely broke. The
`NO_WEATHER_SIGNAL` flag used to detect off-topic posts by looking for a flat
classifier distribution. Once classification became a softmax over seven hazard
classes with no "none of the above" option, it labelled "anyone know when the
power comes back" as THUNDERSTORM at 98% confidence and the flag stopped firing
entirely.

**Text-only by design.** Relevance is a property of the text. Source trust,
corroboration and location confidence are already handled by the rule flags,
and mixing them in here would blur two different questions — and would mean a
well-written report from an untrusted source got marked irrelevant.

**A second signal, not a replacement.** The named flags stay, because an
operator in a disaster needs to know *why* something was doubted. A single
opaque score cannot tell them.

Two earlier versions of this script were wrong in ways worth recording:
  1. Labels were inferred from a missing `intended_event_type`, which swept in
     every satellite and weather-API observation — the most trustworthy sources
     in the system — and labelled them not credible. It scored 100%, because it
     had learned to recognise INSAT bulletins.
  2. The generator's off-topic pool was four fixed sentences, so the task was
     memorisable rather than learnable. It is now 32 varied posts spanning
     transport, civic complaints, daily life, Hinglish and native scripts, with
     a further 6 held out entirely to measure generalisation.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sklearn.linear_model import LogisticRegression          # noqa: E402
from sklearn.metrics import classification_report, precision_recall_fscore_support, roc_auc_score  # noqa: E402
from sklearn.model_selection import train_test_split          # noqa: E402
from sqlalchemy import text as sql                            # noqa: E402

from app.db.session import SessionLocal, engine               # noqa: E402
from app.services.ingestion.generator import NOISE_HOLDOUT, NOISE_POOL  # noqa: E402
from app.services.pipeline import embeddings as E             # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "models" / "credibility_model.npz"
BATCH = 256
POSITIVE_SAMPLE = 6000


async def load_weather_texts(limit: int) -> list[str]:
    """Genuine weather reports, from every source including satellite."""
    async with SessionLocal() as s:
        rows = (await s.execute(sql("""
            SELECT DISTINCT r.normalized_text
            FROM reports r JOIN raw_events e ON e.id = r.raw_event_id
            WHERE r.normalized_text IS NOT NULL
              AND length(r.normalized_text) > 8
              AND COALESCE((e.payload->>'is_noise')::boolean, false) = false
              AND e.payload->>'intended_event_type' IS NOT NULL
            LIMIT :lim
        """), {"lim": limit})).all()
        sat = (await s.execute(sql("""
            SELECT DISTINCT r.normalized_text FROM reports r
            WHERE r.source_type IN ('SATELLITE','WEATHER_API')
              AND r.normalized_text IS NOT NULL LIMIT 400
        """))).all()
    await engine.dispose()
    return [r[0] for r in rows] + [r[0] for r in sat]


def embed(texts: list[str]) -> np.ndarray:
    out = []
    for i in range(0, len(texts), BATCH):
        chunk = E.embed_many(texts[i : i + BATCH])
        if chunk is None:
            raise SystemExit("embedding model unavailable — run `python fetch_model.py`")
        out.extend(chunk)
    return np.asarray(out, dtype=np.float32)


def main() -> None:
    print("loading …")
    weather = asyncio.run(load_weather_texts(POSITIVE_SAMPLE))
    noise = [t.lower() for t in NOISE_POOL]
    holdout = [t.lower() for t in NOISE_HOLDOUT]
    print(f"  {len(weather)} distinct weather texts, {len(noise)} off-topic (+{len(holdout)} held out)")

    texts = weather + noise
    y = np.array([0] * len(weather) + [1] * len(noise))
    X = embed(texts)

    X_tr, X_te, y_tr, y_te = train_test_split(
        X, y, test_size=0.25, random_state=42, stratify=y
    )
    clf = LogisticRegression(max_iter=3000, C=1.0, class_weight="balanced")
    clf.fit(X_tr, y_tr)

    prob = clf.predict_proba(X_te)[:, 1]
    pred = (prob >= 0.5).astype(int)
    print("\n" + "=" * 70)
    print("HELD-OUT SPLIT  (seen phrasing)")
    print("=" * 70)
    print(f"  ROC AUC {roc_auc_score(y_te, prob):.4f}")
    print(classification_report(y_te, pred, target_names=["weather", "off-topic"], digits=3))

    # ---- the informative test: phrasing never seen in training -------------
    Xh = embed(holdout)
    ph = clf.predict_proba(Xh)[:, 1]
    caught = int((ph >= 0.5).sum())
    print("=" * 70)
    print("GENERALISATION  (off-topic phrasing held out of training entirely)")
    print("=" * 70)
    print(f"  {caught}/{len(holdout)} correctly identified as not a weather report\n")
    for t, p_ in zip(NOISE_HOLDOUT, ph):
        print(f"    {'OK  ' if p_ >= 0.5 else 'MISS'} p={p_:.3f}  {t[:54]}")

    # ---- comparison with the keyword relevance detector --------------------
    from app.services.pipeline.classify import has_weather_signal

    kw_hold = [0 if has_weather_signal(t) else 1 for t in holdout]
    kw_all = [0 if has_weather_signal(t) else 1 for t in texts]
    kp, kr, kf, _ = precision_recall_fscore_support(y, kw_all, average="binary", zero_division=0)
    print("\n" + "=" * 70)
    print("COMPARISON — keyword relevance detector (the current fallback)")
    print("=" * 70)
    print(f"  keywords  precision {kp:.3f}  recall {kr:.3f}  f1 {kf:.3f}")
    print(f"  keywords on held-out phrasing: {sum(kw_hold)}/{len(holdout)} caught")
    mp, mr, mf, _ = precision_recall_fscore_support(y_te, pred, average="binary", zero_division=0)
    print(f"  model     precision {mp:.3f}  recall {mr:.3f}  f1 {mf:.3f}")

    np.savez(OUT, coef=clf.coef_.astype(np.float32), intercept=clf.intercept_.astype(np.float32))
    print(f"\nsaved → {OUT} ({OUT.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()

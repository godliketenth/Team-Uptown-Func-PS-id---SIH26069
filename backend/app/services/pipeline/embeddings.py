"""Sentence embeddings via ONNX Runtime.

Phase 1.2 of the roadmap. Replaces character-level string matching with
semantic similarity, so a paraphrase or a translation of the same report is
recognised as the same report.

Deliberately ONNX rather than sentence-transformers: the quantized multilingual
MiniLM is ~118MB against ~2GB for a PyTorch install, starts in milliseconds,
and containerises cleanly for Phase 3.

The model is multilingual by necessity. An English-only encoder scores a Hindi
translation of a report no higher than an unrelated sentence, which would
silently defeat this stage on a third of our intake.

The model is optional. If the files are absent the service reports itself
unavailable and the dedup stage falls back to `difflib`, so the project still
runs with no ML download at all.
"""
from __future__ import annotations

import asyncio
import logging
import threading
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)

MODEL_DIR = Path(__file__).resolve().parents[3] / "models"
MODEL_PATH = MODEL_DIR / "model.onnx"
TOKENIZER_PATH = MODEL_DIR / "tokenizer.json"

EMBEDDING_DIM = 384          # paraphrase-multilingual-MiniLM-L12-v2
MAX_TOKENS = 128          # weather reports are short; truncating keeps it fast
_LOCK = threading.Lock()

_session = None
_tokenizer = None
_load_failed = False


def _load() -> bool:
    """Load model + tokenizer once. Returns False if unavailable."""
    global _session, _tokenizer, _load_failed

    if _session is not None and _tokenizer is not None:
        return True
    if _load_failed:
        return False

    with _LOCK:
        if _session is not None and _tokenizer is not None:
            return True
        if _load_failed:
            return False
        try:
            if not MODEL_PATH.exists() or not TOKENIZER_PATH.exists():
                raise FileNotFoundError(
                    f"embedding model not found in {MODEL_DIR} — run `python fetch_model.py`"
                )
            import onnxruntime as ort
            from tokenizers import Tokenizer

            options = ort.SessionOptions()
            options.intra_op_num_threads = 1      # many small inferences, not one big one
            options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

            _session = ort.InferenceSession(
                str(MODEL_PATH), options, providers=["CPUExecutionProvider"]
            )
            tok = Tokenizer.from_file(str(TOKENIZER_PATH))
            tok.enable_truncation(max_length=MAX_TOKENS)
            tok.enable_padding(length=None)
            _tokenizer = tok
            log.info("embedding model loaded from %s", MODEL_PATH)
            return True
        except Exception as exc:
            _load_failed = True
            log.warning("semantic embeddings unavailable (%s); dedup falls back to difflib", exc)
            return False


def is_available() -> bool:
    return _load()


def embed_many(texts: list[str]) -> list[list[float]] | None:
    """Embed a batch. Returns L2-normalized vectors, or None if unavailable."""
    if not texts:
        return []
    if not _load():
        return None

    try:
        encodings = _tokenizer.encode_batch([t or "" for t in texts])
        input_ids = np.array([e.ids for e in encodings], dtype=np.int64)
        attention_mask = np.array([e.attention_mask for e in encodings], dtype=np.int64)

        feeds = {"input_ids": input_ids, "attention_mask": attention_mask}
        expected = {i.name for i in _session.get_inputs()}
        if "token_type_ids" in expected:
            feeds["token_type_ids"] = np.zeros_like(input_ids)

        hidden = _session.run(None, feeds)[0]          # (batch, seq, dim)

        # Mean-pool over real tokens only, then L2 normalize so cosine
        # similarity is a plain dot product.
        mask = attention_mask[..., None].astype(np.float32)
        summed = (hidden * mask).sum(axis=1)
        counts = np.clip(mask.sum(axis=1), 1e-9, None)
        pooled = summed / counts
        norms = np.clip(np.linalg.norm(pooled, axis=1, keepdims=True), 1e-9, None)
        return (pooled / norms).astype(np.float32).tolist()
    except Exception as exc:
        log.warning("embedding inference failed: %s", exc)
        return None


def embed(text: str) -> list[float] | None:
    result = embed_many([text])
    return result[0] if result else None


async def embed_async(text: str) -> list[float] | None:
    """Inference is blocking CPU work — keep it off the event loop."""
    return await asyncio.to_thread(embed, text)


def cosine(a, b) -> float:
    """Both vectors are already L2-normalized, so this is a dot product."""
    if a is None or b is None:
        return 0.0
    va, vb = np.asarray(a, dtype=np.float32), np.asarray(b, dtype=np.float32)
    if va.shape != vb.shape or va.size == 0:
        return 0.0
    return float(np.clip(np.dot(va, vb), -1.0, 1.0))

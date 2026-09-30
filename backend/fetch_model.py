"""Fetch the ONNX sentence-embedding model into backend/models/.

Idempotent and safe to re-run. Kept deliberately small: the int8 model is
~118MB versus ~2GB for a PyTorch install, and the quality difference for
near-duplicate detection is negligible.
"""
from pathlib import Path

from huggingface_hub import hf_hub_download

# Multilingual is not optional here: the intake is English, Hindi and Gujarati,
# and an English-only model scores a Hindi translation of a report no higher
# than an unrelated sentence — which would silently defeat the whole stage.
REPO = "Xenova/paraphrase-multilingual-MiniLM-L12-v2"
DEST = Path(__file__).parent / "models"
FILES = {"onnx/model_quantized.onnx": "model.onnx", "tokenizer.json": "tokenizer.json"}


def fetch() -> None:
    DEST.mkdir(parents=True, exist_ok=True)
    for remote, local in FILES.items():
        target = DEST / local
        if target.exists():
            print(f"  {local}: already present ({target.stat().st_size / 1e6:.1f} MB)")
            continue
        path = hf_hub_download(repo_id=REPO, filename=remote)
        target.write_bytes(Path(path).read_bytes())
        print(f"  {local}: downloaded ({target.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    print(f"fetching {REPO} →  {DEST}")
    fetch()

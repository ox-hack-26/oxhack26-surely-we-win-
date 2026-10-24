"""Paths and settings shared by every part of ClinicDrift.

Values come from the environment, falling back to the repo's .env file.
Stdlib only, so scripts can use it before anyone has installed anything.
"""
import os
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _load_dotenv(path: Path) -> None:
    """Copy KEY=value lines from .env into os.environ, without overriding real env vars."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


_load_dotenv(REPO / ".env")

DATA_DIR = Path(os.environ.get("CLINICDRIFT_DATA") or REPO / "data")
RAW_DIR = DATA_DIR / "raw"            # parquet files exactly as downloaded
PROCESSED_DIR = DATA_DIR / "processed"  # hand-off files (docs/handoffs.md)

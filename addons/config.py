"""Settings for the add-ons, read from environment variables or a local .env."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


GEMINI_API_KEY = _env("GEMINI_API_KEY")
GEMINI_MODEL = _env("GEMINI_MODEL", "gemini-3.8-flash") or "gemini-3.8-flash"
# Tried in order when GEMINI_MODEL is unavailable or out of quota; each model has its own daily limit.
GEMINI_FALLBACK_MODELS = [
    m.strip()
    for m in _env("GEMINI_FALLBACK_MODELS", "gemini-3.6-flash,gemini-3.5-flash,gemini-3.5-flash-lite").split(",")
    if m.strip()
]
ELEVENLABS_API_KEY = _env("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE_ID = _env("ELEVENLABS_VOICE_ID", "JBFqnCBsd6RMkjVDRZzb") or "JBFqnCBsd6RMkjVDRZzb"
ELEVENLABS_MODEL = _env("ELEVENLABS_MODEL", "eleven_multilingual_v2") or "eleven_multilingual_v2"

ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "out"


def out_dir() -> Path:
    """Return the output folder, creating it if needed."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    return OUT_DIR

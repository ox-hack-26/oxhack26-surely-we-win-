"""Thin wrapper around the Gemini API.

Every call returns None when there is no key or anything goes wrong, so callers
can fall back to their offline path; `last_error` says why ("429 RESOURCE_EXHAUSTED: ...").

Successful answers are saved under addons/cache/, one file per call, named after the
caller's tag (e.g. US-WEAR-01_week9_cause), the model and a hash of the request.
sample-data/gemini/ is read the same way, so committed answers replay with no quota.
An answer from the configured model is preferred; otherwise one from any model is used
for the same request (each file records which model wrote it).
If the configured model is unavailable (404) or out of quota (429), or still busy (503) after a
retry, the call moves on to the next model in config.GEMINI_FALLBACK_MODELS: each model has its
own daily free quota.
MODE picks how the cache is used:
    auto    saved answer if there is one, else call Gemini and save the answer
    replay  saved answers only, never call Gemini
    live    always call Gemini, and save the answer
"""

import functools
import hashlib
import json
import re
import time
from pathlib import Path
from typing import Optional

from . import config

MAX_IMAGES = 4
CACHE_DIR = config.ROOT / "cache"
SAMPLE_CACHE_DIR = config.ROOT.parent / "sample-data" / "gemini"  # read-only, committed
MIN_INTERVAL = 12.0  # seconds between live calls: the free tier allows 5 a minute
MAX_RETRY_WAIT = 90.0  # retry a 429 once if Gemini asks us to wait no longer than this
BUSY_RETRY_WAIT = 10.0  # retry a 503 (model busy) once after this long

MODE = "auto"
last_error: Optional[str] = None
calls = {"live": 0, "cached": 0}
_last_call = 0.0
_exhausted: set = set()  # models that were unavailable or out of quota this run


def available() -> bool:
    return bool(config.GEMINI_API_KEY)


def reset() -> None:
    """Clear last_error and the call counts, e.g. before each alarm."""
    global last_error
    last_error = None
    calls.update(live=0, cached=0)


@functools.lru_cache(maxsize=1)
def _client():
    # One client for the whole run: a throwaway client can be garbage-collected mid-request.
    from google import genai

    return genai.Client(api_key=config.GEMINI_API_KEY)


def _image_parts(images):
    """images: (caption, bytes, mime) tuples -> caption text followed by each image."""
    from google.genai import types

    parts = []
    for caption, data, mime in (images or [])[:MAX_IMAGES]:
        parts += [caption, types.Part.from_bytes(data=data, mime_type=mime)]
    return parts


def _cache_name(tag: str, kind: str, prompt: str, system: str, schema=None, images=None, model=None) -> str:
    # Images are keyed by caption (which names the scan), so a raw scan and its sample copy match.
    captions = [caption for caption, _, _ in (images or [])[:MAX_IMAGES]]
    request = json.dumps([kind, system, prompt, schema, captions], sort_keys=True)
    digest = hashlib.sha256(request.encode("utf-8")).hexdigest()[:12]
    return f"{tag}_{model or config.GEMINI_MODEL}_{digest}.json"


def _load_cached(name: str, any_model: str):
    """The saved response in `name`, else in a file for the same request from another model."""
    candidates = [folder / name for folder in (CACHE_DIR, SAMPLE_CACHE_DIR)]
    for folder in (CACHE_DIR, SAMPLE_CACHE_DIR):
        candidates += sorted(folder.glob(any_model)) if folder.is_dir() else []
    for path in candidates:
        if path.is_file():
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as e:
                print(f"[gemini] ignoring unreadable cache file {path.name}: {type(e).__name__}")
                continue
            if "response" in record:
                if record.get("model") != config.GEMINI_MODEL:
                    print(f"[gemini] using {record.get('model')}'s saved answer for {record.get('tag')}")
                return record["response"]
    return None


def _save_cached(name: str, tag: str, kind: str, response, model: str) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    record = {"tag": tag, "model": model, "kind": kind, "response": response}
    (CACHE_DIR / name).write_text(json.dumps(record, indent=2), encoding="utf-8")


def describe_error(e: Exception) -> str:
    """'429 RESOURCE_EXHAUSTED: <message>' for API errors, else the exception type and text."""
    code, status = getattr(e, "code", None), getattr(e, "status", None)
    message = getattr(e, "message", None) or str(e)
    message = message.split("\n")[0][:200]
    if code:
        return f"{code} {status or ''}".strip() + f": {message}"
    return f"{type(e).__name__}: {message}"


def _retry_delay(e: Exception) -> Optional[float]:
    """Seconds Gemini asks us to wait after a 429 ('Please retry in 1h2m3.4s'), if it says."""
    match = re.search(r"retry in (?:(\d+)h)?(?:(\d+)m)?([\d.]+)s", str(e))
    if not match:
        return None
    hours, minutes, seconds = match.groups()
    return int(hours or 0) * 3600 + int(minutes or 0) * 60 + float(seconds)


def _pace() -> None:
    global _last_call
    wait = MIN_INTERVAL - (time.monotonic() - _last_call)
    if wait > 0:
        time.sleep(wait)
    _last_call = time.monotonic()


def _call(tag: str, kind: str, request, parse, prompt: str, system: str, schema=None, images=None):
    """Shared cache, pacing, retry and error handling for both kinds of call."""
    global last_error
    name = _cache_name(tag, kind, prompt, system, schema, images)
    if MODE != "live":
        cached = _load_cached(name, _cache_name(tag, kind, prompt, system, schema, images, model="*"))
        if cached is not None:
            calls["cached"] += 1
            return cached
        if MODE == "replay":
            last_error = f"no saved Gemini answer for {tag} (replay mode)"
            print(f"[gemini] {last_error}")
            return None
    if not available():
        return None
    models = [config.GEMINI_MODEL] + [m for m in config.GEMINI_FALLBACK_MODELS if m != config.GEMINI_MODEL]
    for model in [m for m in models if m not in _exhausted]:
        for attempt in range(2):
            try:
                _pace()
                calls["live"] += 1
                result = parse(request(model))
                _save_cached(_cache_name(tag, kind, prompt, system, schema, images, model), tag, kind, result, model)
                return result
            except Exception as e:
                last_error = f"{model}: {describe_error(e)}"
                code = getattr(e, "code", None)
                delay = _retry_delay(e) if code == 429 else BUSY_RETRY_WAIT if code == 503 else None
                if attempt == 0 and delay is not None and delay <= MAX_RETRY_WAIT:
                    print(f"[gemini] {last_error}; retrying in {delay:.0f}s")
                    time.sleep(delay)
                    continue
                if code not in (404, 429, 503):
                    print(f"[gemini] falling back: {last_error}")
                    return None
                if code != 503:
                    _exhausted.add(model)
                print(f"[gemini] {last_error}; trying the next model")
                break
    print(f"[gemini] falling back: no Gemini model available (last error {last_error})")
    return None


def generate_json(prompt: str, schema: dict, system: str, images=None, tag: str = "call") -> Optional[dict]:
    """Ask Gemini for JSON matching `schema`. Returns the parsed dict or None."""

    def request(model):
        from google.genai import types

        return _client().models.generate_content(
            model=model,
            contents=[prompt] + _image_parts(images),
            config=types.GenerateContentConfig(
                system_instruction=system,
                response_mime_type="application/json",
                response_json_schema=schema,
                temperature=0.2,
            ),
        )

    return _call(tag, "json", request, lambda resp: json.loads(resp.text), prompt, system, schema, images)


def generate_text(prompt: str, system: str, tag: str = "call") -> Optional[str]:
    """Ask Gemini for free text. Returns the text or None."""

    def request(model):
        from google.genai import types

        return _client().models.generate_content(
            model=model,
            contents=[prompt],
            config=types.GenerateContentConfig(system_instruction=system, temperature=0.3),
        )

    return _call(tag, "text", request, lambda resp: resp.text, prompt, system)

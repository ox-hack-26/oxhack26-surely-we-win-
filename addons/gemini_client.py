"""Thin wrapper around the Gemini API.

Every call returns None when there is no key or anything goes wrong, so callers
can fall back to their offline path.
"""

import json
import mimetypes
from pathlib import Path
from typing import Optional

from . import config

MAX_IMAGES = 4


def available() -> bool:
    return bool(config.GEMINI_API_KEY)


def _client():
    from google import genai

    return genai.Client(api_key=config.GEMINI_API_KEY)


def _image_parts(image_paths):
    from google.genai import types

    parts = []
    for p in (image_paths or [])[:MAX_IMAGES]:
        path = Path(p)
        if not path.is_file():
            continue
        mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
        parts.append(types.Part.from_bytes(data=path.read_bytes(), mime_type=mime))
    return parts


def generate_json(prompt: str, schema: dict, system: str, image_paths=None) -> Optional[dict]:
    """Ask Gemini for JSON matching `schema`. Returns the parsed dict or None."""
    if not available():
        return None
    try:
        from google.genai import types

        resp = _client().models.generate_content(
            model=config.GEMINI_MODEL,
            contents=[prompt] + _image_parts(image_paths),
            config=types.GenerateContentConfig(
                system_instruction=system,
                response_mime_type="application/json",
                response_json_schema=schema,
                temperature=0.2,
            ),
        )
        return json.loads(resp.text)
    except Exception as e:
        print(f"[gemini] falling back: {type(e).__name__}: {e}")
        return None


def generate_text(prompt: str, system: str) -> Optional[str]:
    """Ask Gemini for free text. Returns the text or None."""
    if not available():
        return None
    try:
        from google.genai import types

        resp = _client().models.generate_content(
            model=config.GEMINI_MODEL,
            contents=[prompt],
            config=types.GenerateContentConfig(system_instruction=system, temperature=0.3),
        )
        return resp.text
    except Exception as e:
        print(f"[gemini] falling back: {type(e).__name__}: {e}")
        return None

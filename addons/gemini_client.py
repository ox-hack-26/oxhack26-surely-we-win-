"""Thin wrapper around the Gemini API.

Every call returns None when there is no key or anything goes wrong, so callers
can fall back to their offline path.
"""

import functools
import json
from typing import Optional

from . import config

MAX_IMAGES = 4


def available() -> bool:
    return bool(config.GEMINI_API_KEY)


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


def generate_json(prompt: str, schema: dict, system: str, images=None) -> Optional[dict]:
    """Ask Gemini for JSON matching `schema`. Returns the parsed dict or None."""
    if not available():
        return None
    try:
        from google.genai import types

        resp = _client().models.generate_content(
            model=config.GEMINI_MODEL,
            contents=[prompt] + _image_parts(images),
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

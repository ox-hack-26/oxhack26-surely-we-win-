"""Simulated camera wear: scans get blurrier and darker as the level rises from 0 to 1.

A worn-camera copy of a scan has the ID '<scan_id>@<level>', e.g. 'eyepacs-01234@0.40'.
load_image() understands these IDs, so the model, the dashboard and Gemini all see the same image.
"""
from PIL import Image, ImageEnhance, ImageFilter

MAX_BLUR = 0.02    # Gaussian blur radius at level 1, as a share of image width (about 20 px on a 1024 px scan)
MAX_DARKEN = 0.45  # share of brightness lost at level 1


def degraded_id(scan_id: str, level: float) -> str:
    return f"{scan_id}@{level:.2f}"


def split_id(scan_id: str) -> tuple[str, float]:
    """('eyepacs-01234', 0.4) for 'eyepacs-01234@0.40'; level 0 for an untouched scan."""
    base, _, level = scan_id.partition("@")
    return base, float(level) if level else 0.0


def degrade(img: Image.Image, level: float) -> Image.Image:
    """Blur and darken an RGB image. The blur scales with image width, so it looks the same at any size."""
    level = float(level)  # PIL's blur rejects NumPy numbers
    if level <= 0:
        return img
    img = img.filter(ImageFilter.GaussianBlur(radius=MAX_BLUR * level * img.width))
    return ImageEnhance.Brightness(img).enhance(1 - MAX_DARKEN * level)

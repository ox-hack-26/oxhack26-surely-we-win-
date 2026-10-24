"""Image handling shared by preparation, the model and the camera scenario.

Every source frames the retina differently (black borders, crops, aspect ratio), so each scan is
cropped to the retina and padded to a square before anything looks at it. Quality is measured on
that square at one fixed size, so a sharp 4288 px IDRiD scan and a 224 px APTOS scan compare fairly.
"""
import io

import cv2
import numpy as np
import pandas as pd
from PIL import Image

CACHE_SIZE = 448  # side of the square crops the model sees
STATS_SIZE = 512  # side of the square the quality stats are measured on
BACKGROUND = 12   # grey level at or below which a pixel is the black surround, not retina
EDGE = 0.03       # share of the square trimmed off the retina edge before measuring, to skip the rim


def decode(data: bytes, min_side: int = STATS_SIZE) -> tuple[np.ndarray, int, int]:
    """RGB uint8 array plus the original width and height.

    Large JPEGs are decoded at a reduced scale that still leaves at least min_side pixels, which is
    10x faster for the 4288 px IDRiD scans and loses nothing at the sizes used here.
    """
    im = Image.open(io.BytesIO(data))
    width, height = im.size
    im.draft("RGB", (min_side, min_side))
    return np.asarray(im.convert("RGB")), width, height


def retina_square(rgb: np.ndarray) -> np.ndarray:
    """Crop to the retina's bounding box and pad with black to a centred square, at full resolution."""
    mask = rgb.max(axis=2) > BACKGROUND
    rows = np.flatnonzero(mask.mean(axis=1) > 0.02)
    cols = np.flatnonzero(mask.mean(axis=0) > 0.02)
    if len(rows) and len(cols):
        rgb = rgb[rows[0]:rows[-1] + 1, cols[0]:cols[-1] + 1]
    h, w = rgb.shape[:2]
    side = max(h, w)
    square = np.zeros((side, side, 3), np.uint8)
    top, left = (side - h) // 2, (side - w) // 2
    square[top:top + h, left:left + w] = rgb
    return square


def resize(square: np.ndarray, size: int) -> np.ndarray:
    interpolation = cv2.INTER_AREA if square.shape[0] > size else cv2.INTER_CUBIC
    return cv2.resize(square, (size, size), interpolation=interpolation)


def measure(square: np.ndarray) -> dict:
    """brightness, contrast and sharpness of the retina in a STATS_SIZE square (see docs/handoffs.md)."""
    gray = cv2.cvtColor(square, cv2.COLOR_RGB2GRAY)
    mask = gray > BACKGROUND
    rim = max(1, int(EDGE * square.shape[0]))
    mask = cv2.erode(mask.astype(np.uint8), np.ones((2 * rim + 1, 2 * rim + 1), np.uint8)).astype(bool)
    if mask.sum() < 100:  # almost all black: measure the whole square rather than nothing
        mask = np.ones_like(mask)
    pixels = gray[mask].astype(np.float32)
    laplacian = cv2.Laplacian(gray.astype(np.float32), cv2.CV_32F)
    return {
        "brightness": float(pixels.mean() / 255),
        "contrast": float(pixels.std() / 255),
        "sharpness": float(laplacian[mask].var()),
    }


def prepare(data: bytes) -> tuple[np.ndarray, dict]:
    """One scan's CACHE_SIZE crop for the model, and its stats including original width and height."""
    rgb, width, height = decode(data)
    square = retina_square(rgb)
    stats = measure(resize(square, STATS_SIZE))
    return resize(square, CACHE_SIZE), {"width": width, "height": height, **stats}


def _ramp(x: pd.Series, zero: float, one: float) -> pd.Series:
    """0 at `zero`, 1 at `one`, linear in between and clipped outside."""
    return ((x - zero) / (one - zero)).clip(0, 1)


def quality_score(stats: pd.DataFrame, reference: pd.DataFrame) -> pd.Series:
    """0-1 image quality: the worst of sharpness, contrast and exposure, judged against the training scans.

    Each aspect scores 1 when it is at least as good as the training scans' 25th percentile (for
    exposure, inside their 25th-75th), falling to 0 at their 1st percentile (99th for over-exposure).
    So a typical training scan scores about 1 and a blurred, washed-out or dark one scores low.
    """
    sharp, ref_sharp = np.log1p(stats["sharpness"]), np.log1p(reference["sharpness"])
    q = lambda s, p: s.quantile(p)  # noqa: E731
    sharpness = _ramp(sharp, q(ref_sharp, 0.01), q(ref_sharp, 0.25))
    contrast = _ramp(stats["contrast"], q(reference["contrast"], 0.01), q(reference["contrast"], 0.25))
    b, rb = stats["brightness"], reference["brightness"]
    exposure = np.minimum(_ramp(b, q(rb, 0.01), q(rb, 0.25)), _ramp(b, q(rb, 0.99), q(rb, 0.75)))
    return pd.concat([sharpness, contrast, exposure], axis=1).min(axis=1).astype("float32")

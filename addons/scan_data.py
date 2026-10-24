"""Optional extra evidence for an alarm, read from the other hand-off files.

The alarm itself only lists scan ids. When scans.parquet, weekly.parquet or
clinicdrift.data.load_image are available, they give the cause finder image
statistics, the week's scan count and sample images. Each piece is optional:
anything missing comes back empty and the add-ons carry on without it.
"""

import io
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from clinicdrift.config import PROCESSED_DIR

from .alarm_schema import Alarm, ScanStats, summarise

SCANS_PATH = PROCESSED_DIR / "scans.parquet"
WEEKLY_PATH = PROCESSED_DIR / "weekly.parquet"
IMAGES_PER_SET = 2


@dataclass
class Evidence:
    flagged: Optional[ScanStats] = None
    reference: Optional[ScanStats] = None
    n_scans: Optional[int] = None  # scans at this clinic that week
    images: list = field(default_factory=list)  # (caption, bytes, mime)
    notes: list = field(default_factory=list)


def load_scan_rows(scan_ids, scans_path=None) -> list[dict]:
    """Rows of scans.parquet (or a JSON list with the same columns) for these ids."""
    path = Path(scans_path) if scans_path else SCANS_PATH
    ids = set(scan_ids)
    if not ids or not path.is_file():
        return []
    try:
        if path.suffix == ".json":
            rows = json.loads(path.read_text(encoding="utf-8"))
            return [r for r in rows if r.get("scan_id") in ids]
        import pandas as pd

        df = pd.read_parquet(path)
        return df[df["scan_id"].isin(ids)].to_dict("records")
    except Exception as e:
        print(f"[scans] could not read {path.name}: {type(e).__name__}: {e}")
        return []


def weekly_n_scans(alarm: Alarm, weekly_path=None) -> Optional[int]:
    """n_scans for this clinic and week from weekly.parquet, if it exists."""
    path = Path(weekly_path) if weekly_path else WEEKLY_PATH
    if not path.is_file():
        return None
    try:
        import pandas as pd

        df = pd.read_parquet(path)
        weeks = pd.to_datetime(df["week"]).dt.date
        row = df[(df["clinic_id"] == alarm.clinic_id) & (weeks == alarm.week)]
        return int(row["n_scans"].iloc[0]) if len(row) else None
    except Exception as e:
        print(f"[weekly] could not read {path.name}: {type(e).__name__}: {e}")
        return None


def _to_jpeg(image) -> Optional[bytes]:
    if isinstance(image, bytes):
        return image
    if isinstance(image, (str, Path)):
        return Path(image).read_bytes()
    if hasattr(image, "save"):  # PIL image
        buf = io.BytesIO()
        image.convert("RGB").save(buf, format="JPEG", quality=90)
        return buf.getvalue()
    return None


def load_images(scan_ids, caption: str) -> list:
    """Up to IMAGES_PER_SET images via clinicdrift.data.load_image, once that loader exists."""
    try:
        from clinicdrift.data import load_image
    except ImportError:
        return []
    images = []
    for scan_id in list(scan_ids)[:IMAGES_PER_SET]:
        try:
            data = _to_jpeg(load_image(scan_id))
        except Exception as e:
            print(f"[images] could not load {scan_id}: {type(e).__name__}: {e}")
            continue
        if data:
            images.append((f"{caption} ({scan_id}):", data, "image/jpeg"))
    return images


def gather_evidence(alarm: Alarm, scans_path=None, weekly_path=None, with_images=True) -> Evidence:
    """Everything the add-ons can find about this alarm beyond the alarm file itself."""
    ev = Evidence(
        flagged=summarise(load_scan_rows(alarm.flagged_scan_ids, scans_path)),
        reference=summarise(load_scan_rows(alarm.reference_scan_ids, scans_path)),
        n_scans=weekly_n_scans(alarm, weekly_path),
    )
    if ev.flagged is None or ev.reference is None:
        ev.notes.append("scan statistics unavailable (scans.parquet missing or scan ids not in it)")
    if with_images:
        ev.images = load_images(alarm.flagged_scan_ids, "Flagged scan from this clinic")
        ev.images += load_images(alarm.reference_scan_ids, "Typical training scan")
    return ev

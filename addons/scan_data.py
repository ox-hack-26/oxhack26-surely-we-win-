"""Optional extra evidence for an alarm, read from the other hand-off files.

The alarm normally carries flagged_scan_stats and training_scan_stats. If either
is missing, it is rebuilt from the scans.parquet rows for flagged_scan_ids or
reference_scan_ids, counting a scan as referred when p_referable >= the alarm's
referral_threshold (0.5 if the alarm has none). weekly.parquet gives the week's
scan count, and clinicdrift.data.sources.load_image (or the copies in
sample-data/images) gives sample images for Gemini. Each piece is
optional: anything missing comes back empty and the add-ons carry on without it.
"""

import io
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from clinicdrift.config import PROCESSED_DIR, REPO

from .alarm_schema import FALLBACK_REFER_THRESHOLD, Alarm, ScanStats, summarise

SCANS_PATH = PROCESSED_DIR / "scans.parquet"
STANDIN_SCANS_PATH = PROCESSED_DIR / "standin" / "scans.parquet"  # until Sarah's model has run
WEEKLY_PATH = PROCESSED_DIR / "weekly.parquet"
IMAGES_PER_SET = 2
SAMPLE_IMAGES = REPO / "sample-data" / "images"  # small copies, for machines without the raw scans


@dataclass
class Evidence:
    flagged: Optional[ScanStats] = None
    reference: Optional[ScanStats] = None
    n_scans: Optional[int] = None  # scans at this clinic that week
    images: list = field(default_factory=list)  # (caption, bytes, mime)
    notes: list = field(default_factory=list)
    threshold_note: Optional[str] = None  # set when referral_rate was rebuilt from scans.parquet


def default_scans_path() -> Path:
    """Sarah's scans.parquet, or the stand-in's while hers doesn't exist (as the engine does)."""
    return SCANS_PATH if SCANS_PATH.is_file() else STANDIN_SCANS_PATH


def load_scan_rows(scan_ids, scans_path=None) -> list[dict]:
    """Rows of scans.parquet (or a JSON list with the same columns) for these ids."""
    path = Path(scans_path) if scans_path else default_scans_path()
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
    if not alarm.week_start or not path.is_file():
        return None
    try:
        import pandas as pd

        df = pd.read_parquet(path)
        weeks = pd.to_datetime(df["week"]).dt.date
        row = df[(df["clinic_id"] == alarm.clinic_id) & (weeks == pd.Timestamp(alarm.week_start).date())]
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


def _loader():
    """clinicdrift's load_image, or None if it isn't there."""
    try:
        from clinicdrift.data.sources import load_image
    except ImportError:
        try:
            from clinicdrift.data import load_image
        except ImportError:
            return None
    return load_image


def _load_one(scan_id: str, load_image) -> Optional[bytes]:
    """The scan from the raw data if it is on this machine, else its copy in sample-data/images."""
    if load_image is not None:
        try:
            return _to_jpeg(load_image(scan_id))
        except Exception as e:
            error = f"{type(e).__name__}: {e}"
    else:
        error = "no load_image in clinicdrift.data"
    sample = SAMPLE_IMAGES / f"{scan_id}.jpg"
    if sample.is_file():
        return sample.read_bytes()
    print(f"[images] could not load {scan_id}: {error}")
    return None


def load_images(scan_ids, caption: str) -> list:
    """Up to IMAGES_PER_SET images via clinicdrift.data.sources.load_image, or sample-data/images."""
    load_image = _loader()
    images = []
    for scan_id in list(scan_ids)[:IMAGES_PER_SET]:
        data = _load_one(scan_id, load_image)
        if data:  # numbered, not by scan id: ids name the source dataset
            images.append((f"{caption} {len(images) + 1}:", data, "image/jpeg"))
    return images


def gather_evidence(alarm: Alarm, scans_path=None, weekly_path=None, with_images=True) -> Evidence:
    """The alarm's own stats, filled in from the other hand-off files where they are missing."""
    ev = Evidence(flagged=alarm.flagged_scan_stats, reference=alarm.training_scan_stats)
    threshold = alarm.referral_threshold
    if threshold is None:
        threshold = FALLBACK_REFER_THRESHOLD
    if ev.flagged is None:
        ev.flagged = summarise(load_scan_rows(alarm.flagged_scan_ids, scans_path), threshold)
        if ev.flagged is not None:
            ev.notes.append(f"flagged stats computed from {ev.flagged.n_scans} flagged scans in scans.parquet")
    if ev.reference is None:
        ev.reference = summarise(load_scan_rows(alarm.reference_scan_ids, scans_path), threshold)
        if ev.reference is not None:
            ev.notes.append(f"training stats computed from {ev.reference.n_scans} reference scans in scans.parquet")
    if ev.flagged is not alarm.flagged_scan_stats or ev.reference is not alarm.training_scan_stats:
        if alarm.referral_threshold is None:
            ev.threshold_note = (
                f"referral rate counts p_referable >= {threshold:g} (fallback: the alarm has no referral_threshold)"
            )
        else:
            ev.threshold_note = f"referral rate counts p_referable >= {threshold:g} (the alarm's referral_threshold)"
        ev.notes.append(ev.threshold_note)
    if ev.flagged is None or ev.reference is None:
        ev.notes.append("scan statistics unavailable (not in the alarm, and scans.parquet missing or scan ids not in it)")
    # flagged_scan_stats covers the whole clinic-week; stats built from flagged ids are only a sample
    if alarm.flagged_scan_stats is not None:
        ev.n_scans = alarm.flagged_scan_stats.n_scans
    else:
        ev.n_scans = weekly_n_scans(alarm, weekly_path)
    if with_images:
        ev.images = load_images(alarm.flagged_scan_ids, "Flagged scan from this clinic")
        ev.images += load_images(alarm.reference_scan_ids, "Typical training scan")
    return ev

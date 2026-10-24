"""The alarm files the engine hands to the add-ons.

The format is defined in docs/handoffs.md (section 4): one JSON file per alarm at
`$CLINICDRIFT_DATA/processed/alarms/<clinic_id>_<week>.json`. The add-ons only read it.
"""

import json
from datetime import date
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from clinicdrift.config import PROCESSED_DIR

ALARMS_DIR = PROCESSED_DIR / "alarms"

# scan_id / clinic_id prefix -> (dataset, country)
SOURCES = {
    "eyepacs": ("EyePACS", "US"),
    "aptos": ("APTOS 2019", "India"),
    "messidor2": ("Messidor-2", "France"),
    "idrid": ("IDRiD", "India"),
}

STAT_KEYS = [
    "mean_brightness",
    "mean_sharpness",
    "mean_quality",
    "mean_resolution_px",
    "referral_score_mean",
    "referral_rate",
]

REFER_THRESHOLD = 0.5


class Alarm(BaseModel):
    """One alarm, exactly as in docs/handoffs.md. Rates are fractions 0-1."""

    clinic_id: str
    week: date  # Monday the week starts
    est_sensitivity: float = Field(ge=0, le=1)
    est_low: float = Field(ge=0, le=1)  # 90% band
    est_high: float = Field(ge=0, le=1)
    baseline_sensitivity: float = Field(ge=0, le=1)
    expected_missed: float
    drift: float  # 0 = scans look like training
    quality_mean: float
    flagged_scan_ids: list[str] = []
    reference_scan_ids: list[str] = []

    @property
    def source(self) -> str:
        return self.clinic_id.split("-")[0]

    @property
    def site(self) -> str:
        return SOURCES.get(self.source, (self.source, ""))[0]

    @property
    def country(self) -> str:
        return SOURCES.get(self.source, ("", "unknown"))[1]

    @property
    def stem(self) -> str:
        return f"{self.clinic_id}_{self.week.isoformat()}"


class ScanStats(BaseModel):
    """Summary of a set of scans, built from rows of scans.parquet."""

    n_scans: int
    mean_brightness: Optional[float] = None  # 0-255
    mean_sharpness: Optional[float] = None  # variance of the Laplacian
    mean_quality: Optional[float] = None  # 0-1
    mean_resolution_px: Optional[float] = None  # width
    referral_score_mean: Optional[float] = None  # mean p_referable
    referral_rate: Optional[float] = None  # share with p_referable >= 0.5


def _mean(values) -> Optional[float]:
    vals = [float(v) for v in values if v is not None and v == v]  # drop None and NaN
    return sum(vals) / len(vals) if vals else None


def summarise(rows: list[dict]) -> Optional[ScanStats]:
    """Summarise scans.parquet rows. Returns None for no rows."""
    if not rows:
        return None
    p_known = [r.get("p_referable") for r in rows]
    p_known = [v for v in p_known if v is not None and v == v]
    return ScanStats(
        n_scans=len(rows),
        mean_brightness=_mean(r.get("brightness") for r in rows),
        mean_sharpness=_mean(r.get("sharpness") for r in rows),
        mean_quality=_mean(r.get("quality") for r in rows),
        mean_resolution_px=_mean(r.get("width") for r in rows),
        referral_score_mean=_mean(p_known),
        referral_rate=_mean(v >= REFER_THRESHOLD for v in p_known),
    )


def load_alarm(path) -> Alarm:
    """Read an alarm JSON file."""
    return Alarm.model_validate(json.loads(Path(path).read_text(encoding="utf-8")))


def alarm_path(clinic_id: str, week: str) -> Path:
    """Where the engine writes the alarm for this clinic and week."""
    return ALARMS_DIR / f"{clinic_id}_{week}.json"

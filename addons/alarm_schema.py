"""The alarm files the engine hands to the add-ons.

The format is defined in docs/handoffs.md (section 4): one JSON file per alarm at
`$CLINICDRIFT_DATA/processed/alarms/<clinic_id>_week<week>.json`. The add-ons only read it.
"""

import json
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from clinicdrift.config import PROCESSED_DIR

ALARMS_DIR = PROCESSED_DIR / "alarms"

STAT_KEYS = [
    "mean_brightness",
    "mean_contrast",
    "mean_sharpness",
    "mean_quality",
    "mean_resolution_px",
    "referral_score_mean",
    "referral_rate",
]

# Only used when the add-ons summarise scans.parquet rows themselves; the engine
# applies the model's own operating threshold when it fills referral_rate.
REFER_THRESHOLD = 0.5


class ScanStats(BaseModel):
    """Summary statistics for a set of scans (docs/handoffs.md, ScanStats)."""

    n_scans: int
    mean_brightness: Optional[float] = None  # 0-1
    mean_contrast: Optional[float] = None  # 0-1
    mean_sharpness: Optional[float] = None  # variance of the Laplacian
    mean_quality: Optional[float] = None  # 0-1
    mean_resolution_px: Optional[float] = None  # width
    referral_score_mean: Optional[float] = None  # mean p_referable
    referral_rate: Optional[float] = None  # share of scans referred


class Alarm(BaseModel):
    """One alarm raised by the engine for one clinic and week. Rates are fractions 0-1."""

    clinic_id: str
    site: str
    country: str
    week: int  # weeks since this clinic's replay started (1 = first)
    week_start: Optional[str] = None  # Monday the week starts
    device_name: str = "ClinicDrift-monitored DR screening model"
    device_version: str = "v1.0"
    estimated_catch_rate: float = Field(ge=0, le=1)
    ci_low: float = Field(ge=0, le=1)
    ci_high: float = Field(ge=0, le=1)
    baseline_catch_rate: float = Field(ge=0, le=1)
    expected_missed_cases: Optional[float] = None
    expected_harm: float
    review_cost: float
    # Optional here so a partial alarm still works: missing stats are filled from scans.parquet.
    flagged_scan_stats: Optional[ScanStats] = None
    training_scan_stats: Optional[ScanStats] = None
    flagged_scan_ids: list[str] = []
    reference_scan_ids: list[str] = []
    sample_scan_paths: list[str] = []

    @property
    def stem(self) -> str:
        return f"{self.clinic_id}_week{self.week}"


def _mean(values) -> Optional[float]:
    vals = [float(v) for v in values if v is not None and v == v]  # drop None and NaN
    return sum(vals) / len(vals) if vals else None


def summarise(rows: list[dict]) -> Optional[ScanStats]:
    """Summarise scans.parquet rows into ScanStats. Returns None for no rows."""
    if not rows:
        return None
    p_known = [r.get("p_referable") for r in rows]
    p_known = [v for v in p_known if v is not None and v == v]
    return ScanStats(
        n_scans=len(rows),
        mean_brightness=_mean(r.get("brightness") for r in rows),
        mean_contrast=_mean(r.get("contrast") for r in rows),
        mean_sharpness=_mean(r.get("sharpness") for r in rows),
        mean_quality=_mean(r.get("quality") for r in rows),
        mean_resolution_px=_mean(r.get("width") for r in rows),
        referral_score_mean=_mean(p_known),
        referral_rate=_mean(v >= REFER_THRESHOLD for v in p_known),
    )


def load_alarm(path) -> Alarm:
    """Read an alarm JSON file."""
    return Alarm.model_validate(json.loads(Path(path).read_text(encoding="utf-8")))


def alarm_path(clinic_id: str, week: int) -> Path:
    """Where the engine writes the alarm for this clinic and week."""
    return ALARMS_DIR / f"{clinic_id}_week{week}.json"

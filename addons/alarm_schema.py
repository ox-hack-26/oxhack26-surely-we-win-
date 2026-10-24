"""The hand-off format between the ClinicDrift monitor and the add-ons.

The prediction core writes one JSON file per alarm in this shape; the add-ons
only read it.
"""

import json
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

STAT_KEYS = [
    "mean_brightness",
    "mean_contrast",
    "mean_sharpness",
    "mean_quality",
    "mean_resolution_px",
    "referral_score_mean",
    "referral_rate",
]


class ScanStats(BaseModel):
    """Summary statistics for a batch of retinal scans."""

    n_scans: int
    mean_brightness: Optional[float] = None
    mean_contrast: Optional[float] = None
    mean_sharpness: Optional[float] = None
    mean_quality: Optional[float] = None
    mean_resolution_px: Optional[float] = None
    referral_score_mean: Optional[float] = None
    referral_rate: Optional[float] = None


class Alarm(BaseModel):
    """One alarm raised by the monitor for one clinic and week."""

    clinic_id: str
    site: str
    country: str
    week: int
    week_start: Optional[str] = None
    device_name: str = "ClinicDrift-monitored DR screening model"
    device_version: str = "v1.0"
    estimated_catch_rate: float = Field(ge=0, le=1)
    ci_low: float = Field(ge=0, le=1)
    ci_high: float = Field(ge=0, le=1)
    baseline_catch_rate: float = Field(ge=0, le=1)
    expected_harm: float
    review_cost: float
    expected_missed_cases: Optional[float] = None
    flagged_scan_stats: ScanStats
    training_scan_stats: ScanStats
    sample_scan_paths: list[str] = []


def load_alarm(path) -> Alarm:
    """Read an alarm JSON file."""
    return Alarm.model_validate(json.loads(Path(path).read_text(encoding="utf-8")))

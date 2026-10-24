"""Suggest the most likely cause of a clinic's catch-rate drop.

Rules compare the flagged week's scan statistics with the training data. If a
Gemini key is set, Gemini reviews the same numbers (and a few sample scans) and
gives its own answer; otherwise the rule result is returned.
"""

import json

from pydantic import BaseModel, Field, ValidationError

from . import gemini_client
from .alarm_schema import STAT_KEYS, Alarm

CATEGORIES = [
    "camera or image quality",
    "patient population shift",
    "model degradation",
    "data pipeline issue",
    "unknown",
]

IMAGE_KEYS = ["mean_brightness", "mean_contrast", "mean_sharpness", "mean_quality", "mean_resolution_px"]
NOTABLE = 0.15
MIN_SCANS = 10


class Cause(BaseModel):
    likely_cause: str
    category: str
    evidence: list[str]
    confidence: float = Field(ge=0, le=1)
    recommended_checks: list[str]
    source: str = "rules"


CAUSE_SCHEMA = {
    "type": "object",
    "properties": {
        "likely_cause": {"type": "string"},
        "category": {"type": "string", "enum": CATEGORIES},
        "evidence": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "recommended_checks": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["likely_cause", "category", "evidence", "confidence", "recommended_checks"],
}

SYSTEM = (
    "You are a cautious post-market surveillance analyst for an AI system that screens "
    "retinal photographs for diabetic retinopathy. You explain why a clinic's estimated "
    "catch rate may have dropped. Use only the numbers you are given; never invent numbers. "
    "Say when the evidence is weak."
)


def compute_shifts(alarm: Alarm) -> dict:
    """Relative change of each statistic from training to the flagged week."""
    flagged = alarm.flagged_scan_stats
    training = alarm.training_scan_stats
    shifts = {}
    for key in STAT_KEYS:
        f, t = getattr(flagged, key), getattr(training, key)
        if f is None or t is None or t == 0:
            continue
        shifts[key] = {"flagged": f, "training": t, "relative_change": round((f - t) / t, 3)}
    return shifts


def _label(key: str) -> str:
    return key.removeprefix("mean_").replace("_px", "").replace("_", " ")


def _evidence(key: str, s: dict) -> str:
    name = key.replace("_px", "").replace("_", " ")
    return f"{name}: {s['training']:g} -> {s['flagged']:g} ({s['relative_change']:+.0%})"


def rule_cause(alarm: Alarm) -> Cause:
    """Rule-based guess at the cause."""
    shifts = compute_shifts(alarm)
    notable = {k: s for k, s in shifts.items() if abs(s["relative_change"]) >= NOTABLE}
    evidence = [_evidence(k, s) for k, s in notable.items()]
    image_hits = [k for k in IMAGE_KEYS if k in notable]

    if alarm.flagged_scan_stats.n_scans < MIN_SCANS:
        return Cause(
            likely_cause="Too few scans this week to say what changed.",
            category="unknown",
            evidence=[f"only {alarm.flagged_scan_stats.n_scans} scans this week"] + evidence,
            confidence=0.2,
            recommended_checks=[
                "Wait for more scans before drawing conclusions",
                "Check whether scan uploads from this clinic have stopped or slowed",
            ],
        )
    if len(image_hits) >= 2:
        names = ", ".join(_label(k) for k in image_hits)
        return Cause(
            likely_cause=f"Image quality has changed at this clinic ({names} differ from training).",
            category="camera or image quality",
            evidence=evidence,
            confidence=min(0.9, 0.5 + 0.1 * len(image_hits)),
            recommended_checks=[
                "Confirm the camera model, firmware and settings in use at this clinic",
                "Review a sample of the low-quality scans by eye",
                "Check the pupil dilation and image capture protocol",
                "Have an expert re-grade a sample of this week's scans",
            ],
        )
    if list(notable) == ["referral_rate"]:
        return Cause(
            likely_cause="Images look like training, but the referral rate has moved: the patient mix may have changed.",
            category="patient population shift",
            evidence=evidence,
            confidence=0.55,
            recommended_checks=[
                "Ask the clinic whether its referral pathway or patient intake has changed",
                "Have an expert re-grade a sample of this week's scans",
            ],
        )
    if len(image_hits) == 1:
        return Cause(
            likely_cause=f"One image property ({_label(image_hits[0])}) differs from training.",
            category="camera or image quality",
            evidence=evidence,
            confidence=0.45,
            recommended_checks=[
                "Confirm the camera model, firmware and settings in use at this clinic",
                "Review a sample of the low-quality scans by eye",
                "Have an expert re-grade a sample of this week's scans",
            ],
        )
    return Cause(
        likely_cause="No clear change in the images; the model itself may be behaving differently.",
        category="model degradation",
        evidence=evidence or ["no scan statistic moved by 15% or more"],
        confidence=0.35,
        recommended_checks=[
            "Confirm the deployed model version matches the validated version",
            "Check that image preprocessing has not changed",
            "Re-run the model on a held-out validation set",
        ],
    )


def _prompt(alarm: Alarm, shifts: dict, rules: Cause) -> str:
    return (
        f"Clinic {alarm.clinic_id} ({alarm.site}, {alarm.country}), week {alarm.week}.\n"
        f"Estimated catch rate this week: {alarm.estimated_catch_rate:.0%} "
        f"(uncertainty band {alarm.ci_low:.0%}-{alarm.ci_high:.0%}); baseline {alarm.baseline_catch_rate:.0%}.\n"
        f"Scans this week: {alarm.flagged_scan_stats.n_scans}.\n"
        f"Scan statistics, flagged week vs training:\n{json.dumps(shifts, indent=2)}\n\n"
        f"A rule-based check suggests: {rules.category} - {rules.likely_cause}\n\n"
        "What is the most likely cause? Choose one category, cite the numbers above as "
        "evidence, give a confidence between 0 and 1, and list practical checks for the clinic."
    )


def find_cause(alarm: Alarm) -> Cause:
    """Gemini's view of the cause if available, otherwise the rule result."""
    rules = rule_cause(alarm)
    shifts = compute_shifts(alarm)
    result = gemini_client.generate_json(
        _prompt(alarm, shifts, rules), CAUSE_SCHEMA, SYSTEM, image_paths=alarm.sample_scan_paths
    )
    if result is None:
        return rules
    try:
        cause = Cause.model_validate({**result, "source": "gemini"})
    except ValidationError:
        return rules
    if cause.category not in CATEGORIES:
        return rules
    return cause

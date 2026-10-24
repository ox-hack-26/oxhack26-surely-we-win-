"""Suggest the most likely cause of a clinic's catch-rate drop.

Rules compare the alarm's flagged scans with its reference (training) scans,
using their rows in scans.parquet. If a Gemini key is set, Gemini reviews the
same numbers (and a few of the scans themselves) and gives its own answer;
otherwise the rule result is returned. Without scan statistics the rules
answer "unknown" and say why.
"""

import json
from typing import Optional

from pydantic import BaseModel, Field, ValidationError

from . import gemini_client
from .alarm_schema import STAT_KEYS, Alarm, ScanStats
from .scan_data import Evidence

CATEGORIES = [
    "camera or image quality",
    "patient population shift",
    "model degradation",
    "data pipeline issue",
    "unknown",
]

IMAGE_KEYS = ["mean_brightness", "mean_sharpness", "mean_quality", "mean_resolution_px"]
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
    "catch rate may have dropped. Use only the numbers and images you are given; never invent "
    "numbers. Say when the evidence is weak."
)


def compute_shifts(flagged: Optional[ScanStats], reference: Optional[ScanStats]) -> dict:
    """Relative change of each statistic from the reference scans to the flagged scans."""
    if flagged is None or reference is None:
        return {}
    shifts = {}
    for key in STAT_KEYS:
        f, t = getattr(flagged, key), getattr(reference, key)
        if f is None or t is None or t == 0:
            continue
        shifts[key] = {"flagged": round(f, 3), "training": round(t, 3), "relative_change": round((f - t) / t, 3)}
    return shifts


def _label(key: str) -> str:
    return key.removeprefix("mean_").replace("_px", "").replace("_", " ")


def _evidence(key: str, s: dict) -> str:
    name = key.replace("_px", "").replace("_", " ")
    return f"{name}: {s['training']:g} -> {s['flagged']:g} ({s['relative_change']:+.0%})"


def _alarm_evidence(alarm: Alarm) -> list[str]:
    return [
        f"drift from training: {alarm.drift:g} (0 = scans look like training)",
        f"mean image quality this week: {alarm.quality_mean:g}",
    ]


def rule_cause(alarm: Alarm, ev: Optional[Evidence] = None) -> Cause:
    """Rule-based guess at the cause."""
    ev = ev or Evidence()
    shifts = compute_shifts(ev.flagged, ev.reference)
    notable = {k: s for k, s in shifts.items() if abs(s["relative_change"]) >= NOTABLE}
    evidence = [_evidence(k, s) for k, s in notable.items()] + _alarm_evidence(alarm)
    image_hits = [k for k in IMAGE_KEYS if k in notable]

    if ev.n_scans is not None and ev.n_scans < MIN_SCANS:
        return Cause(
            likely_cause="Too few scans this week to say what changed.",
            category="unknown",
            evidence=[f"only {ev.n_scans} scans this week"] + evidence,
            confidence=0.2,
            recommended_checks=[
                "Wait for more scans before drawing conclusions",
                "Check whether scan uploads from this clinic have stopped or slowed",
            ],
        )
    if not shifts:
        return Cause(
            likely_cause=(
                "Scan statistics for the flagged and reference scans were not available, "
                "so the cause cannot be narrowed down yet."
            ),
            category="unknown",
            evidence=evidence + ev.notes,
            confidence=0.25,
            recommended_checks=[
                "Review the flagged scans by eye next to typical training scans",
                "Confirm the camera model, firmware and settings in use at this clinic",
                "Have an expert re-grade a sample of this week's scans",
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
    if [k for k in notable if k != "referral_score_mean"] == ["referral_rate"]:
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
        evidence=evidence,
        confidence=0.35,
        recommended_checks=[
            "Confirm the deployed model version matches the validated version",
            "Check that image preprocessing has not changed",
            "Re-run the model on a held-out validation set",
        ],
    )


def _prompt(alarm: Alarm, ev: Evidence, rules: Cause) -> str:
    shifts = compute_shifts(ev.flagged, ev.reference)
    stats = json.dumps(shifts, indent=2) if shifts else "not available"
    n = ev.n_scans if ev.n_scans is not None else "unknown"
    return (
        f"Clinic {alarm.clinic_id} ({alarm.site}, {alarm.country}), week starting {alarm.week}.\n"
        f"Estimated catch rate this week: {alarm.est_sensitivity:.0%} "
        f"(90% band {alarm.est_low:.0%}-{alarm.est_high:.0%}); baseline {alarm.baseline_sensitivity:.0%}.\n"
        f"Expected referable cases missed this week: {alarm.expected_missed:g}. Scans this week: {n}.\n"
        f"Drift from training: {alarm.drift:g} (0 = same). Mean image quality: {alarm.quality_mean:g}.\n"
        f"Statistics of the clinic's least typical scans vs typical training scans:\n{stats}\n"
        "(brightness is 0-255, sharpness is variance of the Laplacian, quality is 0-1, "
        "resolution is width in pixels, referral score is the classifier's probability.)\n\n"
        f"A rule-based check suggests: {rules.category} - {rules.likely_cause}\n\n"
        "Any images attached are flagged scans from this clinic and typical training scans, labelled.\n"
        "What is the most likely cause? Choose one category, cite the numbers above as "
        "evidence, give a confidence between 0 and 1, and list practical checks for the clinic."
    )


def find_cause(alarm: Alarm, ev: Optional[Evidence] = None) -> Cause:
    """Gemini's view of the cause if available, otherwise the rule result."""
    ev = ev or Evidence()
    rules = rule_cause(alarm, ev)
    result = gemini_client.generate_json(_prompt(alarm, ev, rules), CAUSE_SCHEMA, SYSTEM, images=ev.images)
    if result is None:
        return rules
    try:
        cause = Cause.model_validate({**result, "source": "gemini"})
    except ValidationError:
        return rules
    if cause.category not in CATEGORIES:
        return rules
    return cause

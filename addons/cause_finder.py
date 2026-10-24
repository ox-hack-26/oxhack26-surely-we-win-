"""Suggest the most likely cause of a clinic's catch-rate drop.

Rules compare the alarm's flagged scan statistics with the training ones
(filled in from scans.parquet if the alarm lacks them). If a Gemini key is set,
Gemini reviews the same numbers (and a few of the scans themselves) and gives
its own answer; otherwise the rule result is returned. Without scan statistics
the rules answer "unknown" and say why.
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

# Resolution is left out: clinics legitimately use cameras with different resolutions.
IMAGE_KEYS = ["mean_brightness", "mean_contrast", "mean_sharpness", "mean_quality"]
NOTABLE = 0.15
SHARP_DROP = 0.30  # a fall in quality or sharpness this big points at the images, not the patients
MAX_RULE_CONFIDENCE = 0.7  # the rules can't tell a different source from a faulty camera
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
    "retinal photographs for diabetic retinopathy. You explain why a clinic was flagged. "
    "Use only the numbers and images you are given; never invent numbers. Say when the evidence "
    "is weak. If the alarm is a drift alarm, its catch rate can't be verified: never quote a "
    "catch rate or catch-rate band for it."
)


def _sig(x: float) -> float:
    """x to 3 significant figures, so tiny values like sharpness 0.000398 don't round to 0."""
    return float(f"{x:.3g}")


def compute_shifts(flagged: Optional[ScanStats], training: Optional[ScanStats]) -> dict:
    """Relative change of each statistic from training to the flagged scans."""
    if flagged is None or training is None:
        return {}
    shifts = {}
    for key in STAT_KEYS:
        f, t = getattr(flagged, key), getattr(training, key)
        if f is None or t is None or t == 0:
            continue
        shifts[key] = {"flagged": _sig(f), "training": _sig(t), "relative_change": round((f - t) / t, 3)}
    return shifts


def _label(key: str) -> str:
    return key.removeprefix("mean_").replace("_px", "").replace("_", " ")


def _evidence(key: str, s: dict) -> str:
    name = key.replace("_px", "").replace("_", " ")
    return f"{name}: {s['training']:g} -> {s['flagged']:g} ({s['relative_change']:+.0%})"


def rule_cause(alarm: Alarm, ev: Optional[Evidence] = None) -> Cause:
    """Rule-based guess at the cause."""
    ev = ev or Evidence(flagged=alarm.flagged_scan_stats, reference=alarm.training_scan_stats)
    shifts = compute_shifts(ev.flagged, ev.reference)
    notable = {k: s for k, s in shifts.items() if abs(s["relative_change"]) >= NOTABLE}
    evidence = [_evidence(k, s) for k, s in notable.items()]
    if ev.threshold_note and "referral_rate" in notable:
        evidence.append(ev.threshold_note)
    image_hits = [k for k in IMAGE_KEYS if k in notable]
    image_drop = [k for k in ("mean_quality", "mean_sharpness") if k in shifts and shifts[k]["relative_change"] <= -SHARP_DROP]
    if "mean_resolution_px" in notable:
        evidence.append("resolution differs from training, but clinics' cameras legitimately differ, so it is context only")
    referral = None
    referral_key = next((k for k in ("referral_rate", "referral_score_mean") if k in notable), None)
    if referral_key:
        s = notable[referral_key]
        more = "more" if s["relative_change"] > 0 else "fewer"
        referral = (
            f"The AI is referring {more} patients than usual "
            f"({_label(referral_key)} {s['training']:g} -> {s['flagged']:g}, {s['relative_change']:+.0%})."
        )

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
                "Scan statistics for this clinic and for training were not available, "
                "so the cause cannot be narrowed down yet."
            ),
            category="unknown",
            evidence=ev.notes or ["no scan statistics available"],
            confidence=0.25,
            recommended_checks=[
                "Review the flagged scans by eye next to typical training scans",
                "Confirm the camera model, firmware and settings in use at this clinic",
                "Have an expert re-grade a sample of this week's scans",
            ],
        )
    if referral and not image_drop:
        return Cause(
            likely_cause=(
                f"{referral} Image quality and sharpness have not dropped sharply, "
                "so the patient mix may have changed."
            ),
            category="patient population shift",
            evidence=evidence,
            confidence=0.55,
            recommended_checks=[
                "Ask the clinic whether its referral pathway or patient intake has changed",
                "Have an expert re-grade a sample of this week's scans",
            ],
        )
    if len(image_hits) >= 2:
        names = ", ".join(_label(k) for k in image_hits)
        lead = f"{referral} " if referral else ""
        return Cause(
            likely_cause=f"{lead}Image quality has changed at this clinic ({names} differ from training).",
            category="camera or image quality",
            evidence=evidence,
            confidence=min(MAX_RULE_CONFIDENCE, 0.5 + 0.1 * len(image_hits)),
            recommended_checks=[
                "Confirm the camera model, firmware and settings in use at this clinic",
                "Review a sample of the low-quality scans by eye",
                "Check the pupil dilation and image capture protocol",
                "Have an expert re-grade a sample of this week's scans",
            ],
        )
    if len(image_hits) == 1:
        lead = f"{referral} " if referral else ""
        return Cause(
            likely_cause=f"{lead}One image property ({_label(image_hits[0])}) differs from training.",
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


def _prompt(alarm: Alarm, ev: Evidence, rules: Cause) -> str:
    shifts = compute_shifts(ev.flagged, ev.reference)
    stats = json.dumps(shifts, indent=2) if shifts else "not available"
    n = ev.n_scans if ev.n_scans is not None else "unknown"
    threshold = f"({ev.threshold_note}.)\n" if ev.threshold_note else ""
    if alarm.is_drift:
        score = f" (drift score {alarm.drift_auc:.2f}; 0.5 = like training, 1 = clearly different)" if alarm.drift_auc else ""
        status = (
            f"Drift alarm{score}: this clinic's scans no longer look like the ones the AI was validated on, "
            "so its catch rate can't be verified. Do not quote a catch rate.\n"
        )
    else:
        status = (
            f"Estimated catch rate this week: {alarm.estimated_catch_rate:.0%} "
            f"(uncertainty band {alarm.ci_low:.0%}-{alarm.ci_high:.0%}); baseline {alarm.baseline_catch_rate:.0%}.\n"
        )
    return (
        f"Clinic {alarm.clinic_id} ({alarm.site}, {alarm.country}), week {alarm.week}.\n"
        f"{status}"
        f"Scans this week: {n}.\n"
        f"Scan statistics, this clinic-week vs training:\n{stats}\n{threshold}"
        "(brightness and contrast are 0-1, sharpness is variance of the Laplacian, quality is 0-1, "
        "resolution is width in pixels, referral score is the classifier's probability.)\n\n"
        f"A rule-based check suggests: {rules.category} - {rules.likely_cause}\n\n"
        "Any images attached are flagged scans from this clinic and typical training scans, labelled.\n"
        "What is the most likely cause? Choose one category, cite the numbers above as "
        "evidence, give a confidence between 0 and 1, and list practical checks for the clinic."
    )


def find_cause(alarm: Alarm, ev: Optional[Evidence] = None) -> Cause:
    """Gemini's view of the cause if available, otherwise the rule result."""
    ev = ev or Evidence(flagged=alarm.flagged_scan_stats, reference=alarm.training_scan_stats)
    rules = rule_cause(alarm, ev)
    result = gemini_client.generate_json(
        _prompt(alarm, ev, rules), CAUSE_SCHEMA, SYSTEM, images=ev.images, tag=f"{alarm.stem}_cause"
    )
    if result is None:
        return rules
    try:
        cause = Cause.model_validate({**result, "source": "gemini"})
    except ValidationError as e:
        print(f"[gemini] cause rejected, using rules: {e.error_count()} invalid field(s)")
        return rules
    if cause.category not in CATEGORIES:
        print(f"[gemini] cause rejected, using rules: unknown category {cause.category!r}")
        return rules
    return cause

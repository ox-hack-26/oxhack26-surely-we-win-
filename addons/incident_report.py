"""Draft an MHRA-style adverse incident report for a ClinicDrift alarm.

The report is a draft for a human to check and submit; nothing is sent anywhere.
It is tagged with categories from the MIT AI Risk Repository.
"""

from typing import Optional

from . import gemini_client
from .alarm_schema import Alarm
from .cause_finder import Cause

# Not part of the alarm file (docs/handoffs.md); fixed for this prototype.
DEVICE_NAME = "ClinicDrift-monitored DR screening model"
DEVICE_VERSION = "v1.0"

MIT_RISKS = {
    "1.3": "Discrimination & toxicity > Unequal performance across groups",
    "3.1": "Misinformation > False or misleading information",
    "5.1": "Human-computer interaction > Overreliance and unsafe use",
    "7.3": "AI system safety, failures & limitations > Lack of capability or robustness",
    "7.4": "AI system safety, failures & limitations > Lack of transparency or interpretability",
}


def mit_tags(cause: Cause) -> list[str]:
    """MIT AI Risk Repository subdomains that apply to this alarm."""
    tags = ["7.3", "1.3", "5.1"]
    if cause.category in ("model degradation", "unknown"):
        tags.append("7.4")
    return tags


def _pct(x: float) -> str:
    return f"{x:.0%}"


def template_report(alarm: Alarm, cause: Cause, n_scans: Optional[int] = None) -> str:
    """Fill the report template from the alarm and cause. No network needed."""
    evidence = "\n".join(f"- {e}" for e in cause.evidence) or "- none recorded"
    checks = "\n".join(f"- [ ] {c}" for c in cause.recommended_checks) or "- [ ] none recorded"
    tags = "\n".join(f"- {t} {MIT_RISKS[t]}" for t in mit_tags(cause))
    based_on = f"{n_scans} scans from this week" if n_scans is not None else "this week's scans"
    return f"""# DRAFT: Medical device adverse incident report

> This is a draft for human review. It has not been submitted. A manufacturer would report
> through the MHRA MORE portal; healthcare professionals and users report through the Yellow Card scheme.

## 1. Device
- Name: {DEVICE_NAME}
- Version: {DEVICE_VERSION}
- Intended use: screening retinal photographs for referable diabetic retinopathy

## 2. Where and when
- Clinic: {alarm.clinic_id} ({alarm.site}, {alarm.country})
- Period: week starting {alarm.week.isoformat()}

## 3. What happened
ClinicDrift estimates the AI's catch rate (sensitivity for referable disease) at this clinic fell to
{_pct(alarm.est_sensitivity)} (90% band {_pct(alarm.est_low)} to {_pct(alarm.est_high)}), against a
baseline of {_pct(alarm.baseline_sensitivity)}. The estimate is predicted from {based_on} alone;
expert grades for these scans have not yet arrived. This week's scans differ from training
(drift {alarm.drift:g}, where 0 means no difference) and their mean image quality is {alarm.quality_mean:g}.

## 4. Potential patient impact
If the estimate is right, about {alarm.expected_missed:g} referable cases may have been missed this week.
No patient harm has been confirmed.

## 5. Likely cause
{cause.likely_cause} (category: {cause.category}; confidence {cause.confidence:.0%}; source: {cause.source})

Evidence:
{evidence}

## 6. Action
The alarm fired because the expected cost of missed cases (expected missed cases x cost per missed case)
exceeded the cost of reviewing this clinic's scans. We recommend pausing the AI at this clinic and
sending its scans for human grading until the checks below are complete.

Checks:
{checks}

## 7. Regulatory context
- Post-market surveillance (PMS): this alarm is part of ongoing monitoring of the device in use.
- Predetermined change control plan (PCCP): any model change made in response should fall within an agreed PCCP.
- MHRA AI Airlock Phase 2 report: see recommendations 3 and 4.

## 8. MIT AI Risk Repository tags
{tags}
"""


SYSTEM = (
    "You edit draft medical device incident reports for a UK regulator audience. Write in British "
    "English, plainly and cautiously. Keep every number exactly as given, keep the section structure, "
    "keep the DRAFT notice, and do not add facts that are not in the input."
)


def draft_report(alarm: Alarm, cause: Cause, n_scans: Optional[int] = None) -> tuple[str, str]:
    """Return (markdown, source). Gemini polishes the template when available."""
    template = template_report(alarm, cause, n_scans)
    text = gemini_client.generate_text(
        "Rewrite this draft incident report so it reads clearly. Return Markdown only.\n\n" + template,
        SYSTEM,
    )
    if not text or "DRAFT" not in text:
        return template, "template"
    return text.strip() + "\n", "gemini"

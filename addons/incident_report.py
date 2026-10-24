"""Draft an MHRA-style adverse incident report for a ClinicDrift alarm.

The report is a draft for a human to check and submit; nothing is sent anywhere.
It is tagged with categories from the MIT AI Risk Repository.
"""

from . import gemini_client
from .alarm_schema import Alarm
from .cause_finder import Cause

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


def template_report(alarm: Alarm, cause: Cause) -> str:
    """Fill the report template from the alarm and cause. No network needed."""
    when = f"week {alarm.week}" + (f" (starting {alarm.week_start})" if alarm.week_start else "")
    missed = (
        f"about {alarm.expected_missed_cases:g} referable cases may have been missed"
        if alarm.expected_missed_cases is not None
        else "the number of possibly missed cases is not yet estimated"
    )
    evidence = "\n".join(f"- {e}" for e in cause.evidence) or "- none recorded"
    checks = "\n".join(f"- [ ] {c}" for c in cause.recommended_checks) or "- [ ] none recorded"
    tags = "\n".join(f"- {t} {MIT_RISKS[t]}" for t in mit_tags(cause))
    action = (
        "Expected harm exceeds the cost of review, so we recommend pausing the AI at this clinic "
        "and sending its scans for human grading until the checks below are complete."
        if alarm.expected_harm > alarm.review_cost
        else "Expected harm does not exceed the cost of review; we recommend continued close monitoring."
    )
    return f"""# DRAFT: Medical device adverse incident report

> This is a draft for human review. It has not been submitted. A manufacturer would report
> through the MHRA MORE portal; healthcare professionals and users report through the Yellow Card scheme.

## 1. Device
- Name: {alarm.device_name}
- Version: {alarm.device_version}
- Intended use: screening retinal photographs for referable diabetic retinopathy

## 2. Where and when
- Clinic: {alarm.clinic_id} ({alarm.site}, {alarm.country})
- Period: {when}

## 3. What happened
ClinicDrift estimates the AI's catch rate (sensitivity for referable disease) at this clinic fell to
{_pct(alarm.estimated_catch_rate)} (band {_pct(alarm.ci_low)} to {_pct(alarm.ci_high)}), against a
baseline of {_pct(alarm.baseline_catch_rate)}. The estimate is based on {alarm.flagged_scan_stats.n_scans}
scans from this week, predicted from the images alone; expert grades for these scans have not yet arrived.

## 4. Potential patient impact
If the estimate is right, {missed}. No patient harm has been confirmed.

## 5. Likely cause
{cause.likely_cause} (category: {cause.category}; confidence {cause.confidence:.0%}; source: {cause.source})

Evidence:
{evidence}

## 6. Action
Expected harm: {alarm.expected_harm:g}. Cost of review: {alarm.review_cost:g}.
{action}

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


def draft_report(alarm: Alarm, cause: Cause) -> tuple[str, str]:
    """Return (markdown, source). Gemini polishes the template when available."""
    template = template_report(alarm, cause)
    text = gemini_client.generate_text(
        "Rewrite this draft incident report so it reads clearly. Return Markdown only.\n\n" + template,
        SYSTEM,
    )
    if not text or "DRAFT" not in text:
        return template, "template"
    return text.strip() + "\n", "gemini"

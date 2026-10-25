"""Copy the saved Gemini cause and incident report for each alarm into the web app.

Run `python -m addons.run_demo --clinic <id> --replay` for each alarm first, so addons/out/ holds
answers for the current alarms (--replay never calls Gemini). Only the alarms in the web bundle whose
cause came from Gemini are exported, one file per clinic: web/public/data/gemini/<clinic_id>.json.
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "addons" / "out"
CACHE_DIRS = [ROOT / "addons" / "cache", ROOT / "sample-data" / "gemini"]
BUNDLE = ROOT / "web" / "public" / "data" / "clinicdrift.json"
DEST = ROOT / "web" / "public" / "data" / "gemini"


def model_for(clinic: str, week: int) -> str | None:
    """The model named in the newest saved cause answer for this alarm."""
    files = [f for d in CACHE_DIRS if d.exists() for f in d.glob(f"{clinic}_week{week}_cause_*.json")]
    if not files:
        return None
    newest = max(files, key=lambda f: f.stat().st_mtime)
    return re.match(rf"{clinic}_week{week}_cause_(.+)_[0-9a-f]+\.json", newest.name).group(1)


def main() -> None:
    DEST.mkdir(parents=True, exist_ok=True)
    alarms = json.loads(BUNDLE.read_text(encoding="utf-8"))["alarms"]
    for alarm in alarms:
        clinic, week = alarm["clinic_id"], alarm["week"]
        cause_file = OUT / f"{clinic}_week{week}_cause.json"
        report_file = OUT / f"{clinic}_week{week}_incident_report.md"
        if not cause_file.exists() or not report_file.exists():
            continue
        cause = json.loads(cause_file.read_text(encoding="utf-8"))
        model = model_for(clinic, week)
        if cause.get("source") != "gemini" or model is None:
            continue
        record = {
            "clinic_id": clinic,
            "week": week,
            "model": model,
            "likely_cause": cause["likely_cause"],
            "category": cause["category"],
            "confidence": cause["confidence"],
            "evidence": cause["evidence"],
            "recommended_checks": cause["recommended_checks"],
            "report_md": report_file.read_text(encoding="utf-8"),
        }
        target = DEST / f"{clinic}.json"
        target.write_text(json.dumps(record, indent=2), encoding="utf-8")
        print(f"wrote {target.relative_to(ROOT)} ({model})")


if __name__ == "__main__":
    main()

"""Run all three add-ons on one alarm, or on every alarm in a folder.

    python -m addons.run_demo                       # the fake alarm in addons/fixtures/
    python -m addons.run_demo path/to/alarm.json
    python -m addons.run_demo --all                 # every file in processed/alarms/
    python -m addons.run_demo alarm.json --scans scans.parquet

Alarm files follow docs/handoffs.md. Outputs go to addons/out/.
"""

import argparse
import json
from pathlib import Path

from . import config
from .alarm_schema import ALARMS_DIR, load_alarm
from .cause_finder import find_cause
from .incident_report import draft_report, mit_tags
from .scan_data import gather_evidence
from .voice_alert import alert_script, speak

FIXTURES = config.ROOT / "fixtures"
DEFAULT_ALARM = FIXTURES / "fake_alarm.json"
FAKE_SCANS = FIXTURES / "fake_scans.json"


def run(alarm_path=DEFAULT_ALARM, scans_path=None, weekly_path=None) -> dict:
    alarm_path = Path(alarm_path)
    if scans_path is None and alarm_path == DEFAULT_ALARM:
        scans_path = FAKE_SCANS  # the fake alarm's scan ids only exist in the fake scans
    alarm = load_alarm(alarm_path)
    ev = gather_evidence(alarm, scans_path, weekly_path)
    out = config.out_dir()

    cause = find_cause(alarm, ev)
    cause_path = out / f"{alarm.stem}_cause.json"
    cause_path.write_text(cause.model_dump_json(indent=2), encoding="utf-8")

    report, report_source = draft_report(alarm, cause, ev.n_scans)
    report_path = out / f"{alarm.stem}_incident_report.md"
    report_path.write_text(report, encoding="utf-8")

    script = alert_script(alarm, cause)
    audio_path = speak(script, f"{alarm.stem}_alert.mp3")

    return {
        "clinic_id": alarm.clinic_id,
        "week": alarm.week,
        "alarm_reason": alarm.alarm_reason,
        "cause_category": cause.category,
        "cause_confidence": cause.confidence,
        "cause_source": cause.source,
        "cause_file": str(cause_path),
        "report_source": report_source,
        "report_file": str(report_path),
        "mit_tags": mit_tags(cause),
        "images_sent": len(ev.images),
        "notes": ev.notes,
        "alert_script": script,
        "alert_audio": audio_path,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the ClinicDrift add-ons on alarm files.")
    parser.add_argument("alarm", nargs="?", default=str(DEFAULT_ALARM), help="alarm JSON file")
    parser.add_argument("--all", action="store_true", help=f"run every alarm in {ALARMS_DIR}")
    parser.add_argument("--scans", help="scans.parquet (default: processed/scans.parquet)")
    parser.add_argument("--weekly", help="weekly.parquet (default: processed/weekly.parquet)")
    args = parser.parse_args()

    paths = sorted(ALARMS_DIR.glob("*.json")) if args.all else [Path(args.alarm)]
    if not paths:
        print(f"No alarm files in {ALARMS_DIR}")
    results = [run(p, args.scans, args.weekly) for p in paths]
    print(json.dumps(results[0] if len(results) == 1 else results, indent=2))

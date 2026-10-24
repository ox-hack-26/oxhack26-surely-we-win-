"""Run all three add-ons on one alarm, or on every alarm in a folder.

    python -m addons.run_demo                       # the fake alarm in addons/fixtures/
    python -m addons.run_demo path/to/alarm.json
    python -m addons.run_demo --all                 # every file in processed/alarms/ (else sample-data/alarms/)
    python -m addons.run_demo --clinic US-WEAR-01   # just that clinic's alarm
    python -m addons.run_demo alarm.json --scans scans.parquet
    python -m addons.run_demo --clinic US-WEAR-01 --light   # also flash the Arduino light (hardware/clinic_light/)

Gemini answers are saved and reused (see gemini_client.py): --replay only uses saved
answers and never calls Gemini, --live always calls it.

Alarm files follow docs/handoffs.md. Outputs go to addons/out/.
"""

import argparse
import json
from pathlib import Path

from . import config, gemini_client
from .alarm_schema import ALARMS_DIR, load_alarm
from .cause_finder import find_cause
from .incident_report import draft_report, mit_tags
from .scan_data import gather_evidence
from .voice_alert import alert_script, speak

FIXTURES = config.ROOT / "fixtures"
DEFAULT_ALARM = FIXTURES / "fake_alarm.json"
FAKE_SCANS = FIXTURES / "fake_scans.json"
SAMPLE_ALARMS_DIR = config.ROOT.parent / "sample-data" / "alarms"


def run(alarm_path=DEFAULT_ALARM, scans_path=None, weekly_path=None) -> dict:
    alarm_path = Path(alarm_path)
    if scans_path is None and alarm_path == DEFAULT_ALARM:
        scans_path = FAKE_SCANS  # the fake alarm's scan ids only exist in the fake scans
    alarm = load_alarm(alarm_path)
    gemini_client.reset()
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
        "gemini_error": gemini_client.last_error,
        "gemini_calls": dict(gemini_client.calls),
        "notes": ev.notes,
        "alert_script": script,
        "alert_audio": audio_path,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the ClinicDrift add-ons on alarm files.")
    parser.add_argument("alarm", nargs="?", default=str(DEFAULT_ALARM), help="alarm JSON file")
    parser.add_argument("--all", action="store_true", help=f"run every alarm in {ALARMS_DIR}")
    parser.add_argument("--clinic", help="only this clinic's alarms, e.g. US-WEAR-01")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--replay", action="store_true", help="only use saved Gemini answers; never call Gemini")
    mode.add_argument("--live", action="store_true", help="always call Gemini, ignoring saved answers")
    parser.add_argument("--scans", help="scans.parquet (default: processed/scans.parquet, else processed/standin/scans.parquet)")
    parser.add_argument("--weekly", help="weekly.parquet (default: processed/weekly.parquet)")
    parser.add_argument("--light", action="store_true", help="send ALARM to the Arduino clinic light for each alarm shown")
    parser.add_argument("--port", help="the light's serial port, e.g. COM3 (default: auto-detect)")
    args = parser.parse_args()

    gemini_client.MODE = "replay" if args.replay else "live" if args.live else "auto"
    if args.all or args.clinic:
        folder = ALARMS_DIR if any(ALARMS_DIR.glob("*.json")) else SAMPLE_ALARMS_DIR
        paths = sorted(folder.glob(f"{args.clinic}_week*.json" if args.clinic else "*.json"))
        if not paths:
            print(f"No alarm files{' for ' + args.clinic if args.clinic else ''} in {folder}")
    else:
        paths = [Path(args.alarm)]
    results = [run(p, args.scans, args.weekly) for p in paths]
    if args.light:
        from .status_light import send_state

        for r in results:
            send_state("ALARM", r["clinic_id"], args.port)
    print(json.dumps(results[0] if len(results) == 1 else results, indent=2))

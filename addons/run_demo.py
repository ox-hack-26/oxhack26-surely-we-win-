"""Run all three add-ons on one alarm.

    python -m addons.run_demo [alarm.json]

Without an argument it uses the fake alarm in addons/fixtures/. Outputs go to addons/out/.
"""

import json
import sys
from pathlib import Path

from . import config
from .alarm_schema import load_alarm
from .cause_finder import find_cause
from .incident_report import draft_report, mit_tags
from .voice_alert import alert_script, speak

DEFAULT_ALARM = config.ROOT / "fixtures" / "fake_alarm.json"


def run(alarm_path=DEFAULT_ALARM) -> dict:
    alarm = load_alarm(alarm_path)
    out = config.out_dir()
    stem = f"{alarm.clinic_id}_week{alarm.week}"

    cause = find_cause(alarm)
    cause_path = out / f"{stem}_cause.json"
    cause_path.write_text(cause.model_dump_json(indent=2), encoding="utf-8")

    report, report_source = draft_report(alarm, cause)
    report_path = out / f"{stem}_incident_report.md"
    report_path.write_text(report, encoding="utf-8")

    script = alert_script(alarm, cause)
    audio_path = speak(script, f"{stem}_alert.mp3")

    return {
        "clinic_id": alarm.clinic_id,
        "week": alarm.week,
        "cause_category": cause.category,
        "cause_confidence": cause.confidence,
        "cause_source": cause.source,
        "cause_file": str(cause_path),
        "report_source": report_source,
        "report_file": str(report_path),
        "mit_tags": mit_tags(cause),
        "alert_script": script,
        "alert_audio": audio_path,
    }


if __name__ == "__main__":
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_ALARM
    print(json.dumps(run(path), indent=2))

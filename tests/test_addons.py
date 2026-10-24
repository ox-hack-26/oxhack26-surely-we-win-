"""Offline tests for the add-ons: no API keys, no network."""

import json

import pytest

from addons import config
from addons.alarm_schema import load_alarm
from addons.cause_finder import compute_shifts, find_cause, rule_cause
from addons.incident_report import template_report
from addons.run_demo import DEFAULT_ALARM, run
from addons.voice_alert import alert_script, speak


@pytest.fixture(autouse=True)
def offline(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "GEMINI_API_KEY", "")
    monkeypatch.setattr(config, "ELEVENLABS_API_KEY", "")
    monkeypatch.setattr(config, "OUT_DIR", tmp_path)


@pytest.fixture
def alarm():
    return load_alarm(DEFAULT_ALARM)


def test_fixture_loads(alarm):
    assert alarm.clinic_id == "FR-MES-03"
    assert alarm.flagged_scan_stats.n_scans == 64
    assert alarm.training_scan_stats.n_scans == 35000


def test_sharpness_shift(alarm):
    s = compute_shifts(alarm)["mean_sharpness"]
    assert s["flagged"] == 0.44
    assert s["training"] == 0.71
    assert s["relative_change"] == round((0.44 - 0.71) / 0.71, 3)


def test_fixture_points_to_camera(alarm):
    assert rule_cause(alarm).category == "camera or image quality"


def test_population_shift_when_images_match_training(alarm):
    flagged = alarm.training_scan_stats.model_copy(update={"n_scans": 64, "referral_rate": 0.14})
    a = alarm.model_copy(update={"flagged_scan_stats": flagged})
    assert rule_cause(a).category == "patient population shift"


def test_too_few_scans_is_unknown(alarm):
    flagged = alarm.flagged_scan_stats.model_copy(update={"n_scans": 5})
    a = alarm.model_copy(update={"flagged_scan_stats": flagged})
    cause = rule_cause(a)
    assert cause.category == "unknown"
    assert cause.confidence == 0.2


def test_find_cause_uses_rules_offline(alarm):
    assert find_cause(alarm).source == "rules"


def test_template_report(alarm):
    md = template_report(alarm, rule_cause(alarm))
    assert "DRAFT" in md
    assert "7.3" in md
    assert "71%" in md


def test_voice_script_and_no_key(alarm):
    script = alert_script(alarm, rule_cause(alarm))
    assert "FR-MES-03" in script
    assert speak(script, "alert.mp3") is None


def test_run_end_to_end(tmp_path):
    summary = run()
    assert summary["cause_source"] == "rules"
    assert summary["report_source"] == "template"
    assert summary["alert_audio"] is None
    cause = json.loads((tmp_path / "FR-MES-03_week7_cause.json").read_text(encoding="utf-8"))
    assert cause["category"] == "camera or image quality"
    assert (tmp_path / "FR-MES-03_week7_incident_report.md").is_file()

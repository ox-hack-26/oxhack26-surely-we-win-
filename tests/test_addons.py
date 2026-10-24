"""Offline tests for the add-ons: no API keys, no network."""

import json
from datetime import date

import pytest

from addons import config
from addons.alarm_schema import alarm_path, load_alarm
from addons.cause_finder import compute_shifts, find_cause, rule_cause
from addons.incident_report import template_report
from addons.run_demo import DEFAULT_ALARM, FAKE_SCANS, run
from addons.scan_data import Evidence, gather_evidence, load_scan_rows
from addons.voice_alert import alert_script, speak


@pytest.fixture(autouse=True)
def offline(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "GEMINI_API_KEY", "")
    monkeypatch.setattr(config, "ELEVENLABS_API_KEY", "")
    monkeypatch.setattr(config, "OUT_DIR", tmp_path)


@pytest.fixture
def alarm():
    return load_alarm(DEFAULT_ALARM)


@pytest.fixture
def ev(alarm):
    return gather_evidence(alarm, scans_path=FAKE_SCANS, with_images=False)


def test_fixture_matches_handoffs_format(alarm):
    assert alarm.clinic_id == "messidor2-a"
    assert alarm.week == date(2026, 3, 2)
    assert alarm.est_sensitivity == 0.71
    assert alarm.site == "Messidor-2"
    assert alarm.country == "France"
    assert alarm.stem == "messidor2-a_2026-03-02"
    assert alarm_path("messidor2-a", "2026-03-02").name == "messidor2-a_2026-03-02.json"


def test_scan_stats_from_rows(ev):
    assert ev.flagged.n_scans == 2
    assert ev.reference.n_scans == 2
    assert ev.flagged.mean_sharpness == 44.0
    assert ev.reference.referral_rate == 0.5


def test_sharpness_shift(ev):
    s = compute_shifts(ev.flagged, ev.reference)["mean_sharpness"]
    assert s["flagged"] == 44.0
    assert s["training"] == 115.0
    assert s["relative_change"] == round((44 - 115) / 115, 3)


def test_fixture_points_to_camera(alarm, ev):
    assert rule_cause(alarm, ev).category == "camera or image quality"


def test_population_shift_when_images_match_training(alarm, ev):
    flagged = ev.reference.model_copy(update={"referral_rate": 0.1, "referral_score_mean": 0.2})
    cause = rule_cause(alarm, Evidence(flagged=flagged, reference=ev.reference))
    assert cause.category == "patient population shift"


def test_too_few_scans_is_unknown(alarm, ev):
    ev.n_scans = 5
    cause = rule_cause(alarm, ev)
    assert cause.category == "unknown"
    assert cause.confidence == 0.2


def test_no_scan_data_is_unknown_with_note(alarm, tmp_path):
    ev = gather_evidence(alarm, scans_path=tmp_path / "missing.parquet", with_images=False)
    assert ev.flagged is None and ev.notes
    cause = rule_cause(alarm, ev)
    assert cause.category == "unknown"
    assert any("drift" in e for e in cause.evidence)
    assert any("unavailable" in e for e in cause.evidence)


def test_load_scan_rows_ignores_unknown_ids():
    assert load_scan_rows(["nope-1"], FAKE_SCANS) == []


def test_find_cause_uses_rules_offline(alarm, ev):
    assert find_cause(alarm, ev).source == "rules"


def test_template_report(alarm, ev):
    md = template_report(alarm, rule_cause(alarm, ev))
    assert "DRAFT" in md
    assert "7.3" in md
    assert "71%" in md and "88%" in md
    assert "2026-03-02" in md
    assert "4.2" in md


def test_voice_script_and_no_key(alarm, ev):
    script = alert_script(alarm, rule_cause(alarm, ev))
    assert "messidor2-a" in script
    assert "88% to 71%" in script
    assert speak(script, "alert.mp3") is None


def test_run_end_to_end(tmp_path):
    summary = run()
    assert summary["cause_source"] == "rules"
    assert summary["report_source"] == "template"
    assert summary["alert_audio"] is None
    cause = json.loads((tmp_path / "messidor2-a_2026-03-02_cause.json").read_text(encoding="utf-8"))
    assert cause["category"] == "camera or image quality"
    assert (tmp_path / "messidor2-a_2026-03-02_incident_report.md").is_file()

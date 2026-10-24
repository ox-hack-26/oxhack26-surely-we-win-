"""Offline tests for the add-ons: no API keys, no network."""

import json

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
def stripped(alarm):
    """The fixture alarm without its stats, as if the engine only sent scan ids."""
    return alarm.model_copy(update={"flagged_scan_stats": None, "training_scan_stats": None})


def test_fixture_matches_handoffs_format(alarm):
    assert alarm.clinic_id == "FR-MES-03"
    assert alarm.week == 7
    assert alarm.flagged_scan_stats.n_scans == 64
    assert alarm.training_scan_stats.mean_contrast == 0.27
    assert alarm.flagged_scan_ids == ["messidor2-00042", "messidor2-00057"]
    assert alarm.reference_scan_ids == ["eyepacs-01234", "eyepacs-05678"]
    assert alarm.stem == "FR-MES-03_week7"
    assert alarm_path("FR-MES-03", 7).name == "FR-MES-03_week7.json"


def test_sharpness_shift(alarm):
    s = compute_shifts(alarm.flagged_scan_stats, alarm.training_scan_stats)["mean_sharpness"]
    assert s["flagged"] == 0.44
    assert s["training"] == 0.71
    assert s["relative_change"] == round((0.44 - 0.71) / 0.71, 3)


def test_alarm_stats_take_priority(alarm):
    ev = gather_evidence(alarm, scans_path=FAKE_SCANS, with_images=False)
    assert ev.flagged is alarm.flagged_scan_stats
    assert ev.n_scans == 64
    assert ev.notes == []


def test_missing_stats_filled_from_scans(stripped):
    ev = gather_evidence(stripped, scans_path=FAKE_SCANS, with_images=False)
    assert ev.flagged.n_scans == 2 and ev.reference.n_scans == 2
    assert ev.flagged.mean_contrast == pytest.approx(0.21)
    assert ev.reference.referral_rate == 0.5
    assert ev.n_scans is None  # flagged ids are a sample, not the whole week
    assert rule_cause(stripped, ev).category == "camera or image quality"


def test_no_stats_anywhere_is_unknown_with_note(stripped, tmp_path):
    ev = gather_evidence(stripped, scans_path=tmp_path / "missing.parquet", with_images=False)
    cause = rule_cause(stripped, ev)
    assert cause.category == "unknown"
    assert any("unavailable" in e for e in cause.evidence)


def test_load_scan_rows_ignores_unknown_ids():
    assert load_scan_rows(["nope-1"], FAKE_SCANS) == []


def test_fixture_points_to_camera(alarm):
    assert rule_cause(alarm).category == "camera or image quality"


def test_population_shift_when_images_match_training(alarm):
    training = alarm.training_scan_stats
    flagged = training.model_copy(update={"n_scans": 64, "referral_rate": 0.14})
    cause = rule_cause(alarm, Evidence(flagged=flagged, reference=training, n_scans=64))
    assert cause.category == "patient population shift"


def test_too_few_scans_is_unknown(alarm):
    flagged = alarm.flagged_scan_stats.model_copy(update={"n_scans": 5})
    a = alarm.model_copy(update={"flagged_scan_stats": flagged})
    cause = rule_cause(a, gather_evidence(a, with_images=False))
    assert cause.category == "unknown"
    assert cause.confidence == 0.2


def test_find_cause_uses_rules_offline(alarm):
    assert find_cause(alarm).source == "rules"


def test_template_report(alarm):
    md = template_report(alarm, rule_cause(alarm), 64)
    assert "DRAFT" in md
    assert "7.3" in md
    assert "71%" in md and "89%" in md
    assert "week 7 (starting 2026-03-02)" in md


def test_voice_script_and_no_key(alarm):
    script = alert_script(alarm, rule_cause(alarm))
    assert "FR-MES-03" in script
    assert "89% to 71%" in script
    assert speak(script, "alert.mp3") is None


def test_run_end_to_end(tmp_path):
    summary = run()
    assert summary["cause_source"] == "rules"
    assert summary["report_source"] == "template"
    assert summary["alert_audio"] is None
    cause = json.loads((tmp_path / "FR-MES-03_week7_cause.json").read_text(encoding="utf-8"))
    assert cause["category"] == "camera or image quality"
    assert (tmp_path / "FR-MES-03_week7_incident_report.md").is_file()

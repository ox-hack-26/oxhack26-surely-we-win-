"""Offline tests for the add-ons: no API keys, no network."""

import json
from pathlib import Path

import pytest

from addons import config
from addons.alarm_schema import alarm_path, load_alarm
from addons.cause_finder import compute_shifts, find_cause, rule_cause
from addons.incident_report import template_report
from addons.run_demo import DEFAULT_ALARM, FAKE_SCANS, run
from addons.scan_data import Evidence, gather_evidence, load_images, load_scan_rows
from addons.voice_alert import alert_script, speak


@pytest.fixture(autouse=True)
def offline(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "GEMINI_API_KEY", "")
    monkeypatch.setattr(config, "ELEVENLABS_API_KEY", "")
    monkeypatch.setattr(config, "OUT_DIR", tmp_path)


@pytest.fixture
def alarm():
    return load_alarm(DEFAULT_ALARM)


SAMPLE_ALARMS = sorted((Path(__file__).parents[1] / "sample-data" / "alarms").glob("*.json"))


@pytest.fixture
def drift_alarm():
    return load_alarm(Path(__file__).parents[1] / "sample-data" / "alarms" / "SW-MES-01_week09.json")


@pytest.fixture
def stripped(alarm):
    """The fixture alarm without its stats, as if the engine only sent scan ids."""
    return alarm.model_copy(update={"flagged_scan_stats": None, "training_scan_stats": None})


def test_fixture_matches_handoffs_format(alarm):
    assert alarm.clinic_id == "FR-MES-03"
    assert alarm.week == 7
    assert alarm.referral_threshold == 0.27
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


def test_small_values_keep_significant_figures(drift_alarm):
    s = compute_shifts(drift_alarm.flagged_scan_stats, drift_alarm.training_scan_stats)
    assert s["mean_sharpness"]["flagged"] == 0.000222
    assert s["mean_sharpness"]["training"] == 0.000399
    assert s["mean_resolution_px"]["training"] == 1020
    assert "mean sharpness: 0.000399 -> 0.000222 (-44%)" in rule_cause(drift_alarm).evidence


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


def test_rebuilt_referral_rate_uses_alarm_threshold(stripped):
    a = stripped.model_copy(update={"referral_threshold": 0.2})
    ev = gather_evidence(a, scans_path=FAKE_SCANS, with_images=False)
    assert ev.flagged.referral_rate == 0.5  # 0.21 >= 0.2, 0.17 < 0.2
    assert ev.reference.referral_rate == 1.0
    assert ev.threshold_note == "referral rate counts p_referable >= 0.2 (the alarm's referral_threshold)"
    assert ev.threshold_note in rule_cause(a, ev).evidence


def test_rebuilt_referral_rate_falls_back_to_half(stripped):
    a = stripped.model_copy(update={"referral_threshold": None})
    ev = gather_evidence(a, scans_path=FAKE_SCANS, with_images=False)
    assert ev.flagged.referral_rate == 0.0
    assert ev.reference.referral_rate == 0.5  # 0.61 >= 0.5, 0.24 < 0.5
    assert "0.5 (fallback" in ev.threshold_note


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


def test_referral_change_leads_the_cause(drift_alarm):
    cause = rule_cause(drift_alarm)
    assert cause.likely_cause.startswith("The AI is referring more patients than usual (referral rate 0.685 -> 0.86, +26%).")
    assert cause.category == "camera or image quality"  # quality fell 61%, so the images still explain it
    assert cause.confidence == 0.7


def test_worn_camera_stays_camera():
    wear = load_alarm(Path(__file__).parents[1] / "sample-data" / "alarms" / "US-WEAR-01_week09.json")
    cause = rule_cause(wear)
    assert cause.category == "camera or image quality"
    assert not cause.likely_cause.startswith("The AI is referring")


def test_resolution_alone_is_not_a_camera_signal(alarm):
    training = alarm.training_scan_stats
    flagged = training.model_copy(update={"n_scans": 64, "mean_resolution_px": 1440})
    cause = rule_cause(alarm, Evidence(flagged=flagged, reference=training, n_scans=64))
    assert cause.category == "model degradation"
    assert any("context only" in e for e in cause.evidence)


def test_rule_confidence_is_capped(alarm):
    assert all(rule_cause(load_alarm(p)).confidence <= 0.7 for p in SAMPLE_ALARMS)
    assert rule_cause(alarm).confidence <= 0.7


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


def test_drift_voice_script_quotes_no_catch_rate(drift_alarm):
    assert drift_alarm.is_drift
    script = alert_script(drift_alarm, rule_cause(drift_alarm))
    assert "can't be verified" in script
    assert "%" not in script


def test_drift_report_quotes_no_catch_rate(drift_alarm):
    md = template_report(drift_alarm, rule_cause(drift_alarm), 50)
    assert "can't be verified" in md
    assert "50%" not in md and "5% to 95%" not in md  # placeholder estimate and band
    assert "catch rate (sensitivity for referable disease) at this clinic fell" not in md
    assert "referable cases may have been missed" not in md
    assert "referring more patients than usual: 86%" in md
    assert "Expected harm" not in md and "337" not in md and "25000" not in md
    assert "drifted beyond what the AI was validated on" in md


def test_non_drift_wording_unchanged(alarm):
    assert not alarm.is_drift
    assert "can't be verified" not in alert_script(alarm, rule_cause(alarm))
    md = template_report(alarm, rule_cause(alarm), 64)
    assert "fell to\n71% (band 62% to 79%)" in md
    assert "Expected harm: 4200. Cost of review: 1500.\nExpected harm exceeds the cost of review" in md


@pytest.mark.parametrize("path", SAMPLE_ALARMS, ids=lambda p: p.stem)
def test_sample_alarms_run_offline(path):
    summary = run(path)
    assert summary["alarm_reason"] == "drift"
    assert "can't be verified" in summary["alert_script"]
    assert "%" not in summary["alert_script"]


@pytest.mark.parametrize("path", SAMPLE_ALARMS, ids=lambda p: p.stem)
def test_sample_alarm_images_load_without_raw_scans(path):
    alarm = load_alarm(path)
    assert len(load_images(alarm.flagged_scan_ids, "flagged")) == 2
    assert len(load_images(alarm.reference_scan_ids, "reference")) == 2


def test_scans_fall_back_to_standin(tmp_path, monkeypatch):
    from addons import scan_data

    monkeypatch.setattr(scan_data, "SCANS_PATH", tmp_path / "scans.parquet")
    monkeypatch.setattr(scan_data, "STANDIN_SCANS_PATH", tmp_path / "standin" / "scans.parquet")
    assert scan_data.default_scans_path() == tmp_path / "standin" / "scans.parquet"
    (tmp_path / "scans.parquet").write_bytes(b"")
    assert scan_data.default_scans_path() == tmp_path / "scans.parquet"

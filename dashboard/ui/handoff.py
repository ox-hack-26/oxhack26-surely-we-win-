"""Read the actual Tejas handoff, without future-data leakage."""
import json
from pathlib import Path
import pandas as pd

REQUIRED = {"clinic_id", "week", "week_start", "n_scans", "catch_rate", "catch_low", "catch_high", "est_sensitivity", "true_sensitivity", "drift_auc", "alarm", "alarm_reason", "belief_cases", "referral_rate", "expected_harm"}

def data_root():
    import os
    return Path(os.getenv("CLINICDRIFT_SAMPLE_DATA", str(Path(__file__).resolve().parents[2] / "sample-data")))

def load_handoff(root=None):
    root = Path(root) if root else data_root()
    weekly = pd.read_csv(root / "weekly.csv")
    missing = REQUIRED - set(weekly.columns)
    if missing:
        raise ValueError(f"Missing handoff columns: {sorted(missing)}")
    if weekly.duplicated(["clinic_id", "week"]).any():
        raise ValueError("Duplicate clinic/week")
    for c in ["catch_rate", "catch_low", "catch_high", "est_sensitivity", "true_sensitivity", "drift_auc"]:
        weekly[c] = pd.to_numeric(weekly[c], errors="coerce")
    if ((weekly.catch_low > weekly.catch_rate) | (weekly.catch_high < weekly.catch_rate)).any():
        raise ValueError("Invalid catch-rate interval")
    weekly["week"] = weekly["week"].astype(int)
    weekly["week_start"] = pd.to_datetime(weekly["week_start"])
    for c in ("alarm", "alarm_this_week"):
        if c in weekly:
            weekly[c] = weekly[c].astype(str).str.lower().eq("true")
    clinics = json.loads((root / "clinics.json").read_text())
    settings = json.loads((root / "decision_settings.json").read_text())
    return weekly.sort_values(["clinic_id", "week"]), clinics, settings

def replay_view(weekly, clinic_id, week):
    """Do not show hindsight or expert-graded results before their availability.

    true_* is always hindsight and never available in the live replay.
    The graded_cases/graded_caught columns are the already-arrived expert labels.
    """
    visible = weekly[(weekly.clinic_id == clinic_id) & (weekly.week <= week)].copy()
    return visible.drop(columns=[c for c in visible.columns if c.startswith("true_")], errors="ignore")

def alarm_for_week(clinic_id, week, root=None):
    root = Path(root) if root else data_root()
    path = root / "alarms" / f"{clinic_id}_week{week:02d}.json"
    return json.loads(path.read_text()) if path.exists() else None

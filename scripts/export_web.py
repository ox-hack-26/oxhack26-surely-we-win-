"""Bundle the engine's outputs into one JSON file (and the scans it shows) for the web app in web/.

The app is a static site: it reads web/public/data/clinicdrift.json and nothing else, so it runs
anywhere without Python. Re-run after the engine changes (the pipeline does it for you):

    python scripts/export_web.py
"""
import json
import math
import shutil
import sys
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from clinicdrift.config import PROCESSED_DIR, REPO  # noqa: E402
from clinicdrift.engine.backtest import change_week, load_replay, policy_flags  # noqa: E402
from clinicdrift.engine.decide import CONFIDENCE, MIN_CATCH_RATE, reference_levels  # noqa: E402
from clinicdrift.engine.estimate import load_inputs  # noqa: E402
from clinicdrift.engine.replay import FIRST_MONDAY, N_WEEKS  # noqa: E402

WEB = REPO / "web" / "public"
SAMPLE_IMAGES = REPO / "sample-data" / "images"
WEEK_FIELDS = [
    "week", "week_start", "n_scans", "est_sensitivity", "est_low", "est_high", "catch_rate", "catch_low", "catch_high",
    "true_sensitivity", "true_cases", "true_missed", "true_false_referrals", "drift_auc", "quality_mean",
    "referral_rate", "referral_threshold", "expected_cases", "belief_cases", "belief_missed", "expected_harm",
    "p_below_standard", "trust", "graded_cases", "graded_caught", "alarm", "alarm_this_week", "alarm_reason",
]


def clean(value):
    """JSON-safe: NaN and NaT become null, NumPy scalars become plain Python, dates become ISO strings."""
    if value is None:
        return None
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float):
        return None if math.isnan(value) else round(value, 5)
    if isinstance(value, (pd.Timestamp, date)):
        return None if pd.isna(value) else value.isoformat()[:10]
    return value


def web_name(scan_id: str) -> str:
    """File name for a scan on the web: worn copies ('eyepacs-01234@0.40') lose the '@', which dev servers don't decode."""
    return scan_id.replace("@", "_w") + ".jpg"


def week_of(ts: pd.Timestamp) -> int:
    return int((ts - FIRST_MONDAY).days // 7) + 1


def main() -> None:
    scans, _, model, _ = load_inputs()
    weekly = pd.read_parquet(PROCESSED_DIR / "weekly.parquet")
    stream = pd.read_parquet(PROCESSED_DIR / "stream.parquet")
    settings = json.loads((PROCESSED_DIR / "decision_settings.json").read_text(encoding="utf-8"))
    clinics = json.loads((PROCESSED_DIR / "clinics.json").read_text(encoding="utf-8"))

    # The week by which every expert grade for a clinic-week has arrived: before then, "real" is unknown.
    arrived = (stream.dropna(subset=["graded_at"]).groupby(["clinic_id", "week"])["graded_at"].max()
               .map(week_of).rename("grades_complete_week"))
    weekly = weekly.join(arrived, on=["clinic_id", "week"])

    # The other policies' alarms don't depend on the costs, so the app only recomputes ClinicDrift's.
    seen, clinic_by_id = load_replay(scans, model)
    graded = seen[seen["graded_at"].notna()]
    ref = reference_levels(scans, model)

    by_clinic, policies = {}, {}
    for clinic_id, rows in weekly.sort_values("week").groupby("clinic_id"):
        by_clinic[clinic_id] = [{**{k: clean(r[k]) for k in WEEK_FIELDS}, "grades_complete_week": clean(r["grades_complete_week"])}
                                for _, r in rows.iterrows()]
        flags = policy_flags(rows, graded[graded["clinic_id"] == clinic_id], ref)
        policies[clinic_id] = {"changed_week": change_week(clinic_by_id[clinic_id]),
                               "alarm_weeks": {name: [int(w) for w in f[f].index] for name, f in flags.items() if name != "ClinicDrift"}}

    alarms = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((PROCESSED_DIR / "alarms").glob("*.json"))]
    optional = {name: json.loads((PROCESSED_DIR / f"{name}.json").read_text(encoding="utf-8"))
                for name in ("robustness_summary", "backtest_summary") if (PROCESSED_DIR / f"{name}.json").exists()}
    sweep_path = PROCESSED_DIR / "robustness_sweep.parquet"
    sweep = pd.read_parquet(sweep_path).to_dict(orient="records") if sweep_path.exists() else []

    images = sorted({i for a in alarms for i in a["flagged_scan_ids"] + a["reference_scan_ids"]})
    images += sorted(p.stem for p in SAMPLE_IMAGES.glob("eyepacs-15898*.jpg"))  # the camera-wear strip
    (WEB / "scans").mkdir(parents=True, exist_ok=True)
    for old in (WEB / "scans").glob("*.jpg"):
        old.unlink()
    shipped = []
    for scan_id in dict.fromkeys(images):
        src = SAMPLE_IMAGES / f"{scan_id}.jpg"
        if src.exists():
            shutil.copy(src, WEB / "scans" / web_name(scan_id))
            shipped.append(scan_id)

    bundle = {
        "generated": date.today().isoformat(),
        "model": {k: clean(v) for k, v in model.items()},
        "settings": {**settings, "min_catch_rate": MIN_CATCH_RATE, "confidence": CONFIDENCE,
                     "n_weeks": N_WEEKS, "first_monday": FIRST_MONDAY.date().isoformat()},
        "clinics": [{**c, **policies[c["clinic_id"]], "weeks": by_clinic[c["clinic_id"]]} for c in clinics],
        "alarms": alarms,
        "robustness": optional.get("robustness_summary"),
        "backtest": optional.get("backtest_summary"),
        "sweep": [{k: clean(v) for k, v in row.items()} for row in sweep],
        "scans": shipped,
    }
    (WEB / "data").mkdir(parents=True, exist_ok=True)
    out = WEB / "data" / "clinicdrift.json"
    out.write_text(json.dumps(bundle, separators=(",", ":")), encoding="utf-8")
    print(f"Wrote {out} ({out.stat().st_size / 1e3:.0f} kB): {len(clinics)} clinics, {len(alarms)} alarms, {len(shipped)} scans")


if __name__ == "__main__":
    main()

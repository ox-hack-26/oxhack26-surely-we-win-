"""Decide each week whether to pull a clinic's AI for review, and say why.

Belief about a clinic's catch rate is a Beta distribution built from:
  1. the label-free estimate (estimate.py), pooled over the last few weeks to calm weekly noise;
  2. how far that estimate can be trusted: as drift_auc rises from 0.7 to 0.9 it is blended into
     'anything is possible' (a uniform belief), because no validated scan looks like these;
  3. expert grades that have arrived by then, from the clinic's last 8 weeks of scans.
The decision is cost-loss: pull the AI if the expected extra harm of carrying on until grades
would show the problem (the horizon) costs more than a review. Costs are illustrative; they
are the dashboard's sliders. Two kinds of alarm:
  drift  the scans no longer look validated (trust below 0.5), so the catch rate can't be verified;
  harm   the scans look validated but we are at least CONFIDENCE sure the catch rate is below the
         screening standard (MIN_CATCH_RATE). Without that evidence test, weekly noise of a few
         points was enough to pull a healthy AI, because a 4-point shortfall already outweighs a review.

Writes processed/weekly.parquet and one processed/alarms/<clinic>_week<NN>.json each time an
alarm starts, in the format addons/alarm_schema.py reads.

    python -m clinicdrift.engine.decide
"""
import json
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd
from scipy import stats

from clinicdrift.config import PROCESSED_DIR
from clinicdrift.engine.estimate import Reference, load_inputs, referral_thresholds

DRIFT_TRUSTED = 0.7    # below this drift_auc the label-free estimate is fully trusted
DRIFT_UNTRUSTED = 0.9  # above this it is ignored
POOL_WEEKS = 3         # label-free estimates pooled over this many weeks
GRADE_WINDOW = 8       # grades count if their scan was taken in the last this-many weeks
FLAGGED = 6            # scans attached to an alarm for Gemini to look at
MIN_CATCH_RATE = 0.80  # UK (Exeter / British Diabetic Association) screening standard: sensitivity of at least 80%
CONFIDENCE = 0.90      # a harm alarm needs this much belief that the catch rate is below that standard


@dataclass(frozen=True)
class Costs:
    missed_case: float = 10_000   # £ per referable case the AI misses: delayed treatment, risk to sight
    false_referral: float = 150   # £ per healthy patient sent to an eye clinic
    review: float = 25_000        # £ to pull the AI and grade by hand while it is checked
    horizon_weeks: int = 6        # how long a problem runs before the grades would show it


def trust(drift_auc: float) -> float:
    return float(np.clip((DRIFT_UNTRUSTED - drift_auc) / (DRIFT_UNTRUSTED - DRIFT_TRUSTED), 0, 1))


def beta_from_moments(mean: float, var: float) -> tuple[float, float]:
    mean = float(np.clip(mean, 0.01, 0.99))
    common = max(mean * (1 - mean) / max(var, 1e-6) - 1, 0.5)
    return mean * common, (1 - mean) * common


def reference_levels(scans: pd.DataFrame, model: dict) -> dict:
    """How the AI performs where it was validated (EyePACS val)."""
    val = scans[scans["split"] == "val"]
    return {
        "catch_rate": model["val_sensitivity"],
        "specificity": model["val_specificity"],
        "prevalence": float(val["referable"].mean()),
    }


def decide_clinic(weeks: pd.DataFrame, graded: pd.DataFrame, ref: dict, costs: Costs) -> pd.DataFrame:
    """Belief and decision for one clinic's weeks, in week order."""
    out = []
    for i, row in enumerate(weeks.itertuples(index=False)):
        pool = weeks.iloc[max(0, i - POOL_WEEKS + 1): i + 1]
        w = pool["expected_cases"].clip(lower=0.1)
        lf_mean = float((w * pool["est_sensitivity"]).sum() / w.sum())
        lf_sd = float(np.sqrt((w ** 2 * ((pool["est_high"] - pool["est_low"]) / 3.29) ** 2).sum()) / w.sum())

        # Blend the label-free belief with 'anything is possible' (uniform: mean 0.5, variance 1/12).
        t = trust(row.drift_auc)
        mean = t * lf_mean + (1 - t) * 0.5
        var = t * lf_sd ** 2 + (1 - t) / 12 + t * (1 - t) * (lf_mean - 0.5) ** 2
        a, b = beta_from_moments(mean, var)

        # Add the grades that have arrived by the end of this week.
        week_end = pd.Timestamp(row.week_start) + pd.Timedelta(days=7)
        arrived = graded[(graded["graded_at"] < week_end) & (graded["week"] > row.week - GRADE_WINDOW)]
        cases = arrived["referable"]
        n_graded, n_caught = int(cases.sum()), int((cases & arrived["referred"]).sum())
        a, b = a + n_caught, b + n_graded - n_caught
        catch = a / (a + b)

        # Expected extra harm per week compared with validated performance, then cost-loss.
        n_cases = t * row.expected_cases + (1 - t) * max(row.expected_cases, ref["prevalence"] * row.n_scans)
        referred = row.referral_rate * row.n_scans
        usual_false = row.n_scans * (1 - ref["prevalence"]) * (1 - ref["specificity"])
        weekly_harm = (costs.missed_case * n_cases * (ref["catch_rate"] - catch)
                       + costs.false_referral * (referred - catch * n_cases - usual_false))
        harm = costs.horizon_weeks * weekly_harm
        below_standard = float(stats.beta.cdf(MIN_CATCH_RATE, a, b))
        drifted = t < 0.5
        alarm = harm > costs.review and (drifted or below_standard >= CONFIDENCE)
        out.append({
            "trust": t,
            "graded_cases": n_graded,
            "graded_caught": n_caught,
            "catch_rate": catch,
            "catch_low": float(stats.beta.ppf(0.05, a, b)),
            "catch_high": float(stats.beta.ppf(0.95, a, b)),
            "belief_cases": n_cases,
            "belief_missed": n_cases * (1 - catch),
            "expected_harm": harm,
            "p_below_standard": below_standard,
            "alarm_this_week": bool(alarm),
            "alarm_reason": ("drift" if drifted else "harm") if alarm else None,
        })
    decided = pd.DataFrame(out)
    # An alarm pulls the AI for review, so it stays on until someone has reviewed it. Without
    # this, grades from weeks before things got bad could switch it off just as harm peaks.
    decided["alarm"] = decided["alarm_this_week"].cummax()
    decided["alarm_reason"] = decided["alarm_reason"].where(decided["alarm_this_week"]).ffill().where(decided["alarm"])
    return pd.concat([weeks.reset_index(drop=True), decided], axis=1)


def scan_stats(rows: pd.DataFrame, threshold: float) -> dict:
    return {
        "n_scans": int(len(rows)),
        "mean_brightness": float(rows["brightness"].mean()),
        "mean_contrast": float(rows["contrast"].mean()),
        "mean_sharpness": float(rows["sharpness"].mean()),
        "mean_quality": float(rows["quality"].mean()),
        "mean_resolution_px": float(rows["width"].mean()),
        "referral_score_mean": float(rows["p_referable"].mean()),
        "referral_rate": float((rows["p_referable"] >= threshold).mean()),
    }


def write_alarms(weekly, seen, scans, features, model, ref, costs, clinics) -> list[str]:
    """One JSON per alarm start, for the add-ons."""
    threshold = model["referral_threshold"]
    reference = Reference(scans, features, np.random.default_rng(0))
    row_of = pd.Series(np.arange(len(scans)), index=scans["scan_id"])
    train = scans[scans["split"] == "train"]
    train_dist = (reference.project(features[row_of.loc[train["scan_id"]].to_numpy()]) ** 2).sum(axis=1)
    typical = train["scan_id"].to_numpy()[np.argsort(train_dist)[:FLAGGED]].tolist()

    out_dir = PROCESSED_DIR / "alarms"
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*.json"):
        old.unlink()
    written = []
    starts = weekly["alarm"] & ~weekly.groupby("clinic_id")["alarm"].shift(fill_value=False)
    for row in weekly[starts].itertuples(index=False):
        week_scans = seen[(seen["clinic_id"] == row.clinic_id) & (seen["week"] == row.week)]
        dist = (reference.project(features[row_of.loc[week_scans["scan_id"]].to_numpy()]) ** 2).sum(axis=1)
        clinic = clinics[row.clinic_id]
        alarm = {
            "clinic_id": row.clinic_id,
            "site": clinic["site"],
            "country": clinic["country"],
            "week": int(row.week),
            "week_start": str(row.week_start),
            "estimated_catch_rate": row.catch_rate,
            "ci_low": row.catch_low,
            "ci_high": row.catch_high,
            "baseline_catch_rate": ref["catch_rate"],
            "expected_missed_cases": row.belief_missed,
            "expected_harm": row.expected_harm,
            "review_cost": costs.review,
            "referral_threshold": row.referral_threshold,  # the one this clinic used that week
            "alarm_reason": row.alarm_reason,
            "drift_auc": row.drift_auc,
            "flagged_scan_stats": scan_stats(week_scans, row.referral_threshold),
            "training_scan_stats": scan_stats(train, threshold),
            "flagged_scan_ids": week_scans["scan_id"].to_numpy()[np.argsort(-dist)[:FLAGGED]].tolist(),
            "reference_scan_ids": typical,
        }
        path = out_dir / f"{row.clinic_id}_week{int(row.week):02d}.json"
        path.write_text(json.dumps(alarm, indent=2), encoding="utf-8")
        written.append(path.name)
    return written


def run(costs: Costs = Costs(), write: bool = True) -> pd.DataFrame:
    """Decide every clinic-week; with write=False just return the table (for cost sweeps)."""
    scans, features, model, _ = load_inputs()
    ref = reference_levels(scans, model)
    weekly = pd.read_parquet(PROCESSED_DIR / "weekly_estimates.parquet")
    stream = pd.read_parquet(PROCESSED_DIR / "stream.parquet")
    seen = stream.merge(scans.drop(columns="wear", errors="ignore"), on=["scan_id", "source"], validate="one_to_one")
    seen["referred"] = seen["p_referable"].to_numpy() >= referral_thresholds(seen, scans, model)
    graded = seen[seen["graded_at"].notna()]

    decided = pd.concat(
        [decide_clinic(g.sort_values("week"), graded[graded["clinic_id"] == c], ref, costs)
         for c, g in weekly.groupby("clinic_id")],
        ignore_index=True,
    )
    if not write:
        return decided
    decided.to_parquet(PROCESSED_DIR / "weekly.parquet", index=False)
    clinics = {c["clinic_id"]: c for c in json.loads((PROCESSED_DIR / "clinics.json").read_text(encoding="utf-8"))}
    written = write_alarms(decided, seen, scans, features, model, ref, costs, clinics)
    (PROCESSED_DIR / "decision_settings.json").write_text(
        json.dumps({"costs": asdict(costs), "reference": ref, "drift_trusted": DRIFT_TRUSTED,
                    "drift_untrusted": DRIFT_UNTRUSTED, "min_catch_rate": MIN_CATCH_RATE,
                    "confidence": CONFIDENCE}, indent=2), encoding="utf-8")
    print(f"Wrote weekly.parquet ({len(decided)} clinic-weeks) and {len(written)} alarm files")
    return decided


if __name__ == "__main__":
    run()

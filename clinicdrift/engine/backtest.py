"""Backtest: replay the 20 weeks under four monitoring policies and count the cost.

  wait for grades  today's practice: alarm when the expert-graded catch rate over the last 8 weeks
                   is clearly below validated (needs at least 5 graded referable cases)
  watch estimate   alarm when the label-free catch-rate estimate drops clearly below validated
  watch drift      alarm when drift_auc stays above 0.8 for two weeks
  ClinicDrift      the drift-aware cost-loss rule in decide.py

A policy's first alarm pulls the AI for review, which is assumed to restore validated
performance. Harm counts from when the clinic's conditions changed until that first alarm,
using every expert grade in hindsight. An alarm on a clinic, or before a change, where
nothing had changed is a false alarm and still costs a review.

    python -m clinicdrift.engine.backtest
"""
import json

import numpy as np
import pandas as pd

from clinicdrift.config import PROCESSED_DIR
from clinicdrift.engine import decide
from clinicdrift.engine.decide import GRADE_WINDOW, POOL_WEEKS, Costs, reference_levels
from clinicdrift.engine.estimate import load_inputs, referral_thresholds

SWEEP_REVIEW_COSTS = (5_000, 10_000, 25_000, 50_000, 100_000)

GRADES_MIN_CASES = 5
CLEAR_DROP = 0.15   # 'clearly below validated' for the graded catch rate
ESTIMATE_DROP = 0.10
DRIFT_ALARM = 0.8


def change_week(clinic: dict) -> int | None:
    """Week the clinic's conditions changed; None if they never did."""
    if clinic["switch_week"]:
        return clinic["switch_week"]
    if clinic.get("wear_from_week"):
        return clinic["wear_from_week"]
    if clinic.get("update_from_week"):
        return clinic["update_from_week"]
    first_source = clinic["segments"][0]["source"]
    return 1 if first_source != "eyepacs" else None


def first_alarm(flags: pd.Series) -> int | None:
    hits = flags[flags].index
    return int(hits[0]) if len(hits) else None


def policy_flags(weekly: pd.DataFrame, graded: pd.DataFrame, ref: dict) -> dict[str, pd.Series]:
    """Week-indexed alarm flags for one clinic under each policy."""
    weekly = weekly.set_index("week")
    grades = []
    for week, start in weekly["week_start"].items():
        end = pd.Timestamp(start) + pd.Timedelta(days=7)
        arrived = graded[(graded["graded_at"] < end) & (graded["week"] > week - GRADE_WINDOW)]
        n = int(arrived["referable"].sum())
        caught = int((arrived["referable"] & arrived["referred"]).sum())
        grades.append(n >= GRADES_MIN_CASES and caught / n < ref["catch_rate"] - CLEAR_DROP)
    pooled = weekly["est_sensitivity"].rolling(POOL_WEEKS, min_periods=1).mean()
    drift_high = weekly["drift_auc"] > DRIFT_ALARM
    return {
        "wait for grades": pd.Series(grades, index=weekly.index),
        "watch estimate": pooled < ref["catch_rate"] - ESTIMATE_DROP,
        "watch drift": drift_high & drift_high.shift(fill_value=False),
        "ClinicDrift": weekly["alarm"],
    }


def true_weekly_harm(weekly: pd.DataFrame, ref: dict, costs: Costs) -> tuple[pd.Series, pd.Series]:
    """Hindsight (harm in £, extra missed cases) per week beyond what the validated AI would cause."""
    usual_missed = weekly["true_cases"] * (1 - ref["catch_rate"])
    usual_false = (weekly["n_scans"] - weekly["true_cases"]) * (1 - ref["specificity"])
    extra_missed = (weekly["true_missed"] - usual_missed).clip(lower=0)
    extra_false = (weekly["true_false_referrals"] - usual_false).clip(lower=0)
    return pd.Series((costs.missed_case * extra_missed + costs.false_referral * extra_false).to_numpy(),
                     index=weekly["week"]), pd.Series(extra_missed.to_numpy(), index=weekly["week"])


def run(costs: Costs = Costs(), weekly: pd.DataFrame | None = None) -> pd.DataFrame:
    scans, _, model, _ = load_inputs()
    ref = reference_levels(scans, model)
    if weekly is None:
        weekly = pd.read_parquet(PROCESSED_DIR / "weekly.parquet")
    stream = pd.read_parquet(PROCESSED_DIR / "stream.parquet")
    seen = stream.merge(scans[["scan_id", "referable", "p_referable"]], on="scan_id", validate="one_to_one")
    seen["referred"] = seen["p_referable"].to_numpy() >= referral_thresholds(seen, scans, model)
    graded = seen[seen["graded_at"].notna()]
    clinics = {c["clinic_id"]: c for c in json.loads((PROCESSED_DIR / "clinics.json").read_text(encoding="utf-8"))}

    rows = []
    for clinic_id, w in weekly.groupby("clinic_id"):
        w = w.sort_values("week")
        changed = change_week(clinics[clinic_id])
        harm, extra_missed = true_weekly_harm(w, ref, costs)
        for policy, flags in policy_flags(w, graded[graded["clinic_id"] == clinic_id], ref).items():
            alarm = first_alarm(flags)
            false_alarm = alarm is not None and (changed is None or alarm < changed)
            if changed is None or false_alarm:
                exposed = pd.Series(dtype=float)  # nothing to catch, or the AI was pulled before the change
            else:
                last = (alarm - 1) if alarm else w["week"].max()
                exposed = harm.loc[changed:last]
            rows.append({
                "clinic_id": clinic_id,
                "policy": policy,
                "changed_week": changed,
                "first_alarm": alarm,
                "weeks_to_alarm": (alarm - changed) if (alarm and changed and not false_alarm) else None,
                "false_alarm": false_alarm,
                "extra_missed_before_alarm": float(extra_missed.loc[exposed.index].sum()) if len(exposed) else 0.0,
                "harm_before_alarm": float(exposed.sum()),
                "review_cost": costs.review if alarm else 0.0,
            })
    results = pd.DataFrame(rows)
    results["total_cost"] = results["harm_before_alarm"] + results["review_cost"]
    return results


def summary(results: pd.DataFrame) -> pd.DataFrame:
    g = results.groupby("policy", sort=False)
    return pd.DataFrame({
        "clinics_caught": g.apply(lambda d: int((d["changed_week"].notna() & d["first_alarm"].notna() & ~d["false_alarm"]).sum())),
        "clinics_changed": g.apply(lambda d: int(d["changed_week"].notna().sum())),
        "false_alarms": g["false_alarm"].sum().astype(int),
        "median_weeks_to_alarm": g["weeks_to_alarm"].median(),
        "extra_missed_cases": g["extra_missed_before_alarm"].sum().round(1),
        "total_cost_gbp": g["total_cost"].sum().round(-2),
    })


def sweep() -> pd.DataFrame:
    """Every policy's summary at each review cost: the costs are made up, so show how much they matter."""
    tables = []
    for review in SWEEP_REVIEW_COSTS:
        costs = Costs(review=review)
        table = summary(run(costs, decide.run(costs, write=False))).reset_index()
        table.insert(0, "review_cost", review)
        tables.append(table)
    return pd.concat(tables, ignore_index=True)


def main() -> None:
    results = run()
    results.to_parquet(PROCESSED_DIR / "backtest.parquet", index=False)
    table = summary(results)
    (PROCESSED_DIR / "backtest_summary.json").write_text(table.reset_index().to_json(orient="records", indent=2), encoding="utf-8")
    print(table.to_string())
    print()
    print(results.pivot(index="clinic_id", columns="policy", values="first_alarm").to_string())
    swept = sweep()
    swept.to_parquet(PROCESSED_DIR / "backtest_sweep.parquet", index=False)
    print()
    print("By review cost (other costs fixed):")
    print(swept.to_string(index=False))


if __name__ == "__main__":
    main()

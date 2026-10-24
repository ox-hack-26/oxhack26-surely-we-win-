"""Robustness: rerun the decision and the backtest under 100 different draws of the expert grades.

Which scans get graded, and how late, is luck, and grades feed both the decision rule and the
wait-for-grades policy. So the backtest is repeated with every clinic's grades redrawn (same share,
same delay range), keeping the scans, the model and the label-free estimates fixed. The answer is
a range per policy, not one lucky run. Needs no new scans, so it works with any model.

Writes processed/robustness.parquet (every draw, clinic and policy), robustness_summary.json, and
robustness_sweep.parquet: the review-cost sweep as medians over SWEEP_DRAWS draws.

    python -m clinicdrift.engine.robustness
"""
import json
import time
import zlib

import numpy as np
import pandas as pd

from clinicdrift.config import PROCESSED_DIR
from clinicdrift.engine import backtest, decide
from clinicdrift.engine.estimate import load_inputs
from clinicdrift.engine.replay import draw_grades

N_DRAWS = 100
SWEEP_DRAWS = 30  # per review cost in the sweep
SEED = 10_000  # far from the replay's own seed, so draw 0 isn't the headline run


def redraw(seen: pd.DataFrame, draw: int) -> pd.DataFrame:
    """The replay's scans with every clinic's grades drawn again."""
    graded = []
    for clinic_id, part in seen.groupby("clinic_id"):
        part = part.copy()
        part["graded_at"] = draw_grades(part["ts"], np.random.default_rng([SEED + draw, zlib.crc32(clinic_id.encode())]))
        graded.append(part[part["graded_at"].notna()])
    return pd.concat(graded, ignore_index=True)


def run(n_draws: int = N_DRAWS, cost_options: tuple[decide.Costs, ...] = (decide.Costs(),)) -> pd.DataFrame:
    """Backtest every policy under n_draws redrawn sets of grades, for each set of costs."""
    scans, _, model, _ = load_inputs()
    ref = decide.reference_levels(scans, model)
    seen, clinics = backtest.load_replay(scans, model)
    estimates = pd.read_parquet(PROCESSED_DIR / "weekly_estimates.parquet")
    by_clinic = {c: w.sort_values("week") for c, w in estimates.groupby("clinic_id")}

    runs, started = [], time.time()
    for draw in range(n_draws):
        graded = redraw(seen, draw)
        graded_by_clinic = {c: g for c, g in graded.groupby("clinic_id")}
        for costs in cost_options:
            weekly = pd.concat([decide.decide_clinic(w, graded_by_clinic.get(c, graded.iloc[:0]), ref, costs)
                                for c, w in by_clinic.items()], ignore_index=True)
            result = backtest.score(weekly, graded, clinics, ref, costs)
            result.insert(0, "draw", draw)
            result.insert(1, "review_price", costs.review)  # the setting; review_cost is what was charged
            runs.append(result)
        if (draw + 1) % 25 == 0 or draw + 1 == n_draws:
            print(f"  {draw + 1}/{n_draws} draws, {time.time() - started:.0f} s", flush=True)
    return pd.concat(runs, ignore_index=True)


def sweep() -> pd.DataFrame:
    """The review-cost sweep, as medians over SWEEP_DRAWS draws: same columns as backtest_sweep.parquet."""
    runs = run(SWEEP_DRAWS, tuple(decide.Costs(review=r) for r in backtest.SWEEP_REVIEW_COSTS))
    runs = runs.assign(caught=runs["changed_week"].notna() & runs["first_alarm"].notna() & ~runs["false_alarm"])
    per_draw = runs.groupby(["review_price", "policy", "draw"], sort=False).agg(
        clinics_caught=("caught", "sum"), clinics_changed=("changed_week", lambda c: int(c.notna().sum())),
        false_alarms=("false_alarm", "sum"), extra_missed_cases=("extra_missed_before_alarm", "sum"),
        total_cost_gbp=("total_cost", "sum"))
    medians = per_draw.groupby(level=["review_price", "policy"], sort=False).median().reset_index()
    return medians.rename(columns={"review_price": "review_cost"})


def summarise(runs: pd.DataFrame) -> dict:
    runs = runs.assign(caught=runs["changed_week"].notna() & runs["first_alarm"].notna() & ~runs["false_alarm"])
    per_draw = runs.groupby(["policy", "draw"], sort=False).agg(
        caught=("caught", "sum"), changed=("changed_week", lambda c: int(c.notna().sum())),
        false_alarms=("false_alarm", "sum"), missed=("extra_missed_before_alarm", "sum"), cost=("total_cost", "sum"))

    def q(s, p):
        return float(np.quantile(s, p))

    policies = []
    for policy, d in per_draw.groupby(level="policy", sort=False):
        delays = runs[(runs["policy"] == policy) & runs["caught"]]["weeks_to_alarm"]
        policies.append({
            "policy": policy,
            "changes": int(d["changed"].iloc[0]),
            "caught_median": q(d["caught"], 0.5), "caught_min": int(d["caught"].min()), "caught_max": int(d["caught"].max()),
            "all_caught_share": float((d["caught"] == d["changed"]).mean()),
            "false_alarms_mean": float(d["false_alarms"].mean()), "any_false_alarm_share": float((d["false_alarms"] > 0).mean()),
            "median_weeks_to_alarm": float(delays.median()) if len(delays) else None,
            "missed_median": q(d["missed"], 0.5), "missed_p5": q(d["missed"], 0.05), "missed_p95": q(d["missed"], 0.95),
            "cost_median": q(d["cost"], 0.5), "cost_p5": q(d["cost"], 0.05), "cost_p95": q(d["cost"], 0.95),
        })
    clinics = []
    for (policy, clinic), d in runs.groupby(["policy", "clinic_id"], sort=False):
        alarms = d["first_alarm"].dropna()
        clinics.append({
            "policy": policy, "clinic_id": clinic,
            "changed_week": None if pd.isna(d["changed_week"].iloc[0]) else int(d["changed_week"].iloc[0]),
            "alarm_share": float(d["first_alarm"].notna().mean()),
            "false_alarm_share": float(d["false_alarm"].mean()),
            "first_alarm_median": q(alarms, 0.5) if len(alarms) else None,
            "first_alarm_p5": q(alarms, 0.05) if len(alarms) else None,
            "first_alarm_p95": q(alarms, 0.95) if len(alarms) else None,
        })
    return {"n_draws": int(runs["draw"].nunique()), "policies": policies, "clinics": clinics}


def main() -> None:
    runs = run()
    runs.to_parquet(PROCESSED_DIR / "robustness.parquet", index=False)
    summary = summarise(runs)
    (PROCESSED_DIR / "robustness_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    table = pd.DataFrame(summary["policies"]).set_index("policy")
    print(table[["caught_median", "caught_min", "all_caught_share", "false_alarms_mean", "any_false_alarm_share",
                 "median_weeks_to_alarm", "missed_median", "missed_p95", "cost_median"]].round(2).to_string())
    print(f"Review-cost sweep, {SWEEP_DRAWS} draws per cost:", flush=True)
    swept = sweep()
    swept.to_parquet(PROCESSED_DIR / "robustness_sweep.parquet", index=False)
    print(swept.pivot(index="review_cost", columns="policy", values="total_cost_gbp").round(-3).to_string())


if __name__ == "__main__":
    main()

"""Write docs/results.md: every number the pitch and Devpost quote, straight from the engine's outputs.

Run it last, after the backtest, and again whenever the model or the replay changes, so nobody
quotes a stale figure:

    python -m clinicdrift.engine.results
"""
import json
from datetime import date

import pandas as pd

from clinicdrift.config import PROCESSED_DIR, REPO
from clinicdrift.engine.backtest import change_week
from clinicdrift.engine.estimate import load_inputs

OUT = REPO / "docs" / "results.md"
DEMO = "US-WEAR-01"
UPDATE = "US-UPD-01"
HEAVY_WEAR_FROM = 15  # weeks of US-WEAR-01 shown as "heavy wear"


def table(rows: list[list], header: list[str]) -> str:
    lines = ["| " + " | ".join(header) + " |", "| " + " | ".join("---" for _ in header) + " |"]
    lines += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return "\n".join(lines)


def pct(x) -> str:
    return "–" if pd.isna(x) else f"{x:.0%}"


def gbp(x) -> str:
    return f"£{x / 1000:,.0f}k" if abs(x) >= 1000 else f"£{x:,.0f}"


def weeks(x) -> str:
    return "–" if pd.isna(x) else f"{x:g}"


def delay(median_weeks) -> str:
    if pd.isna(median_weeks):
        return "never"
    return "in the same week as the change (median)" if median_weeks == 0 else f"a median of {median_weeks:g} weeks after the change"


def main() -> None:
    scans, _, model, base = load_inputs()
    weekly = pd.read_parquet(PROCESSED_DIR / "weekly.parquet")
    stream = pd.read_parquet(PROCESSED_DIR / "stream.parquet")
    backtest = pd.read_parquet(PROCESSED_DIR / "backtest.parquet")
    summary = pd.DataFrame(json.loads((PROCESSED_DIR / "backtest_summary.json").read_text(encoding="utf-8"))).set_index("policy")
    sweep = pd.read_parquet(PROCESSED_DIR / "backtest_sweep.parquet")
    settings = json.loads((PROCESSED_DIR / "decision_settings.json").read_text(encoding="utf-8"))
    clinics = {c["clinic_id"]: c for c in json.loads((PROCESSED_DIR / "clinics.json").read_text(encoding="utf-8"))}
    costs, ref = settings["costs"], settings["reference"]

    changed_at = {c: change_week(clinics[c]) for c in clinics}
    weekly["changed"] = [changed_at[c] is not None and w >= changed_at[c] for c, w in zip(weekly["clinic_id"], weekly["week"])]
    weekly["error"] = (weekly["est_sensitivity"] - weekly["true_sensitivity"]).abs()
    weekly["in_band"] = weekly["true_sensitivity"].between(weekly["est_low"], weekly["est_high"])
    unchanged, changed = weekly[~weekly["changed"]], weekly[weekly["changed"]]

    cd, grades = summary.loc["ClinicDrift"], summary.loc["wait for grades"]
    demo = weekly[weekly["clinic_id"] == DEMO].set_index("week")
    demo_wear = stream[stream["clinic_id"] == DEMO].groupby("week")["wear"].first()
    heavy = demo.loc[HEAVY_WEAR_FROM:]
    demo_bt = backtest[backtest["clinic_id"] == DEMO].set_index("policy")
    demo_alarm = demo_bt.loc["ClinicDrift", "first_alarm"]
    wear_start = clinics[DEMO]["wear_from_week"]
    collapse = next((w for w in demo.index if w > wear_start and demo.loc[w, "true_sensitivity"] < ref["catch_rate"] - 0.2), None)
    first_drift = next((w for w in demo.index if w >= wear_start and demo.loc[w, "drift_auc"] > 0.8), None)

    first_alarms = backtest.pivot(index="clinic_id", columns="policy", values="first_alarm")
    changed_ids = [c for c, w in changed_at.items() if w]
    image_changes = [c for c in changed_ids if not clinics[c].get("update_from_week")]

    cd_sweep = sweep[sweep["policy"] == "ClinicDrift"].set_index("review_cost")
    grades_sweep = sweep[sweep["policy"] == "wait for grades"].set_index("review_cost")
    noisy = [r for r in cd_sweep.index if cd_sweep.loc[r, "false_alarms"] > 0]
    pricey = [r for r in cd_sweep.index if cd_sweep.loc[r, "total_cost_gbp"] > grades_sweep.loc[r, "total_cost_gbp"]]
    cost_caveat = ("- **Costs are illustrative**: across review costs from " + gbp(cd_sweep.index.min()) + " to " + gbp(cd_sweep.index.max())
                   + (f" ClinicDrift raised false alarms at {', '.join(gbp(r) for r in noisy)}" if noisy else " ClinicDrift raised no false alarms")
                   + (f", and at {', '.join(gbp(r) for r in pricey)} reviewing every changed clinic cost more than waiting for grades, "
                      "because several of those clinics were actually fine" if pricey else "")
                   + " (see the sweep).")
    sw = weekly[weekly["clinic_id"] == "SW-MES-01"]
    sw_before, sw_after = sw[~sw["changed"]], sw[sw["changed"]]
    missed_by = {p: [c for c in changed_ids if pd.isna(first_alarms.loc[c, p])] for p in summary.index}
    update_lines = []
    if UPDATE in clinics:
        upd = weekly[weekly["clinic_id"] == UPDATE].set_index("week")
        upd_week = clinics[UPDATE]["update_from_week"]
        before, after = upd.loc[: upd_week - 1], upd.loc[upd_week:]
        upd_alarm = first_alarms.loc[UPDATE, "ClinicDrift"]
        update_lines = [
            f"- **A faulty software update** ({UPDATE}): in week {upd_week} the vendor raises the referral cut-off "
            f"({before['referral_threshold'].iloc[0]:.3f} → {after['referral_threshold'].iloc[0]:.3f}). The scans look exactly the same, "
            f"so drift stays at {after['drift_auc'].mean():.2f} on average and **watching drift never alarms**. The real catch rate falls from "
            f"{pct(before['true_sensitivity'].mean())} to {pct(after['true_sensitivity'].mean())}. ClinicDrift raises a harm alarm in week "
            f"{weeks(upd_alarm)}, once it is 90% sure the catch rate is below the 80% screening standard.",
        ]

    lines = [
        "# ClinicDrift results",
        "",
        f"Generated {date.today():%d %B %Y} by `python -m clinicdrift.engine.results` from the engine's outputs. "
        f"Model: **{model['model']}**. Quote numbers from this file only, and regenerate it after the model or replay changes.",
        "",
        "Slide charts made from the same outputs: [camera wear](charts/1-camera-wear.png), "
        "[software update](charts/2-software-update.png), [backtest](charts/3-backtest.png), [cost sweep](charts/4-cost-sweep.png).",
        "",
        "## Headline",
        "",
        f"At the default costs ({gbp(costs['missed_case'])} per missed urgent case, {gbp(costs['false_referral'])} per unnecessary referral, "
        f"{gbp(costs['review'])} per review), replaying 20 weeks at {len(clinics)} simulated clinics:",
        "",
        f"- **ClinicDrift caught {int(cd.clinics_caught)} of {int(cd.clinics_changed)} clinics whose conditions changed**, "
        f"{delay(cd.median_weeks_to_alarm)}, with **{int(cd.false_alarms)} false alarms** and "
        f"**{cd.extra_missed_cases:g} extra urgent cases missed**. Total cost {gbp(cd.total_cost_gbp)}.",
        f"- **Waiting for expert grades** (today's practice) caught {int(grades.clinics_caught)} of {int(grades.clinics_changed)}, "
        f"{delay(grades.median_weeks_to_alarm)}, and let **{grades.extra_missed_cases:g} extra urgent cases** through. "
        f"Total cost {gbp(grades.total_cost_gbp)}.",
        f"- **The demo clinic {DEMO}**: its camera starts wearing out in week {wear_start}. ClinicDrift raises the alarm in week "
        f"{weeks(demo_alarm)}" + (f", {collapse - int(demo_alarm)} weeks before the catch rate collapses (week {collapse})" if collapse and demo_alarm else "")
        + f". Waiting for grades never flags it within the 20 weeks, and {demo_bt.loc['wait for grades', 'extra_missed_before_alarm']:.0f} extra urgent cases are missed.",
        *update_lines,
        f"- **No single signal catches everything**: watching drift missed {len(missed_by['watch drift'])} of the "
        f"{len(changed_ids)} changes and watching the estimate missed {len(missed_by['watch estimate'])}; "
        f"ClinicDrift, which uses both, missed {len(missed_by['ClinicDrift'])}.",
        f"- **The AI's own confidence is fooled**: in weeks {HEAVY_WEAR_FROM}–20 at {DEMO} the label-free estimate averaged "
        f"{pct(heavy['est_sensitivity'].mean())} while the real catch rate averaged {pct(heavy['true_sensitivity'].mean())} "
        f"({pct(demo.loc[20, 'true_sensitivity'])} in week 20). That is why the decision rule stops trusting the estimate when drift is high.",
        f"- **Drift is reliable here**: none of the {len(unchanged)} clinic-weeks without a change scored above 0.7 "
        f"(highest {unchanged['drift_auc'].max():.2f}); "
        f"{sum(1 for c in image_changes if weekly[(weekly.clinic_id == c) & (weekly.week == changed_at[c])].drift_auc.iloc[0] > 0.8)} of "
        f"{len(image_changes)} changes to the scans themselves scored above 0.8 in their first week"
        + (f", and {DEMO}'s slow wear crossed 0.8 in week {first_drift} (wear {demo_wear[first_drift]:.2f}, barely visible)." if first_drift else "."),
        "",
        "## What the numbers come from",
        "",
        table(
            [[s, f"{(scans['source'] == s).sum():,}" if s != "eyepacs" else f"{((scans['source'] == s) & (scans['split'] == sp)).sum():,} ({sp})", note]
             for s, sp, note in [("eyepacs", "train", "training"), ("eyepacs", "val", "validation: threshold and calibration"),
                                 ("eyepacs", "test", "held-out scans for the quiet clinics, the switch clinics' early weeks and US-WEAR-01 (worn copies included)"),
                                 ("messidor2", "", "deployment clinics"),
                                 ("aptos", "", "deployment clinics (this copy is 224 px: a low-resolution test, not a population one)"),
                                 ("idrid", "", "deployment clinic")]],
            ["Source", "Scans scored", "Used for"],
        ),
        "",
        f"- **Replay**: {len(clinics)} clinics, 20 weeks from 5 January 2026, {len(stream):,} scans, each used once. "
        f"{stream['graded_at'].notna().mean():.0%} of scans get an expert grade, 35–49 days later.",
        f"- **Model**: validation AUC {model['val_auc']:.2f}; at the referral threshold ({model['referral_threshold']:.3f}) it catches "
        f"{pct(model['val_sensitivity'])} of urgent cases and clears {pct(model['val_specificity'])} of healthy scans on validation.",
        f"- **Costs** are illustrative, and the decision horizon is {costs['horizon_weeks']} weeks (how long a problem runs before grades show it).",
        "",
        "## Backtest: four ways to monitor",
        "",
        table(
            [[p, f"{int(r.clinics_caught)} of {int(r.clinics_changed)}", int(r.false_alarms), weeks(r.median_weeks_to_alarm),
              f"{r.extra_missed_cases:g}", gbp(r.total_cost_gbp)] for p, r in summary.iterrows()],
            ["Policy", "Changes caught", "False alarms", "Median weeks to alarm", "Extra urgent cases missed", "Total cost"],
        ),
        "",
        "Policies: **wait for grades** alarms when the graded catch rate over 8 weeks is 15 points below validated (at least 5 graded urgent cases); "
        "**watch estimate** when the label-free estimate is 10 points below; **watch drift** when drift stays above 0.8 for two weeks; "
        "**ClinicDrift** (`decide.py`) raises a *drift* alarm when the scans stop looking validated and a *harm* alarm when it is "
        "90% sure the catch rate is below the 80% UK screening standard, each only if the expected harm outweighs a review. "
        "A first alarm pulls the AI for review; harm counts from the change until then.",
        "",
        "First alarm week per clinic (– = never):",
        "",
        table(
            [[c, weeks(changed_at[c]) if changed_at[c] else "no change"] +
             [weeks(backtest[(backtest.clinic_id == c) & (backtest.policy == p)].first_alarm.iloc[0]) for p in summary.index]
             for c in sorted(clinics)],
            ["Clinic", "Changed in week"] + list(summary.index),
        ),
        "",
        f"## {DEMO}, week by week",
        "",
        "The camera wears from week " f"{wear_start}" ": scans get blurrier and darker. \"Real\" uses every expert grade in hindsight; a clinic would not know it that week.",
        "",
        table(
            [[w, f"{demo_wear[w]:.2f}", pct(r.true_sensitivity), pct(r.est_sensitivity), f"{pct(r.catch_rate)} ({pct(r.catch_low)}–{pct(r.catch_high)})",
              f"{r.drift_auc:.2f}", f"{r.quality_mean:.2f}", f"{int(r.true_missed)} of {int(r.true_cases)}", "**ALARM**" if r.alarm else ""]
             for w, r in demo.iterrows()],
            ["Week", "Wear", "Real catch rate", "AI's own estimate", "ClinicDrift belief (band)", "Drift", "Quality", "Urgent cases missed", "Alarm"],
        ),
        "",
        "## How good is the label-free estimate?",
        "",
        table(
            [[name, len(d), f"{d['error'].mean():.3f}", pct(d["in_band"].mean())]
             for name, d in [("No change", unchanged), ("After a change", changed), (f"{DEMO} weeks {HEAVY_WEAR_FROM}–20", heavy.assign(
                 error=(heavy.est_sensitivity - heavy.true_sensitivity).abs(), in_band=heavy.true_sensitivity.between(heavy.est_low, heavy.est_high)))]],
            ["Clinic-weeks", "Count", "Mean error (catch rate)", "Real value inside its 90% band"],
        ),
        "",
        "## How much the made-up costs matter",
        "",
        table(
            [[gbp(r.review_cost), r.policy, f"{int(r.clinics_caught)} of {int(r.clinics_changed)}", int(r.false_alarms),
              f"{r.extra_missed_cases:g}", gbp(r.total_cost_gbp)] for r in sweep.itertuples()],
            ["Review cost", "Policy", "Changes caught", "False alarms", "Extra urgent cases missed", "Total cost"],
        ),
        "",
        "## Honest caveats",
        "",
        f"- **Model**: {model['model']}. Numbers will change when it changes; regenerate this file.",
        "- **Simulated clinics**: real public scans, but the clinics, camera switches and wear are simulated. The datasets carry no age, sex or ethnicity, "
        "so make no fairness claims about patient groups, only about clinics and cameras. This APTOS copy is 224 px, so the APTOS clinics test low resolution, not Indian patients.",
        cost_caveat,
        (f"- **The evidence test costs time**: ClinicDrift only raises a harm alarm once it is 90% sure the catch rate is below 80%, so on the software update it waits "
         f"{weeks(first_alarms.loc[UPDATE, 'ClinicDrift'] - clinics[UPDATE]['update_from_week'])} weeks where watching the estimate alarms at once. "
         "That is the price of not pulling a healthy AI over a few weeks of noise: without the test, a handful of low grades was enough to pull healthy clinics."
         if UPDATE in clinics and not pd.isna(first_alarms.loc[UPDATE, "ClinicDrift"]) else
         "- **Watching drift alone does almost as well here**, because every harmful change in this replay also changed how the scans look."),
        "- **The 80% floor** is the long-standing UK (Exeter / British Diabetic Association) standard of at least 80% sensitivity for diabetic eye screening.",
        f"- **A new camera doesn't always mean missed cases**: at SW-MES-01 the new camera moved this model's catch rate "
        f"{pct(sw_before.true_sensitivity.mean())} → {pct(sw_after.true_sensitivity.mean())} and its healthy referrals "
        f"{sw_before.true_false_referrals.mean():.0f} → {sw_after.true_false_referrals.mean():.0f} a week. The missed cases came from "
        f"the worn camera ({DEMO}) and the faulty update ({UPDATE}).",
        "- **The belief band** describes the clinic's underlying catch rate. A single week has only about 10 urgent cases, so that week's real value often falls outside it; "
        "don't present it as a 90% interval for one week. The label-free estimate's band is the one checked against weekly values above.",
        "- **Drift alarms say \"can't verify\", not \"X% caught\"**: when drift triggers the alarm the belief is pulled towards 50% with a very wide band "
        "(exactly 50% at clinics that differ from day one, before any grades). Say the AI is outside its validated conditions; don't quote that number as a measured drop.",
        f"- **Late grades can mislead**: at {DEMO} the belief creeps back up in the later weeks because the grades arriving then are for scans "
        "taken 5–7 weeks earlier, when wear was milder. That is why an alarm stays on until someone reviews the AI: without that, old grades would switch it off just as harm peaks.",
        "- **Full wear is obvious**: at wear 1.0 any grader would reject the scans. The point is that drift fired at low wear, when the scans still look normal.",
        f"- **Small**: {len(clinics)} clinics, 20 weeks, one replay seed. \"Real\" values use every expert grade in hindsight.",
        "",
        "## Regenerate",
        "",
        "```bash",
        "python -m clinicdrift.engine.replay",
        "python -m clinicdrift.engine.estimate",
        "python -m clinicdrift.engine.decide",
        "python -m clinicdrift.engine.backtest",
        "python -m clinicdrift.engine.results",
        "python -m clinicdrift.engine.charts",
        "```",
        "",
        "or all of it, after checking the model files fit: `python -m clinicdrift.engine.pipeline`.",
        "",
        f"Inputs read from `{(base.relative_to(PROCESSED_DIR.parent) if base.is_relative_to(PROCESSED_DIR.parent) else base).as_posix()}`.",
        "",
    ]
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()

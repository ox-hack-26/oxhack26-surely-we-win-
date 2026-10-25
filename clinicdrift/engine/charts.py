"""Slide charts in docs/charts/, drawn from the engine's outputs so they follow the model.

    python -m clinicdrift.engine.charts

One colour per idea across the deck, so slides read alike (palette checked for colour-blind
safety; aqua and yellow are under 3:1 on white, so every line also carries a text label):
blue = ClinicDrift, orange = expert grades, aqua = drift, yellow = the AI's own estimate.
Alarms are the status red, always with a marker and a label. Titles state the finding and
compute their numbers, so they stay true when the model changes.
"""
import json
import logging

import matplotlib

matplotlib.use("Agg")
# Segoe UI has a semibold weight; the fallback fonts don't, and matplotlib warns about each one.
logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.patches import PathPatch  # noqa: E402
from matplotlib.path import Path  # noqa: E402
from matplotlib.ticker import FuncFormatter, PercentFormatter  # noqa: E402

from clinicdrift.config import PROCESSED_DIR, REPO  # noqa: E402
from clinicdrift.engine.decide import MIN_CATCH_RATE  # noqa: E402
from clinicdrift.engine.estimate import load_inputs  # noqa: E402
from clinicdrift.engine.robustness import SWEEP_DRAWS  # noqa: E402

OUT = REPO / "docs" / "charts"
WEAR, UPDATE = "US-WEAR-01", "US-UPD-01"

SURFACE, INK, INK_2, MUTED, GRID, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
ALARM = "#d03b3b"  # status: critical
CHANGED = "#f0efec"  # wash behind the weeks after a clinic changed
CLINICDRIFT, GRADES, DRIFT, ESTIMATE = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"
POLICY_COLOURS = {"ClinicDrift": CLINICDRIFT, "wait for grades": GRADES, "watch drift": DRIFT, "watch estimate": ESTIMATE}
POLICY_ORDER = ["ClinicDrift", "wait for grades", "watch drift", "watch estimate"]
LINE, DOT = 2.2, 5.5
SIZE, DPI = (12, 6.75), 160  # 1920 x 1080

plt.rcParams.update({
    "font.family": ["Segoe UI", "Arial", "DejaVu Sans"],
    "font.size": 11, "text.color": INK, "axes.labelcolor": INK_2,
    "axes.edgecolor": AXIS, "axes.linewidth": 0.8, "axes.facecolor": SURFACE, "figure.facecolor": SURFACE,
    "xtick.color": MUTED, "ytick.color": MUTED, "xtick.labelcolor": INK_2, "ytick.labelcolor": INK_2,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8, "grid.linestyle": "-",
    "axes.spines.top": False, "axes.spines.right": False, "legend.frameon": False,
})


def fit_width(fig, text, max_share=0.93, smallest=9):
    """Shrink a line of text until it fits the figure: titles are computed, so their length varies."""
    while text.get_fontsize() > smallest:
        fig.canvas.draw()
        if text.get_window_extent().width <= max_share * fig.bbox.width:
            return
        text.set_fontsize(text.get_fontsize() - 0.5)


def frame(title: str, subtitle: str, footnote: str):
    fig = plt.figure(figsize=SIZE, dpi=DPI)
    fit_width(fig, fig.text(0.04, 0.945, title, fontsize=19, fontweight="semibold", color=INK, va="top"))
    fit_width(fig, fig.text(0.04, 0.885, subtitle, fontsize=12.5, color=INK_2, va="top"))
    fit_width(fig, fig.text(0.04, 0.025, footnote, fontsize=9, color=MUTED, va="bottom"), smallest=7)
    return fig


def end_labels(ax, items, x, min_gap):
    """Direct labels at the line ends, in ink beside a colour key; spread apart with a leader line if they'd collide."""
    items = sorted(items, key=lambda i: i[0])
    placed = []
    for y, _, _ in items:
        placed.append(max(y, placed[-1] + min_gap) if placed else y)
    shift = max(0.0, placed[-1] - (ax.get_ylim()[1] - min_gap / 2))
    placed = [p - shift for p in placed]
    for (y, text, colour), at in zip(items, placed):
        if colour is None:  # a reference line's label: muted text, no colour key
            ax.text(x + 0.5, at, text, va="center", fontsize=10, color=MUTED, clip_on=False)
            continue
        if abs(at - y) > 1e-9:
            ax.plot([x + 0.15, x + 0.45], [y, at], color=AXIS, lw=0.8, clip_on=False)
        ax.plot([x + 0.5, x + 0.9], [at, at], color=colour, lw=LINE + 1, solid_capstyle="round", clip_on=False)
        ax.text(x + 1.05, at, text, va="center", fontsize=11, color=INK, clip_on=False)


def changed_period(axes, week, text, top_ax):
    """Shade the weeks after the clinic changed, with the label low in the top panel."""
    for ax in axes:
        ax.axvspan(week - 0.5, ax.get_xlim()[1], color=CHANGED, lw=0, zorder=0)
    top_ax.text(week - 0.35, 0.03, text, fontsize=10.5, color=INK_2, va="bottom", zorder=7,
                bbox={"facecolor": CHANGED, "edgecolor": "none", "pad": 2})  # the alarm line passes behind it


def alarm_line(axes, week, text, top_ax):
    for ax in axes:
        ax.axvline(week, color=ALARM, lw=1.3, zorder=2)
    ymax = top_ax.get_ylim()[1]
    top_ax.plot(week, ymax, marker="v", color=ALARM, ms=10, clip_on=False, zorder=6,
                markeredgecolor=SURFACE, markeredgewidth=1.5)
    top_ax.text(week + 0.25, ymax - 0.02, text, fontsize=11, color=INK, va="top", fontweight="semibold")


def clinic_story(weekly, clinic_id, event_week, event_text, title, subtitle, footnote, path):
    d = weekly[weekly["clinic_id"] == clinic_id].sort_values("week")
    alarm = d.loc[d["alarm"], "week"].min()
    reason = d.loc[d["week"] == alarm, "alarm_reason"].iloc[0] if pd.notna(alarm) else None

    fig = frame(title, subtitle, footnote)
    top = fig.add_axes([0.07, 0.385, 0.74, 0.405])
    bottom = fig.add_axes([0.07, 0.135, 0.74, 0.16], sharex=top)
    weeks = d["week"]

    top.fill_between(weeks, d["catch_low"], d["catch_high"], color=CLINICDRIFT, alpha=0.10, lw=0, zorder=2)
    top.plot(weeks, d["catch_rate"], color=CLINICDRIFT, lw=LINE, solid_capstyle="round", zorder=4, label="ClinicDrift's belief (band: 90%)")
    top.plot(weeks, d["est_sensitivity"], color=ESTIMATE, lw=LINE, solid_capstyle="round", zorder=3, label="The AI's own estimate")
    top.plot(weeks, d["true_sensitivity"], color=GRADES, lw=LINE, solid_capstyle="round", zorder=4,
             marker="o", ms=DOT, markeredgecolor=SURFACE, markeredgewidth=1.5, label="Real catch rate (known 5–7 weeks later)")
    top.axhline(MIN_CATCH_RATE, color=MUTED, lw=0.9, zorder=1)
    top.set_ylim(0, 1.08)
    top.set_xlim(0.6, 20.4)
    top.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
    top.set_ylabel("Catch rate")
    top.tick_params(labelbottom=False)
    top.legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncol=3, fontsize=10.5, handlelength=1.6, borderaxespad=0.3)
    last = d.iloc[-1]
    end_labels(top, [(last["true_sensitivity"], f"Real {last['true_sensitivity']:.0%}", GRADES),
                     (last["est_sensitivity"], f"AI's own {last['est_sensitivity']:.0%}", ESTIMATE),
                     (last["catch_rate"], f"ClinicDrift {last['catch_rate']:.0%}", CLINICDRIFT),
                     (MIN_CATCH_RATE, f"{MIN_CATCH_RATE:.0%} screening standard", None)], 20, 0.075)

    bottom.plot(weeks, d["drift_auc"], color=DRIFT, lw=LINE, solid_capstyle="round", zorder=3)
    for level, text in ((0.7, "trusted below 0.7"), (0.9, "not trusted above 0.9")):
        bottom.axhline(level, color=MUTED, lw=0.9, zorder=1)
        bottom.text(1.15, level + 0.012, text, fontsize=9, color=MUTED, va="bottom")
    bottom.set_ylim(0.3, 1.05)
    bottom.set_ylabel("Drift")
    bottom.set_xlabel("Week")
    bottom.set_xticks(range(1, 21))
    end_labels(bottom, [(last["drift_auc"], f"Drift {last['drift_auc']:.2f}", DRIFT)], 20, 0.1)

    changed_period([top, bottom], event_week, event_text, top)
    if pd.notna(alarm):
        alarm_line([top, bottom], alarm, f"ClinicDrift alarm, week {int(alarm)} ({reason})", top)
    fig.savefig(path, dpi=DPI, facecolor=SURFACE)
    plt.close(fig)


def bar(ax, y, value, colour, height, radius_px=7):
    """Horizontal bar as one shape: square at the baseline, rounded corners at the data end."""
    if value <= 0:
        return
    fig = ax.figure
    fig.canvas.draw()  # so the axes' size in pixels is known
    box = ax.get_window_extent()
    px_x = box.width / np.diff(ax.get_xlim())[0]
    px_y = box.height / abs(np.diff(ax.get_ylim())[0])
    rx = min(radius_px / px_x, value / 2)
    ry = min(radius_px / px_y, height / 2)
    y0, y1 = y - height / 2, y + height / 2
    arc = np.linspace(0, np.pi / 2, 10)
    top_corner = [(value - rx + rx * np.sin(a), y1 - ry + ry * np.cos(a)) for a in arc]           # up and round to the right
    bottom_corner = [(value - rx + rx * np.cos(a), y0 + ry - ry * np.sin(a)) for a in arc]        # round down to the bottom
    points = [(0, y0), (0, y1), *top_corner, *bottom_corner, (0, y0)]
    codes = [Path.MOVETO] + [Path.LINETO] * (len(points) - 2) + [Path.CLOSEPOLY]
    ax.add_patch(PathPatch(Path(points, codes), lw=0, color=colour))


def backtest_chart(summary, footnote, path):
    s = summary.set_index("policy").loc[POLICY_ORDER]
    cd = s.loc["ClinicDrift"]
    title = (f"Only ClinicDrift caught all {int(cd.clinics_changed)} changed clinics: {int(cd.false_alarms)} false alarms, "
             f"{cd.extra_missed_cases:g} extra missed cases")
    subtitle = "Four ways to monitor the same 10 clinics over 20 weeks · £10k per missed case, £150 per unnecessary referral, £25k per review"
    fig = frame(title, subtitle, footnote)
    panels = [("clinics_caught", f"Failures caught (of {int(cd.clinics_changed)})", lambda v: f"{v:g}"),
              ("extra_missed_cases", "Extra urgent cases missed", lambda v: f"{v:g}"),
              ("total_cost_gbp", "Total cost", lambda v: f"£{v / 1000:,.0f}k")]
    for i, (column, heading, fmt) in enumerate(panels):
        ax = fig.add_axes([0.17 + i * 0.28, 0.12, 0.22, 0.64])
        values = s[column].astype(float)
        xmax = values.max() * 1.3 or 1
        ax.set_xlim(0, xmax)
        ax.set_ylim(len(values) - 0.4, -0.6)
        for row, (policy, value) in enumerate(values.items()):
            bar(ax, row, value, POLICY_COLOURS[policy], 0.42)
            ax.text(value + xmax * 0.02, row, fmt(value), va="center", fontsize=11.5, color=INK)
        ax.set_yticks(range(len(values)), [p if i == 0 else "" for p in values.index], fontsize=12)
        ax.tick_params(axis="y", length=0, labelcolor=INK)
        ax.tick_params(axis="x", labelbottom=False, length=0)
        ax.grid(False)
        ax.spines["bottom"].set_visible(False)
        ax.set_title(heading, loc="left", fontsize=12.5, color=INK, pad=10)
    fig.savefig(path, dpi=DPI, facecolor=SURFACE)
    plt.close(fig)


def robust_backtest_chart(robust, footnote, path):
    """The backtest across many draws of the grades: shares as bars, medians as dots with 90% whiskers."""
    pol = {p["policy"]: p for p in robust["policies"]}
    cd, n = pol["ClinicDrift"], robust["n_draws"]
    every_time = cd["all_caught_share"] == 1 and cd["any_false_alarm_share"] == 0
    title = (f"Across {n} draws of the grades, only ClinicDrift caught all {cd['changes']} changed clinics every time, with no false alarms"
             if every_time else f"How the four monitoring policies did across {n} draws of the expert grades")
    subtitle = ("Same 10 clinics over 20 weeks · dots: median, lines: 90% of draws · "
                "£10k per missed case, £150 per unnecessary referral, £25k per review")
    fig = frame(title, subtitle, footnote)
    panels = [
        ("bar", "all_caught_share", f"Draws catching all {cd['changes']} changes", lambda v: f"{v:.0%}"),
        ("bar", "any_false_alarm_share", "Draws with a false alarm", lambda v: f"{v:.0%}"),
        ("dot", "missed", "Extra urgent cases missed", lambda v: f"{v:.1f}"),
        ("dot", "cost", "Total cost", lambda v: f"£{v / 1000:,.0f}k"),
    ]
    for i, (form, key, heading, fmt) in enumerate(panels):
        ax = fig.add_axes([0.15 + i * 0.215, 0.12, 0.16, 0.64])
        if form == "bar":
            values = [pol[p][key] for p in POLICY_ORDER]
            xmax = 1.3
        else:
            values = [(pol[p][f"{key}_median"], pol[p][f"{key}_p5"], pol[p][f"{key}_p95"]) for p in POLICY_ORDER]
            xmax = max(hi for _, _, hi in values) * 1.35 or 1
        ax.set_xlim(0, xmax)
        ax.set_ylim(len(POLICY_ORDER) - 0.4, -0.6)
        for row, (policy, value) in enumerate(zip(POLICY_ORDER, values)):
            colour = POLICY_COLOURS[policy]
            if form == "bar":
                bar(ax, row, value, colour, 0.42)
                ax.text(value + xmax * 0.03, row, fmt(value), va="center", fontsize=11.5, color=INK)
            else:
                mid, lo, hi = value
                ax.plot([lo, hi], [row, row], color=colour, lw=LINE, solid_capstyle="round", zorder=3)
                ax.plot(mid, row, "o", color=colour, ms=DOT + 2.5, markeredgecolor=SURFACE, markeredgewidth=1.5, zorder=4)
                ax.text(hi + xmax * 0.04, row, fmt(mid), va="center", fontsize=11.5, color=INK)
        ax.set_yticks(range(len(POLICY_ORDER)), POLICY_ORDER if i == 0 else [""] * len(POLICY_ORDER), fontsize=12)
        ax.tick_params(axis="y", length=0, labelcolor=INK)
        ax.tick_params(axis="x", labelbottom=False, length=0)
        ax.grid(False)
        ax.spines["bottom"].set_visible(False)
        ax.set_title(heading, loc="left", fontsize=12, color=INK, pad=10)
    fig.savefig(path, dpi=DPI, facecolor=SURFACE)
    plt.close(fig)


def sweep_chart(sweep, footnote, path, note=""):
    pivot = sweep.pivot(index="review_cost", columns="policy", values="total_cost_gbp")[POLICY_ORDER]
    cheapest = pivot.idxmin(axis=1)
    wins = [r for r in pivot.index if cheapest[r] == "ClinicDrift"]
    cd_false = int(sweep[sweep["policy"] == "ClinicDrift"]["false_alarms"].sum())
    title = (f"ClinicDrift is the cheapest way to monitor while a review costs up to £{max(wins) / 1000:,.0f}k"
             if wins else "How the total cost depends on what a review costs")
    subtitle = (f"Total cost of missed cases, unnecessary referrals and reviews, by review cost; other costs fixed{note} · "
                + ("ClinicDrift raised no false alarms at any review cost" if cd_false == 0 else "ClinicDrift raised false alarms at some review costs"))
    fig = frame(title, subtitle, footnote)
    ax = fig.add_axes([0.08, 0.12, 0.72, 0.66])
    x = list(pivot.index)
    for policy in POLICY_ORDER:
        ax.plot(x, pivot[policy], color=POLICY_COLOURS[policy], lw=LINE, marker="o", ms=DOT,
                markeredgecolor=SURFACE, markeredgewidth=1.5, solid_capstyle="round", label=policy,
                zorder=4 if policy == "ClinicDrift" else 3)
    ax.set_xscale("log")
    ax.set_xticks(x, [f"£{v / 1000:,.0f}k" for v in x])
    ax.minorticks_off()
    ax.set_xlim(x[0] * 0.85, x[-1] * 1.12)
    ax.set_ylim(0, pivot.values.max() * 1.1)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"£{v / 1000:,.0f}k" if v else "£0"))
    ax.set_xlabel("What one review costs")
    ax.set_ylabel("Total cost over 20 weeks")
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncol=4, fontsize=10.5, handlelength=1.6, borderaxespad=0.3)
    span = pivot.values.max() * 1.1
    items = [(pivot[p].iloc[-1], f"{p} £{pivot[p].iloc[-1] / 1000:,.0f}k", POLICY_COLOURS[p]) for p in POLICY_ORDER]
    # end labels sit in log space, so place them by hand just past the last point
    items = sorted(items, key=lambda i: i[0])
    placed = []
    for y, _, _ in items:
        placed.append(max(y, placed[-1] + span * 0.06) if placed else y)
    for (y, text, colour), at in zip(items, placed):
        x0 = x[-1] * 1.04
        if abs(at - y) > 1e-9:
            ax.plot([x[-1] * 1.01, x0], [y, at], color=AXIS, lw=0.8, clip_on=False)
        ax.plot([x0, x0 * 1.05], [at, at], color=colour, lw=LINE + 1, solid_capstyle="round", clip_on=False)
        ax.text(x0 * 1.08, at, text, va="center", fontsize=11, color=INK, clip_on=False)
    fig.savefig(path, dpi=DPI, facecolor=SURFACE)
    plt.close(fig)


def main() -> None:
    _, _, model, _ = load_inputs()
    weekly = pd.read_parquet(PROCESSED_DIR / "weekly.parquet")
    summary = pd.DataFrame(json.loads((PROCESSED_DIR / "backtest_summary.json").read_text(encoding="utf-8")))
    robust_path, robust_sweep = PROCESSED_DIR / "robustness_summary.json", PROCESSED_DIR / "robustness_sweep.parquet"
    robust = json.loads(robust_path.read_text(encoding="utf-8")) if robust_path.exists() else None
    sweep = pd.read_parquet(robust_sweep if robust_sweep.exists() else PROCESSED_DIR / "backtest_sweep.parquet")
    sweep_note = f" (median over {SWEEP_DRAWS} draws of the grades)" if robust_sweep.exists() else ""
    clinics = {c["clinic_id"]: c for c in json.loads((PROCESSED_DIR / "clinics.json").read_text(encoding="utf-8"))}
    footnote = (f"Model: {model['model']} · simulated clinics built from real public scans (EyePACS, Messidor-2, APTOS, IDRiD) "
                "· regenerate with python -m clinicdrift.engine.charts")
    OUT.mkdir(parents=True, exist_ok=True)
    written = []

    if WEAR in clinics:
        d = weekly[weekly["clinic_id"] == WEAR].set_index("week")
        start, alarm = clinics[WEAR]["wear_from_week"], d.index[d["alarm"]].min()
        late = d.loc[15:]
        if late["est_sensitivity"].mean() - late["true_sensitivity"].mean() >= 0.05:
            title = (f"Camera wear: the AI's own estimate stayed near {late['est_sensitivity'].mean():.0%} "
                     f"while the real catch rate fell to {d['true_sensitivity'].iloc[-1]:.0%}")
        else:
            # The estimate tracked reality here, so the finding is timing, not a fooled estimate.
            bt = pd.read_parquet(PROCESSED_DIR / "backtest.parquet").query("clinic_id == @WEAR").set_index("policy")
            est_alarm = bt.loc["watch estimate", "first_alarm"]
            title = (f"Camera wear: drift flagged the worn scans in week {alarm}; watching the AI's own estimate "
                     + (f"only did in week {est_alarm:.0f}" if pd.notna(est_alarm) else "never did"))
        subtitle = (f"{WEAR} · scans blur and darken from week {start} · ClinicDrift saw the scans drift "
                    f"and raised the alarm in week {alarm}, before any grade could show the drop")
        clinic_story(weekly, WEAR, start, f"Camera wearing from week {start}", title, subtitle, footnote, OUT / "1-camera-wear.png")
        written.append("1-camera-wear.png")

    if UPDATE in clinics:
        d = weekly[weekly["clinic_id"] == UPDATE].set_index("week")
        start = clinics[UPDATE]["update_from_week"]
        before, after = d.loc[: start - 1], d.loc[start:]
        title = (f"Faulty update: drift stayed silent while the catch rate fell from "
                 f"{before['true_sensitivity'].mean():.0%} to {after['true_sensitivity'].mean():.0%}")
        upd = next((c for c in robust["clinics"] if c["policy"] == "ClinicDrift" and c["clinic_id"] == UPDATE), None) if robust else None
        when = (f" a median of {upd['first_alarm_median'] - start:g} weeks later (weeks {upd['first_alarm_p5']:g}–"
                f"{upd['first_alarm_p95']:g} across draws of the grades)" if upd and upd["first_alarm_median"] is not None else " instead")
        subtitle = (f"{UPDATE} · a vendor update raises the referral cut-off in week {start} · "
                    f"ClinicDrift's harm alarm comes{when}")
        clinic_story(weekly, UPDATE, start, f"Faulty update running from week {start}", title, subtitle, footnote, OUT / "2-software-update.png")
        written.append("2-software-update.png")

    if robust:
        robust_backtest_chart(robust, footnote, OUT / "3-backtest.png")
    else:
        backtest_chart(summary, footnote, OUT / "3-backtest.png")
    sweep_chart(sweep, footnote, OUT / "4-cost-sweep.png", sweep_note)
    written += ["3-backtest.png", "4-cost-sweep.png"]
    print(f"Wrote {', '.join(written)} to {OUT}")


if __name__ == "__main__":
    main()

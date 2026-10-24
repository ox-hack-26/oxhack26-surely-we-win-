"""Check the accuracy drop: how the EyePACS-trained classifier does at each deployment site.

    python -m clinicdrift.data.report

Uses every scan's expert grade, which no clinic would have in time; this is the ground truth the
engine's image-only estimate is judged against. Writes processed/model_report.json and
docs/model-report.md (commit that one: the pitch quotes it).
"""
import json

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from clinicdrift.config import PROCESSED_DIR, REPO
from clinicdrift.data.score import MODEL_JSON, SCANS
from clinicdrift.data.sources import SOURCES, TRAINING_SOURCE

REPORT_JSON = PROCESSED_DIR / "model_report.json"
REPORT_MD = REPO / "docs" / "model-report.md"
Z = 1.96  # 95% intervals
WEAR_BANDS = ((0.0, 0.35), (0.35, 0.7), (0.7, 1.0))


def wilson(hits: int, n: int) -> tuple[float, float]:
    """95% Wilson score interval for a proportion."""
    if n == 0:
        return float("nan"), float("nan")
    p = hits / n
    centre = (p + Z**2 / (2 * n)) / (1 + Z**2 / n)
    half = Z * np.sqrt(p * (1 - p) / n + Z**2 / (4 * n**2)) / (1 + Z**2 / n)
    return centre - half, centre + half


def site_rates(group: pd.DataFrame, threshold: float) -> dict:
    y = group["referable"].to_numpy(bool)
    p = group["p_referable"].to_numpy()
    refer = p >= threshold
    caught, missed_neg = int(refer[y].sum()), int((~refer[~y]).sum())
    sens_lo, sens_hi = wilson(caught, int(y.sum()))
    return {
        "n_scans": len(group),
        "n_referable": int(y.sum()),
        "prevalence": float(y.mean()),
        "auc": float(roc_auc_score(y, p)) if 0 < y.sum() < len(y) else None,
        "sensitivity": caught / y.sum() if y.sum() else None,
        "sensitivity_low": sens_lo,
        "sensitivity_high": sens_hi,
        "specificity": missed_neg / (~y).sum() if (~y).sum() else None,
        "referral_rate": float(refer.mean()),
        "missed_referable": int(y.sum()) - caught,
        "mean_p_referable": float(p.mean()),
        "confidence_estimate": _confidence_estimate(p, threshold),
        "mean_quality": float(group["quality"].mean()),
        "median_width_px": float(group["width"].median()),
    }


def _confidence_estimate(p: np.ndarray, threshold: float) -> float:
    """The naive image-only catch rate: trust p_referable as the chance each scan is referable."""
    return float((p * (p >= threshold)).sum() / p.sum())


def main() -> None:
    scans = pd.read_parquet(SCANS)
    model = json.loads(MODEL_JSON.read_text(encoding="utf-8"))
    threshold = model["referral_threshold"]

    eyepacs = scans[scans["source"] == TRAINING_SOURCE]
    clean = eyepacs[eyepacs["wear"] == 0]
    groups = {"EyePACS val (threshold set here)": clean[clean["split"] == "val"],
              "EyePACS held-out test (baseline)": clean[clean["split"] == "test"]}
    for name, src in SOURCES.items():
        if name != TRAINING_SOURCE:
            groups[f"{src.site} ({src.country})"] = scans[scans["source"] == name]
    worn = eyepacs[eyepacs["wear"] > 0]
    for low, high in WEAR_BANDS:  # the worn-camera clinic's scans, by how worn the camera was
        band = worn[(worn["wear"] > low) & (worn["wear"] <= high)]
        if len(band):
            groups[f"EyePACS, camera wear {low:.2f}–{high:.2f}"] = band
    report = {name: site_rates(group, threshold) for name, group in groups.items()}
    REPORT_JSON.write_text(json.dumps({"referral_threshold": threshold, "sites": report}, indent=2), encoding="utf-8")

    baseline = report["EyePACS held-out test (baseline)"]["sensitivity"]
    lines = [
        "# Model report: the accuracy drop at each site",
        "",
        "Made by `python -m clinicdrift.data.report`. The classifier is "
        f"`{model['arch']}` fine-tuned on {model['n_train']:,} EyePACS training scans at {model['image_size']} px "
        f"for {model['epochs_run']} of {model['epochs_planned']} planned epochs (best on val: epoch {model['best_epoch']}). "
        f"The referral threshold ({threshold:.3f}) was set on EyePACS val to catch {model['target_sensitivity']:.0%} "
        "of referable cases (grade 2 or above).",
        "",
        "Catch rate is sensitivity: the share of referable scans the model refers, with a 95% interval. "
        "The naive estimate trusts the model's own probabilities and needs no expert grades; "
        "the gap between it and the true catch rate is what the engine has to close.",
        "",
        "| Site | Scans | Referable | AUC | Catch rate (95% CI) | Change vs baseline | Specificity | Referred | Naive estimate | Quality | Median width |",
        "| --- | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    def pct(x) -> str:
        return "n/a" if x is None or np.isnan(x) else f"{x:.1%}"

    for name, r in report.items():
        is_reference = name.startswith("EyePACS val") or "baseline" in name
        change = "" if is_reference or r["sensitivity"] is None else f"{(r['sensitivity'] - baseline) * 100:+.1f} pts"
        auc = "n/a" if r["auc"] is None else f"{r['auc']:.3f}"
        lines.append(
            f"| {name} | {r['n_scans']:,} | {r['n_referable']:,} ({r['prevalence']:.0%}) | {auc} | "
            f"{pct(r['sensitivity'])} ({pct(r['sensitivity_low'])}–{pct(r['sensitivity_high'])}) | {change} | "
            f"{pct(r['specificity'])} | {pct(r['referral_rate'])} | {pct(r['confidence_estimate'])} | "
            f"{r['mean_quality']:.2f} | {r['median_width_px']:,.0f} px |")
    lines += [
        "",
        "Notes:",
        "",
        "- Quality is the 0–1 score in `scans.parquet`: 1 means as sharp, contrasty and well exposed as a typical training scan.",
        "- Camera wear rows are the worn-camera copies the `US-WEAR-01` clinic sees (`clinicdrift/data/degrade.py`): "
        "held-out EyePACS scans, blurred and darkened more each week.",
        "- The APTOS copy we use was resized to 224 × 224 px before upload, so part of its drop is resolution, which a real "
        "low-resolution camera would also cause.",
        "- No dataset has patient age, sex or ethnicity, so these are differences between sites and cameras, not patient groups.",
        "",
    ]
    REPORT_MD.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"Wrote {REPORT_JSON} and {REPORT_MD}")


if __name__ == "__main__":
    main()

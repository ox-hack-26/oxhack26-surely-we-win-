"""Check that the model's files fit the replay, then run the whole engine on them.

Uses Sarah's processed/scans.parquet, features.npy and model.json when they exist, else the stand-in.
The fingerprint identifies the replay's set of scans: it must match on every machine whose model
files are used here, or the worn-camera copies won't line up.

    python -m clinicdrift.engine.pipeline           # check, then estimate, decide, backtest, robustness (~2 min),
                                                    # results, charts, samples, web app data
    python -m clinicdrift.engine.pipeline --check   # only check, and print the fingerprint
"""
import argparse
import hashlib
import runpy

import numpy as np
import pandas as pd

from clinicdrift.config import PROCESSED_DIR, REPO
from clinicdrift.engine.estimate import load_inputs

MODEL_KEYS = ("model", "referral_threshold", "val_sensitivity", "val_specificity", "val_auc")


def fingerprint(stream: pd.DataFrame) -> str:
    """Short hash of the replay's scan IDs."""
    return hashlib.sha256("\n".join(sorted(stream["scan_id"])).encode()).hexdigest()[:12]


def check() -> bool:
    stream = pd.read_parquet(PROCESSED_DIR / "stream.parquet")
    scans, features, model, base = load_inputs()
    problems = []
    if len(features) != len(scans):
        problems.append(f"features.npy has {len(features):,} rows but scans.parquet has {len(scans):,}")
    if not scans["scan_id"].is_unique:
        problems.append("scans.parquet repeats scan IDs")
    missing = sorted(set(stream["scan_id"]) - set(scans["scan_id"]))
    if missing:
        problems.append(f"{len(missing):,} replay scans have no score (e.g. {missing[0]}): "
                        "the model's files were made from a different replay; compare fingerprints")
    if scans["p_referable"].isna().any():
        problems.append(f"{int(scans['p_referable'].isna().sum()):,} scans have no p_referable")
    for split in ("train", "val"):
        if not ((scans["source"] == "eyepacs") & (scans["split"] == split)).any():
            problems.append(f"no EyePACS {split} scans: the drift check and calibration need them")
    absent = [k for k in MODEL_KEYS if k not in model]
    if absent:
        problems.append(f"model.json lacks {', '.join(absent)}")
    if not np.isfinite(features[: min(len(features), 1000)]).all():
        problems.append("features.npy has NaN or infinite values")

    print(f"Model files: {base}")
    print(f"  {model.get('model', '?')}: val AUC {model.get('val_auc', float('nan')):.3f}, "
          f"threshold {model.get('referral_threshold', float('nan')):.4f}")
    print(f"  {len(scans):,} scored scans, {features.shape[1]}-d features")
    print(f"Replay fingerprint {fingerprint(stream)} ({len(stream):,} scans, {stream['clinic_id'].nunique()} clinics)")
    for problem in problems:
        print(f"PROBLEM: {problem}")
    print("OK: the engine can run on these files" if not problems else "Not running the engine until these are fixed")
    return not problems


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="only check the inputs")
    args = parser.parse_args()
    if not check():
        raise SystemExit(1)
    if args.check:
        return

    from clinicdrift.engine import backtest, charts, decide, estimate, results, robustness
    for step, run in (("estimate", estimate.main), ("decide", decide.run), ("backtest", backtest.main),
                      ("robustness", robustness.main), ("results", results.main), ("charts", charts.main)):
        print(f"\n== {step}", flush=True)
        run()
    print("\n== sample data", flush=True)
    runpy.run_path(str(REPO / "scripts" / "export_samples.py"), run_name="__main__")
    print("\n== web app data", flush=True)
    runpy.run_path(str(REPO / "scripts" / "export_web.py"), run_name="__main__")


if __name__ == "__main__":
    main()

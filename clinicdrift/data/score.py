"""Run every scan through the trained classifier once: p_referable, image features and model.json.

    python -m clinicdrift.data.score

The raw logits are calibrated on EyePACS val with one temperature, so p_referable is a probability
on scans like the training ones. The referral threshold is picked on val to catch 90% of referable
cases (docs/handoffs.md). Writes p_referable into processed/scans.parquet,
processed/features/<source>.npy and processed/model.json.
"""
import json
import time

import numpy as np
import pandas as pd
import torch
from scipy.optimize import minimize_scalar
from sklearn.metrics import roc_auc_score

from clinicdrift.config import PROCESSED_DIR
from clinicdrift.data.model import ARCH, MODEL_FILE, load_model, predict
from clinicdrift.data.images import CACHE_SIZE
from clinicdrift.data.prepare import SCANS
from clinicdrift.data.sources import TRAINING_SOURCE

TARGET_SENSITIVITY = 0.90
FEATURES_DIR = PROCESSED_DIR / "features"
MODEL_JSON = PROCESSED_DIR / "model.json"


def fit_temperature(logits: np.ndarray, y: np.ndarray) -> float:
    """The T for which sigmoid(logits / T) has the lowest log loss on these labels."""
    def nll(t: float) -> float:
        z = logits / t
        return float(np.mean(np.logaddexp(0, z) - y * z))
    return float(minimize_scalar(nll, bounds=(0.05, 20), method="bounded").x)


def threshold_for_sensitivity(p: np.ndarray, y: np.ndarray, target: float) -> float:
    """The highest cut-off that still refers at least `target` of the referable scans."""
    positives = np.sort(p[y])[::-1]
    return float(positives[int(np.ceil(target * len(positives))) - 1])


def rates(p: np.ndarray, y: np.ndarray, threshold: float) -> dict:
    refer = p >= threshold
    return {"auc": round(float(roc_auc_score(y, p)), 4),
            "sensitivity": round(float(refer[y].mean()), 4),
            "specificity": round(float((~refer[~y]).mean()), 4),
            "n_scans": int(len(y)), "n_referable": int(y.sum())}


def main() -> None:
    start = time.time()
    scans = pd.read_parquet(SCANS)
    checkpoint = torch.load(MODEL_FILE, map_location="cpu")
    model = load_model()
    logits, features = predict(model, len(scans), np.arange(len(scans)), features=True)
    print(f"Scored {len(scans):,} scans in {time.time() - start:.0f} s; features are {features.shape[1]}-d")

    y = scans["referable"].to_numpy(bool)
    eyepacs = (scans["source"] == TRAINING_SOURCE).to_numpy()
    val = eyepacs & (scans["split"] == "val").to_numpy()
    test = eyepacs & (scans["split"] == "test").to_numpy()
    temperature = fit_temperature(logits[val], y[val])
    p = 1 / (1 + np.exp(-logits / temperature))
    threshold = threshold_for_sensitivity(p[val], y[val], TARGET_SENSITIVITY)
    val_rates, test_rates = rates(p[val], y[val], threshold), rates(p[test], y[test], threshold)

    scans["p_referable"] = p.astype("float32")
    scans.to_parquet(SCANS, index=False)
    FEATURES_DIR.mkdir(parents=True, exist_ok=True)
    for source, rows in scans.groupby("source", sort=False).indices.items():
        assert (np.diff(rows) == 1).all(), f"{source} rows are not contiguous in scans.parquet"
        np.save(FEATURES_DIR / f"{source}.npy", features[rows])

    info = {
        "referral_threshold": round(threshold, 6),
        "val_sensitivity": val_rates["sensitivity"],
        "val_specificity": val_rates["specificity"],
        "val_auc": val_rates["auc"],
        "test_sensitivity": test_rates["sensitivity"],
        "test_specificity": test_rates["specificity"],
        "test_auc": test_rates["auc"],
        "target_sensitivity": TARGET_SENSITIVITY,
        "temperature": round(temperature, 4),
        "arch": ARCH,
        "image_size": CACHE_SIZE,
        "feature_dim": int(features.shape[1]),
        "trained_on": f"{TRAINING_SOURCE} train split",
        "n_train": checkpoint["n_train"],
        "n_val": val_rates["n_scans"],
        "n_test": test_rates["n_scans"],
        "best_epoch": checkpoint["epoch"],
        "epochs": checkpoint["epochs"],
    }
    MODEL_JSON.write_text(json.dumps(info, indent=2), encoding="utf-8")
    print(json.dumps(info, indent=2))
    print(f"Wrote p_referable to {SCANS}, features to {FEATURES_DIR}, {MODEL_JSON}")


if __name__ == "__main__":
    main()

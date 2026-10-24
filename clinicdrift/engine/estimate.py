"""Estimate each clinic's catch rate every week, from the images alone.

The catch rate (sensitivity) is the share of referable scans the AI refers. Clinics don't know it
until expert grades arrive weeks later, so we estimate it from what is available at once: the
model's scores, recalibrated on labelled EyePACS 'val' scans. If the calibrated score of every
scan is the chance it is referable, the scores alone say how many referable cases there are and
how many sit above the referral threshold.

That only holds while the clinic's scans look like the ones the scores were calibrated on, so
every week also gets a drift check: can a classifier tell this week's scans from training scans?
`drift_auc` is its cross-validated AUC (0.5 = indistinguishable, 1.0 = trivially different) and
`lookalikes` is how many labelled reference cases resemble this week's scans.

    python -m clinicdrift.engine.estimate
"""
import json

import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.preprocessing import StandardScaler

from clinicdrift.config import PROCESSED_DIR

SEED = 2026
N_COMPONENTS = 50   # image features are compressed to this many numbers for the drift check
DRIFT_SAMPLE = 500  # reference scans the drift check compares each week against
DRAWS = 400         # simulated weeks behind each uncertainty band
BAND = (0.05, 0.95)


def load_inputs():
    """Scored scans, their image features and model info: Sarah's files if present, else the stand-in."""
    base = PROCESSED_DIR if (PROCESSED_DIR / "scans.parquet").exists() else PROCESSED_DIR / "standin"
    scans = pd.read_parquet(base / "scans.parquet")
    features = np.load(base / "features.npy").astype(np.float32)
    model = json.loads((base / "model.json").read_text(encoding="utf-8"))
    return scans, features, model, base


class Reference:
    """What 'normal' looks like: EyePACS train scans for the feature space, val scans for labels."""

    def __init__(self, scans: pd.DataFrame, features: np.ndarray, rng: np.random.Generator):
        train = (scans["split"] == "train").to_numpy()
        val = (scans["split"] == "val").to_numpy()
        self.scaler = StandardScaler().fit(features[train])
        self.pca = PCA(N_COMPONENTS, whiten=True, random_state=SEED).fit(self.scaler.transform(features[train]))
        self.val_z = self.project(features[val])
        self.val_y = scans.loc[val, "referable"].to_numpy()
        self.drift_z = self.val_z[rng.choice(len(self.val_z), DRIFT_SAMPLE, replace=False)]
        # Isotonic recalibration: turns a raw score into the share of val scans with that score that were referable.
        self.calibrator = IsotonicRegression(y_min=1e-4, y_max=1 - 1e-4, out_of_bounds="clip")
        self.calibrator.fit(scans.loc[val, "p_referable"], self.val_y)

    def project(self, x: np.ndarray) -> np.ndarray:
        return self.pca.transform(self.scaler.transform(x))

    def calibrate(self, p: np.ndarray) -> np.ndarray:
        return self.calibrator.predict(p)

    def drift(self, z_week: np.ndarray) -> tuple[float, float]:
        """(drift_auc, lookalikes) for one week's scans."""
        x = np.vstack([self.drift_z, z_week])
        d = np.r_[np.zeros(len(self.drift_z)), np.ones(len(z_week))]
        clf = LogisticRegression(C=0.1, class_weight="balanced", max_iter=2000)
        folds = StratifiedKFold(5, shuffle=True, random_state=SEED)
        auc = roc_auc_score(d, cross_val_predict(clf, x, d, cv=folds, method="decision_function"))
        # Importance weights on the labelled reference cases: how much each one resembles this week's scans.
        clf.fit(np.vstack([self.val_z, z_week]), np.r_[np.zeros(len(self.val_z)), np.ones(len(z_week))])
        w = np.exp(np.clip(clf.decision_function(self.val_z[self.val_y]), -30, 30))
        return float(auc), float(w.sum() ** 2 / (w ** 2).sum())


def catch_rate_estimate(q: np.ndarray, refer: np.ndarray, rng: np.random.Generator) -> dict:
    """Point estimate and band for the catch rate, from calibrated scores q and referral decisions.

    The band covers the catch rate the expert grades will actually show, so it includes both
    which scans turned up and which of them really were referable.
    """
    point = q[refer].sum() / q.sum()
    draws = []
    for _ in range(DRAWS):
        idx = rng.integers(0, len(q), len(q))
        y = rng.random(len(q)) < q[idx]
        if y.any():
            draws.append((y & refer[idx]).sum() / y.sum())
    low, high = np.quantile(draws, BAND)
    return {
        "est_sensitivity": float(point),
        "est_low": float(low),
        "est_high": float(high),
        "expected_cases": float(q.sum()),
        "expected_missed": float(q[~refer].sum()),
        "expected_false_referrals": float((1 - q[refer]).sum()),
    }


def weekly_estimates(stream: pd.DataFrame, scans: pd.DataFrame, features: np.ndarray, model: dict) -> pd.DataFrame:
    threshold = model["referral_threshold"]
    rng = np.random.default_rng(SEED)
    ref = Reference(scans, features, rng)
    row_of = pd.Series(np.arange(len(scans)), index=scans["scan_id"])
    seen = stream.merge(scans[["scan_id", "p_referable", "referable", "quality"]], on="scan_id", validate="one_to_one")
    seen["row"] = row_of.loc[seen["scan_id"]].to_numpy()

    rows = []
    for (clinic, week), g in seen.groupby(["clinic_id", "week"], sort=True):
        p = g["p_referable"].to_numpy()
        y = g["referable"].to_numpy()
        refer = p >= threshold
        drift_auc, lookalikes = ref.drift(ref.project(features[g["row"].to_numpy()]))
        rows.append({
            "clinic_id": clinic,
            "week": week,
            "week_start": g["week_start"].iloc[0],
            "n_scans": len(g),
            **catch_rate_estimate(ref.calibrate(p), refer, rng),
            "drift_auc": drift_auc,
            "lookalikes": lookalikes,
            "quality_mean": float(g["quality"].mean()),
            "referral_rate": float(refer.mean()),
            # Hindsight, from every expert grade: for the backtest and the dashboard's "real" line only.
            "true_cases": int(y.sum()),
            "true_sensitivity": (refer & y).sum() / y.sum() if y.any() else np.nan,
            "true_missed": int((~refer & y).sum()),
            "true_false_referrals": int((refer & ~y).sum()),
        })
    return pd.DataFrame(rows)


def main() -> None:
    scans, features, model, base = load_inputs()
    stream = pd.read_parquet(PROCESSED_DIR / "stream.parquet")
    weekly = weekly_estimates(stream, scans, features, model)
    weekly.to_parquet(PROCESSED_DIR / "weekly_estimates.parquet", index=False)
    print(f"Inputs from {base}; threshold {model['referral_threshold']:.3f}; "
          f"wrote {len(weekly)} clinic-weeks to {PROCESSED_DIR / 'weekly_estimates.parquet'}")


if __name__ == "__main__":
    main()

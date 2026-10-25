"""Copy small, shareable versions of the engine's outputs into sample-data/.

For teammates without the 9.5 GB of scans: Sneha's dashboard and Tiger tables, Vansh's add-ons.
Re-run after the engine changes (for example when Sarah's model replaces the stand-in):

    python scripts/export_samples.py
"""
import json
import shutil
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from clinicdrift.config import PROCESSED_DIR, REPO  # noqa: E402
from clinicdrift.data.degrade import degraded_id  # noqa: E402
from clinicdrift.data.sources import load_image  # noqa: E402
from clinicdrift.engine.estimate import load_inputs  # noqa: E402

OUT = REPO / "sample-data"
IMAGE_SIZE = 512
SCAN_COLUMNS = ["scan_id", "source", "split", "grade", "referable", "wear", "p_referable", "quality",
                "brightness", "contrast", "sharpness", "width", "height"]
WEAR_STRIP_SCAN = "eyepacs-15898"


def save_scan(scan_id: str, folder: Path) -> None:
    img = load_image(scan_id)
    img.thumbnail((IMAGE_SIZE, IMAGE_SIZE))
    img.save(folder / f"{scan_id}.jpg", quality=85)


def main() -> None:
    OUT.mkdir(exist_ok=True)
    stream = pd.read_parquet(PROCESSED_DIR / "stream.parquet")
    stream.to_csv(OUT / "stream.csv", index=False)
    scans, _, model, _ = load_inputs()
    seen = scans[scans["scan_id"].isin(stream["scan_id"])]
    # Scores at full precision: the referral cut-off sits exactly on one validation score, and a
    # float32 written at its short repr reads back a hair below it, flipping that scan's referral.
    scans_out = seen[[c for c in SCAN_COLUMNS if c in seen]].copy()
    scans_out["p_referable"] = scans_out["p_referable"].astype("float64")
    scans_out.to_csv(OUT / "scans.csv", index=False, float_format="%.17g")
    pd.read_parquet(PROCESSED_DIR / "weekly.parquet").to_csv(OUT / "weekly.csv", index=False)
    pd.read_parquet(PROCESSED_DIR / "backtest.parquet").to_csv(OUT / "backtest.csv", index=False)
    pd.read_parquet(PROCESSED_DIR / "backtest_sweep.parquet").to_csv(OUT / "backtest_sweep.csv", index=False)
    for name in ("clinics.json", "decision_settings.json", "backtest_summary.json"):
        shutil.copy(PROCESSED_DIR / name, OUT / name)
    if (PROCESSED_DIR / "robustness_summary.json").exists():  # ranges across redraws of the grades
        shutil.copy(PROCESSED_DIR / "robustness_summary.json", OUT / "robustness_summary.json")
        pd.read_parquet(PROCESSED_DIR / "robustness_sweep.parquet").to_csv(OUT / "robustness_sweep.csv", index=False)
    (OUT / "model.json").write_text(json.dumps(model, indent=2), encoding="utf-8")

    alarms_out = OUT / "alarms"
    shutil.rmtree(alarms_out, ignore_errors=True)
    shutil.copytree(PROCESSED_DIR / "alarms", alarms_out)

    # The scans each alarm points Gemini at, plus one scan at five wear levels for slides.
    images = OUT / "images"
    shutil.rmtree(images, ignore_errors=True)
    images.mkdir()
    wanted = set()
    for path in sorted(alarms_out.glob("*.json")):
        alarm = json.loads(path.read_text(encoding="utf-8"))
        wanted |= set(alarm["flagged_scan_ids"]) | set(alarm["reference_scan_ids"])
    for level in (0.25, 0.5, 0.75, 1.0):
        wanted.add(degraded_id(WEAR_STRIP_SCAN, level))
    wanted.add(WEAR_STRIP_SCAN)
    for scan_id in sorted(wanted):
        save_scan(scan_id, images)

    total = sum(f.stat().st_size for f in OUT.rglob("*") if f.is_file())
    print(f"Wrote {len(list(OUT.rglob('*')))} files, {total / 1e6:.1f} MB, to {OUT} ({len(wanted)} images)")


if __name__ == "__main__":
    main()

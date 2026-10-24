"""Decode every scan once: cache a retina crop for the model and measure image quality.

    python -m clinicdrift.data.prepare

Writes cache/crops_448.u8, a uint8 memmap of shape (n_scans, 448, 448, 3) in scan-list order, and
processed/scans.parquet with the quality columns. p_referable stays empty until
`python -m clinicdrift.data.score` fills it. Run after all four downloads have finished.
"""
import os
import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from clinicdrift.config import DATA_DIR, PROCESSED_DIR
from clinicdrift.data.images import CACHE_SIZE, prepare, quality_score
from clinicdrift.data.sources import TRAINING_SOURCE, load_scans

CACHE = DATA_DIR / "cache" / f"crops_{CACHE_SIZE}.u8"
SCANS = PROCESSED_DIR / "scans.parquet"
STAT_COLUMNS = ["width", "height", "brightness", "contrast", "sharpness"]
# docs/handoffs.md column order; image_name, file and row_in_file from load_scans() follow
SCAN_COLUMNS = ["scan_id", "source", "split", "grade", "referable", "p_referable", "quality",
                "brightness", "contrast", "sharpness", "width", "height"]


def open_cache(n_scans: int, mode: str = "r") -> np.memmap:
    return np.memmap(CACHE, dtype=np.uint8, mode=mode, shape=(n_scans, CACHE_SIZE, CACHE_SIZE, 3))


def _row_group(path: str, group: int, first_index: int, n_scans: int) -> list[dict]:
    """Prepare one parquet row group's scans; first_index is the first one's row in the scan list."""
    cache = open_cache(n_scans, "r+")
    images = pq.ParquetFile(path).read_row_group(group, columns=["image"]).column("image")
    rows = []
    for offset, cell in enumerate(images):
        crop, stats = prepare(cell["bytes"].as_py())
        cache[first_index + offset] = crop
        rows.append({"index": first_index + offset, **stats})
    cache.flush()
    return rows


def _tasks(scans: pd.DataFrame) -> list[tuple]:
    """(file, row group, first scan-list index, n_scans) for every row group of every file."""
    tasks = []
    for path, rows in scans.groupby("file", sort=False):
        first = rows.index[0]
        assert (rows["row_in_file"].to_numpy() == np.arange(len(rows))).all(), f"{path} rows out of order"
        meta = pq.ParquetFile(path).metadata
        for group in range(meta.num_row_groups):
            tasks.append((path, group, first, len(scans)))
            first += meta.row_group(group).num_rows
        assert first == rows.index[-1] + 1, f"{path}: row groups don't add up to its rows in the scan list"
    return tasks


def main() -> None:
    scans = load_scans(refresh=True)  # re-read the raw files in case a download finished since the last run
    print(f"{len(scans):,} scans: " + ", ".join(f"{s} {n:,}" for s, n in scans["source"].value_counts().items()))
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    open_cache(len(scans), "w+").flush()  # allocate the file; workers fill their own rows

    tasks = _tasks(scans)
    start, stats = time.time(), []
    with ProcessPoolExecutor(max_workers=max(1, (os.cpu_count() or 2) - 2)) as pool:
        for i, rows in enumerate(pool.map(_row_group, *zip(*tasks)), 1):
            stats += rows
            if i % 50 == 0 or i == len(tasks):
                print(f"  {i}/{len(tasks)} row groups, {len(stats):,} scans, {time.time() - start:.0f} s", flush=True)

    stats = pd.DataFrame(stats).set_index("index").sort_index()
    assert len(stats) == len(scans) and (stats.index == scans.index).all(), "some scans were not prepared"
    scans = scans.join(stats[STAT_COLUMNS])
    reference = scans[(scans["source"] == TRAINING_SOURCE) & (scans["split"] == "train")]
    scans["quality"] = quality_score(scans, reference)
    scans["p_referable"] = np.float32(np.nan)
    if SCANS.exists():  # keep the classifier's scores from an earlier run
        old = pd.read_parquet(SCANS, columns=["scan_id", "p_referable"]).set_index("scan_id")["p_referable"]
        scans["p_referable"] = scans["scan_id"].map(old).astype("float32")
    for column in ["brightness", "contrast", "sharpness"]:
        scans[column] = scans[column].astype("float32")
    scans = scans[SCAN_COLUMNS + [c for c in scans.columns if c not in SCAN_COLUMNS]]
    scans.to_parquet(SCANS, index=False)
    print(f"Wrote {SCANS} and {CACHE} in {time.time() - start:.0f} s")
    print(scans.groupby("source")[["quality", "brightness", "contrast", "sharpness", "width"]].median().round(3))


if __name__ == "__main__":
    main()

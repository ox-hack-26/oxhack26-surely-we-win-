"""Decode every scan once: cache a retina crop for the model and measure image quality.

    python -m clinicdrift.engine.replay   # first, so the worn-camera copies it uses get prepared too
    python -m clinicdrift.data.prepare

Prepares every scan in the scan list, plus each worn-camera copy ('<scan_id>@<level>') that
processed/stream.parquet uses. Writes cache/crops_448.u8, a uint8 memmap of shape
(n_rows, 448, 448, 3), and cache/crops_448.parquet, one row per crop in the same order with the
scan-list columns, `wear` and the quality columns. Nothing goes in processed/ yet: the engine
switches from the stand-in to processed/scans.parquet as soon as it exists, so only
`python -m clinicdrift.data.score` writes it, complete. Run after all four downloads have finished.
"""
import os
import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from clinicdrift.config import DATA_DIR, PROCESSED_DIR
from clinicdrift.data.degrade import split_id
from clinicdrift.data.images import CACHE_SIZE, prepare, quality_score
from clinicdrift.data.sources import TRAINING_SOURCE, load_scans

CACHE = DATA_DIR / "cache" / f"crops_{CACHE_SIZE}.u8"
PREPARED = CACHE.with_suffix(".parquet")  # one row per crop in CACHE, same order
STREAM = PROCESSED_DIR / "stream.parquet"  # written by clinicdrift.engine.replay
STAT_COLUMNS = ["width", "height", "brightness", "contrast", "sharpness"]


def open_cache(n_rows: int, mode: str = "r") -> np.memmap:
    shape = (n_rows, CACHE_SIZE, CACHE_SIZE, 3)
    if mode != "w+" and CACHE.stat().st_size != np.prod(shape):
        raise SystemExit(f"{CACHE} does not hold {n_rows:,} crops; run python -m clinicdrift.data.prepare again")
    return np.memmap(CACHE, dtype=np.uint8, mode=mode, shape=shape)


def worn_copies(scans: pd.DataFrame) -> pd.DataFrame:
    """Rows for the worn-camera copies the replay uses: the original's columns, a new scan_id and its wear."""
    if not STREAM.exists():
        print(f"No {STREAM}: preparing no worn-camera copies. Run python -m clinicdrift.engine.replay first.")
        return scans.iloc[:0]
    ids = sorted(i for i in pd.read_parquet(STREAM, columns=["scan_id"])["scan_id"].unique() if "@" in i)
    base, wear = zip(*map(split_id, ids)) if ids else ((), ())
    worn = scans.set_index("scan_id").loc[list(base)].reset_index()
    worn["scan_id"], worn["wear"] = ids, wear
    return worn


def _row_group(path: str, group: int, offsets: list[int], rows: list[int], wears: list[float],
               n_rows: int) -> list[dict]:
    """Prepare the crops that come from one parquet row group; offsets are positions in that group."""
    cache = open_cache(n_rows, "r+")
    images = pq.ParquetFile(path).read_row_group(group, columns=["image"]).column("image")
    out = []
    for offset, row, wear in zip(offsets, rows, wears):
        crop, stats = prepare(images[offset]["bytes"].as_py(), wear)
        cache[row] = crop
        out.append({"row": row, **stats})
    cache.flush()
    return out


def _tasks(prepared: pd.DataFrame) -> list[tuple]:
    """One task per parquet row group, listing which crops (and wear levels) to make from it."""
    tasks = []
    for path, rows in prepared.groupby("file", sort=False):
        meta = pq.ParquetFile(path).metadata
        starts = np.cumsum([0] + [meta.row_group(g).num_rows for g in range(meta.num_row_groups)])
        assert rows["row_in_file"].max() < starts[-1], f"{path} has fewer rows than the scan list says"
        groups = np.searchsorted(starts, rows["row_in_file"].to_numpy(), side="right") - 1
        for group, part in rows.groupby(groups):
            tasks.append((path, int(group), (part["row_in_file"] - starts[group]).tolist(), part.index.tolist(),
                          part["wear"].tolist(), len(prepared)))
    return tasks


def main() -> None:
    start = time.time()
    scans = load_scans(refresh=True).copy()  # re-read the raw files in case a download finished since the last run
    scans["wear"] = 0.0
    worn = worn_copies(scans)
    prepared = pd.concat([scans, worn], ignore_index=True)
    print(f"{len(scans):,} scans (" + ", ".join(f"{s} {n:,}" for s, n in scans["source"].value_counts().items())
          + f") and {len(worn):,} worn-camera copies")
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    PREPARED.unlink(missing_ok=True)  # an old index must never sit next to a half-rewritten cache
    open_cache(len(prepared), "w+").flush()  # allocate the file; workers fill their own rows

    tasks, stats = _tasks(prepared), []
    with ProcessPoolExecutor(max_workers=max(1, (os.cpu_count() or 2) - 2)) as pool:
        for i, rows in enumerate(pool.map(_row_group, *zip(*tasks)), 1):
            stats += rows
            if i % 50 == 0 or i == len(tasks):
                print(f"  {i}/{len(tasks)} row groups, {len(stats):,} crops, {time.time() - start:.0f} s", flush=True)

    stats = pd.DataFrame(stats).set_index("row").sort_index()
    assert (stats.index == prepared.index).all(), "some scans were not prepared"
    prepared = prepared.join(stats[STAT_COLUMNS])
    for column in ["brightness", "contrast", "sharpness"]:
        prepared[column] = prepared[column].astype("float32")
    reference = prepared[(prepared["source"] == TRAINING_SOURCE) & (prepared["split"] == "train")
                         & (prepared["wear"] == 0)]
    prepared["quality"] = quality_score(prepared, reference)
    prepared.to_parquet(PREPARED, index=False)
    print(f"Wrote {CACHE} and {PREPARED} in {time.time() - start:.0f} s")
    summary = prepared.groupby([prepared["source"], prepared["wear"] > 0])[
        ["quality", "brightness", "contrast", "sharpness", "width"]].median()
    print(summary.rename_axis(["source", "worn"]).round(3))


if __name__ == "__main__":
    main()

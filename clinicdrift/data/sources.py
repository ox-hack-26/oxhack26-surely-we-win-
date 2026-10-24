"""The four eye-scan datasets and the shared scan list.

Every part of ClinicDrift names scans by the scan_id built here, so build it here and nowhere else.
"""
import hashlib
import io
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from clinicdrift.config import PROCESSED_DIR, RAW_DIR

SCAN_LIST = PROCESSED_DIR / "scan_list.parquet"  # cache: reading labels from the raw files takes ~20 s


@dataclass(frozen=True)
class Source:
    name: str          # used in scan_id
    site: str          # the name people know it by
    country: str
    grade_column: str  # integer grade 0-4 in the raw parquet


SOURCES = {
    "eyepacs": Source("eyepacs", "EyePACS", "United States", "label_code"),
    "aptos": Source("aptos", "APTOS 2019", "India", "label_code"),
    "messidor2": Source("messidor2", "Messidor-2", "France", "label"),
    "idrid": Source("idrid", "IDRiD", "India", "label"),
}
TRAINING_SOURCE = "eyepacs"
REFERABLE_GRADE = 2  # moderate retinopathy or worse must be referred

# EyePACS has a left and a right eye per patient, so split by patient, never by image.
# A stable hash keeps every teammate's split identical.
SPLIT_SHARES = (("train", 70), ("val", 10), ("test", 20))


def source_files(name: str) -> list[Path]:
    files = sorted((RAW_DIR / name).rglob("*.parquet"))
    if not files:
        raise FileNotFoundError(f"No parquet files for {name} in {RAW_DIR / name}; run scripts/download_data.py")
    return files


def patient_split(image_name: str) -> str:
    """train/val/test for an EyePACS image such as '10_left.jpeg', by its patient number."""
    patient = image_name.split("_")[0]
    bucket = int(hashlib.md5(patient.encode()).hexdigest(), 16) % 100
    for split, share in SPLIT_SHARES:
        if bucket < share:
            return split
        bucket -= share
    raise AssertionError("SPLIT_SHARES must add up to 100")


@cache
def load_scans(refresh: bool = False) -> pd.DataFrame:
    """One row per scan across all sources, without decoding any images.

    Columns: scan_id, source, split, grade, referable, image_name, file, row_in_file.
    scan_id is '<source>-<row>' with rows counted across the source's files in sorted order.
    Cached in processed/scan_list.parquet; pass refresh=True after re-downloading.
    """
    if SCAN_LIST.exists() and not refresh:
        return pd.read_parquet(SCAN_LIST)
    frames = []
    for src in SOURCES.values():
        parts = []
        for path in source_files(src.name):
            table = pq.read_table(path, columns=[src.grade_column, "image.path"])
            part = pd.DataFrame({
                "grade": table.column(src.grade_column).to_numpy().astype("int8"),
                "image_name": table.column("path").to_pylist(),
                "file": str(path),
            })
            part["row_in_file"] = range(len(part))
            parts.append(part)
        df = pd.concat(parts, ignore_index=True)
        df.insert(0, "scan_id", [f"{src.name}-{i:05d}" for i in range(len(df))])
        df.insert(1, "source", src.name)
        df.insert(2, "split", df["image_name"].map(patient_split) if src.name == TRAINING_SOURCE else "deploy")
        frames.append(df)
    scans = pd.concat(frames, ignore_index=True)
    scans.insert(4, "referable", scans["grade"] >= REFERABLE_GRADE)
    SCAN_LIST.parent.mkdir(parents=True, exist_ok=True)
    scans.to_parquet(SCAN_LIST, index=False)
    return scans


def load_image(scan_id: str):
    """The scan as an RGB PIL image, worn-camera copies ('<scan_id>@<level>') included.

    Reads only the row group that holds it.
    """
    from PIL import Image

    from clinicdrift.data.degrade import degrade, split_id

    base_id, level = split_id(scan_id)
    scans = load_scans().set_index("scan_id")
    row = scans.loc[base_id]
    pf = pq.ParquetFile(row["file"])
    offset = int(row["row_in_file"])
    for group in range(pf.num_row_groups):
        n = pf.metadata.row_group(group).num_rows
        if offset < n:
            cell = pf.read_row_group(group, columns=["image"]).column("image")[offset].as_py()
            return degrade(Image.open(io.BytesIO(cell["bytes"])).convert("RGB"), level)
        offset -= n
    raise IndexError(f"{scan_id}: row {row['row_in_file']} is past the end of {row['file']}")

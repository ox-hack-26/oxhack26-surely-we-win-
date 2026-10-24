"""Replay the scans as if they arrived at screening clinics week by week.

Writes processed/stream.parquet (one row per scan a clinic saw) and processed/clinics.json.
Every scan is used at most once. A clinic draws from one source, switches source at a given
week to mimic a new camera arriving, or keeps its camera while it slowly wears out (scans get
blurrier and darker, see clinicdrift/data/degrade.py). Only a sample of scans gets an expert
grade, weeks later: that delay is the gap ClinicDrift fills.

    python -m clinicdrift.engine.replay
"""
import json
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from clinicdrift.config import PROCESSED_DIR
from clinicdrift.data.degrade import degraded_id
from clinicdrift.data.sources import TRAINING_SOURCE, load_scans

SEED = 2026
N_WEEKS = 20
FIRST_MONDAY = pd.Timestamp("2026-01-05")
GRADED_SHARE = 0.10          # share of scans an expert grader checks
GRADE_DELAY_DAYS = (35, 49)  # their grade comes back 5 to 7 weeks later


@dataclass(frozen=True)
class Clinic:
    clinic_id: str
    site: str
    country: str
    note: str
    segments: tuple[tuple[str, int], ...]  # (source, first week it supplies scans)
    scans_per_week: int = 50
    wear_from_week: int | None = None      # camera wear starts here and reaches full strength in the last week

    def wear(self, week: int) -> float:
        """Camera wear level 0-1 in a given week."""
        if self.wear_from_week is None or week < self.wear_from_week:
            return 0.0
        return (week - self.wear_from_week + 1) / (N_WEEKS - self.wear_from_week + 1)


CLINICS = (
    Clinic("US-EYE-01", "EyePACS", "United States", "Same kind of scans as training: the alarm should stay quiet",
           (("eyepacs", 1),)),
    Clinic("US-EYE-02", "EyePACS", "United States", "Same kind of scans as training: the alarm should stay quiet",
           (("eyepacs", 1),)),
    Clinic("SW-MES-01", "EyePACS, then Messidor-2", "Simulated", "New camera at week 9: EyePACS scans, then Messidor-2",
           (("eyepacs", 1), ("messidor2", 9))),
    Clinic("SW-APT-01", "EyePACS, then APTOS 2019", "Simulated", "New camera at week 11: EyePACS scans, then APTOS 2019",
           (("eyepacs", 1), ("aptos", 11))),
    Clinic("FR-MES-01", "Messidor-2", "France", "Different camera and patients from day one",
           (("messidor2", 1),)),
    Clinic("IN-APT-01", "APTOS 2019", "India", "Different camera and patients from day one",
           (("aptos", 1),)),
    Clinic("IN-APT-02", "APTOS 2019", "India", "Different camera and patients from day one",
           (("aptos", 1),)),
    Clinic("IN-IDR-01", "IDRiD", "India", "Small clinic: fewer scans a week, so wider uncertainty",
           (("idrid", 1),), scans_per_week=25),
    # Last, so adding it left the other clinics' scans unchanged.
    Clinic("US-WEAR-01", "EyePACS, wearing camera", "United States",
           "Same camera throughout, but from week 7 its scans get blurrier and darker every week",
           (("eyepacs", 1),), wear_from_week=7),
)


def segment_weeks(clinic: Clinic) -> list[tuple[str, list[int]]]:
    """Each (source, weeks it covers) for a clinic, weeks numbered from 1."""
    starts = [first for _, first in clinic.segments] + [N_WEEKS + 1]
    return [(src, list(range(starts[i], starts[i + 1]))) for i, (src, _) in enumerate(clinic.segments)]


def build_stream(scans: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    # Held-out EyePACS scans stand in for "same as training"; the other sources are deploy-only.
    usable = scans[(scans["split"] == "test") | (scans["source"] != TRAINING_SOURCE)]
    pools = {src: list(rng.permutation(group["scan_id"].to_numpy())) for src, group in usable.groupby("source")}

    rows = []
    for clinic in CLINICS:
        for src, weeks in segment_weeks(clinic):
            need = clinic.scans_per_week * len(weeks)
            if need > len(pools[src]):
                raise ValueError(f"{clinic.clinic_id} needs {need} {src} scans but only {len(pools[src])} are left")
            drawn, pools[src] = pools[src][:need], pools[src][need:]
            for i, week in enumerate(np.repeat(weeks, clinic.scans_per_week)):
                wear = clinic.wear(int(week))
                scan_id = degraded_id(drawn[i], wear) if wear > 0 else drawn[i]
                rows.append((scan_id, clinic.clinic_id, src, int(week), wear))
    stream = pd.DataFrame(rows, columns=["scan_id", "clinic_id", "source", "week", "wear"])

    # Scans happen on weekdays, 08:00 to 18:00.
    stream["week_start"] = FIRST_MONDAY + pd.to_timedelta((stream["week"] - 1) * 7, unit="D")
    day = rng.integers(0, 5, len(stream))
    second = rng.integers(8 * 3600, 18 * 3600, len(stream))
    stream["ts"] = stream["week_start"] + pd.to_timedelta(day, unit="D") + pd.to_timedelta(second, unit="s")

    graded = rng.random(len(stream)) < GRADED_SHARE
    delay = pd.to_timedelta(rng.integers(GRADE_DELAY_DAYS[0], GRADE_DELAY_DAYS[1] + 1, len(stream)), unit="D")
    stream["graded_at"] = (stream["ts"] + delay).where(graded)

    stream["week_start"] = stream["week_start"].dt.date
    return stream.sort_values(["clinic_id", "ts"], ignore_index=True)


def clinic_records() -> list[dict]:
    records = []
    for clinic in CLINICS:
        record = asdict(clinic)
        record["segments"] = [{"source": src, "first_week": first} for src, first in clinic.segments]
        record["switch_week"] = clinic.segments[1][1] if len(clinic.segments) > 1 else None
        records.append(record)
    return records


def main() -> None:
    stream = build_stream(load_scans(), np.random.default_rng(SEED))
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    stream.to_parquet(PROCESSED_DIR / "stream.parquet", index=False)
    (PROCESSED_DIR / "clinics.json").write_text(json.dumps(clinic_records(), indent=2), encoding="utf-8")
    print(f"Wrote {len(stream):,} scans for {stream['clinic_id'].nunique()} clinics over {N_WEEKS} weeks to {PROCESSED_DIR}")


if __name__ == "__main__":
    main()

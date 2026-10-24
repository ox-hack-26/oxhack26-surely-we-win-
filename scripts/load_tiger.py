"""Load the clinics' scans and the engine's weekly results into Tiger Data, then check them.

    python scripts/load_tiger.py                       # from sample-data/, what the dashboard shows
    python scripts/load_tiger.py --data "%CLINICDRIFT_DATA%/processed"   # straight from the engine
    python scripts/load_tiger.py --check               # only connect and count rows

Needs TIMESCALE_SERVICE_URL (or TIGER_DATABASE_URL) in .env: the service URL from Tiger Cloud,
postgres://USER:PASSWORD@HOST:PORT/tsdb?sslmode=require. Never commit it.

Creates the clinicdrift_demo schema (dashboard/sql/tiger_prize.sql), replaces its rows with the
data folder's, refreshes the clinic-week continuous aggregate, checks it against the files row by
row, then turns on compression for the scan hypertable and reports the real sizes.
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from clinicdrift.config import REPO  # noqa: E402  (also loads .env)

SCHEMA_SQL = REPO / "dashboard" / "sql" / "tiger_prize.sql"
URL_VARS = ("TIMESCALE_SERVICE_URL", "TIGER_DATABASE_URL", "DATABASE_URL")
S = "clinicdrift_demo"
SCAN_COLUMNS = ["ts", "scan_id", "clinic_id", "source", "week", "wear", "model_update", "p_referable",
                "referred", "quality", "grade", "graded_at"]


def connect():
    import psycopg

    url = next((os.environ[v] for v in URL_VARS if os.environ.get(v)), None)
    if not url:
        raise SystemExit(f"Set one of {', '.join(URL_VARS)} in .env to the Tiger Cloud service URL")
    try:
        conn = psycopg.connect(url, connect_timeout=15, autocommit=True)
    except psycopg.OperationalError as err:  # the message can include the host but never the password
        raise SystemExit(f"Could not connect to Tiger: {str(err).splitlines()[0]}") from None
    conn.execute("SET TIME ZONE 'UTC'")  # the replay's times are UTC
    return conn


def read(folder: Path, name: str) -> pd.DataFrame:
    for path in (folder / f"{name}.parquet", folder / f"{name}.csv"):
        if path.exists():
            return pd.read_parquet(path) if path.suffix == ".parquet" else pd.read_csv(path)
    raise SystemExit(f"No {name}.parquet or {name}.csv in {folder}")


def scan_events(folder: Path, weekly: pd.DataFrame) -> pd.DataFrame:
    """stream joined to scans: one row per scan a clinic took, as scan_events stores it."""
    stream = read(folder, "stream")
    scans = read(folder, "scans")[["scan_id", "p_referable", "quality", "grade"]]
    events = stream.merge(scans, on="scan_id", how="left", validate="many_to_one")
    if events["p_referable"].isna().any():
        raise SystemExit(f"{int(events['p_referable'].isna().sum()):,} scans in the stream have no score in scans")
    # The cut-off each clinic used that week (raised at US-UPD-01 after its faulty update).
    cut = weekly.set_index(["clinic_id", "week"])["referral_threshold"]
    events["referred"] = events["p_referable"].to_numpy() >= cut.loc[list(zip(events["clinic_id"], events["week"]))].to_numpy()
    for column in ("ts", "graded_at"):
        events[column] = pd.to_datetime(events[column])
    events["model_update"] = events.get("model_update", False)
    events["model_update"] = events["model_update"].astype(str).str.lower().eq("true")
    events["grade"] = events["grade"].where(events["graded_at"].notna()).astype("Int64")  # only scans an expert checked
    return events[SCAN_COLUMNS]


def pg_type(series: pd.Series) -> str:
    if pd.api.types.is_bool_dtype(series):
        return "BOOLEAN"
    if pd.api.types.is_integer_dtype(series):
        return "BIGINT"
    if pd.api.types.is_float_dtype(series):
        return "DOUBLE PRECISION"
    if pd.api.types.is_datetime64_any_dtype(series):
        return "TIMESTAMPTZ"
    return "TEXT"


def tidy_weekly(weekly: pd.DataFrame) -> pd.DataFrame:
    weekly = weekly.copy()
    weekly["week_start"] = pd.to_datetime(weekly["week_start"]).dt.date
    for column in weekly.columns:  # CSV booleans arrive as text
        if weekly[column].dtype == object and set(weekly[column].dropna().astype(str).str.lower()) <= {"true", "false"} \
                and weekly[column].notna().any():
            weekly[column] = weekly[column].astype(str).str.lower().eq("true")
    return weekly


def copy_rows(cur, table: str, frame: pd.DataFrame) -> None:
    columns = ", ".join(f'"{c}"' for c in frame.columns)
    with cur.copy(f"COPY {table} ({columns}) FROM STDIN") as copy:
        for row in frame.itertuples(index=False, name=None):
            copy.write_row([None if (v is None or (not isinstance(v, (str, bool)) and pd.isna(v)))
                            else v.item() if hasattr(v, "item") else v for v in row])


def load(conn, folder: Path) -> dict:
    weekly = tidy_weekly(read(folder, "weekly"))
    events = scan_events(folder, weekly)
    alarms = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((folder / "alarms").glob("*.json"))] \
        if (folder / "alarms").exists() else []

    with conn.cursor() as cur:
        cur.execute(SCHEMA_SQL.read_text(encoding="utf-8"))
        cur.execute(f"DROP TABLE IF EXISTS {S}.weekly_results")  # follows the engine's columns, so rebuilt each load
        cur.execute(f"CREATE TABLE {S}.weekly_results ("
                    + ", ".join(f'"{c}" {"DATE" if c == "week_start" else pg_type(weekly[c])}' for c in weekly.columns)
                    + ", PRIMARY KEY (clinic_id, week))")
        with conn.transaction():
            cur.execute(f"TRUNCATE {S}.scan_events, {S}.alarms")
            copy_rows(cur, f"{S}.scan_events", events)
            copy_rows(cur, f"{S}.weekly_results", weekly)
            for a in alarms:
                cur.execute(f"INSERT INTO {S}.alarms VALUES (%s, %s, %s, %s)",
                            (a["clinic_id"], int(a["week"]), a["week_start"], json.dumps(a)))
        cur.execute(f"CALL refresh_continuous_aggregate('{S}.clinic_week', NULL, NULL)")
    print(f"Loaded {len(events):,} scan events, {len(weekly):,} clinic-weeks and {len(alarms)} alarms from {folder}")
    return {"events": events, "weekly": weekly}


def verify(conn, events: pd.DataFrame) -> None:
    """The continuous aggregate must match the same totals worked out from the files."""
    with conn.cursor() as cur:
        cur.execute(f"SELECT clinic_id, week_start, n_scans, mean_referral_score, referral_rate, mean_quality "
                    f"FROM {S}.clinic_week ORDER BY clinic_id, week_start")
        got = pd.DataFrame(cur.fetchall(), columns=[d.name for d in cur.description])
    events = events.assign(week_start=pd.Timestamp("2026-01-05", tz="UTC")
                           + pd.to_timedelta((events["week"] - 1) * 7, unit="D"))
    want = events.groupby(["clinic_id", "week_start"]).agg(
        n_scans=("scan_id", "size"), mean_referral_score=("p_referable", "mean"),
        referral_rate=("referred", "mean"), mean_quality=("quality", "mean")).reset_index()
    got["week_start"] = pd.to_datetime(got["week_start"], utc=True)
    both = want.merge(got, on=["clinic_id", "week_start"], how="outer", suffixes=("", "_db"), indicator=True)
    problems = []
    if (both["_merge"] != "both").any():
        problems.append(f"{int((both['_merge'] != 'both').sum())} clinic-weeks are in only one of files and Tiger")
    if (both["n_scans"] != both["n_scans_db"]).any():
        problems.append("scan counts differ")
    for column in ("mean_referral_score", "referral_rate", "mean_quality"):
        if ((both[column] - both[f"{column}_db"].astype(float)).abs() > 1e-6).any():
            problems.append(f"{column} differs")
    if problems:
        raise SystemExit("Tiger does not match the files: " + "; ".join(problems))
    print(f"Checked: clinic_week matches the files for all {len(both)} clinic-weeks "
          f"({int(both['n_scans'].sum()):,} scans)")


def compress(conn) -> None:
    """Turn on Tiger's columnstore (compression) for scan_events and report the real before/after sizes."""
    with conn.cursor() as cur:
        cur.execute("SELECT extversion FROM pg_extension WHERE extname = 'timescaledb'")
        version = tuple(int(x) for x in cur.fetchone()[0].split(".")[:2])
        table = f"{S}.scan_events"
        cur.execute(f"SELECT pg_size_pretty(hypertable_size('{table}')), hypertable_size('{table}')")
        before_pretty, before = cur.fetchone()
        if version >= (2, 18):
            cur.execute(f"ALTER TABLE {table} SET (timescaledb.enable_columnstore = true, "
                        "timescaledb.segmentby = 'clinic_id', timescaledb.orderby = 'ts DESC')")
            cur.execute(f"SELECT show_chunks('{table}')")
            for (chunk,) in cur.fetchall():
                cur.execute(f"CALL convert_to_columnstore('{chunk}', if_not_columnstore => true)")
        else:
            cur.execute(f"ALTER TABLE {table} SET (timescaledb.compress, "
                        "timescaledb.compress_segmentby = 'clinic_id', timescaledb.compress_orderby = 'ts DESC')")
            cur.execute(f"SELECT compress_chunk(c, if_not_compressed => true) FROM show_chunks('{table}') c")
        cur.execute(f"SELECT pg_size_pretty(hypertable_size('{table}')), hypertable_size('{table}')")
        after_pretty, after = cur.fetchone()
        cur.execute(f"SELECT count(*) FILTER (WHERE is_compressed), count(*) FROM timescaledb_information.chunks "
                    f"WHERE hypertable_schema = '{S}' AND hypertable_name = 'scan_events'")
        done, chunks = cur.fetchone()
    print(f"Compression (TimescaleDB {'.'.join(map(str, version))}): {done}/{chunks} weekly chunks compressed, "
          f"scan_events {before_pretty} -> {after_pretty} ({before / max(after, 1):.1f}x smaller)")


def show(conn) -> None:
    """A query the dashboard or judges can run: the worn camera, week by week, straight from Tiger."""
    with conn.cursor() as cur:
        cur.execute(f"SELECT to_char(week_start, 'YYYY-MM-DD'), n_scans, round(mean_wear::numeric, 2), "
                    f"round(mean_quality::numeric, 2), round(referral_rate::numeric, 2) FROM {S}.clinic_week "
                    f"WHERE clinic_id = 'US-WEAR-01' ORDER BY week_start")
        rows = cur.fetchall()
    if rows:
        print("US-WEAR-01 from clinic_week (week, scans, wear, quality, referral rate):")
        for row in rows:
            print("  " + "  ".join(str(v) for v in row))


def check(conn) -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT extversion FROM pg_extension WHERE extname = 'timescaledb'")
        version = cur.fetchone()
        print(f"Connected; TimescaleDB {version[0] if version else 'NOT INSTALLED'}")
        for table in ("scan_events", "weekly_results", "alarms", "clinic_week"):
            cur.execute("SELECT to_regclass(%s)", (f"{S}.{table}",))
            if cur.fetchone()[0]:
                cur.execute(f"SELECT count(*) FROM {S}.{table}")
                print(f"  {S}.{table}: {cur.fetchone()[0]:,} rows")
            else:
                print(f"  {S}.{table}: not created yet")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data", type=Path, default=REPO / "sample-data",
                        help="folder with stream, scans and weekly (.parquet or .csv) and alarms/ (default sample-data/)")
    parser.add_argument("--check", action="store_true", help="only connect and count rows")
    parser.add_argument("--no-compress", action="store_true", help="leave scan_events uncompressed")
    args = parser.parse_args()
    start = time.time()
    with connect() as conn:
        if args.check:
            check(conn)
            return
        loaded = load(conn, args.data)
        verify(conn, loaded["events"])
        if not args.no_compress:
            compress(conn)
        show(conn)
        check(conn)
    print(f"Done in {time.time() - start:.0f} s")


if __name__ == "__main__":
    main()

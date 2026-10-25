"""Store the replay's scan events and the engine's monitoring results in Tiger Data, and query them.

    python -m clinicdrift.db.tiger migrate                  # create or update the tables (safe to repeat)
    python -m clinicdrift.db.tiger ingest                   # processed/ if it exists, else sample-data/
    python -m clinicdrift.db.tiger ingest --data sample-data
    python -m clinicdrift.db.tiger check                    # counts, latest ingest, compression
    python -m clinicdrift.db.tiger demo-event --clinic US-WEAR-01 --week 9   # one live demo scan
    python -m clinicdrift.db.tiger clear-demo
    python -m clinicdrift.db.tiger compress                 # columnstore on, with real before/after sizes

The connection string comes from TIGER_DATABASE_URL (or TIMESCALE_SERVICE_URL / DATABASE_URL) in the
environment or the repo's .env. It is never printed. TIGER_SCHEMA picks another schema (tests use it).

Ingesting the same folder twice changes nothing: rows are upserted on each table's primary key, and
rows of the same model that the folder no longer contains (an older replay) are removed.
"""
import argparse
import hashlib
import json
import os
import re
import time
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from clinicdrift.config import PROCESSED_DIR, REPO

MIGRATIONS_DIR = REPO / "db" / "migrations"
URL_VARS = ("TIGER_DATABASE_URL", "TIMESCALE_SERVICE_URL", "DATABASE_URL")
DEFAULT_SCHEMA = "clinicdrift_demo"  # the name written in the migration files
SIMULATED, DEMO = "simulated_replay", "demo_live"
FIRST_MONDAY = pd.Timestamp("2026-01-05", tz="UTC")  # replay week 1, as in clinicdrift.engine.replay

EVENT_COLUMNS = ["ts", "scan_id", "model_version", "clinic_id", "source", "week", "wear", "model_update",
                 "p_referable", "referral_threshold", "referred", "quality", "grade", "graded_at", "data_origin",
                 "run_id"]
WEEKLY_KEYS = ["week_start", "clinic_id", "model_version"]
WEEKLY_COLUMNS = [  # typed columns of weekly_monitoring, as in docs/handoffs.md section 3
    "week", "n_scans", "est_sensitivity", "est_low", "est_high", "expected_cases", "expected_missed",
    "expected_false_referrals", "drift_auc", "lookalikes", "quality_mean", "referral_rate", "referral_threshold",
    "true_cases", "true_sensitivity", "true_missed", "true_false_referrals", "trust", "graded_cases", "graded_caught",
    "catch_rate", "catch_low", "catch_high", "belief_cases", "belief_missed", "expected_harm", "p_below_standard",
    "alarm_this_week", "alarm_reason", "alarm"]
WEEKLY_INTS = {"week", "n_scans", "true_cases", "true_missed", "true_false_referrals", "graded_cases", "graded_caught"}
WEEKLY_BOOLS = {"alarm_this_week", "alarm"}


class TigerError(RuntimeError):
    """A database problem, worded without the connection string."""


# --- connection and schema -------------------------------------------------------------------------

def schema() -> str:
    name = os.environ.get("TIGER_SCHEMA", DEFAULT_SCHEMA)
    if not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", name):
        raise TigerError(f"TIGER_SCHEMA must be a plain lower-case identifier, not {name!r}")
    return name


def database_url() -> str:
    url = next((os.environ[v] for v in URL_VARS if os.environ.get(v, "").strip()), "").strip()
    if not url:
        raise TigerError("TIGER_DATABASE_URL is not set: put the Tiger Cloud service URL in the repo's .env "
                         "(see docs/tiger.md)")
    return url


def _redact(text: str, url: str) -> str:
    """text with the URL and its password replaced by ***."""
    secrets = [url]
    match = re.search(r"//[^:/@]*:([^@]+)@", url)
    if match:
        secrets.append(match.group(1))
    try:
        from psycopg.conninfo import conninfo_to_dict
        secrets.append(conninfo_to_dict(url).get("password") or "")
    except Exception:
        pass
    for secret in sorted({s for s in secrets if s}, key=len, reverse=True):
        text = text.replace(secret, "***")
    return text


def connect():
    """An autocommit connection. Times are sent with their UTC offset, so the session time zone doesn't
    matter; nothing is SET on the session, so it is also safe through Tiger's transaction pooler."""
    import psycopg

    url = database_url()
    try:
        return psycopg.connect(url, connect_timeout=15, autocommit=True, prepare_threshold=None,
                               application_name="clinicdrift")
    except psycopg.ProgrammingError:  # the URL didn't parse; libpq would quote it, password and all
        raise TigerError("TIGER_DATABASE_URL could not be parsed: it should look like "
                         "postgres://tsdbadmin:PASSWORD@HOST:PORT/tsdb?sslmode=require") from None
    except psycopg.Error as err:
        raise TigerError("could not connect to Tiger Data: "
                         + _redact(str(err).strip().splitlines()[0], url)) from None


def _sql(path: Path) -> str:
    """A migration file, with its schema name swapped for TIGER_SCHEMA."""
    return re.sub(rf"\b{DEFAULT_SCHEMA}\b", schema(), path.read_text(encoding="utf-8"))


def timescaledb_version(conn) -> tuple[int, ...] | None:
    row = conn.execute("SELECT extversion FROM pg_extension WHERE extname = 'timescaledb'").fetchone()
    return tuple(int(x) for x in re.findall(r"\d+", row[0])[:3]) if row else None


def migrate(conn) -> list[str]:
    """Apply the migrations in db/migrations/ that haven't been applied yet, each in one transaction."""
    version = timescaledb_version(conn)
    if version is None:
        try:
            conn.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")
        except Exception as err:
            raise TigerError(f"the timescaledb extension is not available here: {err}") from None
        version = timescaledb_version(conn)
    if version < (2, 13):
        raise TigerError(f"needs TimescaleDB 2.13 or newer (by_range hypertables); this is {version}")
    s = schema()
    conn.execute(f"CREATE SCHEMA IF NOT EXISTS {s}")
    conn.execute(f"CREATE TABLE IF NOT EXISTS {s}.schema_migrations "
                 "(version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())")
    done = {r[0] for r in conn.execute(f"SELECT version FROM {s}.schema_migrations")}
    applied = []
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        if path.stem in done:
            continue
        with conn.transaction():
            conn.execute(_sql(path))
            conn.execute(f"INSERT INTO {s}.schema_migrations (version) VALUES (%s)", (path.stem,))
        applied.append(path.stem)
    return applied


# --- reading the engine's files -----------------------------------------------------------------------

def _read(folder: Path, name: str) -> pd.DataFrame:
    for path in (folder / f"{name}.parquet", folder / f"{name}.csv"):
        if path.exists():
            return pd.read_parquet(path) if path.suffix == ".parquet" else pd.read_csv(path)
    raise TigerError(f"no {name}.parquet or {name}.csv in {folder}")


def _json(folder: Path, name: str):
    path = folder / name
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _bool(series: pd.Series) -> pd.Series:
    """CSV booleans arrive as text."""
    return series.astype(str).str.strip().str.lower().isin(["true", "1"])


def model_version_of(model: dict) -> str:
    """A short, stable name for a model: its architecture (or description) plus a hash of model.json."""
    name = str(model.get("arch") or model.get("model") or "model")
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40]
    digest = hashlib.sha256(json.dumps(model, sort_keys=True, default=str).encode()).hexdigest()[:8]
    return f"{slug}-{digest}"


def fingerprint(scan_ids) -> str:
    """Same as clinicdrift.engine.pipeline.fingerprint: identifies the replay's set of scans."""
    return hashlib.sha256("\n".join(sorted(scan_ids)).encode()).hexdigest()[:12]


def read_folder(folder: Path) -> dict:
    """Everything one ingest needs from an engine output folder (processed/ or sample-data/).

    The model's files (model.json, scans) come from the folder itself, or from its standin/ subfolder
    when the engine ran on the stand-in model, as clinicdrift.engine.estimate.load_inputs reads them.
    """
    folder = Path(folder)
    has_model = lambda f: (f / "model.json").exists() and any((f / n).exists() for n in ("scans.parquet", "scans.csv"))  # noqa: E731
    model_dir = folder if has_model(folder) else folder / "standin" if has_model(folder / "standin") else folder
    model = _json(model_dir, "model.json")
    if not model:
        raise TigerError(f"no model.json in {folder} or {folder / 'standin'}")
    clinics = _json(folder, "clinics.json") or []
    alarms = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((folder / "alarms").glob("*.json"))] \
        if (folder / "alarms").is_dir() else []
    return {"folder": folder, "model": model, "clinics": clinics, "alarms": alarms,
            "settings": _json(folder, "decision_settings.json"),
            "stream": _read(folder, "stream"), "scans": _read(model_dir, "scans"), "weekly": _read(folder, "weekly")}


def build_weekly(data: dict, model_version: str) -> pd.DataFrame:
    weekly = data["weekly"].copy()
    weekly["week_start"] = pd.to_datetime(weekly["week_start"], utc=True)
    weekly["model_version"] = model_version
    for column in WEEKLY_BOOLS & set(weekly.columns):
        weekly[column] = _bool(weekly[column])
    for column in WEEKLY_INTS & set(weekly.columns):
        weekly[column] = pd.to_numeric(weekly[column], errors="coerce").round().astype("Int64")
    if "alarm_reason" in weekly:
        weekly["alarm_reason"] = weekly["alarm_reason"].where(weekly["alarm_reason"].notna(), None)
    known = set(WEEKLY_KEYS) | set(WEEKLY_COLUMNS)
    extra_cols = [c for c in weekly.columns if c not in known]
    weekly["extra"] = [json.dumps({c: (None if pd.isna(v) else v.item() if hasattr(v, "item") else v)
                                   for c, v in zip(extra_cols, row)}) for row in weekly[extra_cols].itertuples(index=False)] \
        if extra_cols else "{}"
    for column in WEEKLY_COLUMNS:
        if column not in weekly:
            weekly[column] = None
    return weekly[WEEKLY_KEYS + WEEKLY_COLUMNS + ["extra"]]


def build_events(data: dict, model_version: str, weekly: pd.DataFrame | None = None) -> pd.DataFrame:
    """One row per scan a clinic took: the replay's event, joined to the model's output for that scan."""
    stream = data["stream"].copy()
    scans = data["scans"][["scan_id", "p_referable", "quality", "grade"]]
    events = stream.merge(scans, on="scan_id", how="left", validate="many_to_one")
    if events["p_referable"].isna().any():
        missing = events.loc[events["p_referable"].isna(), "scan_id"]
        raise TigerError(f"{len(missing):,} replay scans have no model score (e.g. {missing.iloc[0]}): "
                         "the folder's scans and stream come from different runs")
    # The cut-off each clinic used that week; US-UPD-01's faulty update raises it.
    threshold = float(data["model"]["referral_threshold"])
    if weekly is not None and "referral_threshold" in weekly and weekly["referral_threshold"].notna().all():
        cut = weekly.set_index(["clinic_id", "week"])["referral_threshold"]
        events["referral_threshold"] = cut.reindex(list(zip(events["clinic_id"], events["week"]))).to_numpy()
        events["referral_threshold"] = events["referral_threshold"].fillna(threshold)
    else:
        events["referral_threshold"] = threshold
    events["referred"] = events["p_referable"] >= events["referral_threshold"]
    events["ts"] = pd.to_datetime(events["ts"], utc=True)
    events["graded_at"] = pd.to_datetime(events["graded_at"], utc=True)
    events["model_update"] = _bool(events["model_update"]) if "model_update" in events else False
    events["wear"] = events["wear"].astype(float) if "wear" in events else 0.0
    events["grade"] = pd.to_numeric(events["grade"]).where(events["graded_at"].notna()).round().astype("Int64")
    events["model_version"], events["data_origin"], events["run_id"] = model_version, SIMULATED, None
    return events[EVENT_COLUMNS]


# --- writing ------------------------------------------------------------------------------------------

def _value(v):
    if v is None or v is pd.NA or v is pd.NaT:
        return None
    if isinstance(v, (str, bool)):
        return v
    if isinstance(v, float) and np.isnan(v):
        return None
    if isinstance(v, pd.Timestamp):
        return v.to_pydatetime()
    return v.item() if hasattr(v, "item") else v


def _stage(cur, table: str, frame: pd.DataFrame) -> str:
    """COPY a frame into a temporary copy of `table` (dropped at commit); returns the temp table's name."""
    stage = f"stage_{table}"
    cur.execute(f"CREATE TEMP TABLE {stage} (LIKE {schema()}.{table} INCLUDING DEFAULTS) ON COMMIT DROP")
    columns = ", ".join(frame.columns)
    with cur.copy(f"COPY {stage} ({columns}) FROM STDIN") as copy:
        for row in frame.itertuples(index=False, name=None):
            copy.write_row([_value(v) for v in row])
    return stage


def _upsert(cur, table: str, stage: str, columns: list[str], keys: list[str]) -> tuple[int, int]:
    """Insert the staged rows, updating rows whose key already exists. Returns (inserted, updated)."""
    s = schema()
    updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in columns if c not in keys) + ", ingested_at = now()"
    rows = cur.execute(
        f"INSERT INTO {s}.{table} ({', '.join(columns)}) SELECT {', '.join(columns)} FROM {stage} "
        f"ON CONFLICT ({', '.join(keys)}) DO UPDATE SET {updates} RETURNING (xmax = 0)").fetchall()
    inserted = sum(1 for (new,) in rows if new)
    return inserted, len(rows) - inserted


def ingest(conn, folder: Path) -> dict:
    """Write one engine output folder to Tiger in a single transaction, then refresh the aggregate."""
    started = time.time()
    data = read_folder(folder)
    model = data["model"]
    version = model_version_of(model)
    weekly = build_weekly(data, version)
    events = build_events(data, version, data["weekly"])
    replay = fingerprint(data["stream"]["scan_id"])
    s = schema()
    with conn.transaction(), conn.cursor() as cur:
        cur.execute(
            f"INSERT INTO {s}.model_versions (model_version, description, referral_threshold, val_auc, "
            "val_sensitivity, val_specificity, details) VALUES (%s, %s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (model_version) DO UPDATE SET details = EXCLUDED.details",
            (version, str(model.get("model", version)), float(model["referral_threshold"]), model.get("val_auc"),
             model.get("val_sensitivity"), model.get("val_specificity"), json.dumps(model)))
        for c in data["clinics"]:
            cur.execute(
                f"INSERT INTO {s}.clinics (clinic_id, site, country, note, scans_per_week, switch_week, "
                "wear_from_week, update_from_week, details) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (clinic_id) DO UPDATE SET site = EXCLUDED.site, country = EXCLUDED.country, "
                "note = EXCLUDED.note, scans_per_week = EXCLUDED.scans_per_week, switch_week = EXCLUDED.switch_week, "
                "wear_from_week = EXCLUDED.wear_from_week, update_from_week = EXCLUDED.update_from_week, "
                "details = EXCLUDED.details, updated_at = now()",
                (c["clinic_id"], c.get("site", ""), c.get("country", ""), c.get("note"), c.get("scans_per_week"),
                 c.get("switch_week"), c.get("wear_from_week"), c.get("update_from_week"), json.dumps(c)))
        run_id = cur.execute(
            f"INSERT INTO {s}.ingest_runs (model_version, replay_fingerprint, source, data_origin, n_scan_events, "
            "n_clinic_weeks, n_alarms, decision_settings) VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING run_id",
            (version, replay, Path(folder).name, SIMULATED, len(events), len(weekly), len(data["alarms"]),
             json.dumps(data["settings"]) if data["settings"] else None)).fetchone()[0]
        events["run_id"] = run_id
        weekly["run_id"], weekly["data_origin"] = run_id, SIMULATED

        stage = _stage(cur, "scan_events", events)
        ev_new, ev_updated = _upsert(cur, "scan_events", stage, EVENT_COLUMNS, ["scan_id", "model_version", "ts"])
        ev_removed = cur.execute(  # rows of this model from an older replay that this folder no longer has
            f"DELETE FROM {s}.scan_events e WHERE e.model_version = %s AND e.data_origin = %s "
            f"AND NOT EXISTS (SELECT 1 FROM {stage} x WHERE x.scan_id = e.scan_id AND x.ts = e.ts)",
            (version, SIMULATED)).rowcount

        columns = WEEKLY_KEYS + WEEKLY_COLUMNS + ["extra", "data_origin", "run_id"]
        stage = _stage(cur, "weekly_monitoring", weekly[columns])
        wk_new, wk_updated = _upsert(cur, "weekly_monitoring", stage, columns, WEEKLY_KEYS)
        wk_removed = cur.execute(
            f"DELETE FROM {s}.weekly_monitoring w WHERE w.model_version = %s AND NOT EXISTS "
            f"(SELECT 1 FROM {stage} x WHERE x.clinic_id = w.clinic_id AND x.week_start = w.week_start)",
            (version,)).rowcount

        cur.execute(f"DELETE FROM {s}.alarms WHERE model_version = %s", (version,))
        for a in data["alarms"]:
            cur.execute(f"INSERT INTO {s}.alarms (clinic_id, model_version, week, week_start, reason, payload, run_id) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                        (a["clinic_id"], version, int(a["week"]), a["week_start"], a.get("alarm_reason"),
                         json.dumps(a), run_id))
    if ev_removed:  # removed rows may lie outside the new span: rematerialise everything
        refresh(conn)
    else:
        refresh(conn, events["ts"].min(), events["ts"].max())
    return {"run_id": run_id, "model_version": version, "replay_fingerprint": replay, "source": str(folder),
            "scan_events": {"inserted": ev_new, "updated": ev_updated, "removed": ev_removed},
            "weekly": {"inserted": wk_new, "updated": wk_updated, "removed": wk_removed},
            "alarms": len(data["alarms"]), "seconds": round(time.time() - started, 1)}


def refresh(conn, start=None, end=None) -> None:
    """Materialise the daily aggregate for [start, end] (whole history if None). Can't run in a transaction."""
    if start is not None:
        start, end = pd.Timestamp(start).floor("D").to_pydatetime(), (pd.Timestamp(end).floor("D") + timedelta(days=1)).to_pydatetime()
    conn.execute(f"CALL refresh_continuous_aggregate('{schema()}.scan_stats_daily', %s::timestamptz, %s::timestamptz)",
                 (start, end))


def latest_model_version(conn) -> str:
    row = conn.execute(f"SELECT model_version FROM {schema()}.ingest_runs ORDER BY run_id DESC LIMIT 1").fetchone()
    if not row:
        raise TigerError("Tiger has no ingested data yet: run python -m clinicdrift.db.tiger ingest")
    return row[0]


def demo_event(conn, clinic_id: str, week: int, model_version: str | None = None) -> dict:
    """Add one live demo scan to a clinic-week: a copy of one of its scans' model output, marked demo_live."""
    s = schema()
    version = model_version or latest_model_version(conn)
    start = FIRST_MONDAY + pd.Timedelta(weeks=week - 1)
    row = conn.execute(
        f"SELECT ts, scan_id, source, wear, model_update, p_referable, referral_threshold, referred, quality "
        f"FROM {s}.scan_events WHERE clinic_id = %s AND model_version = %s AND ts >= %s AND ts < %s "
        "ORDER BY ts DESC LIMIT 1", (clinic_id, version, start.to_pydatetime(), (start + pd.Timedelta(weeks=1)).to_pydatetime())).fetchone()
    if not row:
        raise TigerError(f"no {clinic_id} scans in week {week} for model {version}")
    ts = row[0] + timedelta(minutes=1)
    n = conn.execute(f"SELECT count(*) FROM {s}.scan_events WHERE data_origin = %s", (DEMO,)).fetchone()[0]
    scan_id = f"demo-{clinic_id}-w{week:02d}-{n + 1:03d}"
    conn.execute(
        f"INSERT INTO {s}.scan_events (ts, scan_id, model_version, clinic_id, source, week, wear, model_update, "
        "p_referable, referral_threshold, referred, quality, data_origin) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (ts, scan_id, version, clinic_id, row[2], week, row[3], row[4], row[5], row[6], row[7], row[8], DEMO))
    refresh(conn, ts, ts)
    return {"scan_id": scan_id, "ts": ts.isoformat(), "clinic_id": clinic_id, "week": week, "model_version": version}


def clear_demo(conn) -> int:
    s = schema()
    span = conn.execute(f"SELECT min(ts), max(ts) FROM {s}.scan_events WHERE data_origin = %s", (DEMO,)).fetchone()
    removed = conn.execute(f"DELETE FROM {s}.scan_events WHERE data_origin = %s", (DEMO,)).rowcount
    if removed:
        refresh(conn, span[0], span[1])
    return removed


def compress(conn) -> dict:
    """Turn on the columnstore for scan_events, convert every chunk now, and measure the real sizes."""
    s, table = schema(), f"{schema()}.scan_events"
    version = timescaledb_version(conn)
    before = conn.execute("SELECT hypertable_size(%s::regclass)", (table,)).fetchone()[0]
    if version >= (2, 18):
        conn.execute(f"ALTER TABLE {table} SET (timescaledb.enable_columnstore = true, "
                     "timescaledb.segmentby = 'clinic_id, model_version', timescaledb.orderby = 'ts DESC')")
        for (chunk,) in conn.execute("SELECT show_chunks(%s::regclass)", (table,)).fetchall():
            conn.execute("CALL convert_to_columnstore(%s::regclass, if_not_columnstore => true)", (chunk,))
    else:
        conn.execute(f"ALTER TABLE {table} SET (timescaledb.compress, "
                     "timescaledb.compress_segmentby = 'clinic_id, model_version', timescaledb.compress_orderby = 'ts DESC')")
        conn.execute("SELECT compress_chunk(c, if_not_compressed => true) FROM show_chunks(%s::regclass) c", (table,))
    after = conn.execute("SELECT hypertable_size(%s::regclass)", (table,)).fetchone()[0]
    done, total = conn.execute(
        "SELECT count(*) FILTER (WHERE is_compressed), count(*) FROM timescaledb_information.chunks "
        "WHERE hypertable_schema = %s AND hypertable_name = 'scan_events'", (s,)).fetchone()
    return {"timescaledb": ".".join(map(str, version)), "chunks_compressed": done, "chunks": total,
            "bytes_before": before, "bytes_after": after, "ratio": round(before / max(after, 1), 1)}


# --- reading back (the dashboard has its own copy in dashboard/ui/tiger.py) -----------------------------

def scan_series(conn, clinic_id: str, model_version: str, start, end, bucket: str = "7 days") -> pd.DataFrame:
    """Scans and mean model score per time bucket for one clinic, rolled up from the daily aggregate."""
    rows = conn.execute(
        f"SELECT time_bucket(%s::interval, bucket) AS period, sum(n_scans)::int AS n_scans, "
        "sum(sum_p_referable) / sum(n_scans) AS mean_p_referable, sum(n_referred)::float / sum(n_scans) AS referral_rate, "
        "sum(sum_quality) / nullif(sum(n_quality), 0) AS mean_quality, sum(n_demo_live)::int AS n_demo_live "
        f"FROM {schema()}.scan_stats_daily WHERE clinic_id = %s AND model_version = %s AND bucket >= %s AND bucket < %s "
        "GROUP BY 1 ORDER BY 1",
        (bucket, clinic_id, model_version, pd.Timestamp(start).to_pydatetime(), pd.Timestamp(end).to_pydatetime())).fetchall()
    return pd.DataFrame(rows, columns=["period", "n_scans", "mean_p_referable", "referral_rate", "mean_quality",
                                       "n_demo_live"])


def check(conn) -> dict:
    s = schema()
    out = {"timescaledb": ".".join(map(str, timescaledb_version(conn) or ())) or None}
    if not conn.execute("SELECT to_regclass(%s)", (f"{s}.schema_migrations",)).fetchone()[0]:
        return {**out, "migrated": False}
    out["migrations"] = [r[0] for r in conn.execute(f"SELECT version FROM {s}.schema_migrations ORDER BY 1")]
    for table in ("scan_events", "weekly_monitoring", "alarms", "clinics", "model_versions", "ingest_runs", "scan_stats_daily"):
        out[table] = conn.execute(f"SELECT count(*) FROM {s}.{table}").fetchone()[0]
    out["demo_live_events"] = conn.execute(f"SELECT count(*) FROM {s}.scan_events WHERE data_origin = %s", (DEMO,)).fetchone()[0]
    run = conn.execute(f"SELECT run_id, ingested_at, model_version, replay_fingerprint, source FROM {s}.ingest_runs "
                       "ORDER BY run_id DESC LIMIT 1").fetchone()
    out["latest_ingest"] = dict(zip(["run_id", "ingested_at", "model_version", "replay_fingerprint", "source"],
                                    [str(v) for v in run])) if run else None
    out["chunks"] = dict(zip(["compressed", "total"], conn.execute(
        "SELECT count(*) FILTER (WHERE is_compressed), count(*) FROM timescaledb_information.chunks "
        "WHERE hypertable_schema = %s AND hypertable_name = 'scan_events'", (s,)).fetchone()))
    return out


def default_folder() -> Path:
    return PROCESSED_DIR if (PROCESSED_DIR / "weekly.parquet").exists() else REPO / "sample-data"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("migrate", help="create or update the tables")
    p = sub.add_parser("ingest", help="migrate, then write an engine output folder")
    p.add_argument("--data", type=Path, default=None, help="processed/ (default when present) or sample-data/")
    sub.add_parser("check", help="row counts, latest ingest, compression")
    p = sub.add_parser("demo-event", help="add one live demo scan")
    p.add_argument("--clinic", default="US-WEAR-01")
    p.add_argument("--week", type=int, default=9)
    sub.add_parser("clear-demo", help="remove the live demo scans")
    sub.add_parser("compress", help="turn on the columnstore and report sizes")
    args = parser.parse_args()
    try:
        with connect() as conn:
            if args.command == "migrate":
                applied = migrate(conn)
                print(f"Migrations applied: {', '.join(applied) or 'none (already up to date)'}")
            elif args.command == "ingest":
                migrate(conn)
                print(json.dumps(ingest(conn, args.data or default_folder()), indent=2))
            elif args.command == "check":
                print(json.dumps(check(conn), indent=2, default=str))
            elif args.command == "demo-event":
                print(json.dumps(demo_event(conn, args.clinic, args.week), indent=2))
            elif args.command == "clear-demo":
                print(f"Removed {clear_demo(conn)} demo events")
            elif args.command == "compress":
                print(json.dumps(compress(conn), indent=2))
    except TigerError as err:
        raise SystemExit(f"Tiger Data: {err}") from None


if __name__ == "__main__":
    main()

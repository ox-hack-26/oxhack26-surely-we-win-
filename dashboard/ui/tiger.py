"""Read ClinicDrift's monitoring data from Tiger Data for the dashboard. Read-only.

The tables come from db/migrations/ and are filled by `python -m clinicdrift.db.tiger ingest`
(see docs/tiger.md). The connection string is TIGER_DATABASE_URL (or TIMESCALE_SERVICE_URL /
DATABASE_URL), from the environment, dashboard/.env or the repo's .env. It is never shown.
"""
import json
import os
import re
from pathlib import Path

import pandas as pd

URL_VARS = ("TIGER_DATABASE_URL", "TIMESCALE_SERVICE_URL", "DATABASE_URL")
REPO = Path(__file__).resolve().parents[2]
GRADE_WINDOW = 8  # weeks; as clinicdrift.engine.decide counts the expert grades that have arrived


class TigerError(RuntimeError):
    """A database problem, worded without the connection string."""


def schema() -> str:
    name = os.environ.get("TIGER_SCHEMA", "clinicdrift_demo")
    if not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", name):
        raise TigerError("TIGER_SCHEMA must be a plain lower-case identifier")
    return name


def connect():
    """A read-only connection in UTC."""
    try:
        from dotenv import load_dotenv
        load_dotenv(REPO / ".env", override=False)  # the repo's .env, where load_tiger keeps the URL
    except ImportError:
        pass
    url = next((os.environ[v] for v in URL_VARS if os.environ.get(v, "").strip()), "").strip()
    if not url:
        raise TigerError("CLINICDRIFT_DATA_MODE=tiger but TIGER_DATABASE_URL is not set (see docs/tiger.md)")
    import psycopg
    try:
        conn = psycopg.connect(url, connect_timeout=10, autocommit=True, application_name="clinicdrift-dashboard")
    except psycopg.Error as err:
        raise TigerError(f"could not connect to Tiger Data ({type(err).__name__}); check the service is running") from None
    conn.execute("SET TIME ZONE 'UTC'")
    conn.execute("SET default_transaction_read_only = on")
    return conn


def _frame(conn, query: str, params=()) -> pd.DataFrame:
    import psycopg
    try:
        cur = conn.execute(query, params)
        return pd.DataFrame(cur.fetchall(), columns=[d.name for d in cur.description])
    except psycopg.errors.UndefinedTable:
        raise TigerError("the ClinicDrift tables don't exist yet: run python -m clinicdrift.db.tiger ingest") from None
    except psycopg.Error as err:
        raise TigerError(f"query failed ({type(err).__name__}: {str(err).strip().splitlines()[0]})") from None


def latest_run(conn) -> dict:
    runs = _frame(conn, f"SELECT run_id, ingested_at, model_version, replay_fingerprint, source, n_scan_events, "
                        f"decision_settings FROM {schema()}.ingest_runs ORDER BY run_id DESC LIMIT 1")
    if runs.empty:
        raise TigerError("Tiger has no ingested data yet: run python -m clinicdrift.db.tiger ingest")
    return runs.iloc[0].to_dict()


def load_handoff():
    """weekly, clinics, settings and run info for the latest ingested model, shaped like the sample-data files."""
    with connect() as conn:
        run = latest_run(conn)
        version = run["model_version"]
        weekly = _frame(conn, f"SELECT * FROM {schema()}.weekly_monitoring WHERE model_version = %s "
                              "ORDER BY clinic_id, week", (version,))
        clinics = _frame(conn, f"SELECT details FROM {schema()}.clinics ORDER BY clinic_id")["details"].tolist()
        demo = _frame(conn, f"SELECT count(*) AS n FROM {schema()}.scan_events WHERE data_origin = 'demo_live'")
    if weekly.empty:
        raise TigerError(f"no weekly results stored for model {version}")
    extra = pd.json_normalize(weekly.pop("extra").tolist()) if "extra" in weekly else pd.DataFrame()
    if not extra.empty:
        weekly = pd.concat([weekly, extra.drop(columns=[c for c in extra.columns if c in weekly])], axis=1)
    weekly["week_start"] = pd.to_datetime(weekly["week_start"]).dt.tz_localize(None)
    settings = run["decision_settings"]
    if isinstance(settings, str):
        settings = json.loads(settings)
    info = {**{k: run[k] for k in ("run_id", "ingested_at", "model_version", "replay_fingerprint", "source")},
            "demo_live_events": int(demo["n"].iloc[0])}
    return weekly, clinics, settings, info


def alarm(clinic_id: str, week: int, model_version: str):
    with connect() as conn:
        rows = _frame(conn, f"SELECT payload FROM {schema()}.alarms WHERE clinic_id = %s AND week = %s "
                            "AND model_version = %s", (clinic_id, int(week), model_version))
    return None if rows.empty else rows["payload"].iloc[0]


def scan_series(clinic_id: str, model_version: str, start, end, bucket: str = "7 days") -> pd.DataFrame:
    """Scans, mean model score, referral rate and quality per time bucket for one clinic, in [start, end),
    rolled up from the scan_stats_daily continuous aggregate (real-time, so new events count at once)."""
    if bucket not in ("1 day", "7 days"):
        raise TigerError("bucket must be '1 day' or '7 days'")
    with connect() as conn:
        return _frame(conn,
            f"SELECT time_bucket(%s::interval, bucket) AS period, sum(n_scans)::int AS n_scans, "
            "sum(sum_p_referable) / sum(n_scans) AS mean_p_referable, "
            "sum(n_referred)::float / sum(n_scans) AS referral_rate, "
            "sum(sum_quality) / nullif(sum(n_quality), 0) AS mean_quality, sum(n_demo_live)::int AS n_demo_live "
            f"FROM {schema()}.scan_stats_daily WHERE clinic_id = %s AND model_version = %s "
            "AND bucket >= %s AND bucket < %s GROUP BY 1 ORDER BY 1",
            (bucket, clinic_id, model_version, pd.Timestamp(start, tz="UTC").to_pydatetime(),
             pd.Timestamp(end, tz="UTC").to_pydatetime()))


def expert_evidence(clinic_id: str, model_version: str, week: int, week_start) -> dict:
    """Expert grades that had arrived by the end of a replay week (scans from its last GRADE_WINDOW weeks),
    straight from the scan_events hypertable. Ground truth exists only for these graded scans."""
    end = pd.Timestamp(week_start, tz="UTC") + pd.Timedelta(days=7)
    with connect() as conn:
        row = _frame(conn,
            "SELECT count(*) FILTER (WHERE grade IS NOT NULL) AS grades_arrived, "
            "count(*) FILTER (WHERE grade >= 2) AS referable, "
            "count(*) FILTER (WHERE grade >= 2 AND referred) AS caught "
            f"FROM {schema()}.scan_events WHERE clinic_id = %s AND model_version = %s "
            "AND data_origin = 'simulated_replay' AND graded_at < %s AND week > %s",
            (clinic_id, model_version, end.to_pydatetime(), int(week) - GRADE_WINDOW)).iloc[0]
    out = {k: int(row[k]) for k in ("grades_arrived", "referable", "caught")}
    out["catch_rate"] = out["caught"] / out["referable"] if out["referable"] else None
    return out

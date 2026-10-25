"""Tests for the Tiger Data integration (clinicdrift/db/tiger.py, dashboard/ui/tiger.py).

The offline tests need nothing but sample-data/. The live tests run only when TIGER_TEST_DATABASE_URL
points at a TimescaleDB (a Tiger Cloud service or a local container); they work in their own schema,
clinicdrift_test, and drop it afterwards, so they never touch the demo data.

    python -m pytest -q tests/test_tiger.py
    TIGER_TEST_DATABASE_URL=postgres://... python -m pytest -q tests/test_tiger.py
"""
import json
import os
import re
import shutil
import sys
from pathlib import Path

import pandas as pd
import pytest

from clinicdrift.db import tiger

REPO = Path(__file__).resolve().parents[1]
SAMPLE = REPO / "sample-data"
MIGRATION = REPO / "db" / "migrations" / "001_monitoring.sql"


@pytest.fixture(scope="module")
def data():
    return tiger.read_folder(SAMPLE)


# --- offline ----------------------------------------------------------------------------------------

def test_events_cover_the_replay_once_each(data):
    version = tiger.model_version_of(data["model"])
    events = tiger.build_events(data, version, data["weekly"])
    assert len(events) == len(data["stream"])
    assert not events.duplicated(["scan_id", "model_version", "ts"]).any()  # the hypertable's primary key
    assert (events["data_origin"] == tiger.SIMULATED).all()
    assert events["ts"].dt.tz is not None and events["ts"].min() >= tiger.FIRST_MONDAY


def test_referred_matches_the_engines_weekly_referral_rate(data):
    events = tiger.build_events(data, "v", data["weekly"])
    rate = events.groupby(["clinic_id", "week"])["referred"].mean()
    engine = data["weekly"].set_index(["clinic_id", "week"])["referral_rate"]
    assert (rate - engine.reindex(rate.index)).abs().max() < 1e-9


def test_grades_only_where_an_expert_graded(data):
    events = tiger.build_events(data, "v", data["weekly"])
    assert events.loc[events["graded_at"].isna(), "grade"].isna().all()
    assert events.loc[events["graded_at"].notna(), "grade"].notna().all()


def test_weekly_rows_keep_every_engine_column(data):
    weekly = tiger.build_weekly(data, "v")
    assert len(weekly) == len(data["weekly"])
    assert not weekly.duplicated(tiger.WEEKLY_KEYS).any()
    unknown = set(data["weekly"].columns) - set(tiger.WEEKLY_KEYS) - set(tiger.WEEKLY_COLUMNS)
    if unknown:  # anything new from the engine is kept in extra, not dropped
        assert set(json.loads(weekly["extra"].iloc[0])) == unknown
    assert weekly["alarm"].dtype == bool


def test_model_version_is_stable_and_changes_with_the_model(data):
    model = data["model"]
    assert tiger.model_version_of(model) == tiger.model_version_of(dict(model))
    assert tiger.model_version_of(model) != tiger.model_version_of({**model, "referral_threshold": 0.5})


def test_fingerprint_matches_the_engines():
    from clinicdrift.engine.pipeline import fingerprint
    ids = pd.Series(["b", "a", "c"])
    assert tiger.fingerprint(ids) == fingerprint(pd.DataFrame({"scan_id": ids}))


def test_migration_is_idempotent_sql():
    sql = MIGRATION.read_text(encoding="utf-8")
    for statement in re.findall(r"^\s*CREATE\s+(?:TABLE|SCHEMA|INDEX|MATERIALIZED VIEW)\b[^\n]*", sql, re.M):
        assert "IF NOT EXISTS" in statement, statement
    assert sql.count("create_hypertable") == sql.count("if_not_exists => TRUE") - 1  # + the policy
    assert "PRIMARY KEY (scan_id, model_version, ts)" in sql  # includes the partitioning column


def test_migration_parses_as_postgres():
    pglast = pytest.importorskip("pglast")
    statements = pglast.parse_sql(MIGRATION.read_text(encoding="utf-8"))
    assert len(statements) >= 12


def test_schema_name_is_checked(monkeypatch):
    monkeypatch.setenv("TIGER_SCHEMA", "x; DROP TABLE y")
    with pytest.raises(tiger.TigerError):
        tiger.schema()


@pytest.mark.parametrize("url", [
    "postgresql//tsdbadmin:S3cretPw9@localhost/tsdb",       # a colon lost when pasting
    "postgres://tsdbadmin:S3c%zzretPw9@localhost:1/tsdb",   # an unencoded % in the password
    "postgres://tsdbadmin:S3cretPw9@127.0.0.1:1/tsdb?connect_timeout=2",  # nothing listening
])
def test_connection_errors_never_show_the_password(monkeypatch, url):
    monkeypatch.setenv("TIGER_DATABASE_URL", url)
    with pytest.raises(tiger.TigerError) as err:
        tiger.connect()
    assert "S3c" not in str(err.value) and "Pw9" not in str(err.value)


def test_stand_in_runs_read_the_model_from_standin(tmp_path):
    """After an engine run on the stand-in, model.json and scans live in processed/standin/."""
    for name in ("stream.csv", "weekly.csv", "clinics.json", "decision_settings.json"):
        shutil.copy(SAMPLE / name, tmp_path / name)
    (tmp_path / "standin").mkdir()
    for name in ("model.json", "scans.csv"):
        shutil.copy(SAMPLE / name, tmp_path / "standin" / name)
    data = tiger.read_folder(tmp_path)
    assert data["model"] == json.loads((SAMPLE / "model.json").read_text(encoding="utf-8"))
    assert len(tiger.build_events(data, "v", data["weekly"])) == len(data["stream"])


def test_missing_url_explains_what_to_set(monkeypatch):
    for var in tiger.URL_VARS:
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(tiger.TigerError, match="TIGER_DATABASE_URL"):
        tiger.database_url()


# --- live (a real TimescaleDB) ------------------------------------------------------------------------

LIVE_URL = os.environ.get("TIGER_TEST_DATABASE_URL")
live = pytest.mark.skipif(not LIVE_URL, reason="set TIGER_TEST_DATABASE_URL to run against a TimescaleDB")


def small_folder(tmp: Path, clinics=("US-WEAR-01", "US-EYE-01"), weeks=3) -> Path:
    """A slice of sample-data/: two clinics, first `weeks` weeks."""
    out = tmp / "batch"
    out.mkdir(parents=True)
    stream = pd.read_csv(SAMPLE / "stream.csv")
    stream = stream[stream["clinic_id"].isin(clinics) & (stream["week"] <= weeks)]
    stream.to_csv(out / "stream.csv", index=False)
    scans = pd.read_csv(SAMPLE / "scans.csv")
    scans[scans["scan_id"].isin(stream["scan_id"])].to_csv(out / "scans.csv", index=False)
    weekly = pd.read_csv(SAMPLE / "weekly.csv")
    weekly[weekly["clinic_id"].isin(clinics) & (weekly["week"] <= weeks)].to_csv(out / "weekly.csv", index=False)
    for name in ("model.json", "clinics.json", "decision_settings.json"):
        shutil.copy(SAMPLE / name, out / name)
    return out


@pytest.fixture()
def db(monkeypatch):
    monkeypatch.setenv("TIGER_DATABASE_URL", LIVE_URL)
    monkeypatch.setenv("TIGER_SCHEMA", "clinicdrift_test")
    with tiger.connect() as conn:
        conn.execute("DROP SCHEMA IF EXISTS clinicdrift_test CASCADE")
        yield conn
        conn.execute("DROP SCHEMA IF EXISTS clinicdrift_test CASCADE")


@live
def test_live_migrate_twice(db):
    assert tiger.migrate(db) == ["001_monitoring"]
    assert tiger.migrate(db) == []
    # also safe if the migration file itself runs again
    db.execute(tiger._sql(tiger.MIGRATIONS_DIR / "001_monitoring.sql"))


@live
def test_live_ingest_twice_makes_no_duplicates(db, tmp_path):
    tiger.migrate(db)
    folder = small_folder(tmp_path)
    first = tiger.ingest(db, folder)
    n = first["scan_events"]["inserted"]
    assert n == len(pd.read_csv(folder / "stream.csv")) and first["scan_events"]["updated"] == 0
    second = tiger.ingest(db, folder)
    assert second["scan_events"] == {"inserted": 0, "updated": n, "removed": 0}
    assert second["weekly"]["inserted"] == 0
    s = tiger.schema()
    assert db.execute(f"SELECT count(*) FROM {s}.scan_events").fetchone()[0] == n
    assert db.execute(f"SELECT count(*) FROM {s}.weekly_monitoring").fetchone()[0] == 2 * 3
    assert db.execute(f"SELECT count(*) FROM {s}.ingest_runs").fetchone()[0] == 2


@live
def test_live_clinic_time_query_and_demo_event(db, tmp_path):
    tiger.migrate(db)
    folder = small_folder(tmp_path)
    version = tiger.ingest(db, folder)["model_version"]
    stream = pd.read_csv(folder / "stream.csv")
    want = stream[stream["clinic_id"] == "US-WEAR-01"].groupby("week").size().tolist()
    got = tiger.scan_series(db, "US-WEAR-01", version, "2026-01-05", "2026-01-26")
    assert got["n_scans"].tolist() == want  # weekly buckets start on Monday, like the replay's weeks
    only_week_2 = tiger.scan_series(db, "US-WEAR-01", version, "2026-01-12", "2026-01-19")
    assert only_week_2["n_scans"].tolist() == [want[1]]

    added = tiger.demo_event(db, "US-WEAR-01", 2, version)
    after = tiger.scan_series(db, "US-WEAR-01", version, "2026-01-12", "2026-01-19")
    assert after["n_scans"].tolist() == [want[1] + 1] and after["n_demo_live"].tolist() == [1]
    assert added["scan_id"].startswith("demo-US-WEAR-01-w02")
    assert tiger.clear_demo(db) == 1
    assert tiger.scan_series(db, "US-WEAR-01", version, "2026-01-12", "2026-01-19")["n_scans"].tolist() == [want[1]]


@live
def test_live_reingest_of_a_changed_replay_removes_stale_rows(db, tmp_path):
    tiger.migrate(db)
    folder = small_folder(tmp_path)
    tiger.ingest(db, folder)
    stream = pd.read_csv(folder / "stream.csv")
    stream[stream["week"] <= 2].to_csv(folder / "stream.csv", index=False)  # a shorter replay, same model
    result = tiger.ingest(db, folder)
    assert result["scan_events"]["removed"] == int((stream["week"] == 3).sum())
    assert db.execute(f"SELECT count(*) FROM {tiger.schema()}.scan_events").fetchone()[0] == int((stream["week"] <= 2).sum())
    # the aggregate forgets the removed week too, without waiting for the background policy
    week3 = tiger.scan_series(db, "US-WEAR-01", result["model_version"], "2026-01-19", "2026-01-26")
    assert week3.empty


@live
def test_live_dashboard_reads_what_was_stored(db, tmp_path, monkeypatch):
    tiger.migrate(db)
    folder = small_folder(tmp_path)
    tiger.ingest(db, folder)
    monkeypatch.setenv("CLINICDRIFT_DATA_MODE", "tiger")
    sys.path.append(str(REPO / "dashboard"))  # appended, so the repo's clinicdrift package still wins
    from ui import handoff, tiger as dash
    weekly, clinics, settings, info = handoff.load_source()
    assert info["mode"] == "tiger" and len(weekly) == 6 and settings["costs"]
    assert {c["clinic_id"] for c in clinics} >= {"US-WEAR-01", "US-EYE-01"}
    row = weekly[(weekly.clinic_id == "US-WEAR-01") & (weekly.week == 3)].iloc[0]
    evidence = dash.expert_evidence("US-WEAR-01", info["model_version"], 3, row.week_start)
    assert evidence["grades_arrived"] >= 0  # no grades arrive in the first weeks; the query must still work

    import psycopg
    with dash.connect() as conn:  # the dashboard cannot write
        with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
            conn.execute(f"DELETE FROM {tiger.schema()}.alarms")
    tiger.demo_event(db, "US-WEAR-01", 2)  # and leaves no read-only state behind for writers


@live
def test_live_compress_reports_real_sizes(db, tmp_path):
    tiger.migrate(db)
    tiger.ingest(db, small_folder(tmp_path))
    result = tiger.compress(db)
    assert result["chunks"] > 0 and result["chunks_compressed"] == result["chunks"]
    assert result["bytes_before"] > 0 and result["bytes_after"] > 0
    tiger.ingest(db, small_folder(tmp_path / "again"))  # upserts still work on compressed chunks

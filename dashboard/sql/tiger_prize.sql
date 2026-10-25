-- SUPERSEDED: the schema that runs is db/migrations/ (python -m clinicdrift.db.tiger migrate; see docs/tiger.md).
-- Kept as the original review-only draft.
-- OPTIONAL Tiger Data prize demonstration. Review before running.
-- Creates ONLY clinicdrift_demo objects. Requires TimescaleDB extension.
CREATE SCHEMA IF NOT EXISTS clinicdrift_demo;
CREATE TABLE IF NOT EXISTS clinicdrift_demo.scan_events (
  ts TIMESTAMPTZ NOT NULL,
  scan_id TEXT NOT NULL,
  clinic_id TEXT NOT NULL,
  week INTEGER NOT NULL CHECK (week > 0),
  wear DOUBLE PRECISION NOT NULL DEFAULT 0 CHECK (wear BETWEEN 0 AND 1),
  p_referable DOUBLE PRECISION CHECK (p_referable BETWEEN 0 AND 1),
  grade SMALLINT CHECK (grade BETWEEN 0 AND 4),
  graded_at TIMESTAMPTZ,
  PRIMARY KEY (ts, scan_id)
);
SELECT create_hypertable('clinicdrift_demo.scan_events',by_range('ts'),if_not_exists=>TRUE);
CREATE INDEX IF NOT EXISTS scan_events_clinic_ts_idx ON clinicdrift_demo.scan_events (clinic_id,ts DESC);
-- Refresh after imports or grade updates. Do not infer historic label availability from the latest grade alone.
CREATE MATERIALIZED VIEW IF NOT EXISTS clinicdrift_demo.clinic_week
WITH (timescaledb.continuous) AS
SELECT time_bucket('7 days',ts,TIMESTAMPTZ '2026-01-05 00:00:00+00') AS week_start,
 clinic_id, count(*) AS n_scans, avg(wear) AS mean_wear,
 avg(p_referable) AS mean_referral_score
FROM clinicdrift_demo.scan_events
GROUP BY 1,2 WITH NO DATA;
-- Explicit refresh can be run after ingestion:
-- CALL refresh_continuous_aggregate('clinicdrift_demo.clinic_week', NULL, NULL);
-- Optional columnstore/compression configuration depends on the Tiger service version.
-- Inspect available TimescaleDB capabilities before enabling any policies.

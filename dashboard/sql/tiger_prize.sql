-- ClinicDrift on Tiger Data (TimescaleDB). Run by scripts/load_tiger.py, which also loads the data.
-- Creates only clinicdrift_demo objects, so it can share a service with anything else.

CREATE SCHEMA IF NOT EXISTS clinicdrift_demo;

-- Every scan a simulated clinic took, keyed on when it was taken. The expert grade is filled in
-- only for the ~10% of scans an expert checks, and graded_at says when it arrived (5-7 weeks
-- later): a query "as of" a date must only use grades with graded_at <= that date.
CREATE TABLE IF NOT EXISTS clinicdrift_demo.scan_events (
  ts           TIMESTAMPTZ NOT NULL,
  scan_id      TEXT NOT NULL,
  clinic_id    TEXT NOT NULL,
  source       TEXT NOT NULL,
  week         INTEGER NOT NULL CHECK (week > 0),
  wear         DOUBLE PRECISION NOT NULL DEFAULT 0 CHECK (wear BETWEEN 0 AND 1),
  model_update BOOLEAN NOT NULL DEFAULT FALSE,
  p_referable  DOUBLE PRECISION CHECK (p_referable BETWEEN 0 AND 1),
  referred     BOOLEAN NOT NULL,
  quality      DOUBLE PRECISION CHECK (quality BETWEEN 0 AND 1),
  grade        SMALLINT CHECK (grade BETWEEN 0 AND 4),
  graded_at    TIMESTAMPTZ,
  PRIMARY KEY (ts, scan_id)
);
SELECT create_hypertable('clinicdrift_demo.scan_events', by_range('ts', INTERVAL '7 days'), if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS scan_events_clinic_ts_idx ON clinicdrift_demo.scan_events (clinic_id, ts DESC);
CREATE INDEX IF NOT EXISTS scan_events_graded_at_idx ON clinicdrift_demo.scan_events (graded_at) WHERE graded_at IS NOT NULL;

-- Weekly totals per clinic, kept up to date by Tiger. Weeks start on Monday 5 January 2026, as in the replay.
-- materialized_only = false: scans that arrived since the last refresh still count.
CREATE MATERIALIZED VIEW IF NOT EXISTS clinicdrift_demo.clinic_week
WITH (timescaledb.continuous, timescaledb.materialized_only = false) AS
SELECT time_bucket(INTERVAL '7 days', ts, TIMESTAMPTZ '2026-01-05 00:00:00+00') AS week_start,
       clinic_id,
       count(*)                          AS n_scans,
       avg(wear)                         AS mean_wear,
       avg(p_referable)                  AS mean_referral_score,
       avg(referred::int)                AS referral_rate,
       avg(quality)                      AS mean_quality,
       count(*) FILTER (WHERE graded_at IS NOT NULL) AS n_to_be_graded
FROM clinicdrift_demo.scan_events
GROUP BY 1, 2
WITH NO DATA;

-- The engine's output, one row per clinic-week (processed/weekly.parquet, sample-data/weekly.csv).
-- scripts/load_tiger.py creates it from the file's columns, so it follows the engine's format.

-- Alarm files for the add-ons, one per alarm start.
CREATE TABLE IF NOT EXISTS clinicdrift_demo.alarms (
  clinic_id  TEXT NOT NULL,
  week       INTEGER NOT NULL,
  week_start DATE NOT NULL,
  payload    JSONB NOT NULL,
  PRIMARY KEY (clinic_id, week)
);

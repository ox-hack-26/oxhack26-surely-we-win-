-- Draft for Tiger Cloud (TimescaleDB). Sneha: run once on a fresh service and adjust
-- freely, but keep column names in line with docs/handoffs.md.

-- One row per scan as it happens in the replay (processed/stream.parquet joined to scans.parquet).
CREATE TABLE IF NOT EXISTS scan_events (
    ts           TIMESTAMPTZ NOT NULL,  -- when the scan was taken (simulated)
    clinic_id    TEXT        NOT NULL,
    scan_id      TEXT        NOT NULL,
    source       TEXT        NOT NULL,
    p_referable  REAL,                  -- classifier's referral probability
    quality      REAL,
    drift        REAL,
    grade        SMALLINT,              -- expert grade 0-4, NULL until it arrives
    graded_at    TIMESTAMPTZ            -- when the grade arrived
);
SELECT create_hypertable('scan_events', by_range('ts'), if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS scan_events_clinic_ts ON scan_events (clinic_id, ts DESC);

-- Weekly totals per clinic for the dashboard, maintained by Tiger.
-- time_bucket('7 days') weeks start on Monday, matching weekly_results.week.
CREATE MATERIALIZED VIEW IF NOT EXISTS clinic_week
WITH (timescaledb.continuous, timescaledb.materialized_only = false) AS
SELECT time_bucket(INTERVAL '7 days', ts) AS week,
       clinic_id,
       count(*)         AS n_scans,
       avg(p_referable) AS mean_score,
       avg(quality)     AS mean_quality,
       avg(drift)       AS mean_drift
FROM scan_events
GROUP BY week, clinic_id
WITH NO DATA;
-- The replay loads past timestamps in one go, so refresh the whole range after each load:
--   CALL refresh_continuous_aggregate('clinic_week', NULL, NULL);

-- Engine output (Tejas): mirrors processed/weekly.parquet.
CREATE TABLE IF NOT EXISTS weekly_results (
    clinic_id         TEXT        NOT NULL,
    week              TIMESTAMPTZ NOT NULL,  -- Monday the week starts
    n_scans           INTEGER,
    est_sensitivity   REAL,
    est_low           REAL,
    est_high          REAL,
    true_sensitivity  REAL,
    expected_missed   REAL,
    drift             REAL,
    quality_mean      REAL,
    alarm             BOOLEAN,
    PRIMARY KEY (clinic_id, week)
);

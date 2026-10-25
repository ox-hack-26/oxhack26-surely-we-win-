-- ClinicDrift monitoring tables on Tiger Data (TimescaleDB). Applied by
-- `python -m clinicdrift.db.tiger migrate`, which records it in clinicdrift_demo.schema_migrations.
-- Every statement is idempotent, so running it twice is harmless.
--
-- Times: `ts` / `week_start` are EVENT times from the replay (simulated scans, January-May 2026).
-- `ingested_at` is when the row was written. Every row says where it came from in `data_origin`:
-- 'simulated_replay' for the engine's replay, 'demo_live' for events added during a live demo.

CREATE SCHEMA IF NOT EXISTS clinicdrift_demo;

-- One row per model whose scores are stored (from model.json).
CREATE TABLE IF NOT EXISTS clinicdrift_demo.model_versions (
  model_version      TEXT PRIMARY KEY,
  description        TEXT NOT NULL,
  referral_threshold DOUBLE PRECISION NOT NULL,
  val_auc            DOUBLE PRECISION,
  val_sensitivity    DOUBLE PRECISION,
  val_specificity    DOUBLE PRECISION,
  details            JSONB NOT NULL,
  first_seen_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- The simulated clinics (from clinics.json).
CREATE TABLE IF NOT EXISTS clinicdrift_demo.clinics (
  clinic_id        TEXT PRIMARY KEY,
  site             TEXT NOT NULL,
  country          TEXT NOT NULL,
  note             TEXT,
  scans_per_week   INTEGER,
  switch_week      INTEGER,
  wear_from_week   INTEGER,
  update_from_week INTEGER,
  details          JSONB NOT NULL,
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- One row per ingestion: which model and replay it wrote, and the decision settings it used.
CREATE TABLE IF NOT EXISTS clinicdrift_demo.ingest_runs (
  run_id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  ingested_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  model_version      TEXT NOT NULL,
  replay_fingerprint TEXT NOT NULL,
  source             TEXT NOT NULL,
  data_origin        TEXT NOT NULL,
  n_scan_events      INTEGER NOT NULL,
  n_clinic_weeks     INTEGER NOT NULL,
  n_alarms           INTEGER NOT NULL,
  decision_settings  JSONB
);

-- Every scan a clinic took, with the model's output. A hypertable on event time `ts`, in weekly chunks.
-- The primary key includes `ts` because a hypertable's unique keys must contain its partitioning column;
-- `model_version` is in it so two models' scores for the same scans can sit side by side.
CREATE TABLE IF NOT EXISTS clinicdrift_demo.scan_events (
  ts                 TIMESTAMPTZ NOT NULL,
  scan_id            TEXT NOT NULL,
  model_version      TEXT NOT NULL,
  clinic_id          TEXT NOT NULL,
  source             TEXT NOT NULL,
  week               INTEGER NOT NULL CHECK (week > 0),
  wear               DOUBLE PRECISION NOT NULL DEFAULT 0 CHECK (wear BETWEEN 0 AND 1),
  model_update       BOOLEAN NOT NULL DEFAULT FALSE,
  p_referable        DOUBLE PRECISION NOT NULL CHECK (p_referable BETWEEN 0 AND 1),
  referral_threshold DOUBLE PRECISION NOT NULL,
  referred           BOOLEAN NOT NULL,
  quality            DOUBLE PRECISION,
  grade              SMALLINT CHECK (grade BETWEEN 0 AND 4),  -- only for the ~10% of scans an expert checks
  graded_at          TIMESTAMPTZ,                              -- when that grade arrives, 5-7 weeks later
  data_origin        TEXT NOT NULL DEFAULT 'simulated_replay' CHECK (data_origin IN ('simulated_replay', 'demo_live')),
  run_id             BIGINT,
  ingested_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (scan_id, model_version, ts)
);
SELECT create_hypertable('clinicdrift_demo.scan_events', by_range('ts', INTERVAL '7 days'), if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS scan_events_clinic_ts ON clinicdrift_demo.scan_events (clinic_id, model_version, ts DESC);
CREATE INDEX IF NOT EXISTS scan_events_graded_at ON clinicdrift_demo.scan_events (graded_at) WHERE graded_at IS NOT NULL;

-- The engine's weekly monitoring output (weekly.parquet / weekly.csv), one row per clinic-week and model.
-- Columns follow docs/handoffs.md; engine columns this table doesn't have yet go into `extra`.
CREATE TABLE IF NOT EXISTS clinicdrift_demo.weekly_monitoring (
  week_start               TIMESTAMPTZ NOT NULL,
  clinic_id                TEXT NOT NULL,
  model_version            TEXT NOT NULL,
  week                     INTEGER NOT NULL,
  n_scans                  INTEGER NOT NULL,
  est_sensitivity          DOUBLE PRECISION,
  est_low                  DOUBLE PRECISION,
  est_high                 DOUBLE PRECISION,
  expected_cases           DOUBLE PRECISION,
  expected_missed          DOUBLE PRECISION,
  expected_false_referrals DOUBLE PRECISION,
  drift_auc                DOUBLE PRECISION,
  lookalikes               DOUBLE PRECISION,
  quality_mean             DOUBLE PRECISION,
  referral_rate            DOUBLE PRECISION,
  referral_threshold       DOUBLE PRECISION,
  true_cases               INTEGER,          -- true_*: hindsight from every grade, for the backtest only
  true_sensitivity         DOUBLE PRECISION,
  true_missed              INTEGER,
  true_false_referrals     INTEGER,
  trust                    DOUBLE PRECISION,
  graded_cases             INTEGER,
  graded_caught            INTEGER,
  catch_rate               DOUBLE PRECISION,
  catch_low                DOUBLE PRECISION,
  catch_high               DOUBLE PRECISION,
  belief_cases             DOUBLE PRECISION,
  belief_missed            DOUBLE PRECISION,
  expected_harm            DOUBLE PRECISION,
  p_below_standard         DOUBLE PRECISION,
  alarm_this_week          BOOLEAN,
  alarm_reason             TEXT,
  alarm                    BOOLEAN,
  extra                    JSONB NOT NULL DEFAULT '{}'::jsonb,
  data_origin              TEXT NOT NULL DEFAULT 'simulated_replay',
  run_id                   BIGINT,
  ingested_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (clinic_id, model_version, week_start)
);
SELECT create_hypertable('clinicdrift_demo.weekly_monitoring', by_range('week_start', INTERVAL '28 days'), if_not_exists => TRUE);

-- Alarm files for the add-ons (alarms/<clinic>_week<NN>.json), kept whole.
CREATE TABLE IF NOT EXISTS clinicdrift_demo.alarms (
  clinic_id     TEXT NOT NULL,
  model_version TEXT NOT NULL,
  week          INTEGER NOT NULL,
  week_start    DATE NOT NULL,
  reason        TEXT,
  payload       JSONB NOT NULL,
  run_id        BIGINT,
  ingested_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (clinic_id, model_version, week)
);

-- Daily totals per clinic and model, kept by Tiger. Sums (not averages) so any coarser time_bucket
-- can be rolled up from it exactly. materialized_only = false (real-time aggregation): rows written
-- since the last refresh are still counted, so a new demo event shows at once.
CREATE MATERIALIZED VIEW IF NOT EXISTS clinicdrift_demo.scan_stats_daily
WITH (timescaledb.continuous, timescaledb.materialized_only = false) AS
SELECT time_bucket(INTERVAL '1 day', ts) AS bucket,
       clinic_id,
       model_version,
       count(*)                                               AS n_scans,
       sum(p_referable)                                       AS sum_p_referable,
       sum(CASE WHEN referred THEN 1 ELSE 0 END)              AS n_referred,
       sum(quality)                                           AS sum_quality,
       count(quality)                                         AS n_quality,
       sum(wear)                                              AS sum_wear,
       sum(CASE WHEN graded_at IS NOT NULL THEN 1 ELSE 0 END) AS n_to_be_graded,
       sum(CASE WHEN data_origin = 'demo_live' THEN 1 ELSE 0 END) AS n_demo_live
FROM clinicdrift_demo.scan_events
GROUP BY 1, 2, 3
WITH NO DATA;

-- Keep it materialised in the background too. The replay's events are months old, so the policy
-- refreshes the whole history (start_offset NULL); ingestion also refreshes the range it wrote.
SELECT add_continuous_aggregate_policy('clinicdrift_demo.scan_stats_daily',
  start_offset => NULL, end_offset => INTERVAL '1 hour', schedule_interval => INTERVAL '5 minutes',
  if_not_exists => TRUE);

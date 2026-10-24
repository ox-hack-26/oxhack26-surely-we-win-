-- Safe to re-run. No real patient identifiers are stored.
CREATE TABLE IF NOT EXISTS scans (
 scan_id TEXT PRIMARY KEY, clinic_id TEXT NOT NULL, dataset_name TEXT NOT NULL,
 clinic_week INTEGER NOT NULL CHECK (clinic_week > 0), model_version TEXT NOT NULL,
 model_score DOUBLE PRECISION CHECK (model_score BETWEEN 0 AND 1), predicted_referral BOOLEAN,
 expert_grade SMALLINT CHECK (expert_grade BETWEEN 0 AND 4), expert_referral BOOLEAN,
 label_available_at TIMESTAMPTZ, image_quality_score DOUBLE PRECISION,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(), data_source TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS scans_clinic_week_idx ON scans (clinic_id, clinic_week);
CREATE TABLE IF NOT EXISTS weekly_monitoring (
 clinic_id TEXT NOT NULL, clinic_week INTEGER NOT NULL CHECK (clinic_week > 0), model_version TEXT NOT NULL,
 total_scans INTEGER NOT NULL CHECK (total_scans >= 0),
 estimated_sensitivity DOUBLE PRECISION CHECK (estimated_sensitivity BETWEEN 0 AND 1),
 confidence_lower DOUBLE PRECISION CHECK (confidence_lower BETWEEN 0 AND 1),
 confidence_upper DOUBLE PRECISION CHECK (confidence_upper BETWEEN 0 AND 1),
 observed_sensitivity DOUBLE PRECISION CHECK (observed_sensitivity BETWEEN 0 AND 1),
 observed_positive_count INTEGER NOT NULL DEFAULT 0 CHECK (observed_positive_count >= 0),
 labels_available BOOLEAN NOT NULL DEFAULT FALSE,
 alarm_status TEXT NOT NULL CHECK (alarm_status IN ('stable','monitor','review_recommended','insufficient_evidence')),
 expected_continuation_cost DOUBLE PRECISION, review_cost DOUBLE PRECISION,
 data_source TEXT NOT NULL, prediction_method_version TEXT NOT NULL,
 labels_available_week INTEGER NOT NULL, positive_cases_estimate DOUBLE PRECISION,
 PRIMARY KEY (clinic_id, clinic_week, model_version),
 CHECK (confidence_lower <= estimated_sensitivity AND estimated_sensitivity <= confidence_upper),
 CHECK (labels_available_week >= clinic_week)
);
CREATE INDEX IF NOT EXISTS weekly_clinic_idx ON weekly_monitoring (clinic_id, clinic_week);
CREATE TABLE IF NOT EXISTS alerts (
 alert_id TEXT PRIMARY KEY, clinic_id TEXT NOT NULL, clinic_week INTEGER NOT NULL,
 model_version TEXT NOT NULL, alert_status TEXT NOT NULL,
 estimated_sensitivity DOUBLE PRECISION, uncertainty_lower DOUBLE PRECISION, uncertainty_upper DOUBLE PRECISION,
 expected_harm_cost DOUBLE PRECISION, review_cost DOUBLE PRECISION,
 recommended_action TEXT, explanation TEXT, review_status TEXT NOT NULL DEFAULT 'pending',
 created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS alerts_clinic_week_idx ON alerts (clinic_id, clinic_week);
CREATE TABLE IF NOT EXISTS investigations (
 investigation_id TEXT PRIMARY KEY, alert_id TEXT REFERENCES alerts(alert_id),
 review_status TEXT NOT NULL, reviewer_notes TEXT,
 reviewed_at TIMESTAMPTZ, created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

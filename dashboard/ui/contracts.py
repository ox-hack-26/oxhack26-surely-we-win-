"""Validate hand-off contracts; prediction algorithms belong to Tejas."""
from datetime import datetime, timezone
import pandas as pd

SCAN_FIELDS = ['scan_id','clinic_id','dataset_name','clinic_week','model_version','model_score','predicted_referral','expert_grade','expert_referral','label_available_at','image_quality_score','created_at','data_source']
WEEKLY_FIELDS = ['clinic_id','clinic_week','model_version','total_scans','estimated_sensitivity','confidence_lower','confidence_upper','observed_sensitivity','observed_positive_count','labels_available','alarm_status','expected_continuation_cost','review_cost','data_source','prediction_method_version','labels_available_week','positive_cases_estimate']
ALERT_STATES = {'stable','monitor','review_recommended','insufficient_evidence'}


def validate_weekly(frame):
    df = frame.copy()
    missing = set(WEEKLY_FIELDS) - set(df.columns)
    if missing: raise ValueError(f'Missing weekly columns: {sorted(missing)}')
    if df.duplicated(['clinic_id','clinic_week','model_version']).any(): raise ValueError('Duplicate clinic/week/model entries')
    if df['clinic_id'].isna().any(): raise ValueError('Missing clinic_id')
    for field in ('estimated_sensitivity','confidence_lower','confidence_upper','observed_sensitivity'):
        v = pd.to_numeric(df[field], errors='coerce')
        if (v.dropna().lt(0) | v.dropna().gt(1)).any(): raise ValueError(f'{field} outside [0,1]')
    if ((df.confidence_lower > df.estimated_sensitivity) | (df.confidence_upper < df.estimated_sensitivity)).fillna(False).any():
        raise ValueError('Invalid uncertainty bounds')
    if not df.alarm_status.isin(ALERT_STATES).all(): raise ValueError('Invalid alert status')
    if (df.total_scans < 0).any() or (df.observed_positive_count < 0).any(): raise ValueError('Negative counts')
    if (df.labels_available_week < df.clinic_week).any(): raise ValueError('Label arrival predates monitoring week')
    return df


def validate_scans(frame):
    df = frame.copy()
    missing = set(SCAN_FIELDS) - set(df.columns)
    if missing: raise ValueError(f'Missing scan columns: {sorted(missing)}')
    if df.scan_id.duplicated().any(): raise ValueError('Duplicate scan_id')
    grades = pd.to_numeric(df.expert_grade, errors='coerce').dropna()
    if not grades.isin([0,1,2,3,4]).all(): raise ValueError('Expert grade must be 0..4 or missing')
    scores = pd.to_numeric(df.model_score, errors='coerce').dropna()
    if not scores.between(0,1).all(): raise ValueError('Model score must be a probability')
    return df


def observed_sensitivity(scans, as_of):
    """Only labels available by as_of contribute to observed sensitivity."""
    df = validate_scans(scans)
    arrival = pd.to_datetime(df.label_available_at, utc=True, errors='coerce')
    eligible = df[(arrival <= pd.Timestamp(as_of)) & df.expert_grade.notna()].copy()
    positives = eligible[pd.to_numeric(eligible.expert_grade) >= 2]
    if len(positives) == 0: return None, 0
    return float(positives.predicted_referral.astype(bool).mean()), len(positives)


def visible_weekly(df, clinic, replay_week):
    """Hide outcomes whose simulated arrival week is in the future."""
    rows = validate_weekly(df)
    rows = rows[(rows.clinic_id == clinic) & (rows.clinic_week <= replay_week)].sort_values('clinic_week').copy()
    unavailable = rows.labels_available_week > replay_week
    rows.loc[unavailable,'observed_sensitivity'] = float('nan')
    rows.loc[unavailable,'observed_positive_count'] = 0
    rows.loc[unavailable,'labels_available'] = False
    return rows

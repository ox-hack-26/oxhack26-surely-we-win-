"""Tiger Cloud persistence and explicit mock mode. Never print credentials."""
import os
from pathlib import Path
import pandas as pd
from .mock_data import demo_weekly
from .contracts import validate_weekly, validate_scans

SQL_PATH = Path(__file__).resolve().parents[1] / 'sql' / 'schema.sql'

def mode():
    result = os.getenv('CLINICDRIFT_DATA_MODE','mock').strip().lower()
    if result not in ('mock','tiger'): raise ValueError('CLINICDRIFT_DATA_MODE must be mock or tiger')
    return result

def connect():
    import psycopg
    url = os.getenv('TIMESCALE_SERVICE_URL') or os.getenv('DATABASE_URL')
    if not url: raise RuntimeError('Tiger mode selected but TIMESCALE_SERVICE_URL / DATABASE_URL is not configured')
    try: return psycopg.connect(url, connect_timeout=7)
    except Exception: raise RuntimeError('Tiger Cloud connection failed; check service status and credentials (details withheld)') from None

def healthcheck():
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT 1')
            return cur.fetchone()[0] == 1

def init_schema():
    with connect() as conn:
        with conn.cursor() as cur: cur.execute(SQL_PATH.read_text())
        conn.commit()

def load_weekly():
    if mode() == 'mock': return demo_weekly(), 'SYNTHETIC DEMO'
    try:
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT clinic_id, clinic_week, model_version, total_scans, estimated_sensitivity, confidence_lower, confidence_upper, observed_sensitivity, observed_positive_count, labels_available, alarm_status, expected_continuation_cost, review_cost, data_source, prediction_method_version, labels_available_week, positive_cases_estimate FROM weekly_monitoring ORDER BY clinic_id, clinic_week')
                columns = [c.name for c in cur.description]
                rows = cur.fetchall()
        if not rows: raise RuntimeError('Tiger Cloud weekly_monitoring table is empty. Load records first.')
        return validate_weekly(pd.DataFrame(rows,columns=columns)), 'TIGER CLOUD'
    except RuntimeError: raise
    except Exception: raise RuntimeError('Tiger Cloud query failed. Verify the schema and permissions (details withheld)') from None

def upsert_weekly(frame):
    df = validate_weekly(frame)
    cols = ['clinic_id','clinic_week','model_version','total_scans','estimated_sensitivity','confidence_lower','confidence_upper','observed_sensitivity','observed_positive_count','labels_available','alarm_status','expected_continuation_cost','review_cost','data_source','prediction_method_version','labels_available_week','positive_cases_estimate']
    import psycopg
    from psycopg import sql
    q = sql.SQL('INSERT INTO weekly_monitoring ({}) VALUES ({}) ON CONFLICT (clinic_id,clinic_week,model_version) DO UPDATE SET {}').format(
        sql.SQL(',').join(map(sql.Identifier,cols)),sql.SQL(',').join([sql.Placeholder()]*len(cols)),
        sql.SQL(',').join(sql.SQL('{}=EXCLUDED.{}').format(sql.Identifier(c),sql.Identifier(c)) for c in cols[3:]))
    with connect() as conn:
        with conn.cursor() as cur:
            for row in df[cols].itertuples(index=False,name=None):
                cur.execute(q,tuple(None if pd.isna(v) else v.item() if hasattr(v,'item') else v for v in row))
        conn.commit()
    return len(df)

def upsert_scans(frame):
    df = validate_scans(frame)
    cols = ['scan_id','clinic_id','dataset_name','clinic_week','model_version','model_score','predicted_referral','expert_grade','expert_referral','label_available_at','image_quality_score','created_at','data_source']
    from psycopg import sql
    q = sql.SQL('INSERT INTO scans ({}) VALUES ({}) ON CONFLICT (scan_id) DO UPDATE SET {}').format(
        sql.SQL(',').join(map(sql.Identifier,cols)),sql.SQL(',').join([sql.Placeholder()]*len(cols)),
        sql.SQL(',').join(sql.SQL('{}=EXCLUDED.{}').format(sql.Identifier(c),sql.Identifier(c)) for c in cols[1:]))
    with connect() as conn:
        with conn.cursor() as cur:
            for row in df[cols].itertuples(index=False,name=None):
                cur.execute(q,tuple(None if pd.isna(v) else v.item() if hasattr(v,'item') else v for v in row))
        conn.commit()
    return len(df)

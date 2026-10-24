"""Deterministic fictional clinic-week data. NEVER present as measured performance."""
import numpy as np
import pandas as pd
from .contracts import validate_weekly

CLINICS = {'APTOS 2019 (India)': ('APTOS 2019',-.04), 'Messidor-2 (France)': ('Messidor-2',-.01), 'IDRiD (India)': ('IDRiD',-.07)}


def demo_weekly(seed=2026):
    rng = np.random.default_rng(seed)
    records = []
    for clinic,(dataset,offset) in CLINICS.items():
        for week in range(1,13):
            total = int(rng.integers(120,220))
            positives = int(rng.integers(25,65))
            deterioration = .016 * max(0,week-4)
            est = float(np.clip(.92+offset-deterioration+rng.normal(0,.009),.1,.99))
            obs = float(np.clip(est+rng.normal(0,.025),.1,.99))
            records.append(dict(clinic_id=clinic, clinic_week=week, model_version='retina-demo-v1',
                total_scans=total, estimated_sensitivity=est, confidence_lower=max(0,est-.065),
                confidence_upper=min(1,est+.065), observed_sensitivity=obs,
                observed_positive_count=positives, labels_available=True,
                alarm_status='review_recommended' if est < .80 else ('monitor' if est < .85 else 'stable'),
                expected_continuation_cost=None, review_cost=None, data_source='SYNTHETIC DEMO',
                prediction_method_version='SYNTHETIC PLACEHOLDER', labels_available_week=week+2,
                positive_cases_estimate=positives))
    return validate_weekly(pd.DataFrame(records))

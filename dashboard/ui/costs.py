"""Transparent cost sensitivity analysis from docs/handoffs.md.

The baseline's usual false-referral count is approximated from reference
specificity and prevalence; Tejas's engine is authoritative when integrated.
"""
from math import isfinite

def recompute(row, reference, missed_case=10000, false_referral=150, review=25000, horizon=6):
    vals = [missed_case, false_referral, review, horizon]
    if not all(isfinite(float(v)) and float(v) >= 0 for v in vals):
        raise ValueError("Costs and horizon must be finite nonnegative numbers")
    cases = float(row['belief_cases'])
    catch = float(row['catch_rate'])
    validated = float(reference['catch_rate'])
    n = float(row['n_scans'])
    referrals = float(row['referral_rate']) * n
    prevalence = float(reference['prevalence'])
    specificity = float(reference['specificity'])
    usual_false_referrals = n * (1 - prevalence) * (1 - specificity)
    extra_missed = cases * (validated - catch)
    extra_false_referrals = referrals - catch * cases - usual_false_referrals
    expected_harm = float(horizon) * (float(missed_case) * extra_missed + float(false_referral) * extra_false_referrals)
    return {"expected_harm": expected_harm, "review_cost": float(review),
            "review_recommended_this_week": expected_harm > float(review),
            "extra_missed_cases_per_week": extra_missed,
            "extra_false_referrals_per_week": extra_false_referrals,
            "assumption": "Illustrative cost sensitivity using handoff formula; not a clinical recommendation. Prior alarms remain latched in the original replay."}

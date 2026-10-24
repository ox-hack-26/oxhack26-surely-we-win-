"""Illustrative cost slider only; replace with Tejas's validated decision core."""
import math

def demo_decision(estimated_sensitivity, positive_cases_estimate, review_cost, missed_case_cost):
    values = [estimated_sensitivity,positive_cases_estimate,review_cost,missed_case_cost]
    if not all(isinstance(v,(int,float)) and math.isfinite(v) for v in values): raise ValueError('Nonfinite decision input')
    if not 0 <= estimated_sensitivity <= 1 or min(values[1:]) < 0: raise ValueError('Invalid decision input')
    missed = (1-estimated_sensitivity)*positive_cases_estimate
    expected = missed*missed_case_cost
    return {'expected_missed_cases':round(missed,3),'expected_continuation_cost':round(expected,2),
            'review_cost':float(review_cost), 'recommended_action':'review_recommended' if expected > review_cost else 'monitor',
            'assumption':'ILLUSTRATIVE ONLY: assumes review avoids all estimated missed-case loss; not a validated clinical policy.'}

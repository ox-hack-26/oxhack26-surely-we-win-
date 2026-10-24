import json
from pathlib import Path
import pandas as pd
from ui.handoff import load_handoff, replay_view, alarm_for_week
from ui.costs import recompute

def test_data_contract_and_alarm():
    weekly, clinics, settings=load_handoff()
    assert len(clinics) == weekly["clinic_id"].nunique()
    assert len(clinics) >= 9
    assert "US-WEAR-01" in weekly["clinic_id"].values
    assert "US-UPD-01" in weekly["clinic_id"].values
    assert len(weekly)>100
    alarm=alarm_for_week('US-WEAR-01',9)
    assert alarm['week']==9 and alarm['alarm_reason']=='drift'
    row=weekly[(weekly.clinic_id=='US-WEAR-01')&(weekly.week==9)].iloc[0]
    assert bool(row.alarm)

def test_replay_no_future_truth():
    weekly,_,_=load_handoff()
    shown=replay_view(weekly,'US-WEAR-01',9)
    assert shown.week.max()==9
    assert 'true_sensitivity' not in shown.columns
    assert not any(c.startswith('true_') for c in shown.columns)

def test_cost_formula():
    weekly,_,settings=load_handoff()
    row=weekly.iloc[0]
    r=recompute(row,settings['reference'],10000,150,25000,6)
    assert abs(r['expected_harm']-float(row.expected_harm))<2
    assert r['review_cost']==25000

def test_cost_slider_effect():
    weekly,_,settings=load_handoff()
    row=weekly.iloc[0]
    a=recompute(row,settings['reference'],10000,150,25000,6)
    b=recompute(row,settings['reference'],10000,150,10000000,6)
    assert a['review_recommended_this_week'] and not b['review_recommended_this_week']

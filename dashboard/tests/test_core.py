import json
import pandas as pd
import pytest
from ui.mock_data import demo_weekly
from ui.contracts import visible_weekly,validate_weekly,observed_sensitivity
from ui.decisions import demo_decision
from ui.replay import alert_json

def test_deterministic_mock():
    pd.testing.assert_frame_equal(demo_weekly(),demo_weekly())

def test_replay_no_future_outcomes():
    df=visible_weekly(demo_weekly(),'APTOS 2019 (India)',4)
    assert df.clinic_week.max()==4
    assert df.loc[df.labels_available_week>4,'observed_sensitivity'].isna().all()
    assert df.loc[df.labels_available_week<=4,'observed_sensitivity'].notna().all()

def test_clinic_filter():
    df=visible_weekly(demo_weekly(),'IDRiD (India)',6)
    assert df.clinic_id.nunique()==1 and df.clinic_id.iloc[0]=='IDRiD (India)'

def test_interval_validation():
    df=demo_weekly();df.loc[0,'confidence_lower']=.99
    with pytest.raises(ValueError): validate_weekly(df)

def test_cost_decision():
    assert demo_decision(.5,10,100,100)['recommended_action']=='review_recommended'
    assert demo_decision(.99,10,100,100)['recommended_action']=='monitor'
    with pytest.raises(ValueError): demo_decision(1.2,10,100,100)

def test_alert_json():
    row=demo_weekly().iloc[0]
    alert=json.loads(alert_json(row,demo_decision(.8,10,100,100),1))
    assert alert['clinic_week']==1 and alert['source']=='SYNTHETIC DEMO'

def test_sensitivity_missing_labels_and_zero_positive():
    base={'scan_id':['s1','s2'],'clinic_id':['a','a'],'dataset_name':['APTOS','APTOS'],
    'clinic_week':[1,1],'model_version':['v1','v1'],'model_score':[.9,.1],
    'predicted_referral':[True,False],'expert_grade':[2,None],
    'expert_referral':[True,None],'label_available_at':['2026-10-25T00:00:00Z',None],
    'image_quality_score':[.8,.8],'created_at':['2026-10-24T00:00:00Z']*2,'data_source':['TEST']*2}
    scans=pd.DataFrame(base)
    assert observed_sensitivity(scans,'2026-10-24T23:00:00Z')==(None,0)
    assert observed_sensitivity(scans,'2026-10-26T00:00:00Z')==(1.0,1)
    scans.loc[0,'expert_grade']=0
    assert observed_sensitivity(scans,'2026-10-26T00:00:00Z')==(None,0)

def test_database_schema_exists():
    from ui.storage import SQL_PATH
    s=SQL_PATH.read_text()
    for name in ['scans','weekly_monitoring','alerts','investigations']:
        assert f'CREATE TABLE IF NOT EXISTS {name}' in s

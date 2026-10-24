"""Replay logic and JSON export for the Gemini add-on handoff."""
import json
from .contracts import visible_weekly
from .decisions import demo_decision

def alert_payload(row, decision, replay_week):
    return {'source':'SYNTHETIC DEMO' if str(row['data_source']).startswith('SYNTHETIC') else str(row['data_source']),
        'clinic_id':str(row['clinic_id']),'clinic_week':int(row['clinic_week']),
        'replay_week':int(replay_week),'model_version':str(row['model_version']),
        'estimated_sensitivity':float(row['estimated_sensitivity']),
        'uncertainty_lower':float(row['confidence_lower']),'uncertainty_upper':float(row['confidence_upper']),
        'decision':decision, 'clinical_status':'RESEARCH PROTOTYPE - HUMAN REVIEW ONLY'}

def alert_json(row,decision,replay_week):
    return json.dumps(alert_payload(row,decision,replay_week),indent=2)

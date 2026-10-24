# ClinicDrift add-ons

What happens after the monitor raises an alarm for a clinic.

| Step | What it does | Uses | Without a key |
|---|---|---|---|
| Cause finder (`cause_finder.py`) | Compares the flagged week's scan statistics (and up to 4 sample scans) with training and names the most likely cause | Gemini | Rule-based answer |
| Incident report (`incident_report.py`) | Drafts an MHRA-style adverse incident report tagged with MIT AI Risk Repository categories | Gemini | Filled-in template |
| Spoken alert (`voice_alert.py`) | Reads a short alert (under 25 s) aloud for the clinic lead | ElevenLabs | Skipped (text script still produced) |

## Run

```bash
pip install -r requirements-addons.txt
cp .env.example .env          # optional: add GEMINI_API_KEY / ELEVENLABS_API_KEY
python -m addons.run_demo     # uses addons/fixtures/fake_alarm.json
python -m addons.run_demo path/to/alarm.json
python -m pytest -q tests     # offline, no keys needed
```

Outputs go to `addons/out/` (git-ignored):
`<clinic>_week<N>_cause.json`, `<clinic>_week<N>_incident_report.md`, `<clinic>_week<N>_alert.mp3`.

## Alarm format

The prediction core hands over one JSON file per alarm (see `alarm_schema.py` and
`fixtures/fake_alarm.json`):

| Field | Type | Notes |
|---|---|---|
| `clinic_id`, `site`, `country` | string | |
| `week` | int | |
| `week_start` | string, optional | ISO date |
| `device_name`, `device_version` | string, optional | defaults provided |
| `estimated_catch_rate`, `ci_low`, `ci_high`, `baseline_catch_rate` | float 0-1 | |
| `expected_harm`, `review_cost` | float | same units; alarm when harm > cost |
| `expected_missed_cases` | float, optional | |
| `flagged_scan_stats`, `training_scan_stats` | object | `n_scans` plus optional `mean_brightness`, `mean_contrast`, `mean_sharpness`, `mean_quality`, `mean_resolution_px`, `referral_score_mean`, `referral_rate` |
| `sample_scan_paths` | list of strings | optional images sent to Gemini |

## Note

The incident report is a draft for a human to check. It is not submitted anywhere and is not
clinical or regulatory guidance.

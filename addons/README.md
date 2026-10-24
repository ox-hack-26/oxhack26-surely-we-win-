# ClinicDrift add-ons

What happens after the engine raises an alarm for a clinic.

| Step | What it does | Uses | Without a key |
|---|---|---|---|
| Cause finder (`cause_finder.py`) | Compares the clinic-week's scan statistics with training (and up to 4 flagged and reference scans) and names the most likely cause | Gemini | Rule-based answer |
| Incident report (`incident_report.py`) | Drafts an MHRA-style adverse incident report tagged with MIT AI Risk Repository categories | Gemini | Filled-in template |
| Spoken alert (`voice_alert.py`) | Reads a short alert (under 25 s) aloud for the clinic lead | ElevenLabs | Skipped (text script still produced) |

## Run

```bash
pip install -r requirements-addons.txt
cp .env.example .env                          # optional: add GEMINI_API_KEY / ELEVENLABS_API_KEY
python -m addons.run_demo                     # the fake alarm in addons/fixtures/
python -m addons.run_demo path/to/alarm.json  # one real alarm
python -m addons.run_demo --all               # every alarm in $CLINICDRIFT_DATA/processed/alarms/
python -m pytest -q tests                     # offline, no keys needed
```

Outputs go to `addons/out/` (git-ignored), named after the alarm file:
`<clinic_id>_week<N>_cause.json`, `<clinic_id>_week<N>_incident_report.md`, `<clinic_id>_week<N>_alert.mp3`.

## What the add-ons read

**The alarm file** is defined in [docs/handoffs.md](../docs/handoffs.md), section 4:
`$CLINICDRIFT_DATA/processed/alarms/<clinic_id>_week<week>.json`, written by the engine and read by
`Alarm` in `alarm_schema.py`. Rates are fractions from 0 to 1. `fixtures/fake_alarm.json` is the
example from handoffs.md.

**Fallbacks.** Each one fills a gap in an alarm file; nothing breaks without it:

| From | Used for | If missing |
|---|---|---|
| `processed/scans.parquet` (or `processed/standin/scans.parquet` until it exists) rows for `flagged_scan_ids` / `reference_scan_ids` | Rebuilds `flagged_scan_stats` / `training_scan_stats` when the alarm leaves them out (a scan counts as referred when `p_referable >= referral_threshold` from the alarm, 0.5 if the alarm has none) | Cause is "unknown" with a note saying why |
| `processed/weekly.parquet` (`n_scans` for the clinic and `week_start`) | Week's scan count when `flagged_scan_stats` is missing | "Too few scans" check skipped |
| `clinicdrift.data.sources.load_image(scan_id)`, else `sample-data/images/<scan_id>.jpg` | Up to 2 flagged and 2 reference images sent to Gemini | No images sent |

## Note

The incident report is a draft for a human to check. It is not submitted anywhere and is not
clinical or regulatory guidance.

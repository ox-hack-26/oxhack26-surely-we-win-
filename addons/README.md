# ClinicDrift add-ons

What happens after the engine raises an alarm for a clinic.

| Step | What it does | Uses | Without a key |
|---|---|---|---|
| Cause finder (`cause_finder.py`) | Compares the alarm's flagged scans with its reference training scans (statistics from `scans.parquet`, plus up to 4 of the images) and names the most likely cause | Gemini | Rule-based answer |
| Incident report (`incident_report.py`) | Drafts an MHRA-style adverse incident report tagged with MIT AI Risk Repository categories | Gemini | Filled-in template |
| Spoken alert (`voice_alert.py`) | Reads a short alert (under 25 s) aloud for the clinic lead | ElevenLabs | Skipped (text script still produced) |

## Run

```bash
pip install -r requirements-addons.txt
cp .env.example .env                          # optional: add GEMINI_API_KEY / ELEVENLABS_API_KEY
python -m addons.run_demo                     # fake alarm + fake scans in addons/fixtures/
python -m addons.run_demo path/to/alarm.json  # one real alarm
python -m addons.run_demo --all               # every alarm in $CLINICDRIFT_DATA/processed/alarms/
python -m pytest -q tests                     # offline, no keys needed
```

Outputs go to `addons/out/` (git-ignored), named after the alarm file:
`<clinic_id>_<week>_cause.json`, `<clinic_id>_<week>_incident_report.md`, `<clinic_id>_<week>_alert.mp3`.

## What the add-ons read

**The alarm file** is defined in [docs/handoffs.md](../docs/handoffs.md), section 4:
`$CLINICDRIFT_DATA/processed/alarms/<clinic_id>_<week>.json`, written by the engine. All its fields
are used as they are; rates are fractions from 0 to 1. `addons/fixtures/fake_alarm.json` is the example from handoffs.md.

**Optional extras.** Each one improves the output but nothing breaks without it:

| From | Used for | If missing |
|---|---|---|
| `processed/scans.parquet` rows for `flagged_scan_ids` and `reference_scan_ids` | brightness, sharpness, quality, width and `p_referable`, compared between the two sets | Cause is "unknown" with a note; drift and quality_mean are still reported |
| `processed/weekly.parquet` (`n_scans` for the clinic and week) | "too few scans" check and the report text | Check skipped |
| `clinicdrift.data.load_image(scan_id)` | Up to 2 flagged and 2 reference images sent to Gemini | No images sent |

Site and country come from the `clinic_id` prefix (`messidor2-a` -> Messidor-2, France). Device name and version are fixed in `incident_report.py`.

## Note

The incident report is a draft for a human to check. It is not submitted anywhere and is not
clinical or regulatory guidance.

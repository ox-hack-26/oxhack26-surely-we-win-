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
python -m addons.run_demo --all               # every alarm in $CLINICDRIFT_DATA/processed/alarms/ (else sample-data/alarms/)
python -m addons.run_demo --clinic US-WEAR-01 # one clinic's alarm: test on this, not --all
python -m pytest -q tests                     # offline, no keys needed
python -m addons.run_demo --clinic US-WEAR-01 --light  # also flash the Arduino light: see hardware/clinic_light/README.md
```

## Gemini quota

The free tier allows 20 requests a day and 5 a minute, and each alarm makes 2 calls (cause and
report), so `--all` uses 14. Every successful answer is saved in `addons/cache/` (git-ignored) and
reused the next time, keyed by clinic, week, model and the exact request; live calls are spaced 12 s
apart, and a 429 that asks to wait under 90 s, or a 503 (model busy), is retried once. If the model
is out of its daily quota (429), unavailable to your key (404) or still busy, the call moves on to the
next model in `GEMINI_FALLBACK_MODELS` (default `gemini-3.6-flash,gemini-3.5-flash,gemini-3.5-flash-lite`):
each model has its own daily free quota. Gemini 2.5 models return 404 for new keys, so don't use them. The run summary's `gemini_error`
says why Gemini wasn't used (e.g. `404 NOT_FOUND` for a wrong model name, `429 RESOURCE_EXHAUSTED`
for the quota).

- `--replay` uses saved answers only and never calls Gemini: use it for the live demo.
- `--live` always calls Gemini and overwrites the saved answer.

A saved answer from another model is used when the configured model has none for that request
(the log says which model); each saved file records the model that wrote it.

`sample-data/gemini/` is read the same way, so the demo can show real Gemini output on any machine
with no quota and no key. To fill it once there is quota:

```bash
python -m addons.run_demo --clinic US-WEAR-01   # check one alarm comes back from Gemini
python -m addons.run_demo --all                 # the other six (14 calls in total)
mkdir -p sample-data/gemini && cp addons/cache/*.json sample-data/gemini/
python -m addons.run_demo --all --replay        # check: every cause_source/report_source is gemini
```

Then commit `sample-data/gemini/`.

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

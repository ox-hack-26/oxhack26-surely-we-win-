# Hand-off formats

Everything lives in `$CLINICDRIFT_DATA/processed/`. Change a column here first, then tell whoever reads it. Until the real files exist, build against fake files with these exact columns.

## 1. `scans.parquet`: Sarah → Tejas (Sneha loads it into Tiger)

One row per scan, all four sources, plus the worn-camera copies the replay uses. Made by `python -m clinicdrift.data.score`, which writes it last, complete, after `features.npy` and `model.json`: the engine switches from the stand-in to these files as soon as `scans.parquet` exists. Run order: `clinicdrift.engine.replay`, then `clinicdrift.data.prepare`, `train` and `score`.

Start from `clinicdrift.data.sources.load_scans()`. It already has `scan_id`, `source`, `split`, `grade` and `referable`, plus `image_name`, `file` and `row_in_file` for finding the image; add the other columns. `load_image(scan_id)` in the same file returns any scan as a PIL image. Train only on `split == "train"` and tune on `val`. Never train on `test`: the replay uses those scans for the clinics that should stay quiet.

| Column | Type | Meaning |
| --- | --- | --- |
| `scan_id` | string | `<source>-<row number>`, e.g. `messidor2-00042`. Unique |
| `source` | string | `eyepacs`, `aptos`, `messidor2` or `idrid` |
| `split` | string | `train`, `val` or `test` for EyePACS, split by patient (70/10/20); `deploy` for the other three |
| `grade` | int 0–4 | Expert grade |
| `referable` | bool | `grade >= 2`: the patient must be referred |
| `wear` | float 0–1 | Camera wear applied to this copy; 0 for every untouched scan |
| `p_referable` | float 0–1 | Classifier's probability that the scan needs referral |
| `quality` | float 0–1 | Image quality: the worst of sharpness, contrast and exposure, scored against the EyePACS training scans. Median about 0.9 for training scans, 0.7 for the 224 px APTOS copies; falls week by week as a camera wears (about 0.7, 0.5, 0.4 … 0.2 for wear 0.07 to 1.0) |
| `brightness` | float 0–1 | Mean greyscale pixel value / 255, inside the retina (black surround left out) |
| `contrast` | float 0–1 | Standard deviation of greyscale pixels / 255, inside the retina |
| `sharpness` | float | Variance of the Laplacian inside the retina, measured after resizing the retina to 512 px so cameras compare fairly |
| `width`, `height` | int | Original size in pixels |

Worn-camera copies of scans have IDs like `eyepacs-01234@0.40`: the original scan, blurred and darkened to wear level 0.40 by `clinicdrift/data/degrade.py`. `load_image` returns them already worn, and they need their own rows (and a `wear` column, 0 for normal scans), because the model sees a different image. `clinicdrift.data.prepare` makes a row for every worn copy in `stream.parquet`, so re-run it (then `score`) after changing the replay. A worn copy keeps its original's `split`, `grade` and `referable`.

Image features go in `features.npy`: float16, shape `(n_rows, 768)`, one array with rows in the same order as `scans.parquet`. They are the classifier's pooled features, so they change with the things it looks at.

Until Sarah's files exist, `python -m clinicdrift.data.standin` writes a stand-in `scans.parquet`, `features.npy` (one array, same row order) and `model.json` under `processed/standin/`: frozen ImageNet ResNet-50 features plus a logistic regression, for the ~19,000 scans the engine needs. The engine switches to Sarah's files as soon as `processed/scans.parquet` exists.

When the classifier is trained, also write `model.json` with `referral_threshold`, the `p_referable` cut-off for referring a scan. Pick it on `val` so the model catches 90% of referable cases: screening would rather over-refer than miss sight-threatening disease. Add `val_sensitivity` and `val_specificity` at that threshold. `score.py` also adds `val_auc`, the same three on the held-out EyePACS `test` scans (`test_*`), and the calibration `temperature`. `python -m clinicdrift.data.report` writes the accuracy at each site to `docs/model-report.md`.

## 2. `stream.parquet` and `clinics.json`: Tejas's replay (Sneha loads them into Tiger)

Made by `python -m clinicdrift.engine.replay`. 10 simulated clinics see 9,500 scans over 20 weeks from 5 January 2026, each scan used once. About 10% of scans get an expert grade, 5 to 7 weeks after the scan. Each clinic's times and grades come from its own random stream, so adding a clinic changes no other clinic's data.

| Column | Type | Meaning |
| --- | --- | --- |
| `scan_id` | string | Joins to `scans.parquet` |
| `clinic_id` | string | Simulated clinic, e.g. `FR-MES-01` (country, site, number) |
| `source` | string | Dataset the scan came from |
| `week` | int | Week number, 1 = first week |
| `week_start` | date | Monday the week starts |
| `wear` | float 0–1 | Camera wear applied to this scan (0 for every clinic but `US-WEAR-01`) |
| `model_update` | bool | The faulty software update was running when this scan was judged (only `US-UPD-01`, from week 10): its referral cut-off is raised to one that catches only 70% of validation urgent cases |
| `ts` | timestamp | When the scan was taken (simulated, weekdays 08:00–18:00) |
| `graded_at` | timestamp or null | When its expert grade arrives. The engine must not use `grade` before this time |

`clinics.json` lists each clinic: `clinic_id`, `site`, `country`, `note`, `segments` (source and first week), `scans_per_week`, `switch_week` (null unless the clinic gets a new camera), `wear_from_week` (null unless its camera wears out) and `update_from_week` (null unless it gets the faulty update). The dashboard's clinic list comes from here; don't hard-code the clinics.

| Clinic | Scans | What should happen |
| --- | --- | --- |
| `US-EYE-01`, `US-EYE-02` | Held-out EyePACS, 50 a week | Same as training: the alarm stays quiet |
| `US-WEAR-01` | Held-out EyePACS; the camera wears from week 7 (blurrier and darker each week) | The main demo: the AI misses up to 9 urgent cases a week by week 20 while its own confidence says all is well; drift flags it by week 8–9 |
| `US-UPD-01` | Held-out EyePACS; a vendor update raises the referral cut-off from week 10 | The scans look the same, so drift stays quiet and watching drift never alarms; the catch rate drops and ClinicDrift raises a `harm` alarm (week 13 on the stand-in) |
| `SW-MES-01` | EyePACS, then Messidor-2 from week 9 | A new camera: the AI over-refers healthy patients rather than missing cases |
| `SW-APT-01` | EyePACS, then APTOS from week 11 | A second camera switch |
| `FR-MES-01` | Messidor-2 from day one | Different from the start |
| `IN-APT-01`, `IN-APT-02` | APTOS from day one | Different from the start |
| `IN-IDR-01` | IDRiD, 25 a week | Small clinic, wider uncertainty |

## 3. `weekly.parquet`: Tejas → Sneha

One row per clinic per week.

| Column | Type | Meaning |
| --- | --- | --- |
| `clinic_id` | string | |
| `week` | int | Week number, 1 = first week |
| `week_start` | date | Monday the week starts |
| `n_scans` | int | Scans that week |
| `est_sensitivity` | float 0–1 | Estimated share of referable cases the AI catches, from images alone |
| `est_low`, `est_high` | float 0–1 | 90% band around the estimate, wide enough to cover the catch rate the grades will show |
| `expected_cases` | float | Expected referable cases that week |
| `expected_missed` | float | Expected referable cases missed that week |
| `expected_false_referrals` | float | Expected healthy patients referred that week |
| `drift_auc` | float 0.5–1 | How easily a classifier tells this week's scans from training scans: about 0.5 = same as training, near 1 = clearly different |
| `lookalikes` | float | How many labelled reference cases resemble this week's scans (noisy; small = little evidence) |
| `quality_mean` | float 0–1 | Mean image quality |
| `referral_rate` | float 0–1 | Share of scans the model referred |
| `referral_threshold` | float 0–1 | The cut-off the clinic used that week (higher at `US-UPD-01` after its update) |
| `true_cases`, `true_sensitivity`, `true_missed`, `true_false_referrals` | | Hindsight from every expert grade. Only for the backtest and the dashboard's "real" line: a real clinic would not know these that week |
| `trust` | float 0–1 | How far the label-free estimate is trusted: 1 while `drift_auc` is under 0.7, 0 above 0.9 |
| `graded_cases`, `graded_caught` | int | Referable cases among the expert grades that have arrived by the end of the week (last 8 weeks of scans), and how many the AI referred |
| `catch_rate`, `catch_low`, `catch_high` | float 0–1 | **The engine's belief about the catch rate**, with a 90% band: the estimate, discounted by trust, plus the grades so far. Plot this as "our estimate" |
| `belief_cases`, `belief_missed` | float | Referable cases and missed cases that week under that belief |
| `expected_harm` | float £ | Expected extra harm of carrying on for the horizon (6 weeks) compared with validated performance |
| `p_below_standard` | float 0–1 | Belief that the catch rate is below 80%, the UK screening standard |
| `alarm_this_week` | bool | This week's decision on its own: `expected_harm > review cost`, and either `trust < 0.5` (drift) or `p_below_standard >= 0.9` (harm) |
| `alarm` | bool | Whether the AI is pulled for review. Once on it stays on until someone reviews it, so old grades can't switch it off |
| `alarm_reason` | string or null | `drift` (the scans no longer look validated, so the catch rate can't be verified) or `harm` (the scans look normal but we're 90% sure the catch rate is below 80%) |

`python -m clinicdrift.engine.estimate` writes the label-free columns to `weekly_estimates.parquet`; `python -m clinicdrift.engine.decide` adds the rest and writes `weekly.parquet`, the alarm files and `decision_settings.json` (costs and reference levels). Default costs are illustrative: £10,000 per missed referable case, £150 per unnecessary referral, £25,000 per review, 6-week horizon. For the cost sliders the dashboard can redo the decision from these columns: `expected_harm = 6 × (10,000 × belief_cases × (validated catch rate − catch_rate) + 150 × (referrals − catch_rate × belief_cases − usual false referrals))`, then apply the drift/harm test above, or just call `decide.run(Costs(...), write=False)`.

`python -m clinicdrift.engine.backtest` replays the 20 weeks under four policies (wait for grades, watch the estimate, watch drift, ClinicDrift) and writes `backtest.parquet`, `backtest_summary.json` and a review-cost sweep in `backtest_sweep.parquet`.

## 4. `alarms/<clinic_id>_week<week>.json`: Tejas → Vansh

One file per alarm, in the format Vansh's add-ons read (`Alarm` in `addons/alarm_schema.py`). Example values are made up:

```json
{
  "clinic_id": "FR-MES-01",
  "site": "Messidor-2",
  "country": "France",
  "week": 7,
  "week_start": "2026-03-02",
  "estimated_catch_rate": 0.71,
  "ci_low": 0.62,
  "ci_high": 0.79,
  "baseline_catch_rate": 0.89,
  "expected_missed_cases": 3.4,
  "expected_harm": 4200,
  "review_cost": 1500,
  "referral_threshold": 0.27,
  "flagged_scan_stats": {
    "n_scans": 64,
    "mean_brightness": 0.38,
    "mean_contrast": 0.21,
    "mean_sharpness": 0.44,
    "mean_quality": 0.58,
    "mean_resolution_px": 1440,
    "referral_score_mean": 0.19,
    "referral_rate": 0.14
  },
  "training_scan_stats": {
    "n_scans": 35000,
    "mean_brightness": 0.47,
    "mean_contrast": 0.27,
    "mean_sharpness": 0.71,
    "mean_quality": 0.81,
    "mean_resolution_px": 2592,
    "referral_score_mean": 0.27,
    "referral_rate": 0.22
  },
  "flagged_scan_ids": ["messidor2-00042", "messidor2-00057"],
  "reference_scan_ids": ["eyepacs-01234", "eyepacs-05678"]
}
```

| Field | Type | Meaning |
| --- | --- | --- |
| `clinic_id` | string | Same ID as in `stream.parquet` and `weekly.parquet` |
| `site` | string | Source dataset as people know it, e.g. `Messidor-2` |
| `country` | string | e.g. `France` |
| `week` | int | Week number since this clinic's replay started (1 = first week) |
| `week_start` | date string | Monday the week starts |
| `device_name`, `device_version` | string | Optional; the defaults describe our screening model |
| `estimated_catch_rate` | float 0–1 | Share of referable cases the AI is catching, estimated from images alone |
| `ci_low`, `ci_high` | float 0–1 | Uncertainty band around it. The alarm doesn't assume a confidence level |
| `baseline_catch_rate` | float 0–1 | Catch rate on held-out EyePACS scans |
| `expected_missed_cases` | float | Expected referable cases missed that week |
| `expected_harm` | float | `expected_missed_cases × cost_missed_case`, in the cost sliders' units |
| `review_cost` | float | Cost of pulling the AI for review, same units |
| `referral_threshold` | float 0–1 | `p_referable` cut-off for referring a scan, copied from `model.json` |
| `alarm_reason` | string | `drift` or `harm` (see `weekly.parquet`) |
| `drift_auc` | float 0.5–1 | That week's drift score |
| `flagged_scan_stats` | object | Stats for this clinic-week's scans (below) |
| `training_scan_stats` | object | The same stats for the EyePACS training scans |
| `flagged_scan_ids` | list of strings | This clinic-week's scans that look least like training |
| `reference_scan_ids` | list of strings | Typical training scans to compare against |
| `sample_scan_paths` | list of strings | In Vansh's model; leave empty. Scan IDs work on every machine: fetch the image with `clinicdrift.data.load_image(scan_id)` |

Each stats object (`ScanStats`) summarises the scans it describes, from `scans.parquet` columns:

| Field | Type | Meaning |
| --- | --- | --- |
| `n_scans` | int | Number of scans |
| `mean_brightness`, `mean_contrast` | float 0–1 | Means of `brightness` and `contrast` |
| `mean_sharpness` | float | Mean of `sharpness` |
| `mean_quality` | float 0–1 | Mean of `quality` |
| `mean_resolution_px` | float | Mean of `width` |
| `referral_score_mean` | float 0–1 | Mean of `p_referable` |
| `referral_rate` | float 0–1 | Share of scans the model refers: `p_referable >= referral_threshold` |

Gemini compares the flagged and training stats, and the scans themselves where it can, to name the likely cause. `estimated_catch_rate`, `ci_low`, `ci_high`, `expected_missed_cases` and `expected_harm` are `catch_rate`, `catch_low`, `catch_high`, `belief_missed` and `expected_harm` in `weekly.parquet` for that clinic and week. The engine writes one file per clinic, in the week its alarm starts.

**To do (Vansh):** add `flagged_scan_ids`, `reference_scan_ids` and `referral_threshold` to `Alarm`. Until then pydantic ignores them, so nothing breaks. Read the threshold from the alarm rather than hard-coding it; fall back to 0.5 only when it is missing.

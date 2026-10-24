# Hand-off formats

Everything lives in `$CLINICDRIFT_DATA/processed/`. Change a column here first, then tell whoever reads it. Until the real files exist, build against fake files with these exact columns.

## 1. `scans.parquet`: Sarah → Tejas (Sneha loads it into Tiger)

One row per scan, all four sources. Ship APTOS first so Tejas can start; `p_referable` can be empty until the classifier is trained.

Start from `clinicdrift.data.sources.load_scans()`. It already has `scan_id`, `source`, `split`, `grade` and `referable`, plus `image_name`, `file` and `row_in_file` for finding the image; add the other columns. `load_image(scan_id)` in the same file returns any scan as a PIL image. Train only on `split == "train"` and tune on `val`. Never train on `test`: the replay uses those scans for the clinics that should stay quiet.

| Column | Type | Meaning |
| --- | --- | --- |
| `scan_id` | string | `<source>-<row number>`, e.g. `messidor2-00042`. Unique |
| `source` | string | `eyepacs`, `aptos`, `messidor2` or `idrid` |
| `split` | string | `train`, `val` or `test` for EyePACS, split by patient (70/10/20); `deploy` for the other three |
| `grade` | int 0–4 | Expert grade |
| `referable` | bool | `grade >= 2`: the patient must be referred |
| `p_referable` | float 0–1 | Classifier's probability that the scan needs referral |
| `quality` | float 0–1 | Image quality score, higher is better |
| `brightness` | float 0–1 | Mean greyscale pixel value / 255 |
| `contrast` | float 0–1 | Standard deviation of greyscale pixels / 255 |
| `sharpness` | float | Variance of the Laplacian |
| `width`, `height` | int | Original size in pixels |

Worn-camera copies of scans have IDs like `eyepacs-01234@0.40`: the original scan, blurred and darkened to wear level 0.40 by `clinicdrift/data/degrade.py`. `load_image` returns them already worn, and they need their own rows (and a `wear` column, 0 for normal scans), because the model sees a different image.

Image features go in `features/<source>.npy`: float32, shape `(n_scans, d)`, rows in the same order as that source's rows in `scans.parquet`.

Until Sarah's files exist, `python -m clinicdrift.data.standin` writes a stand-in `scans.parquet`, `features.npy` (one array, same row order) and `model.json` under `processed/standin/`: frozen ImageNet ResNet-50 features plus a logistic regression, for the ~19,000 scans the engine needs. The engine switches to Sarah's files as soon as `processed/scans.parquet` exists.

When the classifier is trained, also write `model.json` with `referral_threshold`, the `p_referable` cut-off for referring a scan. Pick it on `val` so the model catches 90% of referable cases: screening would rather over-refer than miss sight-threatening disease. Add `val_sensitivity` and `val_specificity` at that threshold.

## 2. `stream.parquet` and `clinics.json`: Tejas's replay (Sneha loads them into Tiger)

Made by `python -m clinicdrift.engine.replay`. 9 simulated clinics see 8,500 scans over 20 weeks from 5 January 2026, each scan used once. About 10% of scans get an expert grade, 5 to 7 weeks after the scan.

| Column | Type | Meaning |
| --- | --- | --- |
| `scan_id` | string | Joins to `scans.parquet` |
| `clinic_id` | string | Simulated clinic, e.g. `FR-MES-01` (country, site, number) |
| `source` | string | Dataset the scan came from |
| `week` | int | Week number, 1 = first week |
| `week_start` | date | Monday the week starts |
| `wear` | float 0–1 | Camera wear applied to this scan (0 for every clinic but `US-WEAR-01`) |
| `ts` | timestamp | When the scan was taken (simulated, weekdays 08:00–18:00) |
| `graded_at` | timestamp or null | When its expert grade arrives. The engine must not use `grade` before this time |

`clinics.json` lists each clinic: `clinic_id`, `site`, `country`, `note`, `segments` (source and first week), `scans_per_week`, `switch_week` (null unless the clinic gets a new camera) and `wear_from_week` (null unless its camera wears out). The dashboard's clinic list comes from here.

| Clinic | Scans | What should happen |
| --- | --- | --- |
| `US-EYE-01`, `US-EYE-02` | Held-out EyePACS, 50 a week | Same as training: the alarm stays quiet |
| `US-WEAR-01` | Held-out EyePACS; the camera wears from week 7 (blurrier and darker each week) | The main demo: the AI misses up to 9 urgent cases a week by week 20 while its own confidence says all is well; drift flags it by week 8–9 |
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
| `true_cases`, `true_sensitivity`, `true_missed`, `true_false_referrals` | | Hindsight from every expert grade. Only for the backtest and the dashboard's "real" line: a real clinic would not know these that week |
| `alarm` | bool | Alarm at the default costs |

The engine writes everything except `alarm` to `weekly_estimates.parquet` now (`python -m clinicdrift.engine.estimate`); `weekly.parquet` adds `alarm` once the decision rule is in. The dashboard recomputes the alarm when the cost sliders move, so it needs the expected counts, not just the flag. Draft rule: alarm when `expected_missed × cost_missed_case + expected_false_referrals × cost_false_referral > cost_review`, or when `drift_auc` says the estimates can no longer be trusted.

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

Gemini compares the flagged and training stats, and the scans themselves where it can, to name the likely cause. `estimated_catch_rate`, `ci_low`, `ci_high` and `expected_missed_cases` are the same numbers as `est_sensitivity`, `est_low`, `est_high` and `expected_missed` in `weekly.parquet` for that clinic and week.

**To do (Vansh):** add `flagged_scan_ids`, `reference_scan_ids` and `referral_threshold` to `Alarm`. Until then pydantic ignores them, so nothing breaks. Read the threshold from the alarm rather than hard-coding it; fall back to 0.5 only when it is missing.

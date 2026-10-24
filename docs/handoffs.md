# Hand-off formats

Everything lives in `$CLINICDRIFT_DATA/processed/`. Change a column here first, then tell whoever reads it. Until the real files exist, build against fake files with these exact columns.

## 1. `scans.parquet`: Sarah → Tejas (Sneha loads it into Tiger)

One row per scan, all four sources. Ship APTOS first so Tejas can start; `p_referable` can be empty until the classifier is trained.

| Column | Type | Meaning |
| --- | --- | --- |
| `scan_id` | string | `<source>-<row number>`, e.g. `messidor2-00042`. Unique |
| `source` | string | `eyepacs`, `aptos`, `messidor2` or `idrid` |
| `split` | string | `train`, `val` or `test` for EyePACS; `deploy` for the other three |
| `grade` | int 0–4 | Expert grade |
| `referable` | bool | `grade >= 2`: the patient must be referred |
| `p_referable` | float 0–1 | Classifier's probability that the scan needs referral |
| `quality` | float 0–1 | Image quality score, higher is better |
| `brightness` | float 0–1 | Mean greyscale pixel value / 255 |
| `contrast` | float 0–1 | Standard deviation of greyscale pixels / 255 |
| `sharpness` | float | Variance of the Laplacian |
| `width`, `height` | int | Original size in pixels |

Image features go in `features/<source>.npy`: float32, shape `(n_scans, d)`, rows in the same order as that source's rows in `scans.parquet`.

Sarah also adds `clinicdrift.data.load_image(scan_id)` so Vansh can fetch any scan for Gemini.

## 2. `stream.parquet`: Tejas's replay (Sneha loads it into Tiger)

The deployment simulation: every `deploy` scan gets a clinic and a time.

| Column | Type | Meaning |
| --- | --- | --- |
| `scan_id` | string | Joins to `scans.parquet` |
| `clinic_id` | string | Simulated clinic, e.g. `FR-MES-03` (country, site, number) |
| `ts` | timestamp | When the scan was taken (simulated) |
| `graded_at` | timestamp or null | When its expert grade arrives. Only a sample of scans gets one, weeks later. The engine must not use `grade` before this time |

## 3. `weekly.parquet`: Tejas → Sneha

One row per clinic per week.

| Column | Type | Meaning |
| --- | --- | --- |
| `clinic_id` | string | |
| `week` | date | Monday the week starts |
| `n_scans` | int | Scans that week |
| `est_sensitivity` | float 0–1 | Estimated share of referable cases the AI catches, from images alone |
| `est_low`, `est_high` | float 0–1 | 90% band around the estimate |
| `true_sensitivity` | float or null | From expert grades that have arrived by then; null until there are enough |
| `expected_missed` | float | Expected referable cases missed that week |
| `drift` | float | How different that week's scans look from training (0 = same) |
| `quality_mean` | float | Mean image quality |
| `alarm` | bool | Alarm at the default costs |

The dashboard recomputes the alarm when the cost sliders move, so it needs `expected_missed`, not just the flag. Default rule: alarm when `expected_missed × cost_missed_case > cost_review`. Tejas may refine the rule; the columns stay.

## 4. `alarms/<clinic_id>_week<week>.json`: Tejas → Vansh

One file per alarm, in the format Vansh's add-ons read (`Alarm` in `addons/alarm_schema.py`). Example values are made up:

```json
{
  "clinic_id": "FR-MES-03",
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
| `referral_rate` | float 0–1 | Share of scans the model refers (`p_referable` at or above its operating threshold) |

Gemini compares the flagged and training stats, and the scans themselves where it can, to name the likely cause. `estimated_catch_rate`, `ci_low`, `ci_high` and `expected_missed_cases` are the same numbers as `est_sensitivity`, `est_low`, `est_high` and `expected_missed` in `weekly.parquet` for that clinic and week.

**To do (Vansh):** add `flagged_scan_ids` and `reference_scan_ids` to `Alarm`. Until then pydantic ignores them, so nothing breaks.

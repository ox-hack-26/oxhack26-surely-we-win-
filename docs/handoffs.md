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
| `brightness` | float | Mean pixel brightness, 0–255 |
| `sharpness` | float | Variance of the Laplacian |
| `width`, `height` | int | Original size in pixels |

Image features go in `features/<source>.npy`: float32, shape `(n_scans, d)`, rows in the same order as that source's rows in `scans.parquet`.

Sarah also adds `clinicdrift.data.load_image(scan_id)` so Vansh can fetch any scan for Gemini.

## 2. `stream.parquet`: Tejas's replay (Sneha loads it into Tiger)

The deployment simulation: every `deploy` scan gets a clinic and a time.

| Column | Type | Meaning |
| --- | --- | --- |
| `scan_id` | string | Joins to `scans.parquet` |
| `clinic_id` | string | Simulated clinic, e.g. `messidor2-a` |
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

## 4. `alarms/<clinic_id>_<week>.json`: Tejas → Vansh

One file per alarm. Example values are made up:

```json
{
  "clinic_id": "messidor2-a",
  "week": "2026-03-02",
  "est_sensitivity": 0.71,
  "est_low": 0.62,
  "est_high": 0.79,
  "baseline_sensitivity": 0.88,
  "expected_missed": 4.2,
  "drift": 0.37,
  "quality_mean": 0.54,
  "flagged_scan_ids": ["messidor2-00042", "messidor2-00057"],
  "reference_scan_ids": ["eyepacs-01234", "eyepacs-05678"]
}
```

`flagged_scan_ids` are this clinic's scans that look least like training; `reference_scan_ids` are typical training scans. Gemini compares the two sets to name the likely cause.

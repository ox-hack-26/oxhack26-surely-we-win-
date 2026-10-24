# Sample data

Small copies of the engine's outputs, for anyone without the 9.5 GB of scans. Column meanings are in [docs/handoffs.md](../docs/handoffs.md).

These come from the **stand-in** model, so the numbers will change when Sarah's model lands. Regenerate everything with:

```bash
python scripts/export_samples.py
```

| File | What it holds | Mainly for |
| --- | --- | --- |
| `clinics.json` | The 9 simulated clinics: site, country, note, camera switch or wear week | Sneha: clinic list |
| `stream.csv` | Every scan the clinics saw: clinic, week, time, camera wear, when its expert grade arrives | Sneha: Tiger `scan_events` |
| `scans.csv` | For those scans: model score, image quality, expert grade | Sneha: Tiger `scan_events` |
| `weekly.csv` | One row per clinic-week: estimates, belief with band, drift, expected harm, alarm | Sneha: charts |
| `decision_settings.json` | Default costs and the validated catch rate | Sneha: cost sliders |
| `model.json` | Referral threshold and validation scores | Vansh, Sneha |
| `alarms/*.json` | The 7 alarm files, one per clinic, in the add-ons' format | Vansh |
| `images/*.jpg` | 512 px copies of every scan the alarms point at, plus `eyepacs-15898` at wear 0, 0.25, 0.5, 0.75 and 1 | Vansh: Gemini; slides |
| `backtest.csv`, `backtest_summary.json`, `backtest_sweep.csv` | The four-policy backtest and the review-cost sweep, on one draw of the grades | Pitch, Devpost |
| `robustness_summary.json`, `robustness_sweep.csv` | The same across 100 redraws of the grades (30 per review cost): medians and ranges. **Quote these** | Sneha: results page; pitch |

## Before the repo goes public

The images come from EyePACS, APTOS 2019, Messidor-2 and IDRiD. Only IDRiD is clearly CC BY 4.0; the others are research datasets whose terms may not allow redistribution. That's fine while this repo is private. Before making it public for Devpost, delete `images/` or keep only the `idrid-*.jpg` files.

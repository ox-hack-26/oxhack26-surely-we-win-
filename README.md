# ClinicDrift

Predicts when an eye-screening AI has quietly got worse at a clinic, weeks before the expert grades arrive, and decides when to pull it for review. Built at OxHack 26 for the HRT "Best Use of Data for Predictions and Decision Making" prize.

## Team

| Person | Owns | Code |
| --- | --- | --- |
| Tejas | Prediction and decision engine | `clinicdrift/engine/` |
| Sarah | Data and model | `clinicdrift/data/`, `scripts/` |
| Sneha | Dashboard and database | `web/`, `db/` |
| Vansh | Alarm actions (Gemini, ElevenLabs) and pitch | `addons/` |

The files each person hands to the next are defined in [docs/handoffs.md](docs/handoffs.md). Change them there first, then tell whoever reads them.

## Setup

No scans on your machine? [`sample-data/`](sample-data/README.md) has the clinics, weekly results, alarm files and a few scans, so the dashboard and add-ons can work without downloading anything.

1. Pick a data folder **outside** OneDrive or Dropbox. The scans are about 9.5 GB and syncing them would eat the wifi.
2. Copy `.env.example` to `.env` and set `CLINICDRIFT_DATA` to that folder. Put your API keys in `.env` too; it is never committed.
3. Download the scans. This needs only plain Python, no installs, and can be re-run to resume:

   ```bash
   python scripts/download_data.py
   ```

   Smallest first: IDRiD, APTOS, Messidor-2, then EyePACS (6.5 GB). Pass names to fetch only some, e.g. `python scripts/download_data.py aptos idrid`.
4. For everything else, make a virtual environment (also outside OneDrive) and `pip install -r requirements.txt`. The add-ons have their own `requirements-addons.txt`.
5. Real model (Sarah, needs a GPU): `python -m clinicdrift.engine.replay`, then `python -m clinicdrift.data.prepare`, `train`, `score` and `report`. Until `score` has run, the engine uses the stand-in.
6. Run the engine on whichever model is in place: `python -m clinicdrift.engine.pipeline` checks the model's files fit the replay, then reruns estimate, decide, backtest, `docs/results.md` and `sample-data/` in one go. `--check` only checks and prints the replay fingerprint, which must match on any two machines that swap model files.

## Layout

```
clinicdrift/
  config.py      where the data folder is; reads .env
  data/          Sarah: image quality, image features, classifier
    sources.py   the shared scan list (scan IDs, splits, grades) and load_image
    degrade.py   simulated camera wear (blur + darkening) for the US-WEAR-01 clinic
    prepare.py   crop every scan to the retina, measure quality: python -m clinicdrift.data.prepare
    train.py     fine-tune the referral classifier on EyePACS: python -m clinicdrift.data.train
    score.py     p_referable, features.npy, model.json, scans.parquet: python -m clinicdrift.data.score
    report.py    the accuracy drop at each site: python -m clinicdrift.data.report
    standin.py   stand-in model until Sarah's lands: python -m clinicdrift.data.standin
  engine/        Tejas: run these in order
    replay.py    simulated clinics: python -m clinicdrift.engine.replay
    estimate.py  label-free catch rate and drift per clinic-week
    decide.py    drift-aware belief, grades as they arrive, cost-loss alarm, alarm files
    backtest.py  four monitoring policies compared, plus a review-cost sweep
    results.py   writes docs/results.md, the one source for pitch and Devpost numbers
    charts.py    slide charts in docs/charts/, drawn from the same outputs
    pipeline.py  checks the model files fit, then runs all of the above: python -m clinicdrift.engine.pipeline
addons/          Vansh: Gemini cause-finding and report, ElevenLabs alert (see addons/README.md)
db/schema.sql    Sneha: Tiger Data tables
docs/            hand-off formats
sample-data/     small copies of the outputs for teammates without the scans
scripts/         downloads; export_samples.py refreshes sample-data/
web/             Sneha: dashboard
```

## Data credits

All four are research datasets, used here through Hugging Face re-uploads. Credit the originals:

| Source | Original | Mirror used |
| --- | --- | --- |
| EyePACS (US) | Kaggle Diabetic Retinopathy Detection (2015), EyePACS | [bumbledeep/eyepacs](https://huggingface.co/datasets/bumbledeep/eyepacs) |
| APTOS 2019 (India) | Kaggle APTOS 2019 Blindness Detection, Aravind Eye Hospital | [bumbledeep/aptos](https://huggingface.co/datasets/bumbledeep/aptos) |
| Messidor-2 (France) | Messidor-2, LaTIM and the Messidor program partners | [sngsfydy/Messidor2](https://huggingface.co/datasets/sngsfydy/Messidor2) |
| IDRiD (India) | Indian Diabetic Retinopathy Image Dataset (2018) | [amin-nejad/idrid-disease-grading](https://huggingface.co/datasets/amin-nejad/idrid-disease-grading) |

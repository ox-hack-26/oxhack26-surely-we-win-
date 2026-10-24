# ClinicDrift

Predicts when an eye-screening AI has quietly got worse at a clinic, weeks before the expert grades arrive, and decides when to pull it for review. Built at OxHack 26 for the HRT "Best Use of Data for Predictions and Decision Making" prize.

## Team

| Person | Owns | Code |
| --- | --- | --- |
| Tejas | Prediction and decision engine | `clinicdrift/engine/` |
| Sarah | Data and model | `clinicdrift/data/`, `scripts/` |
| Sneha | Dashboard and database | `web/`, `db/` |
| Vansh | Alarm actions (Gemini, ElevenLabs) and pitch | `clinicdrift/actions/` |

The files each person hands to the next are defined in [docs/handoffs.md](docs/handoffs.md). Change them there first, then tell whoever reads them.

## Setup

1. Pick a data folder **outside** OneDrive or Dropbox. The scans are about 9.5 GB and syncing them would eat the wifi.
2. Copy `.env.example` to `.env` and set `CLINICDRIFT_DATA` to that folder. Put your API keys in `.env` too; it is never committed.
3. Download the scans. This needs only plain Python, no installs, and can be re-run to resume:

   ```bash
   python scripts/download_data.py
   ```

   Smallest first: IDRiD, APTOS, Messidor-2, then EyePACS (6.5 GB). Pass names to fetch only some, e.g. `python scripts/download_data.py aptos idrid`.
4. For everything else, make a virtual environment (also outside OneDrive) and `pip install -r requirements.txt`.

## Layout

```
clinicdrift/
  config.py      where the data folder is; reads .env
  data/          Sarah: load scans, image quality, image features, classifier
  engine/        Tejas: catch-rate estimate, alarm rule, replay, backtest
  actions/       Vansh: Gemini cause-finding and report, ElevenLabs alert
db/schema.sql    Sneha: Tiger Data tables
docs/            hand-off formats
scripts/         one-off scripts (downloads)
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

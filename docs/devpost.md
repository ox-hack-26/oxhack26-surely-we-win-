# ClinicDrift (Devpost draft)

> Draft. Numbers are copied from `docs/results.md` (and `sample-data/`), which come from the
> **stand-in model** (ImageNet ResNet-50 features + logistic regression, validation AUC 0.78). After
> Sarah's model lands, rerun `python -m clinicdrift.engine.pipeline` and update every number here
> from the new `docs/results.md`. Remaining [TBD]s need a decision from the team.

## Try it out

Code: https://github.com/ox-hack-26/oxhack26-surely-we-win-

The alarm demo runs from a fresh clone with **no API keys**: it replays saved Gemini answers from
`sample-data/gemini/` and reads the sample alarms in `sample-data/`, so there is nothing to download.

```bash
git clone -b vansh/addons https://github.com/ox-hack-26/oxhack26-surely-we-win-.git
cd oxhack26-surely-we-win-
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -r requirements-addons.txt
python -m addons.run_demo --clinic US-WEAR-01 --replay   # the worn-camera alarm
python -m addons.run_demo --all --replay                 # all 8 alarms
python -m pytest -q tests                                # 58 offline tests
```

Each run prints the likely cause and a short alert script, and writes the cause and the draft
incident report to `addons/out/`.

The dashboard also starts with no keys. It reads the engine's replay results from `sample-data/`
(no longer synthetic):

```bash
pip install -r dashboard/requirements.txt
cd dashboard
streamlit run app.py
```

## Images for the gallery

Upload these from `docs/charts/` (1920×1080, numbers match `docs/results.md`; pull dev again before
submitting, as they're redrawn when the model changes):

1. `1-camera-wear.png`: the AI's own estimate stays near 94% while the real catch rate falls to 36% by week 20
2. `2-software-update.png`: drift stays silent while the catch rate falls from 90% to 67%
3. `3-backtest.png`: only ClinicDrift caught all 8 failures
4. `4-cost-sweep.png`: cheapest way to monitor while a review costs up to £25k

## Inspiration

AI that screens retinal photos for diabetic retinopathy is validated once, then deployed to many
clinics with different cameras, staff and patients. When it starts missing disease at one clinic,
nobody finds out until expert grades come back, 5 to 7 weeks later and for only about 10% of scans.
We wanted each clinic to get an
early warning, and a clear decision about what to do.

## What it does

- **Predict:** for every clinic, every week, ClinicDrift estimates the screening AI's catch rate
  (sensitivity for referable disease) from the images alone, before any expert grades arrive.
- **Decide:** it raises an alarm only when the expected harm of missed cases is greater than the cost
  of sending that clinic's scans for human review. A *drift* alarm fires when the scans stop looking
  like the validated ones; a *harm* alarm fires when the scans look normal but it is 90% sure the
  catch rate is below the 80% UK screening standard (for example after a faulty software update).
- **Act:** when an alarm fires, Gemini suggests the likely cause and drafts an MHRA-style incident
  report tagged with MIT AI Risk Repository categories, and writes a short alert script for the clinic
  lead (as text; voicing it is future work).

## How we built it

- **Training data:** EyePACS (US).
- **Deployment clinics:** APTOS 2019 (India), Messidor-2 (France), IDRiD (India), split into
  simulated clinics and weeks.
- **Storage:** Tiger Data: a `scan_events` hypertable, a real-time continuous aggregate and the engine's
  weekly results (`db/migrations/`, `clinicdrift/db/tiger.py`, [docs/tiger.md](tiger.md)). Verified on a local
  TimescaleDB 2.31; [TBD: confirm on the Tiger Cloud service]. Without a database the results are CSV files in
  `sample-data/`.
- **Cause finding and reports:** Gemini, with rule-based and template fallbacks so the demo works offline.
- **Alert script:** a short text alert per alarm (`addons/voice_alert.py`); voicing it is future work.
- **Dashboard:** Streamlit and Plotly (`dashboard/`), reading the engine's weekly replay results from
  the CSVs in `sample-data/`.

## Challenges we ran into

- **The AI's own confidence is fooled.** At the worn-camera clinic the AI's own estimate stayed near
  94% while the real catch rate fell to 36% by week 20 (it averaged 66% over weeks 15–20). We had to
  make the decision rule stop trusting the estimate once the scans drift away from what the AI was
  validated on.
- **Expert grades arrive late and are few.** Only about 10% of scans get a grade, 5 to 7 weeks later,
  so a clinic of 50 scans a week has only a handful of graded urgent cases to go on.
- **Wording.** On a drift alarm the catch rate can't be verified, so the reports and the alert script
  must not quote one. We test that every drift output stays silent on it.
- **Keeping it running offline.** Every Gemini step has a rule-based or template
  fallback, which carried the demo when the Gemini free-tier quota ran out.

## Accomplishments that we're proud of

- Alarms raised / true drops caught / false alarms: we reran the backtest over 100 random draws of
  which scans get an expert grade and when. ClinicDrift caught **all 8** clinics whose conditions
  changed in **100% of draws**, with a false alarm in **0% of draws**, and a median of **8.2 extra
  urgent cases missed** (2.0–12.5 across 90% of draws). Waiting for expert grades caught a median of
  0 of 8 (at most 2), raised a false alarm in 28% of draws and let a median of 49.2 extra urgent cases
  through (median total cost £282k versus £555k at the default costs).
- Weeks of warning before expert grades would have shown the drop: ClinicDrift alarmed in the same
  week as the change (median), against a median of 12 weeks for waiting on grades. At the worn-camera
  clinic the AI's own estimate stayed near 94% while the real catch rate fell to 36% by week 20, and
  ClinicDrift alarmed in week 9 (weeks 8–9 across draws), seven weeks before the collapse (week 16);
  in the main run waiting for grades never flagged it within the 20 weeks.
- A failure drift can't see: at the faulty-software-update clinic (US-UPD-01) the vendor raised the
  referral cut-off in week 10 (0.060 → 0.175). The scans look exactly the same, so drift stayed at
  0.50 on average and watching drift never alarmed, while the real catch rate fell from 90% to 67%.
  ClinicDrift raised a harm alarm a median of 6 weeks after the update (weeks 12–17 across draws),
  once it was 90% sure the catch rate was below 80%.
- Catch-rate estimate error versus true catch rate: on the 73 clinic-weeks without a change, the
  label-free estimate was off by 0.078 on average (7.8 points) and the real value was inside its 90%
  band 95% of the time. Under heavy drift the estimate is not reliable (at the worn-camera clinic it
  averaged 94% over weeks 15–20, while the real catch rate averaged 66% over weeks 15–20), which is
  why drift drives the alarm.

## What we learned

The public datasets have no demographic labels, so any fairness claims we make are about clinics and
cameras, not about patient groups.

- A model can be confidently wrong: its own estimate of how well it is doing is the first thing to
  break when the images change.
- Drift was the reliable signal for changes to the scans: none of the 73 clinic-weeks without a change
  scored above 0.7, and 6 of 7 changes to the scans scored above 0.8 in their first week. But no single
  signal catches everything: watching drift missed the software update and watching the estimate
  missed 7 of 8 changes; ClinicDrift, which uses both, missed none.
- Putting a cost on missed cases and on reviews turns "is the AI still OK?" into a decision a clinic
  lead can act on and argue with.

## What's next

- Replace the stand-in with the fine-tuned referral model and regenerate every number.
- Test on real clinic data with real camera changes, not simulated ones.
- Let clinics set their own costs in the dashboard and see the decision change.
- Feed reviewed alarms back in, so a cause confirmed by a human improves the next suggestion.

## Prizes

### HRT: Best Use of Data for Predictions & Decision Making
ClinicDrift turns unlabelled images into a per-clinic catch-rate prediction with an uncertainty band,
then makes an explicit decision: pause and review when expected harm exceeds review cost.
Results: across 4 monitoring policies replayed over 20 weeks at 10 clinics, and 100 draws of the
expert grades, ClinicDrift was the only one to catch all 8 changes (in every draw), with no false
alarms, the fewest extra missed cases (median 8.2) and the lowest total cost (median £282k; watching
drift alone £382k, watching the estimate £381k, waiting for grades £555k).
The costs are illustrative, so we swept the cost of a review from £5k to £100k: ClinicDrift raised no
false alarms at any review cost and is the cheapest policy while a review costs up to £25k. Above that
it is not: at £50k it is still cheaper than waiting for grades (£482k against £555k), but watching the
estimate is cheapest (£406k), and at £100k ClinicDrift costs more than waiting for grades (£925k
against £563k), because several clinics that changed were actually fine.

### Best Use of Gemini
Gemini looks at a flagged clinic's scan statistics and sample images to suggest a likely cause with
evidence and checks, then drafts the incident report a human would otherwise write from scratch.
Results: Gemini (gemini-3.5-flash-lite, and gemini-3.5-flash for one cause) named the cause and
rewrote the incident report for all 8 alarms from the replay, looking at 2 flagged and 2 typical
training scans for each. It sees only the clinic id, country and numbers: no site description, dataset
name or scan id, which would give the simulated answer away (a test checks this). For the 7 drift
alarms it named camera or image quality (confidence 0.95), matching the rule-based check, and added
practical checks such as cleaning the lens and checking focus; none of those reports quoted a catch
rate, which can't be verified on a drift alarm. For the faulty software update it did not find the
real cause: like the rule-based check, it suggested a change in patient mix (confidence 0.45), because
nothing in the scans themselves points to the update. The answers are saved in `sample-data/gemini/`,
so the demo replays them with no API quota.

### Best Use of Tiger Data
Every scan the simulated clinics take goes into a Tiger hypertable keyed on its event time, with the
model's score, the cut-off in force and, weeks later, the expert grade with the time it arrived. A
real-time continuous aggregate keeps per-clinic daily totals, so a new scan shows up the moment it is
written, and the dashboard rolls it up with `time_bucket` for any clinic and week range. Because grades
carry their arrival time, one query answers "what had the experts confirmed by this week?" without
using the future, and it matches the engine's own count. The scan hypertable is converted to Tiger's
columnstore: 14.9 MB to 4.5 MB (3.3x) on our 19,000 rows. Ingestion is idempotent, so re-running the
pipeline (`python -m clinicdrift.engine.pipeline --tiger`) never duplicates a scan. Details and the demo
sequence: [docs/tiger.md](tiger.md).
[TBD: these runs are on a local TimescaleDB 2.31; repeat on the Tiger Cloud service and update the numbers]

## Data and credits

- EyePACS diabetic retinopathy dataset
- APTOS 2019 Blindness Detection dataset
- Messidor-2
- IDRiD (Indian Diabetic Retinopathy Image Dataset)
- MHRA AI Airlock Phase 2 report (June 2026)
- MIT AI Risk Repository

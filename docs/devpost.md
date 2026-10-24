# ClinicDrift (Devpost draft)

> Draft. Numbers are copied from `docs/results.md` (and `sample-data/`), which come from the
> **stand-in model** (ImageNet ResNet-50 features + logistic regression, validation AUC 0.78). After
> Sarah's model lands, rerun `python -m clinicdrift.engine.pipeline` and update every number here
> from the new `docs/results.md`. Remaining [TBD]s need a decision from the team.

## Inspiration

AI that screens retinal photos for diabetic retinopathy is validated once, then deployed to many
clinics with different cameras, staff and patients. When it starts missing disease at one clinic,
nobody finds out until expert grades come back, often weeks later. We wanted each clinic to get an
early warning, and a clear decision about what to do.

## What it does

- **Predict:** for every clinic, every week, ClinicDrift estimates the screening AI's catch rate
  (sensitivity for referable disease) from the images alone, before any expert grades arrive.
- **Decide:** it raises an alarm only when the expected harm of missed cases is greater than the cost
  of sending that clinic's scans for human review.
- **Act:** when an alarm fires, Gemini suggests the likely cause and drafts an MHRA-style incident
  report tagged with MIT AI Risk Repository categories, and ElevenLabs reads a short spoken alert to
  the clinic lead.

## How we built it

- **Training data:** EyePACS (US).
- **Deployment clinics:** APTOS 2019 (India), Messidor-2 (France), IDRiD (India), split into
  simulated clinics and weeks.
- **Storage:** per-clinic, per-week results in Tiger Data.
- **Cause finding and reports:** Gemini, with rule-based and template fallbacks so the demo works offline.
- **Spoken alerts:** ElevenLabs text to speech.
- **Dashboard:** Streamlit and Plotly (`dashboard/`), reading weekly results from Tiger Cloud, with an
  explicit mock mode that is labelled as synthetic.

## Challenges we ran into

- **The AI's own confidence is fooled.** At the worn-camera clinic the label-free estimate stayed
  around 94% while the real catch rate fell to 66% (36% in the last week). We had to make the decision
  rule stop trusting the estimate once the scans drift away from what the AI was validated on.
- **Expert grades arrive late and are few.** Only about 10% of scans get a grade, 5 to 7 weeks later,
  so a clinic of 50 scans a week has only a handful of graded urgent cases to go on.
- **Wording.** On a drift alarm the catch rate can't be verified, so the reports and the spoken alert
  must not quote one. We test that every drift output stays silent on it.
- **Keeping it running offline.** Every Gemini and ElevenLabs step has a rule-based or template
  fallback, which carried the demo when the Gemini free-tier quota ran out.

## Accomplishments that we're proud of

- Alarms raised / true drops caught / false alarms: ClinicDrift caught **7 of 7** clinics whose
  conditions changed, with **0 false alarms** across the 64 clinic-weeks without a change, and
  **0 extra urgent cases missed**. Waiting for expert grades caught 1 of 7 and let 29.3 extra urgent
  cases through (total cost £175k versus £377k at the default costs).
- Weeks of warning before expert grades would have shown the drop: ClinicDrift alarmed in the same
  week as the change (median), against a median of 12 weeks for waiting on grades. At the worn-camera
  clinic it alarmed in week 9, 7 weeks before the catch rate collapsed (week 16); waiting for grades
  never flagged it within the 20 weeks.
- Catch-rate estimate error versus true catch rate: on clinic-weeks whose scans still look like
  training (drift score under 0.7), the label-free estimate was within 7.7 points of the real catch
  rate on average (65 clinic-weeks, computed from `sample-data/weekly.csv`; with about 10 urgent cases
  a week, much of that is noise in the real rate itself). Under heavy drift the estimate is not
  reliable, which is why drift drives the alarm.

## What we learned

The public datasets have no demographic labels, so any fairness claims we make are about clinics and
cameras, not about patient groups.

- A model can be confidently wrong: its own estimate of how well it is doing is the first thing to
  break when the images change.
- Drift was the reliable signal here: no clinic-week without a change scored above 0.7, and 6 of 7
  changes scored above 0.8 in their first week.
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
Results: across 4 monitoring policies replayed over 20 weeks at 9 clinics, ClinicDrift was the only
one with every change caught, no false alarms and no extra missed cases, at the lowest total cost
(£175k; watching drift alone £184k, waiting for grades £377k, watching the estimate £356k).

### Best Use of Gemini
Gemini looks at a flagged clinic's scan statistics and sample images to suggest a likely cause with
evidence and checks, then drafts the incident report a human would otherwise write from scratch.
Results: Gemini (gemini-3.6-flash) named the cause and rewrote the incident report for all 7
alarms from the replay, looking at 2 flagged and 2 typical training scans for each. Every cause it gave
agreed with the rule-based check (camera or image quality, confidence 0.75 to 0.9) and added practical
checks for the clinic; none of the reports quoted a catch rate, which can't be verified on a drift
alarm. The answers are saved in `sample-data/gemini/`, so the demo replays them with no API quota.

### Best Use of ElevenLabs
A spoken alert of under 25 seconds tells a busy clinic lead what changed, why, and the first thing to check.
Results: [TBD: not tested yet, no ElevenLabs key set. The alert scripts are written and tested
offline; without a key the add-ons skip the audio.]

### Best Use of Tiger Data
Scan events go into a Tiger (TimescaleDB) hypertable keyed on time, with a continuous aggregate that
rolls them up per clinic-week (`db/schema.sql`); the dashboard reads its weekly monitoring table from
Tiger Cloud. [TBD: confirm the live tables are loaded before submitting.]

### Best Use of Vultr
[TBD: only include if Sarah's model/backend actually runs on Vultr]

## Data and credits

- EyePACS diabetic retinopathy dataset
- APTOS 2019 Blindness Detection dataset
- Messidor-2
- IDRiD (Indian Diabetic Retinopathy Image Dataset)
- MHRA AI Airlock Phase 2 report (June 2026)
- MIT AI Risk Repository

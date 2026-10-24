# ClinicDrift (Devpost draft)

> Draft. Every [TBD] must be replaced with a measured result before submission.

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
- **Dashboard:** [TBD]

## Challenges we ran into

[TBD]

## Accomplishments that we're proud of

- Catch-rate estimate error versus true catch rate: [TBD]
- Weeks of warning before expert grades would have shown the drop: [TBD]
- Alarms raised / true drops caught / false alarms: [TBD]

## What we learned

The public datasets have no demographic labels, so any fairness claims we make are about clinics and
cameras, not about patient groups.

[TBD]

## What's next

[TBD]

## Prizes

### HRT: Best Use of Data for Predictions & Decision Making
ClinicDrift turns unlabelled images into a per-clinic catch-rate prediction with an uncertainty band,
then makes an explicit decision: pause and review when expected harm exceeds review cost.
Results: [TBD]

### Best Use of Gemini
Gemini looks at a flagged clinic's scan statistics and sample images to suggest a likely cause with
evidence and checks, then drafts the incident report a human would otherwise write from scratch.
Results: [TBD]

### Best Use of ElevenLabs
A spoken alert of under 25 seconds tells a busy clinic lead what changed, why, and the first thing to check.
Results: [TBD]

### Best Use of Tiger Data
[TBD]

### Best Use of Vultr
[TBD: only include if Sarah's model/backend actually runs on Vultr]

## Data and credits

- EyePACS diabetic retinopathy dataset
- APTOS 2019 Blindness Detection dataset
- Messidor-2
- IDRiD (Indian Diabetic Retinopathy Image Dataset)
- MHRA AI Airlock Phase 2 report (June 2026)
- MIT AI Risk Repository

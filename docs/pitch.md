# ClinicDrift pitch (3 minutes)

Every number below is from `docs/results.md` and the charts in `docs/charts/`, which come from the
**stand-in model**. When Sarah's model runs through the pipeline the charts are redrawn and the
numbers may change: pull dev again, re-read `docs/results.md` and update this script before the final run.

## Slide 1: The problem (20 s)

**On the slide:** "An eye-screening AI is validated once. Then it goes to 100 clinics."

> Diabetic eye screening increasingly uses AI to decide who gets referred. It's validated once, then
> deployed to clinics with different cameras and software. When it starts missing disease at one
> clinic, nobody finds out until expert grades come back, 5 to 7 weeks later, and only for about 1 scan in 10.

## Slide 2: The AI fools itself (40 s)

**Chart:** `docs/charts/1-camera-wear.png`

> This clinic's camera starts wearing out in week 7. Orange is the AI's own confidence: it stays near
> 94%. Red is the real catch rate, which nobody knows for weeks: it falls to 36%. The bottom panel is
> drift: how different this week's scans look from the validated ones. It jumps in week 8, and
> ClinicDrift raises the alarm in week 9, 7 weeks before the catch rate collapses. Waiting for expert
> grades never flags it at all within the 20 weeks.

## Slide 3: The failure drift can't see (30 s)

**Chart:** `docs/charts/2-software-update.png`

> Not every failure shows in the images. Here a vendor update in week 10 raises the referral cut-off.
> The scans look exactly the same, so drift stays flat and a drift monitor never fires. But the catch
> rate falls from 90% to 67%. ClinicDrift combines the label-free estimate with the few grades that
> have arrived, and in week 13, once it is 90% sure the catch rate is below the 80% UK screening
> standard, it raises a harm alarm.

## Slide 4: It's a decision, not a dashboard (30 s)

**Chart:** `docs/charts/3-backtest.png`

> We replayed 20 weeks at 10 clinics under four ways of monitoring. Every alarm is a decision: pull
> the AI for review only when the expected harm of missed cases is bigger than the cost of the review.
> ClinicDrift caught all 8 failures, with zero false alarms and 2.3 extra missed urgent cases.
> Today's practice, waiting for grades, caught 2 and let 33 through. £223k against £440k.

(If asked about the costs: `docs/charts/4-cost-sweep.png`. It stays cheapest while a review costs up to
£25k, and raised no false alarms at any review cost.)

## Slide 5: What happens when it fires (40 s, live)

**Live demo:** `python -m addons.run_demo --clinic US-WEAR-01 --replay --light`, with the Arduino on the table.

> When the alarm fires, the clinic lead needs to know what to do. Gemini looks at the flagged scans
> next to typical training scans and names the likely cause, here camera or image quality, with
> checks to run. It drafts an MHRA-style incident report, tagged with the MIT AI Risk Repository. And
> the clinic gets a signal it can't miss.

Point at the Arduino as it switches to the fast ALARM blink. Backup if the board fails:
`python -m addons.status_light --replay --clinic US-WEAR-01 --delay 0.5` prints the same weeks.

## Slide 6: Honest limits and next steps (20 s)

> This is a stand-in model on real public scans, but the clinics, camera wear and the update are
> simulated, and the costs are illustrative. The datasets carry no demographics, so we make no
> fairness claims about patients. Next: the fine-tuned model, real clinic data, and clinics setting
> their own costs.

## Before you present

- [ ] `git pull` dev, then check that the slide numbers match `docs/results.md`
- [ ] Arduino uploaded, Serial Monitor closed, replay tested on this laptop
- [ ] `run_demo --replay` rehearsed (no wifi or quota needed)
- [ ] Each chart opens full screen (they're 1920×1080)

## Likely judge questions

Short, honest answers. Numbers are from `docs/results.md`; recheck them if the model changes.

- **How can you estimate the catch rate without labels?** The model's scores are recalibrated on
  labelled validation scans, so each score is the chance that scan is referable. Added up over a
  week, they say how many referable cases there were and how many sat above the referral cut-off.
  That only holds while the scans look like the calibration scans, so every week we also check drift.
- **What is drift, exactly?** A classifier tries to tell this week's scans from training scans. Its
  cross-validated AUC is the drift score: 0.5 means indistinguishable, 1.0 trivially different.
  None of the 73 clinic-weeks without a change scored above 0.7.
- **How does the decision work?** The belief about the catch rate combines the label-free estimate,
  discounted as drift rises from 0.7 to 0.9, with whatever expert grades have arrived. We alarm when
  the expected harm over the next 6 weeks is bigger than the cost of a review, and either the scans
  have drifted or we are 90% sure the catch rate is below the 80% UK screening standard.
- **Why not just watch drift?** It misses failures that don't change the images: at the software
  update clinic drift stayed near 0.50 and watching drift never alarmed (7 of 8 caught).
- **Why not just watch the AI's own estimate?** It's fooled by bad images: at the worn-camera clinic
  it stayed near 94% while the real catch rate fell to 36% by week 20 (1 of 8 caught).
- **Why did you alarm 3 weeks late on the software update?** By design: a harm alarm needs 90%
  certainty that the catch rate is below 80%. Without that test, a few unlucky grades pulled healthy clinics.
- **Aren't the costs made up?** Yes, they're illustrative, so we swept the review cost from £5k to
  £100k. No false alarms at any cost; cheapest policy up to £25k; at £100k it costs more than waiting
  for grades (£829k against £590k). A clinic would set its own costs.
- **Is this real data?** Real public retinal scans (EyePACS, Messidor-2, APTOS, IDRiD), but the 10
  clinics, the camera wear and the update are simulated, and the model is a stand-in (validation AUC
  0.78). The datasets have no demographics, so we make no fairness claims about patients.
- **Does Gemini just guess?** It sees the scan statistics and 2 flagged plus 2 training scans. On all
  7 drift alarms its cause matched our rule-based check (camera or image quality). On the software
  update it named the update, but the clinic's description mentions it, so we don't count that one.
- **What would you need for a real deployment?** The fine-tuned model, real clinic data with real
  camera changes, and clinics setting their own costs; then a human review loop feeding back confirmed causes.

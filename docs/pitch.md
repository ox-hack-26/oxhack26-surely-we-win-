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

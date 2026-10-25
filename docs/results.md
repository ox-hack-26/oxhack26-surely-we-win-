# ClinicDrift results

Generated 25 October 2026 by `python -m clinicdrift.engine.results` from the engine's outputs. Model: **convnext_tiny.in12k_ft_in1k_384 fine-tuned on EyePACS train at 448 px**. Quote numbers from this file only, and regenerate it after the model or replay changes.

Slide charts made from the same outputs: [camera wear](charts/1-camera-wear.png), [software update](charts/2-software-update.png), [backtest](charts/3-backtest.png), [cost sweep](charts/4-cost-sweep.png).

## Headline

At the default costs (£10k per missed urgent case, £150 per unnecessary referral, £25k per review), replaying 20 weeks at 10 simulated clinics:

- **ClinicDrift caught all 8 clinics whose conditions changed in 100% of 100 draws of the expert grades**, with a false alarm in 0% of draws. It let a median of **1.0 extra urgent cases** through (90% of draws: 0.6–13.4); median total cost £210k.
- **Waiting for expert grades** (today's practice) caught a median of 0 of 8 (at most 2), raised a false alarm in 18% of draws, and let a median of **29.6 extra urgent cases** through; median total cost £489k.
- **The demo clinic US-WEAR-01**: its camera starts wearing out in week 7. ClinicDrift raises the alarm in week 8 (weeks 8–8 across draws of the grades). In the main run waiting for grades never flags it within the 20 weeks, and 11 extra urgent cases are missed.
- **A faulty software update** (US-UPD-01): in week 10 the vendor raises the referral cut-off (0.083 → 0.486). The scans look exactly the same, so drift stays at 0.52 on average and **watching drift never alarms**. The real catch rate falls from 88% to 71%. ClinicDrift raises a harm alarm a median of 2 weeks after the update (weeks 11–18 across 100 draws of the grades), once it is 80% sure the catch rate is below the 80% screening standard.
- **No single signal catches everything**: watching drift missed 1 of the 8 changes and watching the estimate missed 6; ClinicDrift, which uses both, missed 0.
- **The AI's own estimate was close but slow to act**: in weeks 15–20 at US-WEAR-01 it averaged 80% against a real 81%, yet watching it only raised an alarm in week 16: its weekly dips are too small and noisy to act on alone, while drift flagged the wear within a week.
- **Drift is reliable here**: none of the 73 clinic-weeks without a change scored above 0.7 (highest 0.65); 6 of 7 changes to the scans themselves scored above 0.8 in their first week, and US-WEAR-01's slow wear crossed 0.8 in week 8 (wear 0.14, barely visible).

## What the numbers come from

| Source | Scans scored | Used for |
| --- | --- | --- |
| eyepacs | 24,718 (train) | training |
| eyepacs | 3,401 (val) | validation: threshold and calibration |
| eyepacs | 7,689 (test) | held-out scans for the quiet clinics, the switch clinics' early weeks and US-WEAR-01 (worn copies included) |
| messidor2 | 1,744 | deployment clinics |
| aptos | 3,662 | deployment clinics (this copy is 224 px: a low-resolution test, not a population one) |
| idrid | 516 | deployment clinic |

- **Replay**: 10 clinics, 20 weeks from 5 January 2026, 9,500 scans, each used once. 10% of scans get an expert grade, 35–49 days later.
- **Model**: validation AUC 0.91; at the referral threshold (0.083) it catches 90% of urgent cases and clears 71% of healthy scans on validation.
- **Costs** are illustrative, and the decision horizon is 6 weeks (how long a problem runs before grades show it).

## Across 100 draws of the expert grades

Which scans get graded, and how late, is luck, and grades feed both ClinicDrift and the wait-for-grades policy. So the backtest was rerun 100 times with every clinic's grades redrawn (`robustness.py`); the scans, the model and the label-free estimates stay fixed. **Quote these numbers, not the single run below.**

| Policy | Draws catching all changes | Changes caught, median (range) | Draws with a false alarm | Median weeks to alarm | Extra urgent cases missed, median (90% of draws) | Total cost, median (90% of draws) |
| --- | --- | --- | --- | --- | --- | --- |
| wait for grades | 0% | 0 (0–2) | 18% | 9 | 29.6 (23.1–29.6) | £489k (£462k–£514k) |
| watch estimate | 0% | 2 (2–2) | 0% | 4.5 | 6.7 (6.7–6.7) | £302k (£302k–£302k) |
| watch drift | 0% | 7 (7–7) | 0% | 1 | 19.8 (19.8–19.8) | £385k (£385k–£385k) |
| ClinicDrift | 100% | 8 (8–8) | 0% | 0 | 1.0 (0.6–13.4) | £210k (£206k–£334k) |

ClinicDrift's first alarm per clinic across the draws (– = never):

| Clinic | Changed in week | Draws with an alarm | First alarm week, median (90% of draws) |
| --- | --- | --- | --- |
| FR-MES-01 | 1 | 100% | 1 (1–1) |
| IN-APT-01 | 1 | 100% | 1 (1–1) |
| IN-APT-02 | 1 | 100% | 1 (1–1) |
| IN-IDR-01 | 1 | 100% | 1 (1–1) |
| SW-APT-01 | 11 | 100% | 11 (11–11) |
| SW-MES-01 | 9 | 100% | 9 (9–9) |
| US-EYE-01 | no change | 0% | – |
| US-EYE-02 | no change | 0% | – |
| US-UPD-01 | 10 | 100% | 12 (11–18) |
| US-WEAR-01 | 7 | 100% | 8 (8–8) |

## One run in detail: the replay's own grades

A single draw of the grades, so a little lucky or unlucky; the section above gives the ranges.

| Policy | Changes caught | False alarms | Median weeks to alarm | Extra urgent cases missed | Total cost |
| --- | --- | --- | --- | --- | --- |
| wait for grades | 0 of 8 | 0 | – | 29.6 | £489k |
| watch estimate | 2 of 8 | 0 | 4.5 | 6.7 | £302k |
| watch drift | 7 of 8 | 0 | 1 | 19.8 | £385k |
| ClinicDrift | 8 of 8 | 0 | 0 | 1 | £210k |

Policies: **wait for grades** alarms when the graded catch rate over 8 weeks is 15 points below validated (at least 5 graded urgent cases); **watch estimate** when the label-free estimate is 10 points below; **watch drift** when drift stays above 0.8 for two weeks; **ClinicDrift** (`decide.py`) raises a *drift* alarm when the scans stop looking validated and a *harm* alarm when it is 80% sure the catch rate is below the 80% UK screening standard, each only if the expected harm outweighs a review. A first alarm pulls the AI for review; harm counts from the change until then.

First alarm week per clinic (– = never):

| Clinic | Changed in week | wait for grades | watch estimate | watch drift | ClinicDrift |
| --- | --- | --- | --- | --- | --- |
| FR-MES-01 | 1 | – | – | 2 | 1 |
| IN-APT-01 | 1 | – | – | 2 | 1 |
| IN-APT-02 | 1 | – | – | 2 | 1 |
| IN-IDR-01 | 1 | – | – | 2 | 1 |
| SW-APT-01 | 11 | – | – | 12 | 11 |
| SW-MES-01 | 9 | – | – | 10 | 9 |
| US-EYE-01 | no change | – | – | – | – |
| US-EYE-02 | no change | – | – | – | – |
| US-UPD-01 | 10 | – | 10 | – | 12 |
| US-WEAR-01 | 7 | – | 16 | 9 | 8 |

## US-WEAR-01, week by week

The camera wears from week 7: scans get blurrier and darker. "Real" uses every expert grade in hindsight; a clinic would not know it that week.

| Week | Wear | Real catch rate | AI's own estimate | ClinicDrift belief (band) | Drift | Quality | Urgent cases missed | Alarm |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 0.00 | 80% | 92% | 92% (79%–99%) | 0.45 | 0.88 | 2 of 10 |  |
| 2 | 0.00 | 88% | 85% | 89% (77%–98%) | 0.52 | 0.89 | 1 of 8 |  |
| 3 | 0.00 | 100% | 89% | 89% (79%–97%) | 0.58 | 0.86 | 0 of 6 |  |
| 4 | 0.00 | 91% | 88% | 88% (77%–96%) | 0.54 | 0.87 | 1 of 11 |  |
| 5 | 0.00 | 100% | 91% | 90% (80%–97%) | 0.48 | 0.91 | 0 of 8 |  |
| 6 | 0.00 | 100% | 93% | 91% (83%–97%) | 0.51 | 0.90 | 0 of 10 |  |
| 7 | 0.07 | 91% | 90% | 92% (85%–98%) | 0.66 | 0.73 | 1 of 11 |  |
| 8 | 0.14 | 75% | 85% | 86% (61%–99%) | 0.99 | 0.46 | 3 of 12 | **ALARM** |
| 9 | 0.21 | 100% | 91% | 80% (47%–99%) | 1.00 | 0.37 | 0 of 5 | **ALARM** |
| 10 | 0.29 | 86% | 95% | 75% (37%–98%) | 1.00 | 0.35 | 2 of 14 | **ALARM** |
| 11 | 0.36 | 73% | 87% | 80% (47%–99%) | 1.00 | 0.32 | 3 of 11 | **ALARM** |
| 12 | 0.43 | 92% | 92% | 83% (55%–99%) | 1.00 | 0.31 | 1 of 12 | **ALARM** |
| 13 | 0.50 | 92% | 94% | 83% (55%–99%) | 1.00 | 0.28 | 1 of 12 | **ALARM** |
| 14 | 0.57 | 86% | 73% | 67% (22%–97%) | 1.00 | 0.27 | 1 of 7 | **ALARM** |
| 15 | 0.64 | 75% | 81% | 50% (5%–95%) | 1.00 | 0.26 | 3 of 12 | **ALARM** |
| 16 | 0.71 | 85% | 83% | 75% (37%–98%) | 1.00 | 0.26 | 2 of 13 | **ALARM** |
| 17 | 0.79 | 85% | 80% | 86% (61%–99%) | 1.00 | 0.24 | 2 of 13 | **ALARM** |
| 18 | 0.86 | 80% | 72% | 75% (37%–98%) | 1.00 | 0.25 | 2 of 10 | **ALARM** |
| 19 | 0.93 | 82% | 79% | 80% (47%–99%) | 1.00 | 0.24 | 2 of 11 | **ALARM** |
| 20 | 1.00 | 79% | 87% | 67% (22%–97%) | 1.00 | 0.23 | 3 of 14 | **ALARM** |

## How good is the label-free estimate?

| Clinic-weeks | Count | Mean error (catch rate) | Real value inside its 90% band |
| --- | --- | --- | --- |
| No change | 73 | 0.071 | 99% |
| After a change | 127 | 0.029 | 100% |
| US-WEAR-01 weeks 15–20 | 6 | 0.051 | 100% |

## How much the made-up costs matter

Total cost by what one review costs, other costs fixed (median over 30 draws of the grades per review cost).

| Review cost | Policy | Changes caught | False alarms | Extra urgent cases missed | Total cost |
| --- | --- | --- | --- | --- | --- |
| £5k | wait for grades | 0 of 8 | 0 | 29.6 | £489k |
| £5k | watch estimate | 2 of 8 | 0 | 6.7 | £262k |
| £5k | watch drift | 7 of 8 | 0 | 19.8 | £245k |
| £5k | ClinicDrift | 8 of 8 | 0 | 1.0 | £50k |
| £10k | wait for grades | 0 of 8 | 0 | 29.6 | £489k |
| £10k | watch estimate | 2 of 8 | 0 | 6.7 | £272k |
| £10k | watch drift | 7 of 8 | 0 | 19.8 | £280k |
| £10k | ClinicDrift | 8 of 8 | 0 | 1.0 | £90k |
| £25k | wait for grades | 0 of 8 | 0 | 29.6 | £489k |
| £25k | watch estimate | 2 of 8 | 0 | 6.7 | £302k |
| £25k | watch drift | 7 of 8 | 0 | 19.8 | £385k |
| £25k | ClinicDrift | 8 of 8 | 0 | 1.0 | £210k |
| £50k | wait for grades | 0 of 8 | 0 | 29.6 | £489k |
| £50k | watch estimate | 2 of 8 | 0 | 6.7 | £352k |
| £50k | watch drift | 7 of 8 | 0 | 19.8 | £560k |
| £50k | ClinicDrift | 8 of 8 | 0 | 1.0 | £410k |
| £100k | wait for grades | 0 of 8 | 0 | 29.6 | £489k |
| £100k | watch estimate | 2 of 8 | 0 | 6.7 | £452k |
| £100k | watch drift | 7 of 8 | 0 | 19.8 | £910k |
| £100k | ClinicDrift | 8 of 8 | 0 | 1.9 | £821k |

## Honest caveats

- **Model**: convnext_tiny.in12k_ft_in1k_384 fine-tuned on EyePACS train at 448 px. Numbers will change when it changes; regenerate this file.
- **Simulated clinics**: real public scans, but the clinics, camera switches and wear are simulated. The datasets carry no age, sex or ethnicity, so make no fairness claims about patient groups, only about clinics and cameras. This APTOS copy is 224 px, so the APTOS clinics test low resolution, not Indian patients.
- **Costs are illustrative**: across review costs from £5k to £100k ClinicDrift raised no false alarms, and at £100k reviewing every changed clinic cost more than waiting for grades, because several of those clinics were actually fine (see the sweep).
- **The evidence test costs time**: ClinicDrift only raises a harm alarm once it is 80% sure the catch rate is below 80%, so on the software update it waits 2 weeks (median) where watching the estimate alarms at once. Most of ClinicDrift's missed cases come from that wait. It is the price of not pulling a healthy AI over a few weeks of noise: without the test, a handful of low grades was enough to pull healthy clinics.
- **The evidence bar was lowered after the first real-model run**: it was 90% on the stand-in model, set to stop false alarms. With the trained model, 90% held the software-update alarm back to week 19 although ClinicDrift's belief that the clinic was below standard sat at 72–87% from week 11. We lowered it to 80%, which raised that alarm in week 12 and still gave no false alarm in any redraw of the grades. Treat the backtest above as tuned on this replay, not as a fresh test.
- **The 80% floor** is the long-standing UK (Exeter / British Diabetic Association) standard of at least 80% sensitivity for diabetic eye screening.
- **A new camera doesn't always mean missed cases**: at SW-MES-01 the new camera moved this model's catch rate 92% → 100% and its healthy referrals 13 → 17 a week. The missed cases came from the worn camera (US-WEAR-01) and the faulty update (US-UPD-01).
- **The belief band** describes the clinic's underlying catch rate. A single week has only about 10 urgent cases, so that week's real value often falls outside it; don't present it as a 90% interval for one week. The label-free estimate's band is the one checked against weekly values above.
- **Drift alarms say "can't verify", not "X% caught"**: when drift triggers the alarm the belief is pulled towards 50% with a very wide band (exactly 50% at clinics that differ from day one, before any grades). Say the AI is outside its validated conditions; don't quote that number as a measured drop.
- **Late grades can mislead**: at US-WEAR-01 the belief creeps back up in the later weeks because the grades arriving then are for scans taken 5–7 weeks earlier, when wear was milder. That is why an alarm stays on until someone reviews the AI: without that, old grades would switch it off just as harm peaks.
- **Full wear is obvious**: at wear 1.0 any grader would reject the scans. The point is that drift fired at low wear, when the scans still look normal.
- **Small**: 10 clinics and 20 weeks. The expert grades were redrawn 100 times, but the scans, the clinics and the camera changes are one replay. "Real" values use every expert grade in hindsight.

## Regenerate

```bash
python -m clinicdrift.engine.replay
python -m clinicdrift.engine.estimate
python -m clinicdrift.engine.decide
python -m clinicdrift.engine.backtest
python -m clinicdrift.engine.robustness
python -m clinicdrift.engine.results
python -m clinicdrift.engine.charts
```

or all of it, after checking the model files fit: `python -m clinicdrift.engine.pipeline`.

Inputs read from `processed`.

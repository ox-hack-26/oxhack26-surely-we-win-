# ClinicDrift results

Generated 24 October 2026 by `python -m clinicdrift.engine.results` from the engine's outputs. Model: **stand-in: ImageNet ResNet-50 features + logistic regression**. Quote numbers from this file only, and regenerate it after the model or replay changes.

## Headline

At the default costs (£10k per missed urgent case, £150 per unnecessary referral, £25k per review), replaying 20 weeks at 9 simulated clinics:

- **ClinicDrift caught 7 of 7 clinics whose conditions changed**, in the same week as the change (median), with **0 false alarms** and **0 extra urgent cases missed**. Total cost £175k.
- **Waiting for expert grades** (today's practice) caught 1 of 7, a median of 12 weeks after the change, and let **29.3 extra urgent cases** through. Total cost £377k.
- **The demo clinic US-WEAR-01**: its camera starts wearing out in week 7. ClinicDrift raises the alarm in week 9, 7 weeks before the catch rate collapses (week 16). Waiting for grades never flags it within the 20 weeks, and 19 extra urgent cases are missed.
- **The AI's own confidence is fooled**: in weeks 15–20 at US-WEAR-01 the label-free estimate averaged 94% while the real catch rate averaged 66% (36% in week 20). That is why the decision rule stops trusting the estimate when drift is high.
- **Drift is reliable here**: none of the 64 clinic-weeks without a change scored above 0.7 (highest 0.66); 6 of 7 changes scored above 0.8 in their first week, and US-WEAR-01's slow wear crossed 0.8 in week 8 (wear 0.14, barely visible).

## What the numbers come from

| Source | Scans scored | Used for |
| --- | --- | --- |
| eyepacs | 8,000 (train) | training (sample) |
| eyepacs | 3,401 (val) | validation: threshold and calibration |
| eyepacs | 3,900 (test) | held-out scans for the quiet clinics, the switch clinics' early weeks and US-WEAR-01 (worn copies included) |
| messidor2 | 1,600 | deployment clinics |
| aptos | 2,500 | deployment clinics (this copy is 224 px: a low-resolution test, not a population one) |
| idrid | 500 | deployment clinic |

- **Replay**: 9 clinics, 20 weeks from 5 January 2026, 8,500 scans, each used once. 10% of scans get an expert grade, 35–49 days later.
- **Model**: validation AUC 0.78; at the referral threshold (0.060) it catches 90% of urgent cases and clears 35% of healthy scans on validation.
- **Costs** are illustrative, and the decision horizon is 6 weeks (how long a problem runs before grades show it).

## Backtest: four ways to monitor

| Policy | Changes caught | False alarms | Median weeks to alarm | Extra urgent cases missed | Total cost |
| --- | --- | --- | --- | --- | --- |
| wait for grades | 1 of 7 | 0 | 12 | 29.3 | £377k |
| watch estimate | 0 of 7 | 0 | – | 29.3 | £356k |
| watch drift | 7 of 7 | 0 | 1 | 0.5 | £184k |
| ClinicDrift | 7 of 7 | 0 | 0 | 0 | £175k |

Policies: **wait for grades** alarms when the graded catch rate over 8 weeks is 15 points below validated (at least 5 graded urgent cases); **watch estimate** when the label-free estimate is 10 points below; **watch drift** when drift stays above 0.8 for two weeks; **ClinicDrift** is the cost-loss rule in `decide.py`. A first alarm pulls the AI for review; harm counts from the change until then.

First alarm week per clinic (– = never):

| Clinic | Changed in week | wait for grades | watch estimate | watch drift | ClinicDrift |
| --- | --- | --- | --- | --- | --- |
| FR-MES-01 | 1 | – | – | 2 | 1 |
| IN-APT-01 | 1 | – | – | 2 | 1 |
| IN-APT-02 | 1 | 13 | – | 2 | 1 |
| IN-IDR-01 | 1 | – | – | 2 | 1 |
| SW-APT-01 | 11 | – | – | 12 | 11 |
| SW-MES-01 | 9 | – | – | 10 | 9 |
| US-EYE-01 | no change | – | – | – | – |
| US-EYE-02 | no change | – | – | – | – |
| US-WEAR-01 | 7 | – | – | 9 | 9 |

## US-WEAR-01, week by week

The camera wears from week 7: scans get blurrier and darker. "Real" uses every expert grade in hindsight; a clinic would not know it that week.

| Week | Wear | Real catch rate | AI's own estimate | ClinicDrift belief (band) | Drift | Quality | Urgent cases missed | Alarm |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 0.00 | 100% | 90% | 90% (71%–99%) | 0.66 | 0.51 | 0 of 10 |  |
| 2 | 0.00 | 88% | 93% | 92% (81%–99%) | 0.58 | 0.49 | 1 of 8 |  |
| 3 | 0.00 | 83% | 91% | 92% (83%–98%) | 0.51 | 0.46 | 1 of 6 |  |
| 4 | 0.00 | 73% | 88% | 91% (82%–97%) | 0.56 | 0.49 | 3 of 11 |  |
| 5 | 0.00 | 88% | 85% | 88% (77%–96%) | 0.53 | 0.51 | 1 of 8 |  |
| 6 | 0.00 | 90% | 92% | 89% (78%–96%) | 0.54 | 0.51 | 1 of 10 |  |
| 7 | 0.07 | 91% | 88% | 89% (79%–97%) | 0.56 | 0.31 | 1 of 11 |  |
| 8 | 0.14 | 92% | 93% | 90% (62%–100%) | 0.81 | 0.26 | 1 of 12 |  |
| 9 | 0.21 | 80% | 93% | 75% (37%–98%) | 0.96 | 0.21 | 1 of 5 | **ALARM** |
| 10 | 0.29 | 86% | 95% | 75% (37%–98%) | 1.00 | 0.20 | 2 of 14 | **ALARM** |
| 11 | 0.36 | 100% | 96% | 80% (47%–99%) | 1.00 | 0.20 | 0 of 11 | **ALARM** |
| 12 | 0.43 | 92% | 98% | 71% (42%–94%) | 1.00 | 0.18 | 1 of 12 | **ALARM** |
| 13 | 0.50 | 92% | 99% | 67% (34%–92%) | 1.00 | 0.17 | 1 of 12 | **ALARM** |
| 14 | 0.57 | 86% | 97% | 83% (55%–99%) | 1.00 | 0.13 | 1 of 7 | **ALARM** |
| 15 | 0.64 | 92% | 98% | 83% (55%–99%) | 1.00 | 0.12 | 1 of 12 | **ALARM** |
| 16 | 0.71 | 69% | 93% | 86% (61%–99%) | 1.00 | 0.13 | 4 of 13 | **ALARM** |
| 17 | 0.79 | 85% | 95% | 89% (69%–99%) | 1.00 | 0.11 | 2 of 13 | **ALARM** |
| 18 | 0.86 | 60% | 94% | 88% (65%–99%) | 1.00 | 0.12 | 4 of 10 | **ALARM** |
| 19 | 0.93 | 55% | 91% | 86% (61%–99%) | 1.00 | 0.10 | 5 of 11 | **ALARM** |
| 20 | 1.00 | 36% | 91% | 75% (37%–98%) | 1.00 | 0.06 | 9 of 14 | **ALARM** |

## How good is the label-free estimate?

| Clinic-weeks | Count | Mean error (catch rate) | Real value inside its 90% band |
| --- | --- | --- | --- |
| No change | 64 | 0.078 | 94% |
| After a change | 116 | 0.054 | 84% |
| US-WEAR-01 weeks 15–20 | 6 | 0.278 | 17% |

## How much the made-up costs matter

| Review cost | Policy | Changes caught | False alarms | Extra urgent cases missed | Total cost |
| --- | --- | --- | --- | --- | --- |
| £5k | wait for grades | 1 of 7 | 0 | 29.3 | £357k |
| £5k | watch estimate | 0 of 7 | 0 | 29.3 | £356k |
| £5k | watch drift | 7 of 7 | 0 | 0.5 | £44k |
| £5k | ClinicDrift | 5 of 7 | 4 | 0 | £45k |
| £10k | wait for grades | 1 of 7 | 0 | 29.3 | £362k |
| £10k | watch estimate | 0 of 7 | 0 | 29.3 | £356k |
| £10k | watch drift | 7 of 7 | 0 | 0.5 | £79k |
| £10k | ClinicDrift | 7 of 7 | 2 | 0 | £90k |
| £25k | wait for grades | 1 of 7 | 0 | 29.3 | £377k |
| £25k | watch estimate | 0 of 7 | 0 | 29.3 | £356k |
| £25k | watch drift | 7 of 7 | 0 | 0.5 | £184k |
| £25k | ClinicDrift | 7 of 7 | 0 | 0 | £175k |
| £50k | wait for grades | 1 of 7 | 0 | 29.3 | £402k |
| £50k | watch estimate | 0 of 7 | 0 | 29.3 | £356k |
| £50k | watch drift | 7 of 7 | 0 | 0.5 | £359k |
| £50k | ClinicDrift | 7 of 7 | 0 | 0 | £350k |
| £100k | wait for grades | 1 of 7 | 0 | 29.3 | £452k |
| £100k | watch estimate | 0 of 7 | 0 | 29.3 | £356k |
| £100k | watch drift | 7 of 7 | 0 | 0.5 | £709k |
| £100k | ClinicDrift | 7 of 7 | 0 | 0.5 | £709k |

## Honest caveats

- **Model**: stand-in: ImageNet ResNet-50 features + logistic regression. Numbers will change when it changes; regenerate this file.
- **Simulated clinics**: real public scans, but the clinics, camera switches and wear are simulated. The datasets carry no age, sex or ethnicity, so make no fairness claims about patient groups, only about clinics and cameras. This APTOS copy is 224 px, so the APTOS clinics test low resolution, not Indian patients.
- **Costs are illustrative**: cheap reviews make the rule raise false alarms on noise, and very expensive reviews make checking every drifted clinic cost more than waiting (see the sweep).
- **Watching drift alone does almost as well here**, because every harmful change in this replay also changed how the scans look. ClinicDrift adds a decision priced in pounds, alarms a week sooner than a two-week drift rule, and folds in grades as they arrive. A change that harms without showing in the images is untested.
- **New camera vs worn camera**: at SW-MES-01 the new camera made this model refer more healthy patients (27 → 31 a week) rather than miss urgent cases. Only the worn camera produced missed cases.
- **The belief band** describes the clinic's underlying catch rate. A single week has only about 10 urgent cases, so that week's real value often falls outside it; don't present it as a 90% interval for one week. The label-free estimate's band is the one checked against weekly values above.
- **Drift alarms say "can't verify", not "X% caught"**: when drift triggers the alarm the belief is pulled towards 50% with a very wide band (exactly 50% at clinics that differ from day one, before any grades). Say the AI is outside its validated conditions; don't quote that number as a measured drop.
- **Late grades can mislead**: at US-WEAR-01 the belief creeps back up in the later weeks because the grades arriving then are for scans taken 5–7 weeks earlier, when wear was milder. That is why an alarm stays on until someone reviews the AI: without that, old grades would switch it off just as harm peaks.
- **Full wear is obvious**: at wear 1.0 any grader would reject the scans. The point is that drift fired at low wear, when the scans still look normal.
- **Small**: 9 clinics, 20 weeks, one replay seed. "Real" values use every expert grade in hindsight.

## Regenerate

```bash
python -m clinicdrift.engine.replay
python -m clinicdrift.engine.estimate
python -m clinicdrift.engine.decide
python -m clinicdrift.engine.backtest
python -m clinicdrift.engine.results
```

Inputs read from `processed/standin`.

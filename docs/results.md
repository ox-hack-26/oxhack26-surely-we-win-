# ClinicDrift results

Generated 24 October 2026 by `python -m clinicdrift.engine.results` from the engine's outputs. Model: **stand-in: ImageNet ResNet-50 features + logistic regression**. Quote numbers from this file only, and regenerate it after the model or replay changes.

## Headline

At the default costs (£10k per missed urgent case, £150 per unnecessary referral, £25k per review), replaying 20 weeks at 10 simulated clinics:

- **ClinicDrift caught 8 of 8 clinics whose conditions changed**, in the same week as the change (median), with **0 false alarms** and **2.3 extra urgent cases missed**. Total cost £223k.
- **Waiting for expert grades** (today's practice) caught 2 of 8, a median of 6 weeks after the change, and let **33.3 extra urgent cases** through. Total cost £440k.
- **The demo clinic US-WEAR-01**: its camera starts wearing out in week 7. ClinicDrift raises the alarm in week 9, 7 weeks before the catch rate collapses (week 16). Waiting for grades never flags it within the 20 weeks, and 19 extra urgent cases are missed.
- **A faulty software update** (US-UPD-01): in week 10 the vendor raises the referral cut-off (0.060 → 0.175). The scans look exactly the same, so drift stays at 0.50 on average and **watching drift never alarms**. The real catch rate falls from 90% to 67%. ClinicDrift raises a harm alarm in week 13, once it is 90% sure the catch rate is below the 80% screening standard.
- **No single signal catches everything**: watching drift missed 1 of the 8 changes and watching the estimate missed 7; ClinicDrift, which uses both, missed 0.
- **The AI's own confidence is fooled**: in weeks 15–20 at US-WEAR-01 the label-free estimate averaged 94% while the real catch rate averaged 66% (36% in week 20). That is why the decision rule stops trusting the estimate when drift is high.
- **Drift is reliable here**: none of the 73 clinic-weeks without a change scored above 0.7 (highest 0.67); 6 of 7 changes to the scans themselves scored above 0.8 in their first week, and US-WEAR-01's slow wear crossed 0.8 in week 8 (wear 0.14, barely visible).

## What the numbers come from

| Source | Scans scored | Used for |
| --- | --- | --- |
| eyepacs | 8,000 (train) | training |
| eyepacs | 3,401 (val) | validation: threshold and calibration |
| eyepacs | 4,900 (test) | held-out scans for the quiet clinics, the switch clinics' early weeks and US-WEAR-01 (worn copies included) |
| messidor2 | 1,600 | deployment clinics |
| aptos | 2,500 | deployment clinics (this copy is 224 px: a low-resolution test, not a population one) |
| idrid | 500 | deployment clinic |

- **Replay**: 10 clinics, 20 weeks from 5 January 2026, 9,500 scans, each used once. 10% of scans get an expert grade, 35–49 days later.
- **Model**: validation AUC 0.78; at the referral threshold (0.060) it catches 90% of urgent cases and clears 35% of healthy scans on validation.
- **Costs** are illustrative, and the decision horizon is 6 weeks (how long a problem runs before grades show it).

## Backtest: four ways to monitor

| Policy | Changes caught | False alarms | Median weeks to alarm | Extra urgent cases missed | Total cost |
| --- | --- | --- | --- | --- | --- |
| wait for grades | 2 of 8 | 0 | 6 | 33.3 | £440k |
| watch estimate | 1 of 8 | 0 | 0 | 29.3 | £382k |
| watch drift | 7 of 8 | 0 | 1 | 20.3 | £382k |
| ClinicDrift | 8 of 8 | 0 | 0 | 2.3 | £223k |

Policies: **wait for grades** alarms when the graded catch rate over 8 weeks is 15 points below validated (at least 5 graded urgent cases); **watch estimate** when the label-free estimate is 10 points below; **watch drift** when drift stays above 0.8 for two weeks; **ClinicDrift** (`decide.py`) raises a *drift* alarm when the scans stop looking validated and a *harm* alarm when it is 90% sure the catch rate is below the 80% UK screening standard, each only if the expected harm outweighs a review. A first alarm pulls the AI for review; harm counts from the change until then.

First alarm week per clinic (– = never):

| Clinic | Changed in week | wait for grades | watch estimate | watch drift | ClinicDrift |
| --- | --- | --- | --- | --- | --- |
| FR-MES-01 | 1 | – | – | 2 | 1 |
| IN-APT-01 | 1 | – | – | 2 | 1 |
| IN-APT-02 | 1 | 9 | – | 2 | 1 |
| IN-IDR-01 | 1 | – | – | 2 | 1 |
| SW-APT-01 | 11 | – | – | 12 | 11 |
| SW-MES-01 | 9 | – | – | 10 | 9 |
| US-EYE-01 | no change | – | – | – | – |
| US-EYE-02 | no change | – | – | – | – |
| US-UPD-01 | 10 | 14 | 10 | – | 13 |
| US-WEAR-01 | 7 | – | – | 9 | 9 |

## US-WEAR-01, week by week

The camera wears from week 7: scans get blurrier and darker. "Real" uses every expert grade in hindsight; a clinic would not know it that week.

| Week | Wear | Real catch rate | AI's own estimate | ClinicDrift belief (band) | Drift | Quality | Urgent cases missed | Alarm |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 0.00 | 100% | 90% | 90% (75%–99%) | 0.67 | 0.51 | 0 of 10 |  |
| 2 | 0.00 | 88% | 93% | 92% (82%–98%) | 0.54 | 0.49 | 1 of 8 |  |
| 3 | 0.00 | 83% | 91% | 92% (84%–97%) | 0.56 | 0.46 | 1 of 6 |  |
| 4 | 0.00 | 73% | 88% | 91% (82%–97%) | 0.54 | 0.49 | 3 of 11 |  |
| 5 | 0.00 | 88% | 85% | 88% (78%–96%) | 0.55 | 0.51 | 1 of 8 |  |
| 6 | 0.00 | 90% | 92% | 89% (78%–96%) | 0.52 | 0.51 | 1 of 10 |  |
| 7 | 0.07 | 91% | 88% | 90% (80%–97%) | 0.55 | 0.31 | 1 of 11 |  |
| 8 | 0.14 | 92% | 93% | 92% (71%–100%) | 0.83 | 0.26 | 1 of 12 |  |
| 9 | 0.21 | 80% | 93% | 80% (47%–99%) | 0.96 | 0.21 | 1 of 5 | **ALARM** |
| 10 | 0.29 | 86% | 95% | 75% (37%–98%) | 1.00 | 0.20 | 2 of 14 | **ALARM** |
| 11 | 0.36 | 100% | 96% | 40% (10%–75%) | 1.00 | 0.20 | 0 of 11 | **ALARM** |
| 12 | 0.43 | 92% | 98% | 67% (34%–92%) | 1.00 | 0.18 | 1 of 12 | **ALARM** |
| 13 | 0.50 | 92% | 99% | 83% (55%–99%) | 1.00 | 0.17 | 1 of 12 | **ALARM** |
| 14 | 0.57 | 86% | 97% | 67% (22%–97%) | 1.00 | 0.13 | 1 of 7 | **ALARM** |
| 15 | 0.64 | 92% | 98% | 50% (5%–95%) | 1.00 | 0.12 | 1 of 12 | **ALARM** |
| 16 | 0.71 | 69% | 93% | 75% (37%–98%) | 1.00 | 0.13 | 4 of 13 | **ALARM** |
| 17 | 0.79 | 85% | 95% | 86% (61%–99%) | 1.00 | 0.11 | 2 of 13 | **ALARM** |
| 18 | 0.86 | 60% | 94% | 75% (37%–98%) | 1.00 | 0.12 | 4 of 10 | **ALARM** |
| 19 | 0.93 | 55% | 91% | 60% (25%–90%) | 1.00 | 0.10 | 5 of 11 | **ALARM** |
| 20 | 1.00 | 36% | 91% | 33% (3%–78%) | 1.00 | 0.06 | 9 of 14 | **ALARM** |

## How good is the label-free estimate?

| Clinic-weeks | Count | Mean error (catch rate) | Real value inside its 90% band |
| --- | --- | --- | --- |
| No change | 73 | 0.078 | 95% |
| After a change | 127 | 0.062 | 86% |
| US-WEAR-01 weeks 15–20 | 6 | 0.278 | 17% |

## How much the made-up costs matter

| Review cost | Policy | Changes caught | False alarms | Extra urgent cases missed | Total cost |
| --- | --- | --- | --- | --- | --- |
| £5k | wait for grades | 2 of 8 | 0 | 33.3 | £400k |
| £5k | watch estimate | 1 of 8 | 0 | 29.3 | £362k |
| £5k | watch drift | 7 of 8 | 0 | 20.3 | £242k |
| £5k | ClinicDrift | 8 of 8 | 0 | 2.3 | £63k |
| £10k | wait for grades | 2 of 8 | 0 | 33.3 | £410k |
| £10k | watch estimate | 1 of 8 | 0 | 29.3 | £366k |
| £10k | watch drift | 7 of 8 | 0 | 20.3 | £277k |
| £10k | ClinicDrift | 8 of 8 | 0 | 2.3 | £103k |
| £25k | wait for grades | 2 of 8 | 0 | 33.3 | £440k |
| £25k | watch estimate | 1 of 8 | 0 | 29.3 | £382k |
| £25k | watch drift | 7 of 8 | 0 | 20.3 | £382k |
| £25k | ClinicDrift | 8 of 8 | 0 | 2.3 | £223k |
| £50k | wait for grades | 2 of 8 | 0 | 33.3 | £490k |
| £50k | watch estimate | 1 of 8 | 0 | 29.3 | £406k |
| £50k | watch drift | 7 of 8 | 0 | 20.3 | £557k |
| £50k | ClinicDrift | 8 of 8 | 0 | 2.3 | £423k |
| £100k | wait for grades | 2 of 8 | 0 | 33.3 | £590k |
| £100k | watch estimate | 1 of 8 | 0 | 29.3 | £456k |
| £100k | watch drift | 7 of 8 | 0 | 20.3 | £907k |
| £100k | ClinicDrift | 8 of 8 | 0 | 2.8 | £829k |

## Honest caveats

- **Model**: stand-in: ImageNet ResNet-50 features + logistic regression. Numbers will change when it changes; regenerate this file.
- **Simulated clinics**: real public scans, but the clinics, camera switches and wear are simulated. The datasets carry no age, sex or ethnicity, so make no fairness claims about patient groups, only about clinics and cameras. This APTOS copy is 224 px, so the APTOS clinics test low resolution, not Indian patients.
- **Costs are illustrative**: across review costs from £5k to £100k ClinicDrift raised no false alarms, and at £100k reviewing every changed clinic cost more than waiting for grades, because several of those clinics were actually fine (see the sweep).
- **The evidence test costs time**: ClinicDrift only raises a harm alarm once it is 90% sure the catch rate is below 80%, so on the software update it waits 3 weeks where watching the estimate alarms at once. That is the price of not pulling a healthy AI over a few weeks of noise: without the test, a handful of low grades was enough to pull healthy clinics.
- **The 80% floor** is the long-standing UK (Exeter / British Diabetic Association) standard of at least 80% sensitivity for diabetic eye screening.
- **A new camera doesn't always mean missed cases**: at SW-MES-01 the new camera moved this model's catch rate 93% → 95% and its healthy referrals 27 → 31 a week. The missed cases came from the worn camera (US-WEAR-01) and the faulty update (US-UPD-01).
- **The belief band** describes the clinic's underlying catch rate. A single week has only about 10 urgent cases, so that week's real value often falls outside it; don't present it as a 90% interval for one week. The label-free estimate's band is the one checked against weekly values above.
- **Drift alarms say "can't verify", not "X% caught"**: when drift triggers the alarm the belief is pulled towards 50% with a very wide band (exactly 50% at clinics that differ from day one, before any grades). Say the AI is outside its validated conditions; don't quote that number as a measured drop.
- **Late grades can mislead**: at US-WEAR-01 the belief creeps back up in the later weeks because the grades arriving then are for scans taken 5–7 weeks earlier, when wear was milder. That is why an alarm stays on until someone reviews the AI: without that, old grades would switch it off just as harm peaks.
- **Full wear is obvious**: at wear 1.0 any grader would reject the scans. The point is that drift fired at low wear, when the scans still look normal.
- **Small**: 10 clinics, 20 weeks, one replay seed. "Real" values use every expert grade in hindsight.

## Regenerate

```bash
python -m clinicdrift.engine.replay
python -m clinicdrift.engine.estimate
python -m clinicdrift.engine.decide
python -m clinicdrift.engine.backtest
python -m clinicdrift.engine.results
```

Inputs read from `processed/standin`.

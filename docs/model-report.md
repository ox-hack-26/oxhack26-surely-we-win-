# Model report: the accuracy drop at each site

Made by `python -m clinicdrift.data.report`. The classifier is `convnext_tiny.in12k_ft_in1k_384` fine-tuned on 24,718 EyePACS training scans at 448 px for 2 of 10 planned epochs (best on val: epoch 2). The referral threshold (0.083) was set on EyePACS val to catch 90% of referable cases (grade 2 or above).

Catch rate is sensitivity: the share of referable scans the model refers, with a 95% interval. The naive estimate trusts the model's own probabilities and needs no expert grades; the gap between it and the true catch rate is what the engine has to close.

| Site | Scans | Referable | AUC | Catch rate (95% CI) | Change vs baseline | Specificity | Referred | Naive estimate | Quality | Median width |
| --- | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| EyePACS val (threshold set here) | 3,401 | 645 (19%) | 0.914 | 90.1% (87.5%–92.2%) |  | 71.1% | 40.5% | 88.7% | 0.88 | 1,024 px |
| EyePACS held-out test (baseline) | 6,989 | 1,398 (20%) | 0.909 | 88.8% (87.1%–90.4%) |  | 69.7% | 42.0% | 89.2% | 0.87 | 1,024 px |
| APTOS 2019 (India) | 3,662 | 1,487 (41%) | 0.968 | 100.0% (99.7%–100.0%) | +11.2 pts | 13.7% | 91.8% | 99.3% | 0.72 | 224 px |
| Messidor-2 (France) | 1,744 | 457 (26%) | 0.964 | 98.9% (97.5%–99.5%) | +10.1 pts | 52.0% | 61.4% | 95.5% | 0.80 | 2,240 px |
| IDRiD (India) | 516 | 323 (63%) | 0.974 | 100.0% (98.8%–100.0%) | +11.2 pts | 44.0% | 83.5% | 99.1% | 0.91 | 4,288 px |
| EyePACS, camera wear 0.00–0.35 | 200 | 42 (21%) | 0.798 | 85.7% (72.2%–93.3%) | -3.1 pts | 46.8% | 60.0% | 91.0% | 0.48 | 1,024 px |
| EyePACS, camera wear 0.35–0.70 | 250 | 54 (22%) | 0.750 | 83.3% (71.3%–91.0%) | -5.5 pts | 41.3% | 64.0% | 87.8% | 0.29 | 1,024 px |
| EyePACS, camera wear 0.70–1.00 | 250 | 61 (24%) | 0.692 | 82.0% (70.5%–89.6%) | -6.9 pts | 43.4% | 62.8% | 78.2% | 0.24 | 1,024 px |

Notes:

- Quality is the 0–1 score in `scans.parquet`: 1 means as sharp, contrasty and well exposed as a typical training scan.
- Camera wear rows are the worn-camera copies the `US-WEAR-01` clinic sees (`clinicdrift/data/degrade.py`): held-out EyePACS scans, blurred and darkened more each week.
- The APTOS copy we use was resized to 224 × 224 px before upload, so part of its drop is resolution, which a real low-resolution camera would also cause.
- No dataset has patient age, sex or ethnicity, so these are differences between sites and cameras, not patient groups.

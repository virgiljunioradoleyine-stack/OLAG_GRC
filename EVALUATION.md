# Evaluation

Generated 2026-11-01T10:08:36+00:00 by `python -m pipeline.models.evaluate`.
Do not edit by hand — this file is regenerated from
`data/evaluation/evaluation.json`.

## What can and cannot be measured

No in-situ water-quality measurements are available, so no turbidity accuracy metrics (MAE/RMSE against NTU) can be computed. What is reported is how well the expected-condition model generalises to unseen time periods, and how stable the anomaly flag rate is outside its calibration window.

**Ground-truth records available: 0.** No MAE, RMSE or R² against measured turbidity can be reported, because no measured turbidity exists for this basin. Reporting such figures would require inventing the measurements.

## Validation design

`train <= 2023-12-31; validation 2023-12-31 < t <= 2024-12-31; test > 2024-12-31`

Chronological, never shuffled. Preprocessing is fitted on the training
period alone; thresholds are chosen on validation; the test period is
untouched until this report.

## Expected-condition model (Model B)

`skill` is the fractional improvement in mean absolute error over a naive
predictor that assumes the last 30 days repeat. Positive means the model
adds information; zero or below means it does not.

| Station | Train | Val | Test | Test MAE | Test RMSE | Skill vs naive |
|---|---|---|---|---|---|---|
| P01 Pra Upper Basin | 217 | 35 | 51 | 0.0137 | 0.02072 | 0.4467 |
| P10 Pra Reach P10 | 215 | 26 | 51 | 0.01262 | 0.01959 | 0.5467 |
| P11 Pra Reach P11 | 239 | 30 | 59 | 0.01578 | 0.02284 | 0.4232 |
| P02 Pra Mid-Upper Reach | 184 | 24 | 53 | 0.01394 | 0.01931 | 0.0907 |
| P09 Pra Reach P09 | 220 | 28 | 58 | 0.0139 | 0.01927 | 0.3962 |
| P03 Pra at Beposo Reach | 212 | 30 | 61 | 0.02383 | 0.03586 | 0.3953 |
| P04 Pra Mid-Lower Reach | 225 | 28 | 60 | 0.01923 | 0.02975 | 0.3939 |
| P05 Daboase Intake (GWCL) | 200 | 32 | 59 | 0.0232 | 0.03234 | 0.3381 |
| P06 Pra Lower Reach | 205 | 29 | 53 | 0.015 | 0.02035 | 0.5852 |
| P07 Pra Lower Reach South | 193 | 23 | 51 | 0.01375 | 0.02165 | 0.4587 |
| P08 Pra Estuary Approach | 203 | 28 | 50 | 0.0247 | 0.04989 | 0.3803 |

### Error by season (test period, mean absolute residual)

| Station | dry | wet major | wet minor |
|---|---|---|---|
| P01 | 0.01795 | 0.00927 | 0.01625 |
| P10 | 0.01746 | 0.01006 | 0.00812 |
| P11 | 0.01799 | 0.01542 | 0.01341 |
| P02 | 0.02059 | 0.00721 | 0.01324 |
| P09 | 0.01849 | 0.01151 | 0.00894 |
| P03 | 0.02853 | 0.01965 | 0.0222 |
| P04 | 0.02522 | 0.01724 | 0.01191 |
| P05 | 0.02601 | 0.01706 | 0.02575 |
| P06 | 0.01721 | 0.01748 | 0.0061 |
| P07 | 0.01822 | 0.01019 | 0.01136 |
| P08 | 0.03946 | 0.01107 | 0.00905 |

### Error by rainfall regime (test period)

| Station | Wetter half | Drier half |
|---|---|---|
| P01 | 0.01395 | 0.01344 |
| P10 | 0.00958 | 0.01577 |
| P11 | 0.01494 | 0.01665 |
| P02 | 0.01089 | 0.01711 |
| P09 | 0.01315 | 0.01464 |
| P03 | 0.02672 | 0.02084 |
| P04 | 0.01561 | 0.02285 |
| P05 | 0.02021 | 0.02629 |
| P06 | 0.01182 | 0.01831 |
| P07 | 0.01033 | 0.0173 |
| P08 | 0.01725 | 0.03214 |

## Anomaly detector (Model A)

The threshold is calibrated on the validation period, not set by a
`contamination` argument. `stability` is the absolute difference
between validation and test flag rates — small is good, and means the
detector behaves the same on data it has never seen.

| Station | Threshold | Source | Train | Val | Test | Stability |
|---|---|---|---|---|---|---|
| P01 | -0.58551 | validation quantile | 0.0138 | 0.0571 | 0.0 | 0.0571 |
| P10 | -0.5355 | training quantile — validation had only 26 rows, too few to calibrate on | 0.0512 | 0.0385 | 0.098 | 0.0595 |
| P11 | -0.527126 | validation quantile | 0.0628 | 0.0667 | 0.1356 | 0.0689 |
| P02 | -0.53642 | training quantile — validation had only 24 rows, too few to calibrate on | 0.0543 | 0.0417 | 0.0943 | 0.0526 |
| P09 | -0.527801 | training quantile — validation had only 28 rows, too few to calibrate on | 0.05 | 0.1429 | 0.069 | 0.0739 |
| P03 | -0.602155 | validation quantile | 0.0047 | 0.0667 | 0.0492 | 0.0175 |
| P04 | -0.539448 | training quantile — validation had only 28 rows, too few to calibrate on | 0.0533 | 0.0 | 0.0167 | 0.0167 |
| P05 | -0.55225 | validation quantile | 0.025 | 0.0625 | 0.1017 | 0.0392 |
| P06 | -0.538845 | training quantile — validation had only 29 rows, too few to calibrate on | 0.0537 | 0.0 | 0.0943 | 0.0943 |
| P07 | -0.533814 | training quantile — validation had only 23 rows, too few to calibrate on | 0.0518 | 0.0435 | 0.098 | 0.0545 |
| P08 | -0.537719 | training quantile — validation had only 28 rows, too few to calibrate on | 0.0542 | 0.0 | 0.12 | 0.12 |

## Publication gate

**PASS**

Every model beat the naive baseline and produced a plausible flag rate on the held-out test period.

## Limitations

- **No calibration to NTU or TSS.** The index is dimensionless. Nothing
  in this system converts it to a concentration, and it must not be
  presented as one.
- **Skill is measured against a naive baseline, not against truth.** A
  model can predict the index well while the index itself is a poor proxy
  for water quality. Only ground-truth measurements can settle that.
- **Irregular sampling.** Cloud decides when observations exist, so test
  periods contain fewer rows than a regular time series would.
- **Single basin.** Eight stations on one river. No claim of
  generalisation to other rivers is supported.

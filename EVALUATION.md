# Evaluation

Generated 2026-09-07T16:29:20+00:00 by `python -m pipeline.models.evaluate`.
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
| P01 Pra Upper Basin | 217 | 35 | 45 | 0.01508 | 0.02163 | 0.3978 |
| P02 Pra Mid-Upper Reach | 184 | 24 | 46 | 0.01392 | 0.01913 | 0.0563 |
| P03 Pra at Beposo Reach | 220 | 30 | 56 | 0.02651 | 0.03612 | 0.3394 |
| P04 Pra Mid-Lower Reach | 233 | 28 | 54 | 0.01949 | 0.02847 | 0.3979 |
| P05 Daboase Intake (GWCL) | 207 | 32 | 52 | 0.02175 | 0.03036 | 0.4074 |
| P06 Pra Lower Reach | 218 | 29 | 50 | 0.01618 | 0.02276 | 0.5608 |
| P07 Pra Lower Reach South | 205 | 23 | 48 | 0.01506 | 0.02299 | 0.4399 |
| P08 Pra Estuary Approach | 207 | 28 | 48 | 0.02786 | 0.05025 | 0.3412 |

### Error by season (test period, mean absolute residual)

| Station | dry | wet major | wet minor |
|---|---|---|---|
| P01 | 0.02194 | 0.01138 | 0.00552 |
| P02 | 0.01845 | 0.01018 | 0.01167 |
| P03 | 0.03164 | 0.02009 | 0.02894 |
| P04 | 0.02558 | 0.01749 | 0.00704 |
| P05 | 0.02319 | 0.01787 | 0.02509 |
| P06 | 0.01844 | 0.01807 | 0.00519 |
| P07 | 0.0174 | 0.0105 | 0.01972 |
| P08 | 0.04278 | 0.01095 | 0.01239 |

### Error by rainfall regime (test period)

| Station | Wetter half | Drier half |
|---|---|---|
| P01 | — | — |
| P02 | — | — |
| P03 | — | — |
| P04 | — | — |
| P05 | — | — |
| P06 | — | — |
| P07 | — | — |
| P08 | — | — |

## Anomaly detector (Model A)

The threshold is calibrated on the validation period, not set by a
`contamination` argument. `stability` is the absolute difference
between validation and test flag rates — small is good, and means the
detector behaves the same on data it has never seen.

| Station | Threshold | Source | Train | Val | Test | Stability |
|---|---|---|---|---|---|---|
| P01 | -0.585101 | validation quantile | 0.023 | 0.0571 | 0.0444 | 0.0127 |
| P02 | -0.528904 | training quantile — validation had only 24 rows, too few to calibrate on | 0.0543 | 0.0417 | 0.1087 | 0.067 |
| P03 | -0.597765 | validation quantile | 0.0182 | 0.0667 | 0.0714 | 0.0047 |
| P04 | -0.538768 | training quantile — validation had only 28 rows, too few to calibrate on | 0.0515 | 0.0 | 0.0556 | 0.0556 |
| P05 | -0.512076 | validation quantile | 0.1159 | 0.0625 | 0.1731 | 0.1106 |
| P06 | -0.545274 | training quantile — validation had only 29 rows, too few to calibrate on | 0.0505 | 0.0 | 0.1 | 0.1 |
| P07 | -0.529427 | training quantile — validation had only 23 rows, too few to calibrate on | 0.0537 | 0.0435 | 0.0833 | 0.0398 |
| P08 | -0.529165 | training quantile — validation had only 28 rows, too few to calibrate on | 0.0531 | 0.0 | 0.125 | 0.125 |

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

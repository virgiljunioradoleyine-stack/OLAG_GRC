# Evaluation

Generated 2026-10-01T09:50:04+00:00 by `python -m pipeline.models.evaluate`.
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
| P01 Pra Upper Basin | 217 | 35 | 45 | 0.013 | 0.02023 | 0.4817 |
| P10 Pra Reach P10 | 215 | 26 | 46 | 0.0129 | 0.02026 | 0.5338 |
| P11 Pra Reach P11 | 239 | 30 | 52 | 0.01554 | 0.02206 | 0.4134 |
| P02 Pra Mid-Upper Reach | 184 | 24 | 47 | 0.01345 | 0.01892 | 0.0813 |
| P09 Pra Reach P09 | 220 | 28 | 55 | 0.01447 | 0.01976 | 0.4008 |
| P03 Pra at Beposo Reach | 212 | 30 | 56 | 0.02486 | 0.03706 | 0.3721 |
| P04 Pra Mid-Lower Reach | 225 | 28 | 54 | 0.01909 | 0.02968 | 0.4112 |
| P05 Daboase Intake (GWCL) | 200 | 32 | 53 | 0.02299 | 0.03274 | 0.3749 |
| P06 Pra Lower Reach | 205 | 29 | 50 | 0.01568 | 0.02092 | 0.5745 |
| P07 Pra Lower Reach South | 193 | 23 | 48 | 0.01424 | 0.02224 | 0.4708 |
| P08 Pra Estuary Approach | 203 | 28 | 47 | 0.02606 | 0.05145 | 0.3809 |

### Error by season (test period, mean absolute residual)

| Station | dry | wet major | wet minor |
|---|---|---|---|
| P01 | 0.01795 | 0.00927 | 0.01222 |
| P10 | 0.01746 | 0.01006 | 0.00692 |
| P11 | 0.01799 | 0.01542 | 0.00982 |
| P02 | 0.02059 | 0.00721 | 0.01075 |
| P09 | 0.01849 | 0.01151 | 0.01043 |
| P03 | 0.02853 | 0.01965 | 0.0284 |
| P04 | 0.02522 | 0.01724 | 0.00621 |
| P05 | 0.02601 | 0.01706 | 0.02612 |
| P06 | 0.01721 | 0.01748 | 0.007 |
| P07 | 0.01822 | 0.01019 | 0.01344 |
| P08 | 0.03946 | 0.01107 | 0.01061 |

### Error by rainfall regime (test period)

| Station | Wetter half | Drier half |
|---|---|---|
| P01 | 0.01202 | 0.01403 |
| P10 | 0.01186 | 0.01393 |
| P11 | 0.01344 | 0.01765 |
| P02 | 0.01063 | 0.01639 |
| P09 | 0.01412 | 0.01482 |
| P03 | 0.02692 | 0.02281 |
| P04 | 0.01564 | 0.02255 |
| P05 | 0.01916 | 0.02697 |
| P06 | 0.01243 | 0.01893 |
| P07 | 0.01094 | 0.01754 |
| P08 | 0.01791 | 0.03457 |

## Anomaly detector (Model A)

The threshold is calibrated on the validation period, not set by a
`contamination` argument. `stability` is the absolute difference
between validation and test flag rates — small is good, and means the
detector behaves the same on data it has never seen.

| Station | Threshold | Source | Train | Val | Test | Stability |
|---|---|---|---|---|---|---|
| P01 | -0.58551 | validation quantile | 0.0138 | 0.0571 | 0.0 | 0.0571 |
| P10 | -0.5355 | training quantile — validation had only 26 rows, too few to calibrate on | 0.0512 | 0.0385 | 0.087 | 0.0485 |
| P11 | -0.527126 | validation quantile | 0.0628 | 0.0667 | 0.0769 | 0.0102 |
| P02 | -0.53642 | training quantile — validation had only 24 rows, too few to calibrate on | 0.0543 | 0.0417 | 0.0851 | 0.0434 |
| P09 | -0.527801 | training quantile — validation had only 28 rows, too few to calibrate on | 0.05 | 0.1429 | 0.0545 | 0.0884 |
| P03 | -0.602155 | validation quantile | 0.0047 | 0.0667 | 0.0536 | 0.0131 |
| P04 | -0.539448 | training quantile — validation had only 28 rows, too few to calibrate on | 0.0533 | 0.0 | 0.0185 | 0.0185 |
| P05 | -0.55225 | validation quantile | 0.025 | 0.0625 | 0.1132 | 0.0507 |
| P06 | -0.538845 | training quantile — validation had only 29 rows, too few to calibrate on | 0.0537 | 0.0 | 0.1 | 0.1 |
| P07 | -0.533814 | training quantile — validation had only 23 rows, too few to calibrate on | 0.0518 | 0.0435 | 0.1042 | 0.0607 |
| P08 | -0.537719 | training quantile — validation had only 28 rows, too few to calibrate on | 0.0542 | 0.0 | 0.1277 | 0.1277 |

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

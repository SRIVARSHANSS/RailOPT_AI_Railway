# RailOpt AI - model card (Phase 4)

**SIMULATED data - sample corridor, synthetic disruptions, not real railway records.** These models are trained and evaluated only on simulated runs of the
sample corridor. Nothing here is a measurement of real Indian Railways operations.
All numbers below are generated from `metrics.json` (shown to 3 decimals).

## Data and split
- 68011 rows from 2945 simulated runs (`training_rows.csv`), seed 42 (3000 runs generated; runs where every train had already entered its sections at state time give no rows).
- Dataset SHA-256 `a41c8f03fa1bd3d632d741625824f01e65ec4f5837acc6c8af314be3f270476e`; model files hashed in `metrics.json`.
- Split: by run_id in run order: first 70 % train, next 15 % validation, last 15 % test. No run appears in two splits.
  - train: 2062 runs (R00001-R02103), 47862 rows
  - val: 442 runs (R02104-R02554), 10324 rows
  - test: 441 runs (R02555-R03000), 9825 rows
- Preprocessing: one-hot categoricals, headway_gap_min capped at 120 then scaled, numerics scaled; fitted on train only.
- Tuning: fixed random search, at most 20 configurations per model, scored on validation only. The test split was scored once, after all choices were made.
- Final models trained on: train split only. Training time: 154.6 s.

## Delay at destination (`label_delay_min`, minutes)
Best model: **xgboost** (lowest validation MAE).

| Method | Kind | Val MAE | Val RMSE | Val R2 | Test MAE | Test RMSE | Test R2 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| carry_known_delay | baseline | 12.903 | 17.072 | -1.051 | 12.643 | 16.909 | -1.040 |
| deterministic_projection | baseline | 10.626 | 14.523 | -0.484 | 10.161 | 13.943 | -0.387 |
| linear_regression | baseline | 7.715 | 10.674 | 0.198 | 7.508 | 10.513 | 0.211 |
| random_forest | model | 7.109 | 10.293 | 0.255 | 6.894 | 10.010 | 0.285 |
| xgboost | model | 7.055 | 10.292 | 0.255 | 6.850 | 10.005 | 0.286 |

`deterministic_projection` is the existing simulator run with no randomness on the events
known at state time: what the rules plus the simulator predict without ML.

## Conflict before the section (`label_conflict`)
Positive rate: train 0.165, val 0.171, test 0.173. Best model: **xgboost** (highest validation PR-AUC).
Each model's threshold: best validation precision with validation recall >= 0.80.

| Method | Kind | Threshold | Val P | Val R | Val F1 | Val PR-AUC | Test P | Test R | Test F1 | Test PR-AUC |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| rule_flags_conflict | baseline | n/a | 0.791 | 0.245 | 0.375 | 0.323 | 0.808 | 0.257 | 0.390 | 0.337 |
| logistic_regression | baseline | 0.701 | 0.531 | 0.802 | 0.639 | 0.658 | 0.547 | 0.803 | 0.650 | 0.678 |
| random_forest | model | 0.622 | 0.563 | 0.801 | 0.661 | 0.726 | 0.593 | 0.807 | 0.684 | 0.756 |
| xgboost | model | 0.633 | 0.560 | 0.800 | 0.659 | 0.726 | 0.583 | 0.818 | 0.681 | 0.758 |

The rule baseline is a 0/1 flag, so its PR-AUC is the average precision of that flag.

### Operating points of the deployed model (xgboost)

| Operating point | Threshold | Val P | Val R | Val F1 | Test P | Test R | Test F1 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| recall_at_least_0.80 | 0.633 | 0.560 | 0.800 | 0.659 | 0.583 | 0.818 | 0.681 |
| equal_to_rule_precision | 0.871 | 0.792 | 0.465 | 0.586 | 0.802 | 0.483 | 0.603 |

- `recall_at_least_0.80` is the threshold the predictor uses (a missed conflict is the costly error).
- `equal_to_rule_precision` is the head-to-head with the rule: at the rule's validation precision (0.791), the rule's validation recall is 0.245 and the model's is 0.465. On test the rule has precision 0.808 / recall 0.257; the model at this threshold has 0.802 / 0.483.
- With 10% of the data and minimal tuning the model did not beat the rule (recall 0.150 vs 0.216), so the result depends on data volume.

### Ablation: xgboost with and without `rule_flags_conflict` (same parameters)

| Variant | Operating point | Threshold | Val P | Val R | Val F1 | Val PR-AUC | Test P | Test R | Test F1 | Test PR-AUC |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| with_rule_flag | recall_at_least_0.80 | 0.633 | 0.560 | 0.800 | 0.659 | 0.726 | 0.583 | 0.818 | 0.681 | 0.758 |
| with_rule_flag | equal_to_rule_precision | 0.871 | 0.792 | 0.465 | 0.586 | 0.726 | 0.802 | 0.483 | 0.603 | 0.758 |
| without_rule_flag | recall_at_least_0.80 | 0.612 | 0.533 | 0.800 | 0.640 | 0.701 | 0.553 | 0.820 | 0.661 | 0.732 |
| without_rule_flag | equal_to_rule_precision | 0.885 | 0.794 | 0.395 | 0.527 | 0.701 | 0.803 | 0.411 | 0.544 | 0.732 |

## Global feature importance (mean |SHAP| on validation rows)

- **delay**: time_to_section_min 1.820, current_delay_min 1.670, disruption_duration_min 1.077, hour_of_day 0.957, disruption_type 0.841, train_type 0.703
- **conflict**: section_id 1.611, headway_gap_min 0.380, time_to_section_min 0.303, rule_flags_conflict 0.235, section_tracks 0.225, disruption_duration_min 0.145

Computed on 2000 validation rows. Delay SHAP is in minutes; conflict SHAP is in the model's raw output units (log-odds for XGBoost, probability for random forest).

## Known limits
- Trained on SIMULATED data from one sample corridor with assumed variability ranges
  (docs/ASSUMPTIONS.md). Performance on real operations is unknown.
- Conflicts caused by disruptions that start after state time are unforeseeable: the
  features only contain what is known at state time, so some missed conflicts are expected.
- The models advise a human controller. They do not control trains or signals.

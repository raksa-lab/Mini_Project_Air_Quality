# Cambodia PM2.5 Forecasting

This project compares four classical regression algorithms for hourly PM2.5 forecasting in Phnom Penh: Linear Regression, Random Forest, HistGradientBoosting, and XGBoost. The interpretation below is refreshed automatically after a complete run of Train_Model.ipynb.


Generated from the latest successful notebook run: 2026-11-13 11:08 SE Asia Standard Time

> **How to read this report:** MAE and RMSE are errors in µg/m³; lower is better. R² describes variance explained on the evaluated sample; closer to 1 is better. Backtest scores describe past held-out windows, not guaranteed future accuracy.

## 1. Experiment setup

- Target: hourly PM2.5 concentration; the models predict one hour ahead during training.
- Chronological split: 17,549 training rows (70%), 2,507 validation rows (10%), and 5,014 test rows (20%). Later timestamps are held out from training.
- Models compared: Linear Regression, Random Forest, HistGradientBoosting, XGBoost.
- The loss graph uses 100 model-specific training progress points, not epochs or equivalent update steps. Its vertical axis is MAE, not MSE.

## 2. One-hour regression results

| Model | Validation MAE | Test MAE | Test RMSE | Test R² |
| --- | --- | --- | --- | --- |
| Linear Regression | 2.669 | 1.886 | 3.686 | 0.952 |
| Random Forest | 2.160 | 1.628 | 3.474 | 0.957 |
| HistGradientBoosting | 2.359 | 1.673 | 3.549 | 0.955 |
| XGBoost | 2.243 | 1.644 | 3.466 | 0.957 |

**Interpretation:** Random Forest had the lowest validation MAE (2.160 µg/m³), so it is the model selected for the current one-hour-based forecasts. On the held-out one-hour test set its MAE was 1.628 µg/m³. This means its absolute error averaged about that many µg/m³ on these test examples; it does not mean every prediction was that close.

Validation data chooses models; test data estimates final performance. Do not choose a model because it happened to score best on the test set.

## 3. Training and validation loss interpretation

| Model | Train MAE first point | Train MAE final point | Validation MAE first point | Validation MAE final point |
| --- | --- | --- | --- | --- |
| Linear Regression | 1.627 | 1.652 | 2.785 | 2.669 |
| Random Forest | 1.346 | 0.876 | 3.124 | 2.160 |
| HistGradientBoosting | 2.790 | 1.296 | 3.942 | 2.359 |
| XGBoost | 2.822 | 1.067 | 3.997 | 2.243 |

**Interpretation:** A declining training curve means the model fits its training data better as its model-specific training amount grows. Compare the validation curve to check whether that improvement carries over to unseen data. The models' progress points are constructed differently, so compare final loss values—not the speed or x-position of the lines. A widening train/validation gap can indicate overfitting; a low training error alone is not proof of a good model.

## 4. Category evaluation from regression predictions

The model predicts a continuous PM2.5 value. The confusion matrices are a secondary view created by converting actual and predicted values into Good, Moderate, and Polluted bands. Precision, recall, and F1 therefore describe these derived categories; they are not the primary regression metrics.

| Model | Polluted correctly found / actual | Polluted recall | Polluted precision |
| --- | --- | --- | --- |
| Linear Regression | 573/620 | 92.4% | 89.5% |
| Random Forest | 578/620 | 93.2% | 91.5% |
| HistGradientBoosting | 568/620 | 91.6% | 92.4% |
| XGBoost | 574/620 | 92.6% | 92.7% |

**Interpretation:** Polluted recall answers: of the actually Polluted hours, what fraction did the model identify? Polluted precision answers: of the hours labeled Polluted by the model, what fraction were actually Polluted? Check the matrix cells to see which categories were confused. False negatives may be more consequential for air-quality monitoring. These category scores do not replace MAE/RMSE.

## 5. Forecast horizon accuracy

The future forecast values are unknown when this report is generated. The accuracy below comes from historical forecasts made at held-out test origins and compared with later actual readings.

### One hour ahead

The held-out one-step test MAE values are in the table in Section 2. In next_24h_forecasts.csv, each model also has one-step test MAE and the historical recursive error for each lead from +1h to +24h. This answers both how the model performed on one-step test examples and how error changed across a recursively generated day.

### Full 24-hour recursive forecast

| Model | Backtest MAE (µg/m³) | Backtest RMSE (µg/m³) |
| --- | --- | --- |
| Linear Regression | 5.704 | 9.268 |
| Random Forest | 6.262 | 9.907 |
| HistGradientBoosting | 5.405 | 8.636 |
| XGBoost | 5.757 | 9.495 |

Interpret these scores across 30 held-out forecast origins. Lower error indicates closer predictions on those historical 24-hour windows. The per-lead columns in next_24h_forecasts.csv show whether error changes as the lead increases.

### Full 72-hour recursive forecast

| Model | Backtest MAE (µg/m³) | Backtest RMSE (µg/m³) |
| --- | --- | --- |
| Linear Regression | 8.518 | 12.411 |
| Random Forest | 8.650 | 12.160 |
| HistGradientBoosting | 7.669 | 10.909 |
| XGBoost | 6.441 | 9.574 |

These scores use 10 held-out 72-hour origins. The lowest aggregate score is a retrospective comparison only. The current forecast model is still selected by validation MAE; test-window performance must not be used to tune the model.

### Full 30-day hourly recursive forecast

| Model | Backtest MAE (µg/m³) | Backtest RMSE (µg/m³) |
| --- | --- | --- |
| Linear Regression | 16.671 | 24.550 |
| Random Forest | 14.123 | 21.371 |
| HistGradientBoosting | 13.652 | 19.950 |
| XGBoost | 12.075 | 17.864 |

The forecast CSV has 720 future rows, with hourly predictions for each forecast date. Month-horizon accuracy here uses 1 complete held-out 720-hour window(s), so it is a limited historical estimate rather than a robust average over many months. Absolute errors at 1, 7, 14, and 30 days are included in the same CSV; those are individual lead-date errors, not average errors at each lead across many origins.

**Comparing horizons:** MAE and RMSE remain in µg/m³, but longer-horizon errors are measured on different windows and forecast procedures. Use each horizon's baseline and lead-specific results; do not claim the month forecast is better just because one score appears numerically smaller.

## 6. Main findings and limitations

1. **One-hour selection:** Random Forest was selected by validation MAE. Its test result is an estimate of one-hour performance on the held-out period.
2. **Longer horizons:** recursive predictions use earlier predictions as later inputs. Errors can accumulate, so inspect the lead-time columns, not only the aggregate score.
3. **Future inputs:** the recursive forecast estimates future weather from the previous day's same-hour values and estimates PM10 using a recent PM10/PM2.5 ratio. This adds uncertainty beyond the model's fitted error.
4. **Coverage:** the 30-day test backtest currently has only one complete held-out window. Report that limitation prominently and avoid claiming reliable month-ahead accuracy from one window.
5. **Use:** treat these as experimental forecasts for a student project, not operational health warnings.

## Files

- results_regression.csv: one-step regression metrics for all models and the persistence baseline.
- next_24h_forecasts.csv: current 24-hour predictions plus one-step and per-lead/whole-day backtest metrics.
- next_3d_hourly_forecasts.csv: 72 hourly predictions plus one-step and 72-hour backtest metrics.
- next_30d_daily_forecasts.csv: 720 hourly predictions plus the 30-day backtest metrics.
- chart_train_val_loss.png: 100 model-specific progress-point loss curves.
- chart_confusion_matrix.png: category evaluation matrices derived from continuous regression predictions.

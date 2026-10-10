# ShelfSignal: starter kit

Forecast each product's demand for the next 7 days, flag what will run out before the next delivery,
and recommend how much to order today. Read PLAN.md for the why; this file is the how.

## 1. Set up (5 min)

```
pip install -r requirements.txt
```

Python 3.10+.

## 2. See it work on MOCK data (2 min, no download)

```
python make_mock_data.py
python pipeline.py --data data_mock --out outputs
streamlit run app.py
```

The app shows a red MOCK banner. Never present these numbers.

## 3. Real data: Kaggle "Store Sales - Time Series Forecasting"

1. Log in to Kaggle, open https://www.kaggle.com/competitions/store-sales-time-series-forecasting and click **Join Competition** (accept the rules).
2. Either download the zip from the Data tab, or use the CLI:
   ```
   pip install kaggle
   # put kaggle.json (Account > Create New Token) in %USERPROFILE%\.kaggle\ on Windows or ~/.kaggle/ on Mac/Linux
   kaggle competitions download -c store-sales-time-series-forecasting -p data/store-sales
   ```
3. Unzip into `data/store-sales/`, so that `data/store-sales/train.csv` exists:
   - Windows PowerShell: `Expand-Archive data\store-sales\store-sales-time-series-forecasting.zip data\store-sales`
4. Run the pipeline and the app:
   ```
   python pipeline.py --data data/store-sales --out outputs
   streamlit run app.py
   ```

Useful pipeline options:
- `--stores 1 2 3`: only some stores (faster).
- `--families "EGGS,DAIRY,POULTRY"`: only some product families. The pipeline prints the available names.
- `--lead-time 2`: lead time used in the simulation.
- `--max-iter 150`: faster training.

**Fallback data:** Kaggle "Store Item Demand Forecasting Challenge" (`demand-forecasting-kernels-only`). Put its `train.csv` in a folder and point `--data` at it; the format is detected automatically. It has no promotions or holidays.

## 4. Files

| File | Owner | What it does |
|---|---|---|
| `pipeline.py` | P1 (S, K) | S: data, features, forecast model and error spread. K: baselines, metrics, band check, simulation. Writes `outputs/` |
| `inventory.py` | P2 (T, O) | T: stockout risk and CRITICAL/ORDER/OK status. O: order quantity and ranking. Also the policy simulation |
| `app.py` | P3 | Streamlit demo in sections T, O, S, K; reads only `outputs/` |
| `make_mock_data.py` | Anyone | Mock data in the Favorita format, for building before the download |

## 5. Output contract (`outputs/`, written by pipeline.py, read by app.py)

| File | Columns / content |
|---|---|
| `forecasts.parquet` | date, sid, store, product, y (actual), promo, holiday, split (train/val/test), pred_model, pred_naive7, pred_ma28 |
| `sigma.csv` | sid, store, product, mean_daily_val, sigma_d (daily forecast-error std from validation) |
| `metrics.json` | data_source, splits, test_daily, test_weekly_totals (per method: MAE, WMAPE, bias), simulation (label, assumptions, headline) |
| `per_product_metrics.csv` | test WMAPE per product for each method |
| `importance.csv` | permutation importance per feature (validation sample) |
| `sim_frontier.csv` | policy, z, demand, sold, lost, stockout_days, days_of_cover, fill_rate |

## 6. Status

- **Implemented and tested** end to end on mock data in the Favorita format and on a sample in the Store Item format. The app was run headlessly and checked in a browser.
- **Not yet run on the real Kaggle data**, so there are no real accuracy numbers yet. Run step 3 first.
- **Not built:** CSV upload, scenario preset buttons, deployment.

## 7. Honesty rules for the pitch

- Say "trained and tested on Corporacion Favorita (Ecuador) public data". Never call it Malaysian data.
- Accuracy numbers come only from the held-out test period. The simulation is labelled SIMULATED, with its assumptions.
- RM values and stock levels in the demo are inputs, not data.

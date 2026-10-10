# LARIS: Biar laris, jangan habis.

A budget-aware restocking assistant for small Malaysian grocers (kedai runcit, minimarts). Hackathon
Track 1, **Predictive Model Track: Predict Early, Decide Better**.

LARIS **predicts** each product's sales for the next 7 days with a machine-learning model, **spots** what
will run out before the next delivery or expire unsold, **ranks** those problems by what they could cost,
**explains** each one in plain language, and **decides** the best order list for the cash available.

Read `LARIS_OVERVIEW.md` for the why, `LARIS_BUILD.md` for the method, `PITCH_PLAN.md` for the pitch.
This file is the how.

## 1. Set up

Python 3.10+ with the packages in `requirements.txt`:

```
pip install -r requirements.txt
```

On the team laptop, `python` opens the Microsoft Store. Use the Anaconda interpreter instead (it already
has everything installed):

```powershell
$PY = "$env:USERPROFILE\anaconda3\python.exe"
```

## 2. See it work on MOCK data (about 2 minutes, no download)

```powershell
& $PY make_mock_data.py
& $PY pipeline.py --data data_mock --out outputs_mock
& $PY -m pytest -q
$env:SHELFSIGNAL_OUT = "outputs_mock"; & $PY -m streamlit run app.py
```

The app shows a red MOCK banner. Never present mock numbers.

## 3. Real data: Kaggle "Store Sales - Time Series Forecasting" (Corporacion Favorita, Ecuador)

1. Log in to Kaggle, open https://www.kaggle.com/competitions/store-sales-time-series-forecasting, click
   **Join Competition** and accept the rules (you must do this yourself).
2. Download the zip from the Data tab and unzip it so that `data\store-sales\train.csv` exists:
   `Expand-Archive store-sales-time-series-forecasting.zip data\store-sales`
3. Run the pipeline (timed) and the app:
   ```powershell
   Measure-Command { & $PY pipeline.py --data data/store-sales --out outputs | Out-Host }
   Remove-Item Env:SHELFSIGNAL_OUT -ErrorAction SilentlyContinue; & $PY -m streamlit run app.py
   ```
   If training takes more than about 5 minutes, add `--max-iter 150` and say so on the slides.

Pipeline options:
- `--stores 1 2 3`, `--families "EGGS,DAIRY"`: subsets (faster). The pipeline prints the available names.
- `--holdout-stores 10`: stores left out of a second training run, to test on unseen shops (0 = skip).
- `--sim-stores 10`: stores in the budget replay (0 = skip). `--sim-only` reruns just the replay.
- `--settings product_settings.csv`: lead times, shelf lives, costs, must-haves (placeholders).
- `--max-iter 150`: faster training.

## 4. How LARIS maps to the code

| | Track capability | What it does | Code |
|---|---|---|---|
| **L** Lihat ke depan | Detect and predict | 7-day forecast per store x product family, with a range from measured error; model what-if effects of promotions, holidays, payday | `pipeline.py` (model, `uncertainty_table`), `views/look_ahead.py`, `views/product.py` |
| **A** Amaran stok habis | Detect, categorize, prioritize, explain | P(running out before delivery), risk categories, tiers (Act today / This order / Watch), RM at risk, bridge top-up, explanation card | `inventory.assess`, `categorize`, `priority`; `laris_core.assess_products`, `explain`, `plan_table`; `planning.alert_table`; `views/alerts.py`, `views/home.py` |
| **R** Rendahkan pembaziran | Detect, explain | Stock that will expire unsold or ties up cash; skip or discount | `inventory.dead_stock`, `planning.waste_table`, `views/waste.py` |
| **I** Ikut bajet | Decide | Best order list for the cash: must-haves first up to expected demand, then value per RM; "with RM X more"; estimate vs ordering last week's sales | `inventory.allocate_budget`, `score_allocation`; `planning.strategy_compare`, `laris_core.budget_scenario`; `views/budget.py` |
| **S** Semak hasil | Prove it | Accuracy vs 3 simple rules with CIs; unseen stores; range coverage; alert backtest (false alarms); budget replay vs usual ordering rules | `pipeline.py`, `budget_sim.py` (metrics.json; SIMULATED replay line on I · Invest Within Budget; range coverage on charts). In the app, S is Send & Sync: `views/send.py` |

Three layers: **(1) the AI model** (offline, `pipeline.py`) → **(2) risk assessment and prioritisation**
(live, `inventory.py` + `laris_core.py`) → **(3) the budget optimiser** (live, `inventory.allocate_budget`).

## 5. Files

| File | What it does |
|---|---|
| `pipeline.py` | Data, features, model, baselines, evaluation (CIs, volume tiers, unseen stores, range coverage, alert backtest), budget replay; writes `outputs/` |
| `budget_sim.py` | SIMULATED day-by-day replay: LARIS vs usual ordering rules at the same cash, with sensitivity scenarios |
| `inventory.py` | Pure decision functions: stockout risk, bridge top-up, dead stock, budget allocation, risk categories, priority |
| `laris_core.py` | Shared per-week context for the app: risk, explanation, allocation, the pitch-scenario rule |
| `laris_ui.py`, `.streamlit/config.toml`, `assets/` | Look and feel (green theme, logo) |
| `app.py`, `views/*.py` | Streamlit app (top navigation): Home (insights + assistant), LARIS (one workspace, letters L/A/R/I/S), Products, Orders, Settings; product detail opens from any product. `app.py` builds the one shared planning context every page reads |
| `workspace/*.py` | The five LARIS tools (L Look Up, A Analyse, R Recommend, I Inventory, S Sales), drawn inside `views/laris.py` |
| `assistant.py`, `assistant_tools.py` | The Home assistant: allowlisted read-only business tools over the shared context, an OpenAI-compatible client, and a labelled quick-answer fallback |
| `planning.py` | Page logic derived from the shared context (alerts, look-ahead options, waste, budget breakdown, sales and gross profit, product validation, WhatsApp draft); no Streamlit, tested in `tests/test_laris2.py` |
| `store.py` | Local JSON store (`state/laris_state.json`, git-ignored) for events, alert/waste decisions, order status records and preferences |
| `product_settings.csv` | Per-product cost, margin, shelf life, lead time, review cycle, pack size, must-have. **All PLACEHOLDERS** |
| `make_mock_data.py` | Mock data in the Favorita format, for building before the download |
| `tests/` | pytest: decision logic, pipeline helpers, budget replay, headless app checks |

## 6. Output contract (`outputs/`, written by pipeline.py, read by the app)

| File | Content |
|---|---|
| `forecasts.parquet` | date, sid, store, product, y, promo, holiday, payday, split, suspect_zero, pred_model, pred_naive7, pred_ma28, pred_dow4, pred_no_promo, pred_no_holiday, pred_no_payday |
| `sigma.csv` | daily forecast-error spread per series (validation period) |
| `uncertainty.csv` | validation error quantiles of L-day totals per product (L = 1..7) |
| `metrics.json` | test accuracy, CIs, volume tiers, unseen stores, range coverage, data quality, alert backtest, budget replay, frontier simulation |
| `alert_eval.csv`, `budget_sim.csv`, `sim_frontier.csv` | detail behind the backtest and the simulations |
| `per_product_metrics.csv`, `importance.csv` | test error per product; permutation importance |

## 7. Measured vs simulated vs placeholder

| Kind | What | Where it comes from |
|---|---|---|
| **MEASURED** | Forecast error (WAPE) vs 3 simple rules, with 95% CIs; error by volume tier; error on unseen stores; share of actual sales inside the forecast range | Held-out test period of the real data; the model never saw those dates |
| **MEASURED on real sales, SIMULATED stock** | Alert precision, recall, false-alarm rate; ranking quality; calibration | Real future sales against a grid of stock levels (the data has no stock records); thresholds chosen on validation |
| **SIMULATED** | Lost margin, waste, must-have shortfalls of LARIS vs usual ordering rules at the same budget; frontier chart | Replay of real test-period sales with stated assumptions; never a claim of real savings |
| **ESTIMATE** | Expected lost margin / waste on the Budget & orders page | The forecast distribution and placeholder costs |
| **PLACEHOLDER** | Costs, margins, shelf lives, lead times, pack sizes, must-haves, goodwill cost, shop size, shop profile and persona | `product_settings.csv` and Settings; replace with a shop's own numbers |

## 8. Status

- **Built and tested on MOCK data:** everything above (37 tests pass; every page renders headlessly).
- **Not yet run on the real Kaggle data**, so there are no real numbers yet. Run step 3 first; until then
  the Results page shows mock values under a MOCK banner.
- **Not demonstrable with this data:** performance on Malaysian shops, true stockouts (alerts are tested
  with simulated stock), real costs, whether owners find the advice clear, time saved, real savings.
  These need a pilot (3 shops, 4 weeks).

## 9. Known limitations

- Favorita data is product **families** at supermarket volume, not SKUs in a small shop. The Shop size
  setting scales forecasts for illustration only (linear scaling understates uncertainty at small volumes).
- Sales stand in for demand; past stockouts hide some true demand.
- Stock age is unknown, so expiry risk assumes fresh stock.
- Placeholder costs drive the allocation; the budget replay reports how its conclusion changes when they move.

## 10. Honesty rules for the pitch

- Say "trained and tested on Corporacion Favorita (Ecuador) public data". Never call it Malaysian data.
- Accuracy numbers come only from the held-out test period. Simulated numbers are labelled SIMULATED with
  their assumptions. Placeholders are labelled. If a simple rule beats the model somewhere, say so.
- RM values and stock levels in the demo are inputs, not data.


## 11. LARIS 2.1 notes

**Forecast column fix.** Root cause: the Look Ahead table's column headed "Forecast" held a reliability note
("Less certain" or an empty string), so it looked blank for every reliable forecast; the forecast itself was in
another column, and the data and joins were fine. A deeper gap: nothing recorded where a forecast came from, so a
product with no forecast showed 0, the same as a real forecast of 0. Fix: `assess_products` now sets
`forecast_source` (`model` = AI model scaled to the shop, `baseline` = last week's sales, `unavailable` = neither),
`plan_table` carries `forecast_7d` (NaN only when unavailable), and every screen and the assistant read that one value
(`planning.forecast_text` shows "Forecast unavailable"). Regression test:
`tests/test_laris2.py::test_forecast_column_is_filled_and_missing_is_explicit`.

**Assistant setup (optional).** Without settings, Home answers common questions with labelled quick answers from
LARIS's own calculations. To use an AI model, set before starting the app (environment variables or
`.streamlit/secrets.toml`):

| Variable | Meaning |
|---|---|
| `AI_API_KEY` | API key for any OpenAI-compatible chat-completions service |
| `AI_MODEL` | Model name from that service |
| `AI_BASE_URL` | Optional; default `https://api.openai.com/v1` |

The model only chooses tools from `assistant_tools.TOOL_SPECS`; the tools do every calculation. It never sees the
owner's name or supplier contacts, keeps the last 10 messages for follow-ups, and can only *propose* an order-quantity
change, which the owner confirms on Home and LARIS then checks against the rebuilt plan. Test it in Settings › Assistant.

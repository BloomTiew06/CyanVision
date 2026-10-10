# LARIS: build and method

Track 1, **Predictive Model Track: Predict Early, Decide Better**. LARIS *predicts* what will run out or go
to waste before the next delivery, *categorizes* and *ranks* those risks by what they could cost,
*explains* each one, and *decides* how to spend a limited budget to prevent them.

## 1. Track fit

| Track asks | LARIS answer | Letter |
|---|---|---|
| **Detect and predict** | 7-day demand forecast with a measured range; chance of running out before delivery; stock that will expire unsold; demand surges; unusual recent sales | **L**, **A**, **R** |
| **Categorize** | Named risk types: runs out before delivery, needs this order, expiry risk, cash tied up, demand surge, unusual recent sales, not enough reliable data | **A**, **R** |
| **Prioritize** | Tiers (Act today / This order / Watch), then RM at risk if nothing is done, with an act-by day | **A** |
| **Explain** | Card per alert: prediction, evidence (incl. the model's own what-if driver effects and its recent track record), RM impact, confidence, action; every line tagged AI forecast / Calculation / Your setting | **A**, **R**, **L** |
| **Decide** | Best order list for the cash available, must-haves first; bridge top-up; skip or discount dead stock | **I**, **A**, **R** |
| **Prove it** | Measured accuracy vs 3 simple rules (with CIs, on unseen stores too); alert backtest; budget replay vs usual ordering rules (SIMULATED) | **S** |

## 2. Architecture (offline model, live decisions, no servers)

```
sales.csv (+ promotions, holidays)               shop inputs + product_settings.csv (placeholders)
      |                                                     |
      v                                                     |
[1] pipeline.py  (run once)  -> outputs/                    |
    forecast, error spread, L-day error quantiles,          |
    what-if driver effects, evaluation, alert backtest,     |
    budget replay (budget_sim.py)                           |
      |                                                     v
      +----> [2] risk assessment + prioritisation (inventory.py, laris_core.py), live
                  -> category, tier, RM at risk, explanation
             [3] budget optimiser (inventory.allocate_budget), live
                  -> order list within the cash, cut reasons
                        |
                        v
             app.py + views/ (Streamlit, green multipage design)
```

No database, no web API, no LLM: explanations are templated from the numbers, so nothing is made up.
"Today" is a replay date in the held-out test period, so "reveal what actually happened" works.

## 3. Predictive model (layer 1)

- **Targets:** daily units per store x product family for the next 7 days; total demand over the
  product's lead time (for P(stockout before delivery)); unsold units by expiry (for dead stock).
- **Model:** one global `HistGradientBoostingRegressor` (Poisson loss). Chosen over per-series ARIMA/ETS
  (about 1,800 series, slow, no cross-learning, weak with promotions), Prophet (slow, extra dependency),
  deep learning (needs a GPU, little gain at family level, harder to explain) and LightGBM (same family,
  extra dependency). Fast on CPU, handles zeros and missing lags.
- **Leakage rule:** every feature uses sales at least 7 days old, plus things known in advance (calendar,
  payday, national holidays, planned promotions). One model forecasts all 7 days without recursion.
- **Features:** lags 7/14/21/28; same-weekday 4-week mean; 7/28-day rolling mean, spread, zero share;
  day of week, day of month, month, payday, holiday; planned and recent promotions; store and product.
- **Baselines:** same day last week; 28-day average; same weekday, 4-week mean.
- **Split:** train, then validation (42 days: error spread, error quantiles, thresholds), then test
  (63 days: every reported number).
- **Uncertainty:** daily error spread per series, and error quantiles of L-day totals from validation
  (split conformal). The alert backtest picks whichever gives better-calibrated probabilities on validation.
- **Data quality:** runs of 5+ zero-sales days in a busy series are flagged (possible stockout, closure,
  missing data) and excluded from training targets and evaluation.
- **Explanations from the model:** the same model re-run with the promotion, holiday or payday switched
  off gives each driver's effect on the week ("the promotion adds about 66 units").

## 4. Risk assessment and prioritisation (layer 2)

- **Run-out risk:** P(demand over lead time > stock + on order), from the forecast and the chosen
  uncertainty model. Alert ("Runs out before delivery") at a threshold chosen on the validation period.
- **Bridge top-up:** expected shortfall before the order lands, rounded up to packs, from a wholesaler.
- **Dead stock:** E[(stock - demand over shelf life)+]; flagged if cover exceeds the shelf life (or 4
  weeks for long-life items). Action: skip the reorder, move to the front or discount.
- **Other categories:** needs this order (below the order-up-to level), demand surge (forecast at least
  1.3x last week), unusual recent sales (2+ days outside +/-3 sigma, or a zero run), not enough reliable
  data (short history, missing error estimate, a range wider than the forecast, or the model doing worse
  than "same day last week" on this product lately; never escalates to Act today).
- **Priority:** tier, then RM at risk if nothing is done (stockout: units short x (margin + goodwill for
  must-haves); expiry: RM expiring; overstock: cash tied up x holding rate), with an act-by day.

## 5. Budget optimiser (layer 3)

- Each product's window = lead time + min(review cycle, shelf life).
- Value of the next pack = (margin + goodwill if must-have) x P(it sells) - overstock cost x P(it doesn't);
  overstock cost = unit cost if it would expire, else a 2% holding cost.
- Must-have packs are bought first until the item covers its expected demand; then every pack competes on
  value per ringgit until the cash runs out. Packs that don't fit are skipped and cheaper ones still
  considered. With no cash limit this is the newsvendor critical fractile.
- Output: quantity, ideal quantity, RM, expected units short, expected waste, and why anything was cut.

## 6. Evaluation (S)

| Dimension | Metric | Label |
|---|---|---|
| Forecast | WAPE (daily, 7-day totals), MAE, bias vs 3 rules; bootstrap 95% CI of the difference; by volume tier; on stores left out of training | MEASURED |
| Uncertainty | Share of actual L-day sales inside the 50/80/90/95% ranges; Brier score; reliability | MEASURED |
| Alerts | Precision, recall, false-alarm rate, PR-AUC vs a min-stock rule and a last-week rule; share of real RM loss in the top 20% of ranked cases | MEASURED on real sales, SIMULATED stock |
| Decisions | Lost margin, expiry waste, must-have units short, fill rate, stockout days, cash in stock: LARIS vs the same optimiser with simpler forecasts, vs a pro-rata cut, vs three usual-practice rules, at 50/75/100% cash, across a size-stratified store sample; win rate by store; sensitivity (margins +/-30%, goodwill 0/6, shelf lives +/-30%, deliveries 1 day late) | SIMULATED |
| Usefulness | Order fits the budget (asserted); owner comprehension and time saved | By design / needs a pilot |

## 7. Tests (`pytest`)

Allocator: never over budget (200 random cases), equals brute force with equal pack costs and stays within
one pack otherwise, must-haves cut last, pack sizes, newsvendor limit. Dead stock, categories and tiers,
low confidence never Act today. Pipeline helpers (zero runs, bootstrap CI, L-day windows, alert threshold
chosen on validation). Budget replay (budget respected, units conserved, fast allocator equals the exact
greedy). Every app page renders headlessly; the pitch scenario loads; more budget spends more.

## 8. Demo scenario

"Tight-budget Wednesday", chosen by a stated rule (Settings, "Load the pitch scenario"): the median-volume
store and the Wednesday with the largest predicted rise in must-have demand, stock from the "Tight budget"
preset, cash at 60% of the ideal order. See `PITCH_PLAN.md` for the 3-minute flow.

## 9. Responsible AI

- **Disclosure:** every page names the data (Ecuador, not Malaysia); MOCK data shows a banner.
- **Uncertainty:** always shown; probabilities are checked for calibration.
- **Advice only:** no automatic ordering; "download" is the only output.
- **Inputs:** costs and margins are the shop's own; defaults are labelled placeholders.
- **Honest labels:** measured, simulated, estimates and placeholders are never mixed; where a simple rule
  wins, the app says so.

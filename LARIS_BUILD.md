# LARIS: prototype build plan

Track 1, **Predict Early, Decide Better**. LARIS *predicts* what will run out or go to waste before the next delivery, and *decides* how to spend a limited budget to prevent it.

## 1. Track fit

| Track asks | LARIS answer | Letter |
|---|---|---|
| Spot the problem before it's expensive | 7-day sales forecast; products that run out before the next delivery; stock that will expire unsold | **L**, **A**, **R** |
| Help someone decide what to do | The best order list for the cash available, must-haves first; a bridge buy for urgent gaps; skip or discount dead stock | **I**, **A**, **R** |
| Credible evidence | Accuracy vs simple rules on data the model never saw; simulated comparison at the same budget, labelled | **S** |

## 2. Architecture (offline-first, no servers)

```
sales.csv  +  product_settings.csv
      |
      v
pipeline.py  (run once, about 1-3 min)        -> outputs/  forecasts, error spread, metrics, simulation
      |
      v
app.py (Streamlit)  <- shop inputs: stock on hand, on order, budget, must-have ticks
      |
      +-- inventory.py: run-out risk (A), dead stock (R), budget allocation (I)
```

**Design choices:**
- **No database and no API.** The app reads precomputed files, so the demo can't break on a network failure.
- **No LLM.** Explanations are templated from the numbers, so nothing is made up.
- **Replay mode.** "Today" is any date in the held-out test period, so "reveal what actually happened" works.

## 3. Tech stack

| Layer | Choice | Why |
|---|---|---|
| Language | Python 3.10+ | Whole team can read it; one language end to end |
| Data | pandas, pyarrow (parquet) | Fast enough for about 1M rows; no database needed |
| Forecast model (L) | scikit-learn HistGradientBoostingRegressor, Poisson loss | Fast on CPU, handles categories natively, suits counts with many zeros |
| Uncertainty | Validation-period forecast errors + normal approximation (scipy) | Safety stock and stockout chances come from measured error, not guesses |
| Decision engine (A, R, I) | numpy/scipy: greedy marginal allocation | Optimal for this problem shape, explainable, no solver to install |
| Evaluation (S) | Chronological train / validation / test; WMAPE, MAE, bias; band coverage; policy simulation | Fair, leakage-free, reproducible |
| UI | Streamlit + Altair | Interactive sliders and tables in pure Python; already built |
| Run / deploy | Local laptop (primary); Streamlit Community Cloud (optional) | Fewest moving parts; backup screen recording |
| Data | Kaggle Store Sales (Corporacion Favorita, Ecuador); fallback: Store Item Demand | Real daily retail sales with promotions and holidays |
| Dev tools | Git/GitHub; Kiro credits optional (claim before 10 Oct); Grafilab not needed (no GPU) | Never depend on credits |

## 4. Components and status

| Letter | Module | What it computes | Status |
|---|---|---|---|
| **L** Lihat ke depan | `pipeline.py` | 7-day forecast per store x product; error spread from validation | **Built**, tested on mock data; real-data run pending |
| **A** Amaran stok habis | `inventory.assess` | Chance of running out before delivery; run-out day; CRITICAL / ORDER / OK; **bridge buy** quantity | Built; **add** bridge buy and per-product lead time + review cycle |
| **R** Rendahkan pembaziran | `inventory.dead_stock` (new) | Days of cover vs shelf life; expected units expiring; action: skip reorder or discount | **New** (small) |
| **I** Ikut bajet | `inventory.allocate_budget` (new) | Best order list within budget; must-have items protected; pack sizes; what got cut and why | **New** (core differentiator) |
| **S** Semak hasil | `pipeline.py` metrics + `simulate_budget` (new) | Accuracy vs 2 baselines; band coverage; LARIS vs 3 allocation rules at 50/75/100% budget; ±30% margin check | Metrics **built**; budget simulation **new** |
| App | `app.py` | LARIS sections with Malay titles and English subtitles; budget slider; must-have ticks; dead-stock card | **Update** |
| Settings | `product_settings.csv` (new) | Per product: unit cost, margin, shelf life, lead time, review days, pack size, must-have | **New**; defaults labelled as placeholders |

## 5. Model (L)

- **Target:** daily units per store x product for the next 7 days.
- **Leakage rule:** every input uses sales from 7+ days earlier, plus things known in advance (calendar, holidays, planned promotions). One model therefore forecasts all 7 days, with no recursion.
- **Features:**
  - lags at 7, 14, 21 and 28 days; same-weekday 4-week mean
  - 7/28-day rolling mean and spread; zero-sales share
  - day of week, month, payday, holiday
  - planned and recent promotions
  - store and product
- **Baselines:** same day last week; 28-day average.
- **Split:** train, then validation (42 days, used only for error spread), then test (63 days, all reported numbers).
- **Metrics:** WMAPE on daily and 7-day totals, MAE, bias, and the share of actuals inside the 90% band.

## 6. Decision engine

**A (run-out):**
- P(run out before delivery) = P(demand over lead time > stock + on order). The spread is sigma x sqrt(lead time).
- **CRITICAL** if the run-out day falls within the lead time.
- **Bridge buy:** expected shortfall before the order lands, rounded up. Suggest buying it from a wholesaler.

**R (dead stock):**
- Expected units unsold by expiry = E[(stock - demand over shelf life)+].
- Flag if the units held cover more days than the shelf life (or more than 4 weeks for non-perishables).
- Action: skip the reorder, plus a discount or bundle suggestion.

**I (budget allocation):**
- For each product, use its own window: lead time + review cycle, capped by shelf life.
- Value of the k-th extra unit = shortage cost x P(D > x+k-1) - overstock cost x P(D <= x+k-1).
  - Shortage cost = margin, plus a goodwill cost for must-have items.
  - Overstock cost = unit cost if it would expire unsold, else a holding cost.
- Take units (or packs) in order of value per ringgit, while value > 0 and budget remains.
- With no budget limit, this reduces to the classic newsvendor rule.
- Output: quantity, RM spent, expected units short, expected waste, and what was cut and why.

**S (budget simulation):**
- Replay the test weeks with historical sales as demand.
- Compare LARIS with three rules at the same budgets (50/75/100% of the ideal order):
  1. split by last month's sales value
  2. top up the fastest sellers first
  3. scale the ideal order down pro rata
- Report lost margin (RM), waste (RM) and must-have units short, plus a ±30% margin sensitivity check. Labelled SIMULATED.

## 7. Tests (before the demo)

- **Allocator:** never exceeds the budget; matches a brute-force search on 3-product toy cases; must-have items are cut last; pack sizes respected.
- **Dead stock:** a product with cover beyond its shelf life is flagged; a fast seller isn't.
- **Pipeline:** the model beats both baselines on the test period (or the slide says so); band coverage is near 90%.
- **App:** runs headless with no exceptions; the three demo scenarios load.

## 8. Demo scenarios

1. **Normal week, full budget:** mostly OK, a few routine orders.
2. **Tight budget (the Encik Hafiz story):** RM 600 against a RM 1,055 ideal order. Eggs are CRITICAL with a bridge buy, milk and yoghurt are flagged as dead stock, and the allocation protects must-haves. Then drag the budget to RM 900.
3. **Edge case:** a product with sparse history (wide band) or a false alarm, showing that the cost of being wrong is small.

## 9. Responsible AI

- **Disclosure:** a banner names the data (Ecuador, not Malaysia).
- **Uncertainty:** always shown.
- **Advice only:** no automatic ordering.
- **Inputs:** costs and margins are the shop's own.
- **Privacy:** shop data is processed locally.
- **Honest labels:** measured and simulated results are never mixed.

## 10. Remaining build (about 5-6 dev-hours, split 4 ways)

| Who | Task | Est. |
|---|---|---|
| P1 (ML) | Download Kaggle data; run the pipeline; check the model beats the baselines; fill in the S numbers | 1.5 h |
| P2 (decision) | `dead_stock`, `allocate_budget`, bridge buy, per-product windows, tests | 2.5 h |
| P2/P1 | `simulate_budget` + sensitivity check | 1.5 h |
| P3 (app) | LARIS labels (Malay + English), budget slider, must-have ticks, dead-stock card, allocation table | 2 h |
| P4 (pitch) | `product_settings.csv` defaults (labelled), demo script, slides, 2-3 shop-owner calls | parallel |

Order: P1 starts the data download now. P2 and P3 work in parallel against mock outputs. Integrate, freeze a working version, then rehearse.

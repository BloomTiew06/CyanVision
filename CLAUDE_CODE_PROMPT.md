You're working in the `ShelfSignal` folder of our hackathon project (Track 1: **Predict Early, Decide Better**). Turn the existing ShelfSignal/STOK prototype into **LARIS**, a budget-aware restocking assistant for small Malaysian grocers. Work in small, tested steps and don't break what already works.

## Read first
`LARIS_BUILD.md` (the spec), `LARIS_OVERVIEW.md`, `README.md`, `pipeline.py`, `inventory.py`, `app.py`, `make_mock_data.py`.

Then confirm the baseline runs:
```
python make_mock_data.py
python pipeline.py --data data_mock --out outputs_mock
# PowerShell: $env:SHELFSIGNAL_OUT="outputs_mock"; streamlit run app.py
```
Run `git init` if needed, and commit as "baseline" before changing anything.

## The product: L·A·R·I·S (Malay title, English subtitle)
- **L · Lihat ke depan (Look ahead):** a 7-day sales forecast per product, with a confidence range.
- **A · Amaran stok habis (Out-of-stock alert):** what runs out before the next delivery, with a suggested bridge top-up.
- **R · Rendahkan pembaziran (Reduce waste):** dead stock that won't sell before it expires; skip the reorder or discount it.
- **I · Ikut bajet (Stay within budget):** the best order list for the cash available, with must-have items first.
- **S · Semak hasil (Check the results):** accuracy against simple rules, plus a simulated comparison at the same budget.

Tagline: "Biar laris, jangan habis." (Sell well, never run out.)

## Non-negotiable rules
- **Never invent metrics, savings, quotes or market numbers.** Measured numbers come only from the held-out test period. Simulated numbers are labelled SIMULATED, with their assumptions listed. Placeholder settings are labelled as placeholders.
- **Keep the leakage rule in `pipeline.py`.** Features use sales at least 7 days old plus the calendar, holidays and planned promotions. Keep the chronological train → validation → test split.
- **Keep the MOCK banner logic and the data disclosure.** The model is trained and tested on Kaggle Store Sales (Corporación Favorita, Ecuador), not Malaysian data.
- **No LLM, no database, no web API.** The app reads precomputed `outputs/`; the decision logic runs live in `inventory.py`.
- **Work in small steps.** After each one, run pytest, the mock pipeline and a headless app check (`streamlit.testing.v1.AppTest`), then commit.
- **Use Windows-friendly paths and commands.**

## Tasks, in order

### 1. `product_settings.csv` and a loader
Columns: `product, unit_cost_rm, margin_rm, shelf_life_days, lead_time_days, review_days, pack_size, must_have`.

Add one row per default Favorita family (GROCERY I, BEVERAGES, DAIRY, BREAD/BAKERY, EGGS, POULTRY, PRODUCE, MEATS, FROZEN FOODS, CLEANING, PERSONAL CARE, DELI), plus a `DEFAULT` row. The fallback dataset's `ITEM n` products use the `DEFAULT` row. Placeholder values, documented as placeholders in the README and the app:
- **Fresh** (BREAD/BAKERY, PRODUCE, POULTRY, MEATS, DELI): shelf life 3–5 days, lead time 1, review 2.
- **DAIRY:** shelf life 10. **EGGS:** shelf life 21. Both: lead time 3, review 7.
- **Longer-life:** FROZEN FOODS 90, GROCERY I 180, BEVERAGES 365, CLEANING and PERSONAL CARE 730. All: lead time 3, review 7.
- **must_have:** True for EGGS, BREAD/BAKERY and GROCERY I.
- **Cost, margin and packs:** unit cost RM 5.00, margin 20–30% of cost, pack size 1.

Add `inventory.load_settings(path)`, which returns a DataFrame indexed by product with the DEFAULT row as fallback.

### 2. `inventory.py`: pure functions, unit-tested
**a) Per-product protection window.** Window = lead time + review cycle. For perishables, never plan to hold more than `shelf_life_days` of cover.

**b) Extend `assess()`.** Accept the review cycle per product. When the status is CRITICAL, add `bridge_qty` = ceil(expected shortfall before the order lands).

**c) `dead_stock(daily_fc, sigma_d, on_hand, shelf_life_days, unit_cost)`.** Returns:
- `days_of_cover`
- `expected_expire_units` = E[(on_hand − D_shelf)+], using a normal approximation, where D_shelf is demand over the shelf life
- `expected_expire_rm`
- `flag`: cover > shelf life, or cover > 28 days when shelf life > 60
- action text, e.g. "Skip reorder; move to front or discount"

**d) `allocate_budget(items, budget, goodwill_rm=3.0)`.** `items` has: product, mu_window, sd_window, position (on hand + on order), unit_cost, margin, overstock_cost, pack_size, must_have.
- **Value of the next pack:** shortage_cost × P(D > y) − overstock_cost × P(D ≤ y). Here y is the stock after the previous packs (use +0.5 per unit for continuity), and shortage_cost = margin, plus goodwill_rm if the item is must-have.
- **Overstock cost:** unit_cost if shelf_life ≤ window + 3, else 0.02 × unit_cost (a holding cost).
- **Greedy:** pick packs by value per RM, while value > 0 and the next pack fits the budget.
- **Return per product:** qty, ideal_qty (budget = ∞), spend_rm, exp_short_units, exp_leftover_units, exp_lost_margin_rm, exp_waste_rm, and `cut_reason` (e.g. "budget: lower value per RM", "enough stock", "dead stock").
- **Also return** totals and the ideal order value.

**e) Baseline allocation rules for evaluation:** `proportional_to_sales_value`, `top_sellers_first`, `prorata_of_ideal`.

**Tests (`tests/test_inventory.py`, pytest):**
- the budget is never exceeded
- greedy matches brute force on small 3-product toy cases
- must-have items are cut last under a tight budget
- pack sizes are respected
- `dead_stock` flags a product with 15 days of cover and a 10-day shelf life, but not a fast seller
- `bridge_qty` > 0 only when the status is CRITICAL
- with no budget limit, the allocation matches the newsvendor critical fractile

### 3. `pipeline.py`: `simulate_budget`
Over the test period, using the existing forecasts and sigma, replay the weekly order cycles for one store (the busiest by default, for speed).
- **Budgets:** 50%, 75% and 100% of each cycle's ideal order value.
- **Policies:** LARIS (`allocate_budget`), proportional, top-sellers-first, and pro-rata.
- **Demand:** historical sales. Note that this is censored by past stockouts.
- **Tracked per policy:**
  - lost margin (RM)
  - waste (RM): perishables expiring past their shelf life; simple FIFO or age buckets is fine
  - must-have units short
  - fill rate
- **Sensitivity run:** margins ±30%. Do the conclusions still hold?

Write `outputs/budget_sim.csv`. Add a `budget_simulation` block to `metrics.json` with the label "SIMULATED", the assumptions, and the headline at 75% budget. Keep runtime under about 2 minutes on the full Favorita data; if you subsample, say so.

### 4. `app.py`: the LARIS UI
- **Header:** "LARIS", the tagline, a strip showing **L·A·R·I·S** with the Malay titles, the data-disclosure caption, and the MOCK banner (kept).
- **Sidebar:**
  - store, "Pretend today is", service level
  - **budget slider (RM):** default 60% of the ideal order value, maximum 150%
  - reveal toggle
  - demo presets: "Normal week", "Tight budget" and "Sparse history". Each sets stock levels and budget deterministically.
- **Input editor:** per product, on hand, on order and a must-have tick, plus cost, margin, shelf life, lead time and review cycle from `product_settings.csv`. All editable, and labelled as placeholders.
- **Sections in demo order, each headed "Malay title · English":**
  1. **A · Amaran stok habis (Out-of-stock alert):** the red CRITICAL banner, the bridge top-up suggestion, and metrics.
  2. **I · Ikut bajet (Stay within budget):**
     - allocation table: product, must-have, ideal qty, LARIS qty, RM, expected short, cut reason
     - totals: spent / budget / ideal
     - a line such as "With RM X more you would add …"
  3. **R · Rendahkan pembaziran (Reduce waste):** dead-stock cards showing cover vs shelf life, expected units and RM expiring, and the action.
  4. **L · Lihat ke depan (Look ahead):** the existing forecast chart with its band, plus projected stock.
  5. **S · Semak hasil (Check the results):**
     - the existing accuracy table and band coverage
     - a new "Budget simulation" tab: a chart of lost margin and waste by policy and budget level, labelled SIMULATED, with the assumptions and the sensitivity result
- **Check:** `AppTest` runs every preset with no exceptions, and every number on screen traces to `outputs/` or `inventory.py`.

### 5. Real data (only if available)
If `data/store-sales/train.csv` exists, run `python pipeline.py --data data/store-sales --out outputs`. If it doesn't, check for Kaggle credentials (`%USERPROFILE%\.kaggle\kaggle.json`), and **ask me before downloading anything**.

Report the real test metrics exactly as printed. If the model doesn't beat a baseline, say so plainly.

### 6. Docs
Update `README.md` with:
- run steps
- the file list
- the LARIS-to-code mapping
- status: built, mocked or untested
- a short section on what is measured vs simulated vs placeholder

## Definition of done
- pytest passes. The mock flow, and the real flow if the data is available, run end to end.
- The app shows all five LARIS sections. The budget slider and the must-have ticks change the allocation live, and the presets work.
- Every simulated number is labelled SIMULATED, every placeholder is labelled, and no figure anywhere is invented.
- Your final message covers: what changed, how to run it, the real metrics (or "not run"), and known limitations.

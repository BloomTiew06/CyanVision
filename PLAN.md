# ShelfSignal: Cukup stok?

**Track 1: Predict Early, Decide Better** · Plan v3 · 9 Oct 2026

> **In one line:** ShelfSignal tells a small shop, before the shelf is empty, what will run out before the next delivery and how much to order today.

**Build status:**
- **Built and tested on mock data:** the pipeline, the decision engine, and the app (organised as S·T·O·K).
- **Not yet run on the real Kaggle data,** so there are no real accuracy numbers yet.
- **Not built:** CSV upload and scenario preset buttons.

---

## 1. Problem statement

Small Malaysian retailers (minimarts, kedai runcit, independent grocers) decide every week how much to reorder, before they know next week's demand. Most decide by looking at the shelf and remembering last week. *(Assumption: confirm with 2-3 shop owners.)* The problem shows up too late, at the shelf:

- **Order too little.** The shelf is empty before the lorry arrives. The sale is lost, and a customer who can't find a staple may start shopping elsewhere.
- **Order too much.** Cash sits in slow-moving stock, and perishables expire.

By the time either is visible, the cost has already happened. A supplier who takes three days can't fix a shelf that empties tomorrow.

**How might we** tell a small retailer, before the shelf is empty, which products will run out before the next delivery and how much to order today?

---

## 2. Persona *(illustrative; replace with what real shop owners tell you)*

**Encik Hafiz, 42, family minimart owner, Shah Alam housing area** *(fictional composite)*

| | |
|---|---|
| **Shop** | 3 aisles, about 300 regularly stocked products, one helper |
| **Tools** | A basic POS till that records every sale; orders by WhatsApp or phone |
| **Suppliers** | Two or three distributors, each delivering 2-4 days after an order *(assumption)* |
| **Routine** | Walks the aisles on Tuesday night, eyeballs the shelves, places orders on Wednesday |
| **Pains** | Runs out of eggs, bread and drinks on busy weekends and festive weeks, while slow items gather dust; cash is tight before payday |
| **Goals** | Never be empty on staples; don't tie up cash; spend under 10 minutes a week on ordering |
| **What would make him switch** | A short list each Wednesday: what will run out, what to order, and why |

**Secondary users:**
- the shop helper who places orders
- a distributor's sales rep who wants to suggest orders to many shops

---

## 3. Target audience

**Primary users:** owner-operators of independent minimarts, kedai runcit and small grocers in Malaysia who already record sales digitally (POS or e-invoicing). This is the entry condition: STOK needs daily sales per product.

**Who could pay, and how it reaches shops:**
1. **Shop subscription:** a low monthly fee, with a free tier for a few products.
2. **POS vendors:** embed STOK as a feature in the tills shops already use. This is the fastest route to many shops.
3. **FMCG distributors:** offer it to the retailers they supply, which sells more of their stock and cuts emergency deliveries.

**Not for now:**
- large chains, which already run planning systems
- shops with no digital sales records

**Market size: not yet sourced.** Before any slide claims a number, find a credible count of small grocery retailers in Malaysia (e.g. the DOSM economic census or MSME statistics).

---

## 4. Solution: S·T·O·K

"Stok" is Malay for stock. Each letter is one part of the solution the shopkeeper sees, and each is a labelled section of the app. The input underneath is the shop's daily sales (demo: Kaggle Favorita; real shop: a POS export of date, store, item, sales).

| Letter | Feature | What the shopkeeper sees | How it works |
|---|---|---|---|
| **S**: Sales forecast | Next 7 days, with confidence | "Next 7 days: 2,472 units, -11% vs last week" (illustrative), with an uncertainty band | Gradient boosting on sales from 7+ days earlier, calendar, holidays and planned promotions. Must beat "same day last week" and "28-day average" on held-out data. The band comes from the measured forecast error |
| **T**: Time to run out | Risk and urgency | "88% chance of running out before delivery; runs out on day 2" (illustrative). A red alert when an order placed today would arrive too late: expedite, transfer or substitute | Forecast over the supplier lead time vs stock + on order. Status CRITICAL / ORDER / OK |
| **O**: Order now | What to buy, ranked | "Order 90 units today" (illustrative), sorted by ringgit at risk; a 90-99% service-level slider | Forecast for lead time + 7 days + safety stock from the measured error, minus stock held, rounded to pack size |
| **K**: Keep score | Proof it works | Accuracy vs the two simple rules; how often real sales fell inside the band; a "reveal what actually happened" replay; stock needed for the same service level | Held-out test metrics (measured) + band-coverage check + policy simulation (labelled SIMULATED) |

**How it comes together:**
- **S** says what will sell.
- **T** says what runs out before the lorry comes.
- **O** says what to order today.
- **K** proves it works.

**Pitch line:** "Cukup stok? ShelfSignal tells a small shop, before the shelf is empty, what will run out before the next delivery and how much to order today."

---

## 5. How it works (under the hood)

**Data in:** daily sales per store x product. For the demo, that is Kaggle Store Sales (Corporacion Favorita, Ecuador): real data at product-family level, with promotions and holidays.

**S: Sales forecast** (`pipeline.py`)
- **Target:** daily units for each of the next 7 days.
- **No peeking at the future:** every input uses sales from at least 7 days earlier, plus things known in advance (calendar, national holidays, planned promotions). One model therefore forecasts all 7 days at once, without feeding its own guesses back in.
- **Inputs:**
  - sales 7, 14, 21 and 28 days ago
  - the same-weekday average over the last 4 weeks
  - 7- and 28-day rolling averages and spread, and the share of zero-sales days
  - day of week, day of month, month, payday
  - holidays, planned and recent promotions
  - store and product
- **Model:** scikit-learn gradient boosting (Poisson loss, suited to counts with many zeros). It is kept only if it beats both simple rules on the test period.
- **Testing in time order:** train, then 42-day validation (used only to measure forecast error), then a 63-day test (all reported numbers). Accuracy measures: WMAPE on daily sales and on 7-day totals (what ordering depends on), MAE and bias.

**T: Time to run out** (`inventory.assess`)
- P(stockout before delivery) = P(demand during lead time > stock + on order), using the measured daily error x sqrt(lead time).
- The run-out day is the first day cumulative forecast exceeds available stock.
- **CRITICAL** if that day falls within the lead time. Otherwise **ORDER** if below the reorder target, or **OK**.

**O: Order now** (`inventory.assess`, `inventory.rank`)
- Order-up-to level = forecast(lead time + 7) + z x error x sqrt(lead time + 7). Order = order-up-to level - stock - on order, rounded up to pack size.
- z comes from the chosen service level.
- Ranked by status, then ringgit margin at risk (expected units short x unit margin).

**K: Keep score** (`pipeline.py`, app Evidence tabs)
- **Measured:** test accuracy vs the two simple rules, per product, plus the share of test days inside the 90% band.
- **Simulated:**
  - replays the test period with historical sales as demand
  - both policies use the same ordering rule; only the forecast differs (model vs 28-day average)
  - service levels are swept, and the stock each needs for the same fill rate is compared

---

## 6. Solution impact

Three kinds of claims, never mixed:

| Type | What we show | Status |
|---|---|---|
| **Measured** (held-out real data) | 7-day forecast error vs "same day last week" and "28-day average"; share of real sales inside the 90% band | **TBD:** run the pipeline on real data |
| **Simulated** (replay of the test period) | Days of stock needed to serve the same share of demand: forecast policy vs moving-average policy; stockout days at equal stock | **TBD.** Assumptions: sales used as demand (censored by past stockouts), fixed lead time, weekly orders, no minimum order or shelf life |
| **Projected for one shop** (formula, the shop's own numbers) | Monthly benefit = (stockout units avoided x unit margin) + (stock reduced x unit cost x monthly holding-cost rate) | Calculate only from a real shop's inputs; no RM claims until then |

**Wider impact (potential, not measured):**
- fewer empty shelves on staples for neighbourhood customers
- less working capital locked in stock for micro-businesses
- fewer expired perishables

**How to prove it after the hackathon:** a 4-week pilot with 3 shops, comparing stockout days and average stock against their previous 4 weeks.

---

## 7. Data: what's real, what isn't

**No credible public Malaysian product-level sales data exists.** Searching OpenDOSM, data.gov.my and the web found no daily store x product sales, inventory, stockout, promotion or lead-time data. Real Malaysian data is either aggregate (DOSM) or prices only (PriceCatcher). The full audit is in Appendix A.

**Decision (option C, built as A first):**
- **Train and test on real public international retail data:** Favorita, with Store Item Demand as the fallback.
- **Add Malaysian context only where it's real:** RM costs, stock and lead times as the shop's own inputs; a POS-export path for real shops; optionally, a DOSM retail seasonality chart.
- **Never claim the model learned Malaysian demand.**

---

## 8. Why it can win

- **Decision first, not a dashboard.** The demo opens on a red alert: "3 products run out before your delivery can arrive". The order list follows.
- **Beats the obvious alternatives, measurably:**
  - **Fixed low-stock alerts.** POS tools commonly use these *(check 2-3 local POS products before claiming)*. STOK accounts for upcoming demand and supplier lead time, so it warns while there's still time to act.
  - **A spreadsheet moving average.** It's one of the two baselines in K, compared on held-out data.
- **Fair evidence:**
  - stock is compared at the same service level, not cherry-picked
  - the uncertainty band is checked for honesty
  - the replay shows what really happened
- **Honest about limits:** the data source is on screen, and the simulation is labelled.
- **Known weakness:** demand forecasting is a familiar topic. The decision-first demo and the evidence are what set it apart.

---

## 9. Responsible AI and limitations

- **Not Malaysian data:** the model is trained and tested on Ecuadorian grocery data and says so on screen. A Malaysian shop would retrain on its own sales export.
- **Product family, not individual items,** in the demo data. Individual-item data (e.g. M5) is a next step.
- **Censored demand:** past sales understate demand on days a product ran out.
- **Uncertainty is shown, not hidden:**
  - the band, the service-level slider, and safety stock from measured error
  - products with little history get wider bands
- **Advice, not automation:** STOK recommends; the shopkeeper decides and places the order.
- **Privacy:** shop sales are business data, processed locally in the demo. Nothing personal is collected.
- **Wrong forecasts:** a false alarm costs a few extra days of stock; a miss is limited by safety stock. Both trade-offs appear in K.

---

## 10. Risks and mitigations

| Risk | Mitigation |
|---|---|
| The model doesn't beat the moving average for some products | Report per product; use the better method where it loses; say so |
| Kaggle account or download delays | A teammate's account; the Store Item fallback works with no code change |
| The band is too narrow (coverage well below 90%) | Widen the error estimate before demoing; show the check |
| The demo laptop fails | Run locally from precomputed outputs; keep a recorded backup video |
| Placeholder RM values look like claims | Label them as inputs on screen and in the pitch |

---

## 11. One-day build plan

**Roles, for 4 people** (with 3, merge P4 into P2):
- **P1, S (ML):** real data run, data quirks, at most 1-2 tweaks, error analysis.
- **P2, T + O (decision):** check `inventory.py`, design the three demo scenarios, test lead-time sensitivity.
- **P3, app:** polish the STOK sections, scenario presets, number formats, backup video.
- **P4, K + pitch:** evidence slides, shop-owner calls, judge Q&A, timekeeping.

**Dependencies:** everything flows through `outputs/` (contract in the README). P3 can build on mock outputs straight away; P2 needs no data.

| Time | What happens |
|---|---|
| 0:00-0:30 | Everyone runs the mock flow end to end; P1 starts the Kaggle download |
| 0:30-2:00 | P1: first real metrics vs baselines. P2: scenarios and edge cases. P3: polish on mock outputs. P4: slide skeleton, line up shop calls |
| **2:00** | **Checkpoint:** real `outputs/` in place, app runs on real data. Save as v1 |
| 2:00-4:00 | P1: per-product error analysis, at most 1-2 tweaks kept only if test error falls. P2: lead time 2/3/5 sensitivity. P3: presets and wording. P4: slides with real numbers, Q&A |
| **4:00-5:00** | **Integration; freeze v2; break** |
| 5:00-7:00 | Stretch only if v2 is solid: DOSM context panel, CSV upload of stock levels |
| 7:00-8:00 | Rehearse the 3 scenarios; fix bugs; record the backup video |
| 8:00-9:00 | Pitch x3; Q&A drill; submission and README |
| 9:00-10:00 | Buffer |

**Cut order if behind:**
1. stretch goals
2. the feature-importance chart
3. the simulation chart (keep its one-line headline)

**Never cut:** S accuracy vs baselines, the T alert, and O order quantities.

---

## 12. Demo script (60-90 s, in the order T, O, S, K)

1. **Hook:** "It's Wednesday. Encik Hafiz's supplier needs 3 days."
2. **T:** the red alert. Three products run out before an order placed today can arrive.
3. **O:** the ranked order list, with RM at risk and recommended quantities.
4. **S:** open one product: forecast vs last week, a planned promotion, the uncertainty band. A judge edits stock or lead time, and the status flips live.
5. **K:** "Reveal what actually happened" (a replay), then accuracy vs the simple rules, band coverage, and the SIMULATED stock comparison.
6. **Close:** "Trained and tested on real public retail data; a Malaysian shop plugs in its own POS export."

**Three scenarios to prepare:**
- **Normal:** all OK, so no action.
- **High risk:** promotion week, critical items.
- **Edge case:** a product with sparse history (wide band) or a false alarm, showing that the cost of being wrong is small.

---

## 13. Judge Q&A

- **Why ML and not a moving average?** Show the K accuracy table. If the model doesn't win, say so and use the better method.
- **This isn't Malaysian data.** Correct. No public Malaysian product-level data exists (we checked). The method is validated on real retail data, and a shop retrains on its own POS export.
- **There's no inventory in the data.** Stock and lead time are the shop's inputs. The simulation uses sales as demand, with censoring disclosed. FreshRetailNet-50K (stockout-labelled) is the next step.
- **What if the forecast is wrong?** The band, safety stock from measured error, and the service-level slider. A false alarm costs extra days of stock, shown in K.
- **Don't shopkeepers already know what sells?** They know the pattern. They don't know which products cross zero before a delivery lands, or how much buffer the uncertainty justifies. Test it in the 3-shop pilot.
- **Who pays?** POS vendors embedding it, shop subscriptions, and distributors offering it to the shops they supply.

---

## 14. Next action

P1 downloads Store Sales now and runs `python pipeline.py --data data/store-sales --out outputs`. The real S accuracy and K numbers decide the pitch.

---

## Appendix A: Data audit

Legend: **V** = I opened the source page; **D** = documented by a third-party README; **U** = Kaggle pages don't render for my tools, so check on download.

| # | Dataset (URL) | Publisher / coverage | Period, granularity, columns | Supports the forecast? | Licence / access | Usable today? |
|---|---|---|---|---|---|---|
| 1 | Headline Wholesale & Retail Trade, https://open.dosm.gov.my/data-catalogue/iowrt | DOSM, Malaysia (national) | Monthly, latest Jul 2026. series, date, sales (RM mn), volume, volume_sa. **V** | No: context only | CC BY 4.0, direct download | Yes |
| 2 | Wholesale & Retail Trade by Group (3-digit), https://open.dosm.gov.my/data-catalogue/iowrt_3d | DOSM, Malaysia | Monthly by MSIC group, latest Jul 2026. series, date, group, sales, volume. **V** | No: seasonality context | CC BY 4.0 | Yes |
| 3 | PriceCatcher, https://data.gov.my/data-catalogue/pricecatcher | KPDN & DOSM, shop-level | Daily prices, monthly files (2022 onward exist). **V** | No: prices, no quantities | CC BY 4.0 | Yes, not needed |
| 4 | Multi-Country Retail Sales Dataset, https://data.mendeley.com/datasets/v8h8wn4w37 | Mendeley; UK, Malaysia, EU | Mixes real and synthetic sources without saying which; no licence shown. **V** | **Rejected** | Unclear | No |
| 5 | **Store Sales - Time Series Forecasting**, https://www.kaggle.com/competitions/store-sales-time-series-forecasting | Corporacion Favorita, Ecuador | Daily, about 2013 to Aug 2017, about 54 stores x 33 families (**U**). date, store_nbr, family, sales, onpromotion; holidays, stores, oil (**D**) | **Yes** (family level) | Kaggle account + join | **Yes (recommended)** |
| 6 | Store Item Demand Forecasting Challenge, https://www.kaggle.com/competitions/demand-forecasting-kernels-only | Unnamed retailer | Daily, 5 years, 10 stores x 50 items (**U**). date, store, item, sales | Yes, but no prices or promotions; very clean | Kaggle account + join | Yes (fallback) |
| 7 | M5 Forecasting - Accuracy, https://www.kaggle.com/competitions/m5-forecasting-accuracy | Walmart, 10 US stores | Daily, item level, with prices and events (**U**) | Yes | Kaggle; large files | Not in one day |
| 8 | FreshRetailNet-50K, https://huggingface.co/datasets/Dingdong-Inc/FreshRetailNet-50K | Dingdong, 898 stores, 865 fresh SKUs | 90 days, hourly; stockout labels; normalised sales. **V** (card on a mirror) | Partly | CC BY 4.0 | Future step |

## Appendix B: Files

The starter code (`pipeline.py`, `inventory.py`, `app.py`, `make_mock_data.py`) and the output contract are described in README.md.

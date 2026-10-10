# LARIS: overview

***Biar laris, jangan habis.*** (Sell well, never run out.)

## Problem statement

Small Malaysian grocers decide every week what to restock with limited cash or supplier credit, before they know next week's demand. They discover mistakes too late: an empty shelf before the lorry arrives, or cash stuck in slow and expiring stock.

Small businesses' access to finance is tight:
- only **33.3%** of micro enterprises have access to banking facilities, vs 74.6% of large firms;
- **57.8%** of surveyed firms mainly sought financing for working capital and cash flow.

(ACCCIM M-BECS 1H 2026, 791 businesses, surveyed June 2026. SMEs in general, not grocers specifically. Confirm the 33.3% against ACCCIM's own release; the news report has a typo.)

`[Add 1 quote from a real shop owner here once interviewed]`

## Persona *(illustrative; validate with real owners)*

**Encik Hafiz, 42, owner of Hafiz Mini Market in Seksyen 7, Shah Alam.** He runs a family-owned minimart selling daily essentials such as eggs, bread, drinks and groceries to nearby residents and students. He uses a basic POS system and orders from regular suppliers, partly on credit.
- **Shop:** about 300 product lines, restocked weekly (fresh items more often).
- **Money:** limited cash and supplier credit for replenishment.
- **Challenges:** uncertain demand leads to stockouts or cash tied up in slow-moving stock. He doesn't keep an exact stock count.
- **Wants:** keep essentials available, reduce waste, and plan weekly orders in under 10 minutes.

**His weekly routine with LARIS (about 10 minutes):**
1. Upload the week's POS sales export.
2. Count only the 20 items LARIS lists, noting when each fresh batch arrived (5 minutes).
3. Enter the budget (cash or supplier credit limit).
4. Read the ranked alerts.
5. Approve the order list and send it to suppliers.

## Target audience

- **Primary:** independent minimarts, kedai runcit and small grocers that already record sales on a POS system.
- **Channels:** POS vendors (built-in feature), FMCG distributors, direct shop subscription.
- **Not for now:** big chains (they already have planning systems) and shops with no digital sales records.

## Solution: L·A·R·I·S

| | Malay title | English | What it does |
|---|---|---|---|
| **L** | **Lihat ke depan** | Look ahead | Forecasts each product's sales for the next 7 days, with a confidence range. |
| **A** | **Amaran stok habis** | Out-of-stock alert | Flags products that will run out before the next delivery can arrive, and suggests a quick top-up from a wholesaler if needed. |
| **R** | **Rendahkan pembaziran** | Reduce waste | Spots dead stock that won't sell before it expires, and suggests skipping the reorder or discounting it. |
| **I** | **Ikut bajet** | Stay within budget | Builds the best order list for the cash or supplier credit available, protecting must-have items (e.g. eggs, bread) first. |
| **S** | **Semak hasil** | Check the results | Shows forecast accuracy against simple rules, and how LARIS compares with the usual ordering method at the same budget. |

**How it works (three layers):**
1. **AI model:** a machine-learning forecast of each product's sales for the next 7 days, with a range from its measured errors. It is tested against three simple rules on weeks and stores it never saw.
2. **Risk assessment:** it spots what will run out before the delivery or expire unsold, names the type of problem, ranks it by the ringgit at stake and explains why, in plain language.
3. **Budget optimiser:** it spends each ringgit where it protects the most margin, must-haves first, with each product's own delivery cycle and shelf life taken into account.

## Impact *(fill in from `outputs/metrics.json` after the real-data run; never from mock data)*

- **Measured (held-out weeks of real data):** 7-day forecast error [x%] vs [y%] for the best simple rule, 95% CI of the difference [a to b]; on stores the model never saw: [x%] vs [y%].
- **Measured on real sales with simulated stock:** at the same stockout catch rate as a min-stock rule, false alarms on [p%] vs [q%] of no-stockout cases.
- **Simulated (same cash, same suppliers, real sales replayed across [n] stores):** lost margin + waste [RM a] vs [RM b] for "order last week's sales"; must-have units short [n] vs [m]; LARIS better in [k] of [n] stores; holds under the sensitivity checks: [yes / no, except ...].
- **Not yet shown:** real savings in a Malaysian shop, owner comprehension, time saved. These need the pilot.
- **Wider:** fewer empty shelves for neighbourhood customers, less cash locked in stock, fewer expired perishables.

> **Illustration only. A made-up shop, not a result; do not use on the proof slide.** With RM 600 against a RM 1,055 ideal order, an early hand-worked example had LARIS halving expected waste (RM 99 vs RM 198), cutting lost margin from RM 55 to RM 33 and must-have shortfalls from 18.8 to 7.5 units.

## Validation gates (fixed before seeing results)

| Gate | Pass when | If it fails, we say |
|---|---|---|
| G1 Forecast | The model beats the best simple rule on 7-day error, 95% CI of the difference above zero | "A simple rule is as good here", and we show where the model does win |
| G2 Honest range | 85-95% of real sales fall inside the 90% range | Widen the range using validation errors, and report it |
| G3 Decision value | Replay: LARIS beats the usual rules on lost margin + waste at 50% and 75% cash, in most sampled stores; the ML forecast beats the simple ones inside the same optimiser | Report the win rate honestly; lead with where it wins |
| G4 Robustness | G3 holds under the sensitivity checks (margins, goodwill, shelf lives, late deliveries) | Name the conditions where it breaks |
| G5 Real owners | At least 2 of 3 shop owners confirm the pain, would do the 5-minute count, and name a price | Reframe the user or the budget story |
| G6 Demo | Every page renders offline on real outputs; backup video recorded | Fix before polishing |

## Finance

- **Revenue:**
  - free for up to [N] products, then RM [__]/month per shop;
  - licensing to POS vendors;
  - distributors pay per shop they sign up.
- **Costs:** low, because LARIS runs on the shop's own sales export with light weekly retraining. The main costs are POS integrations and onboarding.
- **What a shop gains:** monthly value = (stockouts avoided x margin) + (stock reduced x cost x holding rate) - subscription. Prove it with a 3-shop, 4-week pilot before quoting numbers.

Prices and returns stay as [placeholders] until the pilot or the real-data run.

## Source

- ACCCIM M-BECS 1H 2026: https://www.malaymail.com/news/malaysia/2026/07/23/acccim-survey-finds-malaysian-businesses-still-struggling-with-financing-access-alternative-channels-underutilised/228669

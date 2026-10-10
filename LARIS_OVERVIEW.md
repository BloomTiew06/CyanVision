# LARIS: overview

***Biar laris, jangan habis.*** (Sell well, never run out.)

## Problem statement

Small Malaysian grocers decide every week what to restock with limited cash, before they know next week's demand. They discover mistakes too late: an empty shelf before the lorry arrives, or cash stuck in slow and expiring stock.

Cash is the real constraint:
- only **33.3%** of micro enterprises have access to banking facilities;
- **57.8%** of firms seeking financing need it for working capital.

(ACCCIM M-BECS, 1H 2026. These are SMEs in general, not grocers specifically.)

## Persona *(illustrative; validate with real owners)*

**Encik Hafiz, 42**, runs a family minimart in Shah Alam.
- **Shop:** about 300 products, orders every Wednesday, supplier takes 3 days.
- **Cash:** about RM [600-900] to spend before payday.
- **Wants:** never empty on staples, never tied-up cash, under 10 minutes a week on ordering.

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
| **I** | **Ikut bajet** | Stay within budget | Builds the best order list for the cash available, protecting must-have items (e.g. eggs, bread) first. |
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

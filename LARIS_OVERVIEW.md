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

**How it works:** a machine-learning forecast (tested against two simple rules on data it never saw) feeds a budget optimiser. The optimiser spends each ringgit where it protects the most margin, with each product's own delivery cycle and shelf life taken into account.

## Impact *(fill in after the real-data run)*

- **Measured:** forecast error [x%] vs "same day last week" [y%].
- **Simulated:** at the same budget:
  - lost margin [RM a] vs [RM b] for the usual "split by last month's sales" rule;
  - waste [RM c] vs [RM d];
  - must-have items short [n] vs [m].
- **Wider:** fewer empty shelves for neighbourhood customers, less cash locked in stock, fewer expired perishables.
- **Illustration (made-up shop, not a result):** with RM 600 against a RM 1,055 ideal order:
  - LARIS halved expected waste (RM 99 vs RM 198);
  - it cut lost margin from RM 55 to RM 33;
  - it cut must-have shortfalls from 18.8 to 7.5 units.

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

# LARIS: pitch deck plan

**Assumption:** a 5-minute pitch plus Q&A. A 3-minute cut is at the end. Bracketed items `[like this]` must be filled with real numbers or quotes. Never invent them.

**Story arc:** one shopkeeper's Wednesday → two costly mistakes → cash is the real constraint → LARIS decides where the money goes → live demo → proof → why it's different → how it reaches shops → honesty → close.

## Slides

| # | Slide | On the slide | What to say | Time |
|---|---|---|---|---|
| 1 | **LARIS: Biar laris, jangan habis.** | Name, tagline, "Budget-aware restocking for small Malaysian shops", team, Track 1 | "Every shopkeeper wishes 'semoga laris'. We help them sell well without running out or running out of cash." | 0:10 |
| 2 | **It's Wednesday. Encik Hafiz has RM [1,500] and 300 products.** | Persona card *(illustrative composite)*: minimart in Shah Alam, supplier takes 3 days, orders every Wednesday | "He has to decide today what to buy for next week, with limited cash and no idea what next week brings." | 0:20 |
| 3 | **Two costly mistakes, both found too late** | Two columns. Too little: the shelf empties before the lorry arrives, the sale is lost and the customer goes elsewhere. Too much: cash stuck in slow stock, perishables expire | "He only finds out at the empty shelf, or at month end when the cash is gone." | 0:30 |
| 4 | **Cash is the real constraint** | Three big numbers: **33.3%** of micro enterprises have banking access (vs 74.6% of large firms); **57.8%** of firms seeking financing need it for working capital (ACCCIM, 1H 2026, 791 firms); **42%** of SMEs name cash flow a top concern (Airwallex, 2026, 415 SMEs). Footnote: SMEs in general. Add `[shop-owner quote]` if you get one | "Small shops can't just order everything. Every ringgit has to go to the right shelf." | 0:30 |
| 5 | **Today's tools don't decide where the money goes** | Eyeballing shelves; fixed low-stock alerts; "order what sold last week"; cutting at random when cash is short | "None of these looks at next week's demand, the supplier's lead time and the cash together." | 0:20 |
| 6 | **LARIS** | Five letters, one line each: **L**ook ahead: 7-day forecast · **A**lert: what runs out before delivery · **R**educe dead stock: what won't sell before it expires · **I**nvest the budget: the best order list for this week's cash · **S**how proof | "Five steps, one decision: what to order this Wednesday with the money you have." | 0:30 |
| 7 | **How LARIS decides** | Flow diagram: sales history → forecast with uncertainty → stockout and dead-stock risk → budget allocation → order list. Under the budget step: "each ringgit goes where it protects the most margin" | "The forecast beats two simple rules on data it never saw. Then every ringgit goes, one by one, to the order that protects the most margin." | 0:30 |
| 8 | **Live demo** | Switch to the app (backup: recorded video) | Script: (1) A: "3 products run out before delivery." (2) I: a judge drags the budget from RM 2,000 to RM 1,000; LARIS protects the fast staples and cuts slow perishables. (3) R: the dead-stock card. (4) L: one product's forecast and band. (5) S: "reveal what actually happened." | 1:30 |
| 9 | **Proof** | Two panels, clearly labelled. **Measured** (held-out data): 7-day forecast error `[x%]` vs `[y%]` same-day-last-week and `[z%]` 28-day average; `[n%]` of real sales inside the 90% band. **Simulated** (same budget): lost margin `[RM a]` vs `[RM b]` for "split by last month's sales"; waste `[RM c]` vs `[RM d]`; holds when margins move ±30% `[yes/no]` | "Measured where we can, simulated where we must, and we label which is which." | 0:30 |
| 10 | **Why LARIS is different** | 3-column table. Fixed low-stock alerts *(check 2-3 local POS products first)*: react after the fact. Forecast-only tools: say what sells, not what to buy with the cash you have. **LARIS:** forecast + lead time + budget in one decision | "Others predict. LARIS decides where the money goes." | 0:20 |
| 11 | **How it reaches shops** | Three channels: POS vendors embed it, distributors offer it to the shops they supply, shop subscription. Next step: 3-shop pilot for 4 weeks, comparing stockout days and stock held vs their previous 4 weeks | "Shops already have the data, in their POS. LARIS runs on their own sales export." | 0:20 |
| 12 | **Honest about the limits** | Trained and tested on public grocery data (Corporacion Favorita, Ecuador). No public Malaysian product-level data exists; we checked. Costs, margins and shelf life are the shop's inputs. Advice, not automatic ordering. Uncertainty is always shown | "We'd rather show you the limits than oversell. A real shop plugs in its own data." | 0:20 |
| 13 | **Biar laris, jangan habis.** | Tagline, one line ask (pilot shops, POS partner), team contacts | "Help us find our first three shops." | 0:10 |

**Total: about 5:20.** Rehearse to land under 5:00.

## 3-minute cut

Keep slides 1, 3 (absorb 2 into it), 4, 6, 8 (shortened to 60 s), 9 and 13. Fold 10's one-liner into 13 and 12's into 9.

## Backup slides (for Q&A only)

- **B1. Model details:** features, lag-7 rule, train/validation/test dates, baselines.
- **B2. The allocation method:** value of each unit = margin x P(sells) - overstock cost x P(doesn't); greedy by value per ringgit; reduces to the newsvendor with no budget limit.
- **B3. Simulation assumptions:** sales used as demand (censored), fixed lead time, weekly orders, costs and margins as inputs.
- **B4. Data audit:** what Malaysian data exists and why it can't train the model.
- **B5. Next vertical:** restaurants and bazaar stalls (cook quantities), once kitchen data exists.

## Q&A answers to rehearse

- **Why not just a moving average?** Point to slide 9's measured numbers. If the model loses on some products, say so.
- **This isn't Malaysian data.** Correct, and none exists publicly. The method is proven on real retail data, and a shop retrains on its own POS export.
- **Where do costs and margins come from?** The shop enters them. Every policy is compared under the same assumptions, and the ±30% check shows the conclusion holds.
- **What if the forecast is wrong?** The band and safety stock are sized from measured error. A false alarm costs a few days of extra stock, shown in the simulation.
- **Don't shopkeepers already know what sells?** They know the pattern. They can't compute which 20 of 300 items deserve the last RM 500 this week.
- **Who pays?** POS vendors as a feature, distributors, shop subscription.

## Before you present

- [ ] Real numbers on slide 9, from the pipeline on Kaggle data
- [ ] Budget allocator (I) and dead-stock check (R) built, or the demo can't show them
- [ ] One real shop-owner quote for slide 4, or leave it out
- [ ] Check 2-3 local POS products' low-stock features before using slide 10's claim
- [ ] Team names and contacts on slides 1 and 13
- [ ] Backup screen recording of the demo

## Sources

- ACCCIM M-BECS 1H 2026: https://www.malaymail.com/news/malaysia/2026/07/23/acccim-survey-finds-malaysian-businesses-still-struggling-with-financing-access-alternative-channels-underutilised/228669
- Airwallex SME Outlook 2026: https://www.thestar.com.my/business/business-news/2026/10/01/rising-costs-top-concern-for-malaysian-smes-as-growth-remains-priority

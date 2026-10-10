# LARIS: pitch plan (3 minutes + 2 minutes Q&A)

**Core judging question:** *Does your model help someone make a better decision, and can you prove it?*
The pitch answers it with one realistic scenario and the full chain:
**Prediction → Categorisation → Prioritisation → Explanation → Recommended action → Measurable evaluation.**

Bracketed items `[like this]` must be filled from `outputs/metrics.json` after the real-data run, or left
out. Never use mock numbers, and never invent numbers or quotes.

## The scenario

"Tight-budget Wednesday". In the app: Settings → **Load the pitch scenario**. The store and week are chosen
by a stated rule, not by hand: the median-volume store, and the Wednesday with the largest predicted rise
in must-have demand. Stock comes from the "Tight budget" preset; cash is 60% of the ideal order. Set Shop
size in Settings if you want small-shop RM figures, and say that it is scaled.

## Script

| Time | Slide / screen | What to say |
|---|---|---|
| 0:00–0:20 | **Problem and user.** Persona card *(illustrative)*: a minimart owner orders every Wednesday with limited cash | "Every week he guesses what to restock before he knows next week's demand. He finds out too late: an empty shelf before the lorry comes, or cash stuck in stock that expires." Cash is the constraint: ACCCIM 1H 2026 (SMEs in general, not grocers specifically). |
| 0:20–0:35 | **LARIS in one line**, the three layers | "An AI forecast spots the problems early, LARIS ranks them by what they'd cost, and a budget optimiser turns them into an order list that fits the cash." |
| 0:35–2:05 | **Live demo** (below) | |
| 2:05–2:45 | **Proof**: three labelled panels | MEASURED: 7-day forecast error `[x%]` vs `[y%]` for the best simple rule (CI `[a to b]`), also on stores the model never saw. MEASURED on real sales with simulated stock: false alarms `[p%]` vs `[q%]` for a min-stock rule at the same catch rate. SIMULATED: same cash and suppliers, lost margin + waste `[RM a]` vs `[RM b]` for "order last week's sales", must-have units short `[n]` vs `[m]`, better in `[k]` of `[n]` stores; holds under the sensitivity checks `[yes / except ...]`. |
| 2:45–3:00 | **Limits and ask** | "Trained on real grocery data from Ecuador, not Malaysia; costs are the shop's own inputs; the next step is a 4-week pilot in 3 shops. Help us find them." |

### Live demo (90 seconds)

1. **Predict (Dashboard, then Sales forecast).** "[n] problems spotted before they happen, RM [x] at stake." Open the must-have product with the biggest rise: forecast, range, and "the model estimates payday adds about [n] units".
2. **Categorize (Risk alerts).** Point at the chips: "Runs out before delivery", "Expiry risk", "Demand surge". "Not just abnormal: it says which problem."
3. **Prioritize.** "Ranked by urgency, then by the ringgit at stake, with an act-by day."
4. **Explain.** Open the top card: prediction, evidence, chance of running out, RM at risk, confidence, and the tags that say which lines come from the AI.
5. **Act (Budget & orders, 60% cash).** Must-haves protected first; dead stock skipped; "with RM X more you'd add ...". Point at the ESTIMATE line vs ordering last week's sales.
6. **Evaluate (Sales forecast, Reveal).** Toggle "Reveal what actually happened": real sales against the forecast for that week.

## Q&A (2 minutes): prepared answers

1. **"It's not Malaysian data."** Correct; no public Malaysian product-level data exists. We show the method on real grocery data, including stores the model never saw. A shop retrains on its own POS export.
2. **"How do you know about stockouts without stock data?"** We test alerts on real future sales against a grid of stock levels, and say so. The pilot measures real stockouts.
3. **"Why not just a moving average?"** Results → Forecast accuracy: error vs three simple rules with confidence intervals. Where a rule wins, the app says so.
4. **"Too many false alarms?"** Results → Alert quality: false-alarm rate at the same catch rate as a min-stock rule; the threshold was set on earlier weeks; low-confidence items never become "Act today".
5. **"Your costs are made up."** They're the shop's inputs. Results → Decision quality shows whether the conclusion survives ±30% margins, shelf lives and late deliveries, and where it doesn't.
6. **"A simulation isn't reality."** Agreed. It's labelled SIMULATED with its assumptions; the pilot is the real test.
7. **"What does the AI actually do vs rules?"** The forecast and the what-if driver effects are the model; probabilities are calculated from its measured errors; categories, thresholds and costs are rules or settings. Every explanation line is tagged.
8. **"What if the data is missing or odd?"** Suspicious zero runs are excluded; thin or unreliable data shows "Not enough reliable data: check manually".
9. **"Is this overkill for a kedai runcit?"** One list of problems, one order list, reasons in BM/EN, runs on a laptop.
10. **"Why trust the probabilities?"** The reliability chart and range coverage, measured on held-out weeks.

## Before you present

- [ ] Real-data run done (`README.md` step 3); every bracket above filled from `outputs/metrics.json`, or the line cut
- [ ] If the model loses to a simple rule anywhere, say so on the proof slide
- [ ] Persona labelled illustrative; one real shop-owner quote only if you actually get one
- [ ] Shop size: either 1.0 (data scale) or a stated scaling, captioned
- [ ] Backup screen recording of the demo
- [ ] Team names and contacts on the first and last slides

## Sources

- ACCCIM M-BECS 1H 2026: https://www.malaymail.com/news/malaysia/2026/07/23/acccim-survey-finds-malaysian-businesses-still-struggling-with-financing-access-alternative-channels-underutilised/228669
- Airwallex SME Outlook 2026: https://www.thestar.com.my/business/business-news/2026/10/01/rising-costs-top-concern-for-malaysian-smes-as-growth-remains-priority

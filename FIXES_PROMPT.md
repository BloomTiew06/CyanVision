<!--
Fix pack v3: for the team's coding session in C:\Users\User\Downloads\Dormathon\ShelfSignal
-->

You're in **plan mode**. Plan first, and implement only after I approve. These are the remaining plot holes in LARIS (milestones M1–M8 are done; see `git log`, `README.md` and `LARIS_BUILD.md`). Keep every existing rule: no invented numbers, the leakage rule, nothing selected on the test set, and MOCK, SIMULATED and PLACEHOLDER labels. Extend; don't rewrite.

## Fixes, in priority order

**1. Small-shop uncertainty is too narrow (correctness).**
- **The problem:** `laris_core.sigma_for` scales sigma linearly with the Shop size setting. At small volumes, sampling noise dominates, so the ranges, P(stockout) and safety stock come out overconfident.
- **The fix:** when scale < 1, use a Poisson noise floor:
  - daily spread: sigma_scaled = sqrt((scale·sigma)^2 + scale·mean_daily_forecast)
  - L-day spread: var_L = scale^2·var_model_L + scale·mu_L
  - apply the same to the L-day quantile path from `uncertainty.csv`
- **Must hold:** at scale = 1 nothing changes.
- **Tests:**
  - scale = 1 is unchanged;
  - at scale = 0.02, the relative width (sigma / forecast) is larger than with linear scaling;
  - P(stockout) at a fixed stock level rises accordingly.
- **Docs:** update the README limitation line.

**2. "Kira 20": the owner doesn't keep an exact stock count (usability, realism).**
- Add `laris_core.count_list(rows, n=20)`: rank by tier, then RM at risk, then sales value.
- On the Dashboard, show a "Kira 20: count these first" panel, with inputs for counted stock and, for perishables, "days since this batch arrived".
- Items that aren't counted keep their current preset values, labelled "not counted (estimate)".
- **Test:** the list is deterministic, and its order follows tier, then RM.

**3. Stock age is unknown (expiry underestimated).**
- `inventory.dead_stock(..., age_days=0)` uses remaining shelf life = max(shelf − age, 0).
- Use the same remaining life for the protection-window cap and the overstock cost.
- Feed `age_days` from the Kira 20 inputs.
- **Test:** older stock means more expected expiry; age 0 equals the current behaviour.

**4. The budget may be supplier credit, not cash (framing).**
- Relabel the budget input "Budget (cash or supplier credit), RM" in the app and docs.
- No logic change.

**5. Malaysian deployment path (stretch, small).**
- Add an optional `--holidays-csv` (date, name) and `--payday-days` (e.g. `15,last`) to `pipeline.py`. The demo keeps Favorita's Ecuador holidays.
- Ship `holidays_my_2024_2026.csv` with: CNY, Hari Raya Aidilfitri, Hari Raya Haji, Deepavali and Christmas.
  - 2024–2026 dates are in `../pasar_feasibility.py` (`FESTIVALS`): copy them, and keep its note that Islamic dates depend on moon sighting.
- Docs: "for a Malaysian shop, LARIS uses the Malaysian festive calendar."
- **Test:** the flags load and the default behaviour is unchanged.

**6. Real-data run (if possible).**
- If `data/store-sales/train.csv` exists, run the pipeline, timed. If it's slow, use `--max-iter 150 --sim-stores 5 --holdout-stores 5`, and say so.
- If the file doesn't exist, stop and tell me; don't download anything.
- Report gate results exactly as printed:
  - **G1:** the model beats the best simple rule on 7-day WAPE, with the 95% CI above 0.
  - **G2:** 85–95% coverage of the 90% range.
  - **G3:** the LARIS win rate vs the usual rules at 50% and 75% cash, and ML vs simpler forecasts inside the optimiser.
  - **G4:** sensitivity checks.
- If a gate fails, say so plainly. Don't tune on the test set.

## For each fix
Run pytest, the mock pipeline, and a headless check of every page. Commit with a clear message, then give a 3-line checkpoint: done / verified / next. Stop and ask if a check fails twice.

## Final summary
What changed, test count, gate results (or "real data not run"), and any limitation that remains.

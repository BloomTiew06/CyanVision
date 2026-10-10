"""Business-data tools for the LARIS assistant.

Every function reads the shared planning context (laris_core.build_context via app.py) and returns plain,
JSON-safe data with units, periods and missing-data notes. All numbers come from LARIS's existing calculations
(planning.py, laris_core.py, inventory.py); the language model only chooses tools and explains results.
Read-only, except propose_order_change, which only *proposes*: the owner confirms it with a button in the app.
"""
import math
import re

import numpy as np
import pandas as pd

import planning


def clean(x):
    """Make tool output JSON-safe: numpy -> python, NaN -> None, dates -> ISO strings, floats rounded."""
    if isinstance(x, dict):
        return {str(k): clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [clean(v) for v in x]
    if isinstance(x, pd.Timestamp):
        return str(x.date())
    if isinstance(x, np.integer):
        return int(x)
    if isinstance(x, (float, np.floating)):
        return None if math.isnan(x) or math.isinf(x) else round(float(x), 2)
    if isinstance(x, np.bool_):
        return bool(x)
    return x


def plain(name):
    """Product name without the leading emoji, for matching and for the model."""
    return re.sub(r"^[^\w(]+", "", str(name)).strip()


def find_product(ctx, query):
    """Resolve a product from free text (name words or product code). Returns (product key or None, candidates)."""
    q = str(query or "").lower().strip()
    words = set(re.findall(r"[a-z0-9]+", q))
    plan = ctx["plan"]
    names = dict(zip(plan["product"], plan["name"]))
    scores = {}
    for p, n in names.items():
        name = plain(n).lower()
        if q and (q == p.lower() or q == name):
            return p, [n]
        tokens = {t for t in re.findall(r"[a-z0-9]+", name) if len(t) >= 3}
        hit = len(tokens & words) + (2 if q and q in name else 0)
        if hit:
            scores[p] = hit
    if not scores:
        return None, []
    best = max(scores.values())
    top = [p for p, s in scores.items() if s == best]
    return (top[0] if len(top) == 1 else None), [names[p] for p in top]


# ---------------- read tools ----------------
def get_business_summary(ctx):
    return clean({"currency": "RM", **planning.business_summary(ctx),
                  "data_note": "Sample shop: prices and stock are illustrative; sales patterns are replayed sample "
                               "data. Forecasts and RM impacts are estimates."})


def get_budget_status(ctx):
    bd = planning.budget_breakdown(ctx)
    sc = ctx["scenario"] or {}
    return clean({
        "currency": "RM", "available_budget": ctx["budget_rm"], "order_total": ctx["order_rm"],
        "laris_recommended_total": ctx["totals"]["spent_rm"], "full_recommended_order": ctx["ideal_rm"],
        "remaining_after_order": ctx["budget_rm"] - ctx["order_rm"], "budget_limits_the_order": ctx["budget_limited"],
        "strategy": "essentials first" if ctx["protect_must_have"] else "best value per ringgit",
        "products_fully_covered": len(bd["full"]),
        "products_reduced_or_left_out": [{"name": plain(r.name), "in_order": r.qty, "needed": r.ideal,
                                          "reason": r.reason} for r in bd["cut"].itertuples()],
        "extra_cash_scenario": {"extra_rm": sc.get("extra"), "would_add": [{"name": plain(n), "units": q}
                                                                            for n, q in sc.get("added", [])],
                                "estimated_loss_avoided_rm": max(0.0, sc.get("saves", 0.0))},
        "note": "Order total includes the owner's own quantity changes; LARIS's recommended total does not."})


def get_restock_recommendations(ctx, limit=10):
    plan = ctx["plan"]
    order = plan[plan["order_qty"] > 0].copy()
    order["_u"] = ~order["urgent"]
    order = order.sort_values(["_u", "cover_days"]).head(int(limit or 10))
    return clean({
        "currency": "RM", "week_start": ctx["week"]["as_of"], "order_total": float(plan["order_rm"].sum()),
        "available_budget": ctx["budget_rm"],
        "items": [{"name": plain(r.name), "product_id": r.product, "action": planning.ACTION_LABEL[r.action],
                   "order_qty": r.order_qty, "usual_qty": r.usual, "unit_cost": r.unit_cost, "line_cost": r.order_rm,
                   "runs_out_before_delivery": bool(r.urgent), "stock_lasts_days": r.cover_days,
                   "forecast_7d": r.forecast_7d, "forecast_source": planning.SOURCE_LABEL[r.forecast_source],
                   "reason": r.why, "risk": r.risk, "estimated_impact": r.impact_txt or None,
                   "changed_by_owner": bool(r.adjusted)} for r in order.itertuples()],
        "buy_less_or_skip": [{"name": plain(r.name), "action": planning.ACTION_LABEL[r.action], "order_qty": r.order_qty,
                              "usual_qty": r.usual, "reason": r.risk}
                             for r in plan[plan["action"].isin(["REDUCE", "STOP"])].itertuples()],
        "note": "Quantities come from LARIS's optimiser within the budget; impacts are estimates vs reordering last "
                "week's sales."})


def get_stockout_risks(ctx):
    al = planning.alert_table(ctx)
    plan = ctx["plan"]
    return clean({
        "ranking": "URGENT (may run out before an order placed today arrives) first, then must-haves, then margin "
                   "at risk",
        "items": [{"name": plain(r.name), "level": r.level, "must_have": r.must_have, "stock": r.stock,
                   "sells_per_day": r.daily, "stock_lasts_days": r.cover, "may_run_out_around": r.runout,
                   "next_delivery_if_ordered_today": r.delivery, "estimated_margin_at_risk_rm": r.rm_at_risk,
                   "in_this_weeks_order": r.order_qty, "suggestion": r.why} for r in al.itertuples()],
        "no_forecast": [plain(n) for n in plan.loc[plan["forecast_source"] == "unavailable", "name"]],
        "note": "Run-out dates are estimates from the forecast and its usual error."})


def get_excess_stock(ctx):
    w = planning.waste_table(ctx)
    return clean({"currency": "RM", "items": [{"name": plain(r.name), "type": r.kind, "stock": r.stock,
                                               "sold_last_7_days": r.sold7, "estimated_unsold": r.unsold,
                                               "estimated_cost_tied_up_rm": r.tied_rm, "shelf_life_days": r.shelf_life,
                                               "suggestion": r.why} for r in w.itertuples()],
                  "note": "Expiry dates aren't recorded; estimates assume the stock on hand is fresh."})


def get_inventory_status(ctx):
    inv = planning.inventory_table(ctx)
    return clean({"currency": "RM", "stock_value_at_cost_rm": float(inv["value_rm"].sum(skipna=True)),
                  "products_without_cost_price": int(inv["value_rm"].isna().sum()),
                  "items": [{"name": plain(r.name), "status": r.status, "stock": r.stock, "sells_per_day": r.daily,
                             "stock_lasts_days": r.cover_days, "reorder_point": r.reorder_point,
                             "order_up_to": r.max_level, "value_at_cost_rm": r.value_rm}
                            for r in inv.itertuples()]})


def search_products(ctx, query=""):
    t = planning.lookup_table(ctx, plain(query) if query else "")
    if t.empty and query:
        p, cands = find_product(ctx, query)
        t = planning.lookup_table(ctx)
        t = t[t["product"] == p] if p else t[t["name"].isin(cands)]
    return clean({"matches": [{"name": plain(r.name), "product_id": r.product, "stock": r.stock, "sold_last_7_days":
                               r.sold7, "forecast_next_7_days": r.forecast, "forecast_source": r.source,
                               "reorder_point": r.reorder_point, "order_this_week": r.order_qty, "plan": r.action}
                              for r in t.itertuples()]})


def get_product_details(ctx, product=""):
    p, cands = find_product(ctx, product)
    if p is None:
        return {"error": "No single product matches.", "candidates": [plain(c) for c in cands]}
    pl = ctx["plan"].set_index("product").loc[p]
    r = ctx["rows"].set_index("product").loc[p]
    return clean({
        "name": plain(pl["name"]), "product_id": p, "plan": planning.ACTION_LABEL[pl["action"]],
        "recommendation": pl["rec"], "why": pl["why"], "risk": pl["risk"], "estimated_impact": pl["impact_txt"] or None,
        "stock": r["on_hand"] + r["on_order"], "sold_last_7_days": r["demand_last7"],
        "forecast_next_7_days": planning.forecast_text(pl["forecast_7d"], pl["forecast_source"]),
        "forecast_source": planning.SOURCE_LABEL[pl["forecast_source"]],
        "daily_forecast": [round(float(v), 1) for v in planning.daily_forecast(ctx, p)]
        if pl["forecast_source"] != "unavailable" else None,
        "stock_lasts_days": pl["cover_days"], "delivery_days": r["lead_time"], "shelf_life_days": r["shelf_life"],
        "unit_cost_rm": r["unit_cost"], "selling_price_rm": r["unit_cost"] + r["margin"], "must_have": r["must_have"],
        "order_this_week": pl["order_qty"], "laris_suggested_qty": pl["qty"], "usual_qty": pl["usual"],
        "evidence": [f"{t}: {x}" for t, x in r["why"]]})


def get_sales_summary(ctx, days=7):
    days = int(days) if days in (7, 28, 90) else 7
    df, t = planning.sales_summary(ctx, days)
    cmp = planning.sales_compare(ctx, days)
    h = df[df["has_history"]]
    return clean({
        "currency": "RM", "period": [t["start"], t["end"]], "days": t["days"], "revenue_rm": t["revenue"],
        "previous_period_revenue_rm": cmp["previous_rm"], "change_pct": cmp["change_pct"],
        "best_sellers_by_revenue": [{"name": plain(r.name), "revenue_rm": r.revenue, "units": r.units}
                                    for r in h.nlargest(5, "revenue").itertuples()],
        "best_sellers_by_units": [{"name": plain(r.name), "units": r.units} for r in h.nlargest(5, "units").itertuples()],
        "products_without_history_in_period": t["no_history"],
        "note": "Recorded sales (replayed sample data scaled to this shop) priced at your selling prices."})


def get_profit_summary(ctx, days=28):
    days = int(days) if days in (7, 28, 90) else 28
    df, t = planning.sales_summary(ctx, days)
    k = df.dropna(subset=["gross_profit"])
    return clean({
        "currency": "RM", "period": [t["start"], t["end"]], "days": t["days"], "revenue_rm": t["revenue"],
        "cost_of_goods_rm": t["cogs"], "gross_profit_rm": t["gross_profit"], "gross_margin_pct": t["margin_pct"],
        "top_gross_profit": [{"name": plain(r.name), "gross_profit_rm": r.gross_profit, "margin_pct": r.margin_pct}
                             for r in k.nlargest(5, "gross_profit").itertuples()],
        "products_without_cost_price": t["no_cost"],
        "note": "Gross profit only: rent, wages and other running costs are not included, so this is not net profit."})


# ---------------- the one action: proposed, never executed here ----------------
MAX_QTY = 100000


def propose_order_change(ctx, product="", quantity=None):
    p, cands = find_product(ctx, product)
    if p is None:
        return {"status": "rejected", "error": "No single product matches.", "candidates": [plain(c) for c in cands]}
    try:
        q = float(quantity)
    except (TypeError, ValueError):
        return {"status": "rejected", "error": "Quantity must be a number."}
    if not (0 <= q <= MAX_QTY) or q != int(q):
        return {"status": "rejected", "error": f"Quantity must be a whole number from 0 to {MAX_QTY}."}
    pl = ctx["plan"].set_index("product").loc[p]
    return clean({"status": "needs_confirmation", "product_id": p, "name": plain(pl["name"]),
                  "current_order_qty": pl["order_qty"], "proposed_qty": int(q), "laris_suggested_qty": pl["qty"],
                  "unit_cost_rm": pl["unit_cost"], "proposed_line_cost_rm": int(q) * pl["unit_cost"],
                  "note": "Not changed yet. The owner must press Confirm in the app."})


TOOLS = {"get_business_summary": get_business_summary, "get_budget_status": get_budget_status,
         "get_restock_recommendations": get_restock_recommendations, "get_stockout_risks": get_stockout_risks,
         "get_excess_stock": get_excess_stock, "get_inventory_status": get_inventory_status,
         "search_products": search_products, "get_product_details": get_product_details,
         "get_sales_summary": get_sales_summary, "get_profit_summary": get_profit_summary,
         "propose_order_change": propose_order_change}


def _spec(name, desc, props=None, required=()):
    return {"type": "function", "function": {"name": name, "description": desc, "parameters": {
        "type": "object", "properties": props or {}, "required": list(required)}}}


_DAYS = {"days": {"type": "integer", "enum": [7, 28, 90], "description": "Period length in days"}}
TOOL_SPECS = [
    _spec("get_business_summary", "Overview: budget, restock needs, sales, gross profit, stock alerts, data issues."),
    _spec("get_budget_status", "Budget vs this week's order, what was cut for budget, what extra cash would add."),
    _spec("get_restock_recommendations", "This week's order list with quantities, costs and reasons.",
          {"limit": {"type": "integer", "description": "Max items (default 10)"}}),
    _spec("get_stockout_risks", "Products that may run out, ranked by urgency, with run-out estimates."),
    _spec("get_excess_stock", "Products overstocked or at risk of expiring, with cost tied up."),
    _spec("get_inventory_status", "Stock levels, status (out/low/excess/OK), reorder points, stock value."),
    _spec("search_products", "Find products by name; returns stock, forecast and plan.",
          {"query": {"type": "string"}}, ["query"]),
    _spec("get_product_details", "Everything about one product, including why LARIS recommends its quantity.",
          {"product": {"type": "string", "description": "Product name or id"}}, ["product"]),
    _spec("get_sales_summary", "Revenue for a period, comparison with the previous period, best sellers.", _DAYS),
    _spec("get_profit_summary", "Gross profit and margin for a period, top gross-profit products.", _DAYS),
    _spec("propose_order_change", "Propose changing this week's order quantity for a product. Does NOT change "
                                  "anything; the owner must confirm in the app.",
          {"product": {"type": "string"}, "quantity": {"type": "integer"}}, ["product", "quantity"]),
]
_ALLOWED = {s["function"]["name"]: set(s["function"]["parameters"]["properties"]) for s in TOOL_SPECS}


def run_tool(ctx, name, args):
    """Run an allowlisted tool with only its declared arguments; anything else is refused."""
    if name not in TOOLS:
        return {"error": f"Unknown tool '{name}'."}
    kwargs = {k: v for k, v in (args or {}).items() if k in _ALLOWED[name]}
    try:
        return TOOLS[name](ctx, **kwargs)
    except Exception as e:   # a bad tool call must not crash the conversation
        return {"error": f"The tool failed ({type(e).__name__})."}

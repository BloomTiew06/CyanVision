"""Home: a one-line greeting, the order panel and Ask LARIS side by side (one screen), then the conversation."""
import os
from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo

import numpy as np
import streamlit as st

import assistant
import assistant_tools as T
import laris_ui as ui
import planning

ss = st.session_state
ctx = ss["ctx"]
ui.require_plan(ctx)
as_of = ctx["week"]["as_of"]

# ---------------- A. greeting (owner name and form of address from Settings; local time) ----------------
now = None
for tz in (st.context.timezone, os.environ.get("LARIS_TZ"), "Asia/Kuala_Lumpur"):   # the viewer's own clock first
    try:
        now = datetime.now(ZoneInfo(tz)) if tz else None
    except Exception:
        now = None
    if now:
        break
now = now or datetime.now()
greet = "Good morning" if now.hour < 12 else "Good afternoon" if now.hour < 18 else "Good evening"
who = ss["owner"] if ss.get("title") in (None, "", "(none)") else f"{ss['title']} {ss['owner']}"
st.markdown(ui.ribbon("rb_hero", top=-40)
            + f'<div class="lr-hero"><div class="lr-hero-top"><div class="lr-eyebrow" style="margin:0">Week of '
              f'{as_of:%d %b %Y} · replay</div>{ui.mock_pill() if ctx.get("is_mock") else ""}</div>'
              f'<h1 class="lr-h1">{escape(greet)}, {escape(who)}.</h1>'
              '<p class="lr-sub">Here\'s your shop at a glance. This week\'s order is ready for you to review.</p>'
              "</div>", unsafe_allow_html=True)

# ---------------- shared numbers: every figure from planning.business_summary ----------------
s = planning.business_summary(ctx)
b, rs, sa, pr, inv, iss = s["budget"], s["restock"], s["sales"], s["profit"], s["inventory"], s["issues"]
left = b["remaining_rm"]
chg = sa["change_pct"]
gp_ok = sa["last_7_days_rm"] > 0 and np.isfinite(pr["gross_profit_7d_rm"]) and pr["products_without_cost"] < len(
    ctx["plan"])
issues = []
if iss["forecast_unavailable"]:
    issues.append(f"{len(iss['forecast_unavailable'])} without a forecast")
if iss["unusual_recent_sales"]:
    issues.append(f"{len(iss['unusual_recent_sales'])} with unusual sales")
if iss["baseline_forecast"]:
    issues.append(f"{len(iss['baseline_forecast'])} on a simple forecast")

# ---------------- assistant state ----------------
try:
    secrets = dict(st.secrets)
except Exception:
    secrets = {}
cfg = assistant.config(secrets)
chat = ss.setdefault("chat", [])
memory = ss.setdefault("chat_mem", {})
SOURCE = {"ai": "AI answer · numbers from LARIS's calculations",
          "fallback": "Quick answer from LARIS's own calculations (AI assistant not set up; see Settings › Assistant)",
          "error": "AI unavailable · quick answer from LARIS's own calculations", "app": "LARIS"}
urgent = ctx["plan"][ctx["plan"]["urgent"]].sort_values(["must_have", "cover_days"], ascending=[False, True])
SUGGESTIONS = [f"Why is {urgent['name'].iloc[0]} urgent this week?" if len(urgent) else "What should I restock this week?",
               "Where can I save RM 50 on this order?", "Which products may expire before they sell?"]

# verify an action the owner confirmed on the previous run, against the rebuilt plan
v = ss.pop("chat_verify", None)
if v:
    pid, qty, name = v
    plan = ctx["plan"].set_index("product")
    if pid in plan.index and plan.at[pid, "order_qty"] == qty:
        chat.append({"role": "assistant", "source": "app", "content":
                     f"Done: this week's order for **{name}** is now **{qty:,} units** "
                     f"({ui.money(plan.at[pid, 'order_rm'])}). You can change it back in LARIS › R · Recommend."})
    else:
        chat.append({"role": "assistant", "source": "app",
                     "content": f"Sorry, the change for {name} didn't apply. Nothing in your order was changed."})


def _confirm(i):
    m = chat[i]
    p = m["proposal"]
    m["pending"] = False
    plan = ss["ctx"]["plan"]
    qty = p.get("proposed_qty")
    if p.get("product_id") not in set(plan["product"]) or not isinstance(qty, int) or not 0 <= qty <= T.MAX_QTY:
        chat.append({"role": "assistant", "source": "app", "content": "That change isn't valid any more, so nothing "
                                                                      "was changed."})
        return
    ui.set_qty_value(p["product_id"], qty)
    ss["chat_verify"] = (p["product_id"], qty, p["name"])


def _cancel(i):
    chat[i]["pending"] = False
    chat.append({"role": "assistant", "source": "app", "content": "Cancelled. Nothing was changed."})


panel_col, ask_col = st.columns([1.75, 1], gap="medium")

# ---------------- B. order panel ----------------
with panel_col, st.container(key="glass_panel"):
    st.markdown(ui.panel_head(
        "This week's order",
        f"{b['products_in_order']} products in the order · {len(rs['running_out'])} may run out before the next delivery",
        ui.money(b["order_rm"]), f"of your {ui.money(b['available_rm'])} budget"), unsafe_allow_html=True)
    ui.budget_slider(ctx, "home_budget", label_visibility="collapsed")
    st.markdown(f'<div class="lr-left">Drag to set your budget · '
                + (f"{ui.money(left)} left" if left >= -0.5 else f"Over budget by {ui.money(-left)}")
                + (f" · the full recommended order is {ui.money(b['full_order_rm'])}" if b["budget_limited"] else "")
                + "</div>" + ui.tiles([
                    ("Restock", f"{len(rs['buy_more'])} to buy", f"{len(rs['running_out'])} may run out",
                     "risk" if rs["running_out"] else None),
                    ("Sales 7 days", ui.money(sa["last_7_days_rm"]),
                     f"{chg:+.1f}% vs week before" if chg is not None and np.isfinite(chg) else "no earlier week", None),
                    ("Gross profit 7d", ui.money(pr["gross_profit_7d_rm"]) if gp_ok else "–",
                     f"{pr['margin_pct_7d']:.1f}% margin" if gp_ok else "needs cost prices", "lime" if gp_ok else None),
                    ("Inventory", f"{len(inv['low_stock']) + len(inv['out_of_stock'])} low",
                     f"{len(inv['excess'])} excess · {ui.money(inv['stock_value_rm'])} stock", None),
                    ("Needs a look", str(len(iss["forecast_unavailable"]) + len(iss["unusual_recent_sales"])),
                     ", ".join(issues) or "no data issues", None)])
                + '<div class="lr-attn">Needs your attention</div>', unsafe_allow_html=True)
    found = planning.insights(ctx)[:3]
    if not found:
        st.markdown('<span class="lr-muted">Nothing needs your attention this week.</span>', unsafe_allow_html=True)
    for i, (level, text, letter) in enumerate(found):
        # one flex row per card: [badge | text] grows, the Review button keeps a fixed width at the right
        with st.container(key=f"attn_{i}", horizontal=True, vertical_alignment="center", gap="small"):
            st.markdown(f'<div class="lr-attn-row">{ui.status_chip(level)}<span>{escape(text)}</span></div>',
                        unsafe_allow_html=True, width="stretch")
            ui.tool_button(letter, "Review", key=f"ins_{i}", width=96)

# ---------------- C. Ask LARIS: the whole conversation stays in this panel ----------------
with ask_col, st.container(key="glass_ask"):
    a, c = st.columns([3, 1.2], vertical_alignment="center")
    a.markdown('<div class="lr-eyebrow" style="margin:0">Ask LARIS</div>', unsafe_allow_html=True)
    if chat:
        c.button("Clear", key="chat_clear", icon=":material/delete_sweep:",
                 on_click=lambda: ss.update(chat=[], chat_mem={}), use_container_width=True)
    log = st.container(height=300, key="chatlog", border=False, autoscroll=True)   # filled below
    typed = st.chat_input("What would you like to know about your shop today?", key="chat_in")
    with st.container(key="chips", horizontal=True, gap="small"):
        for i, q in enumerate(SUGGESTIONS):
            st.button(q, key=f"chip_{i}", icon=":material/auto_awesome:", on_click=ss.update, kwargs={"chat_q": q})

question = typed or ss.pop("chat_q", None)
with log:
    if not chat and not question:
        with st.chat_message("assistant", avatar=":material/storefront:"):
            st.markdown("Ask me about your stock, sales, profit or this week's order.")
    for i, m in enumerate(chat):
        with st.chat_message(m["role"], avatar=":material/storefront:" if m["role"] == "assistant"
                             else ":material/person:"):
            st.markdown(m["content"])
            if m["role"] == "assistant":
                st.caption(SOURCE.get(m.get("source"), ""))
                if m.get("proposal") and m.get("pending"):
                    x, y = st.columns(2)
                    x.button("Confirm", key=f"chat_ok_{i}", type="primary", on_click=_confirm, args=(i,),
                             use_container_width=True)
                    y.button("Cancel", key=f"chat_no_{i}", on_click=_cancel, args=(i,), use_container_width=True)
    if question:   # show the question at once, with a small "thinking" line, inside the box
        with st.chat_message("user", avatar=":material/person:"):
            st.markdown(question)
        with st.spinner("Thinking…"):
            r = assistant.ask(question, chat, ctx, cfg, memory)
        chat.append({"role": "user", "content": question})
        chat.append({"role": "assistant", "content": r["text"], "source": r["source"], "tools": r["tools"],
                     "proposal": r["proposal"], "pending": bool(r["proposal"])})
        st.rerun()

st.markdown('<p class="lr-disclaimer">'
            + ("AI assistant on. " if cfg["enabled"] else "Quick answers (AI assistant not set up). ")
            + "Answers use your shop's numbers. LARIS never sends orders or changes stock by itself.</p>",
            unsafe_allow_html=True)

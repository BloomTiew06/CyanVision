"""Home: a greeting, one insights panel built from the shared business summary, and the LARIS assistant."""
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
try:
    now = datetime.now(ZoneInfo(os.environ.get("LARIS_TZ", "Asia/Kuala_Lumpur")))
except Exception:
    now = datetime.now()
greet = "Good morning" if now.hour < 12 else "Good afternoon" if now.hour < 18 else "Good evening"
who = ss["owner"] if ss.get("title") in (None, "", "(none)") else f"{ss['title']} {ss['owner']}"
st.markdown(ui.page_header(f"Week of {as_of:%d %b %Y}", f"{greet}, {who}.",
                           "Welcome to LARIS. Here's your shop at a glance."), unsafe_allow_html=True)

# ---------------- B. insights panel: every figure from planning.business_summary ----------------
s = planning.business_summary(ctx)
b, rs, sa, pr, inv, iss = s["budget"], s["restock"], s["sales"], s["profit"], s["inventory"], s["issues"]
scale = max(b["available_rm"], b["order_rm"], 1)
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
st.markdown(ui.hero(
    eyebrow="THIS WEEK'S ORDER",
    lead=f"{b['products_in_order']} products in the order · {len(rs['running_out'])} may run out before the next delivery",
    big=ui.money(b["order_rm"]), big_note=f"of your {ui.money(b['available_rm'])} budget",
    fill=b["order_rm"] / scale, marker=b["available_rm"] / scale,
    legend=(f"{ui.money(left)} left" if left >= -0.5 else f"Over budget by {ui.money(-left)}")
           + (f" · the full recommended order is {ui.money(b['full_order_rm'])}" if b["budget_limited"] else ""),
    stats=[("Restock", f"{len(rs['buy_more'])} to buy more", f"{len(rs['running_out'])} may run out",
            "risk" if rs["running_out"] else None),
           ("Sales, last 7 days", ui.money(sa["last_7_days_rm"]),
            f"{chg:+.1f}% vs week before" if chg is not None and np.isfinite(chg) else "no earlier week", None),
           ("Gross profit, 7 days", ui.money(pr["gross_profit_7d_rm"]) if gp_ok else "–",
            f"{pr['margin_pct_7d']:.1f}% margin" if gp_ok else "needs cost prices", "lime" if gp_ok else None),
           ("Inventory", f"{len(inv['low_stock']) + len(inv['out_of_stock'])} low · {len(inv['excess'])} excess",
            f"stock worth {ui.money(inv['stock_value_rm'])} at cost", None),
           ("Needs a look", str(len(iss["forecast_unavailable"]) + len(iss["unusual_recent_sales"])),
            ", ".join(issues) or "no data problems", None)]), unsafe_allow_html=True)

for i, (level, text, letter) in enumerate(planning.insights(ctx)[:3]):
    a, c = st.columns([6, 1.1], vertical_alignment="center")
    a.markdown(f'<div class="lr-insight {level.lower()}">{ui.status_chip(level)}{escape(text)}</div>',
               unsafe_allow_html=True)
    with c:
        ui.tool_button(letter, "Review", key=f"ins_{i}")

# ---------------- C. the assistant ----------------
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
SUGGESTIONS = ["What should I restock this week?", "How much should I spend on replenishment?",
               "Which products are selling best?", "How much profit did I make this month?",
               "Which products are at risk of running out?", "Which of those is the most urgent?"]

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


def _from_pill():
    if ss.get("chat_pill"):
        ss["chat_q"] = ss["chat_pill"]
    ss["chat_pill"] = None


with st.container(border=True, key="chatcard"):
    a, c = st.columns([5, 1.2], vertical_alignment="center")
    a.markdown('<div class="lr-eyebrow">Ask LARIS</div><span class="lr-muted">'
               + ("AI assistant on. " if cfg["enabled"] else "Quick answers (AI assistant not set up). ")
               + "Answers use your shop's numbers; LARIS never sends orders or changes stock by itself.</span>",
               unsafe_allow_html=True)
    if chat:
        c.button("Clear chat", key="chat_clear", use_container_width=True,
                 on_click=lambda: (ss.update(chat=[], chat_mem={})))
    log = st.container(height=430, border=False)
    with log:
        if not chat:
            with st.chat_message("assistant", avatar=":material/storefront:"):
                st.markdown(f"{greet}, {who}. What would you like to know about your shop today?")
        for i, m in enumerate(chat):
            with st.chat_message(m["role"], avatar=":material/storefront:" if m["role"] == "assistant"
                                 else ":material/person:"):
                st.markdown(m["content"])
                if m["role"] == "assistant":
                    st.caption(SOURCE.get(m.get("source"), ""))
                    if m.get("proposal") and m.get("pending"):
                        x, y, _ = st.columns([1, 1, 3])
                        x.button("Confirm", key=f"chat_ok_{i}", type="primary", on_click=_confirm, args=(i,))
                        y.button("Cancel", key=f"chat_no_{i}", on_click=_cancel, args=(i,))
    st.pills("Try asking", SUGGESTIONS, key="chat_pill", on_change=_from_pill, label_visibility="collapsed")
    typed = st.chat_input("Ask about stock, sales, profit or this week's order…", key="chat_in")

question = typed or ss.pop("chat_q", None)
if question:
    chat.append({"role": "user", "content": question})
    with st.spinner("Checking your shop's numbers…"):
        r = assistant.ask(question, chat[:-1], ctx, cfg, memory)
    chat.append({"role": "assistant", "content": r["text"], "source": r["source"], "tools": r["tools"],
                 "proposal": r["proposal"], "pending": bool(r["proposal"])})
    st.rerun()

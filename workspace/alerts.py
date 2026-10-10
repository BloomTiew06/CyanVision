"""A · Alert Before Stockout: products that may run out before the next delivery, when, how short, what it may cost,
and what to do. Risk and options come from planning.alert_table; the risk category (BM / EN) and act-by day come from
the shared rows (inventory.categorize / priority). Decisions are saved in the local store (alerts[ref|product], the
same records Home and the assistant read). Muted products stay visible: muting only silences reminders, it never hides
a risk."""
from html import escape

import pandas as pd
import streamlit as st

import laris_ui as ui
import planning
import store

HERE = "views/laris.py"
STATUSES = ["New", "Reviewed", "Action planned", "Resolved", "Snoozed"]
OPTIONS = {"topup": "Top up today", "next": "Next order", "sub": "Substitute", "none": "No action"}
OPTION_LONG = {"topup": "top up from a wholesaler today", "next": "order more for the next delivery",
               "sub": "offer a substitute", "none": "do nothing for now"}


def _write(ref, p, name, rec, toast):
    try:
        store.update("alerts", f"{ref}|{p}", {**rec, "at": store.now()})
    except OSError:
        ui.flash(f"Couldn't save the decision for {name}: the local file isn't writable. Nothing was changed.")
        return False
    ui.flash(toast)
    return True


def _save(ref, p, name, k_status, k_choice, k_sub):
    ss = st.session_state
    rec = {"status": ss[k_status], "choice": ss.get(k_choice) or "none", "substitute": ss.get(k_sub, "")}
    _write(ref, p, name, rec, f"Saved: {name} · {rec['status'].lower()}.")


def _primary(ref, r, name, status):
    """The one recommended action for this alert, done in one click."""
    if status in ("Action planned", "Reviewed"):
        return _write(ref, r.product, name, {"status": "Resolved", "choice": r.choice},
                      f"{name}: marked resolved.")
    if r.choice == "topup":
        return _write(ref, r.product, name, {"status": "Action planned", "choice": "topup"},
                      f"Top-up planned: about {r.bridge_qty:,.0f} × {name}. Buy it from your wholesaler today.")
    if r.choice == "next" and r.order_qty == 0 and r.bridge_qty > 0:
        ui.set_qty_value(r.product, r.bridge_qty)
        return _write(ref, r.product, name, {"status": "Action planned", "choice": "next"},
                      f"{name}: {r.bridge_qty:,.0f} added to this week's order.")
    if r.choice == "next":
        return _write(ref, r.product, name, {"status": "Action planned", "choice": "next"},
                      f"{name}: covered by this week's order ({r.order_qty:,.0f} units).")
    return _write(ref, r.product, name, {"status": "Reviewed", "choice": "none"}, f"{name}: reviewed.")


def _primary_label(r, status):
    if status in ("Action planned", "Reviewed"):
        return "Mark resolved"
    if r.choice == "topup":
        return f"Plan top-up of {r.bridge_qty:,.0f} (≈ {ui.money(r.bridge_qty * r.unit_cost)})"
    if r.choice == "next" and r.order_qty == 0 and r.bridge_qty > 0:
        return f"Add {r.bridge_qty:,.0f} to this order"
    if r.choice == "next":
        return f"Confirm {r.order_qty:,.0f} in this order"
    return "Mark as reviewed"


def _days(ts, as_of):
    return (ts - as_of) / pd.Timedelta(days=1) if ts is not None and not pd.isna(ts) else float("inf")


def _card(ctx, r, rec, key, muted, info, nested=False):
    ref, as_of = ctx["ref"], ctx["week"]["as_of"]
    icon, name = ui.split_name(r.name)
    status = rec.get("status", "New")
    with st.container(border=True, key=key):
        a, b = st.columns([3, 1.25])
        bm, en = (info.get("label") or " / ").split(" / ", 1) if " / " in str(info.get("label")) else ("", "")
        act_by = info.get("act_by")
        when = ("" if act_by is None or pd.isna(act_by) else
                "Act today" if int(act_by) <= 0 else f"Act by {as_of + pd.Timedelta(days=int(act_by)):%a %d %b}")
        a.markdown(f'{ui.status_chip(r.level)}{ui.must_chip(r.must_have)}'
                   f'{ui.status_chip("Muted") if muted else ""}'
                   f'{ui.chip(status, "lr-s-handled", "✓") if status in ("Action planned", "Reviewed") else ""}'
                   f'<span class="lr-name">{escape(icon)} {escape(name)}</span>'
                   + (f'<div class="lr-cat">{escape(en)} <i lang="ms">{escape(bm)}</i>'
                      + (f' · <b>{escape(when)}</b>' if when else "") + "</div>" if en else "")
                   + ui.product_spark(ctx, r.product, 240, 40), unsafe_allow_html=True)
        b.markdown(f'<div style="text-align:right">{ui.label("ESTIMATED", "estimated")}<br>'
                   f'<span class="lr-impact">{ui.money(r.rm_at_risk)} margin at risk</span><br>'
                   f'<span class="lr-muted">if nothing is done</span></div>', unsafe_allow_html=True)
        lo, hi = _days(r.runout_lo, as_of), _days(r.runout_hi, as_of)
        horizon = min(14.0, max(float(r.lead), r.cover if r.cover != float("inf") else 0, hi if hi != float("inf") else 0)
                      + 1)
        st.markdown(ui.timeline(r.cover, lo, hi, r.lead, horizon, anim=ui.first_view(f"tl:{ref}:{r.product}")),
                    unsafe_allow_html=True)
        if r.runout is None:
            runs = "doesn't run out this week"
        else:
            runs = f"runs out around <b>{r.runout:%a %d %b}</b>"
            if r.runout_lo is not None and r.runout_hi is not None and r.runout_lo.date() != r.runout_hi.date():
                runs += f" (likely {r.runout_lo:%a %d}–{r.runout_hi:%a %d %b})"
        st.markdown(f'<div class="lr-tl-legend"><span>Today · stock <b>{r.stock:,.0f}</b>, sells ~<b>{r.daily:,.1f}</b>/day'
                    f'</span><span>{runs}</span><span>Delivery if ordered today: <b>{r.delivery:%a %d %b}</b></span></div>',
                    unsafe_allow_html=True)
        c, d = st.columns([3, 1.6], vertical_alignment="center")
        c.markdown(f'<span class="lr-muted"><b>LARIS suggests:</b> {escape(OPTION_LONG[r.choice])}. {escape(r.why)}</span>',
                   unsafe_allow_html=True)
        d.button(_primary_label(r, status), key=f"al_go_{r.product}", type="primary", width="stretch",
                 on_click=_primary, args=(ref, r, name, status), disabled=status == "Resolved")
        with (st.container() if nested else st.expander("More options: substitute, status, details")):
            keys = list(OPTIONS)
            k_choice, k_status, k_sub = f"al_choice_{r.product}", f"al_status_{r.product}", f"al_sub_{r.product}"
            default = rec.get("choice", r.choice) if rec.get("choice", r.choice) in keys else r.choice
            choice = ui.choice("What will you do?", keys, k_choice, default,
                               format_func=lambda o, r=r: OPTIONS[o] + (" ★" if o == r.choice else ""))
            if choice == "topup":
                st.caption(f"Bridge the gap with about {r.bridge_qty:,.0f} units (expected shortfall before the delivery). "
                           f"LARIS can't see wholesaler prices or stock; at your usual cost it's about "
                           f"{ui.money(r.bridge_qty * r.unit_cost)}, a wholesaler may charge more.")
            elif choice == "next":
                st.caption(f"In this week's order: {r.order_qty:,.0f} units.")
            elif choice == "sub":
                st.text_input("Which product can customers buy instead?", value=rec.get("substitute", ""), key=k_sub,
                              help="Your choice. LARIS doesn't know which products substitute for each other.")
            else:
                st.caption("A short gap can be acceptable for a low-priority item. Check the shelf again tomorrow.")
            e, f, g = st.columns([1.4, 1, 1], vertical_alignment="bottom")
            e.selectbox("Status", STATUSES, index=STATUSES.index(status) if status in STATUSES else 0, key=k_status)
            f.button("Save", key=f"al_save_{r.product}", width="stretch",
                     on_click=_save, args=(ref, r.product, name, k_status, k_choice, k_sub))
            with g:
                ui.why_button(r.product, HERE, key=f"al_why_{r.product}", label="Details")
            if rec.get("at"):
                st.caption(f"Last saved {rec['at']}: {rec.get('status')}.")


def render(ctx):
    ref = ctx["ref"]
    anim = ui.first_view("tool:A")
    al = planning.alert_table(ctx)
    info = ctx["rows"].set_index("product")[["label", "act_by"]].to_dict("index")
    muted = set(store.get("prefs", {}).get("muted", []))
    saved = store.get("alerts", {})
    rec_of = lambda p: saved.get(f"{ref}|{p}", {})
    status_of = lambda p: rec_of(p).get("status", "New")

    counts = al["level"].value_counts().to_dict() if len(al) else {}
    k = st.columns(3)
    for col, level, text, tone in zip(k, ["URGENT", "WARNING", "MONITOR"],
                                      ["may run out before the next delivery", "may run low before the delivery after",
                                       "fine for now, worth a check"], ["bad", "warn", None]):
        n = int(counts.get(level, 0))
        col.markdown(ui.kpi(level.title(), " products", text, tone if n else None, n, f"al_{level}"),
                     unsafe_allow_html=True)
    if al.empty:
        st.markdown(ui.empty("✓", "No product is expected to run out before your next delivery",
                             "LARIS checks again whenever your stock or budget changes."), unsafe_allow_html=True)
        return

    keep = ui.filter_bar("al", ctx)
    view = keep(al)
    if view is None or view.empty:
        st.markdown(ui.empty("🔍", "No alert matches", "Clear the search or the category filter."),
                    unsafe_allow_html=True)
        return
    done_mask = view["product"].map(status_of).isin(["Resolved", "Snoozed"])
    mute_mask = view["product"].isin(muted) & ~done_mask
    active, quiet, done = view[~done_mask & ~mute_mask], view[mute_mask], view[done_mask]
    fresh = ui.newly(f"urgent:{ref}", list(al.loc[al["level"] == "URGENT", "product"]))

    ui.section("Alerts", "Most urgent first; must-haves and bigger losses rank higher. Dates are estimates from the "
                         "forecast and its usual error, not exact.")
    if active.empty:
        st.markdown(ui.empty("✓", "Everything here is handled", "See the handled and muted lists below."),
                    unsafe_allow_html=True)
    keys = []
    grid = st.columns(2, gap="medium")
    for i, r in enumerate(active.itertuples()):
        key = f"card_al_{ui.safe_key(r.product)}"
        keys.append(key)
        with grid[i % 2]:
            _card(ctx, r, rec_of(r.product), key, False, info.get(r.product, {}))
    ui.enter(keys, anim, pulse=[f"card_al_{ui.safe_key(p)}" for p in fresh if p in set(active["product"])])
    if len(quiet):
        with st.expander(f"Muted, still at risk ({len(quiet)})", icon=":material/notifications_off:"):
            st.caption("Muting stops reminders for these products (S · Send & Sync). The risk is still real.")
            for r in quiet.itertuples():
                _card(ctx, r, rec_of(r.product), f"done_alm_{ui.safe_key(r.product)}", True, info.get(r.product, {}),
                      nested=True)
    if len(done):
        with st.expander(f"Handled or snoozed ({len(done)})", icon=":material/task_alt:"):
            for r in done.itertuples():
                _card(ctx, r, rec_of(r.product), f"done_al_{ui.safe_key(r.product)}", r.product in muted,
                      info.get(r.product, {}), nested=True)
    st.caption("Alert decisions are saved on this computer (state/laris_state.json) for this order week.")

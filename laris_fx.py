"""LARIS motion layer: a few small interactive components that animate between real states.

Built on st.components.v2: the JavaScript runs inline in the page (no iframe) and the element survives reruns, so a
number can roll from its old value to the new one and a bar can spring to its new width. That is what CSS alone
can't do in Streamlit, because every rerun repaints the HTML.

The interaction patterns are adapted from 21st.dev community components (MIT): Number Flow / Number Ticker (rolling
digits), Vercel Tabs / Sliding Tabs (a highlight that slides to the active tab and follows the pointer), and the
shadcn Progress bar. They're written from scratch with the Web Animations API: no external library, so the demo
also works offline.

Rules:
- Animate only real changes: Python passes the previous value it saw (laris_ui.track); an unchanged value never moves.
- prefers-reduced-motion: everything jumps straight to its final state, unless the owner chose
  'Animations: always on' in Settings (for a demo laptop whose system asks for reduced motion).
- With LARIS_FX=0, or where components v2 isn't available (e.g. AppTest), every function draws a static fallback
  from laris_ui instead, so behaviour never depends on the animation layer.
"""
import json
import os
from html import escape

import streamlit as st

import laris_ui as ui

try:
    from streamlit.components.v2 import component as _component
except Exception:   # older Streamlit: static fallbacks only
    _component = None

EASE_SPRING = "cubic-bezier(.22, 1.25, .36, 1)"     # a touch of overshoot, like a spring settling


def enabled():
    return _component is not None and os.environ.get("LARIS_FX", "1") != "0"


# ---------------- rolling number (Number Flow pattern) ----------------
_NUMBER_CSS = """
:host {display: block;}
.n {display: flex; align-items: baseline; font-variant-numeric: tabular-nums; line-height: 1.1; white-space: nowrap;
    letter-spacing: -.02em;}
.d {display: inline-block; height: 1.1em; overflow: hidden; position: relative;}
.d > span {display: flex; flex-direction: column; will-change: transform;}
.d > span > i {font-style: normal; height: 1.1em; line-height: 1.1em; text-align: center;}
.s {display: inline-block; white-space: pre;}
"""
_NUMBER_JS = """
const DIGIT = /[0-9]/;
export default function (c) {
  const { data, parentElement: host } = c;
  const reduce = !data.force && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const text = String(data.text);
  let root = host.querySelector('.n');
  if (!root) { root = document.createElement('div'); root.className = 'n'; host.appendChild(root); }
  Object.assign(root.style, { fontSize: data.size || '', fontWeight: data.weight || 800, color: data.color || 'inherit',
                              justifyContent: data.align || 'flex-start' });
  root.setAttribute('role', 'img');
  root.setAttribute('aria-label', data.label || text);
  const prev = host.__text !== undefined ? host.__text : data.prev;
  host.__text = text;
  const shape = text.replace(/[0-9]/g, '0');
  if (host.__shape !== shape) {            // digits added or removed: rebuild the columns
    root.innerHTML = '';
    for (const ch of text) {
      if (DIGIT.test(ch)) {
        const d = document.createElement('span'); d.className = 'd'; d.setAttribute('aria-hidden', 'true');
        const col = document.createElement('span');
        for (let k = 0; k < 10; k++) { const i = document.createElement('i'); i.textContent = k; col.appendChild(i); }
        d.appendChild(col); root.appendChild(d);
      } else {
        const s = document.createElement('span'); s.className = 's'; s.setAttribute('aria-hidden', 'true');
        s.textContent = ch; root.appendChild(s);
      }
    }
    host.__shape = shape;
  }
  const digits = [...text].filter(ch => DIGIT.test(ch)).map(Number);
  const same = typeof prev === 'string' && prev.replace(/[0-9]/g, '0') === shape;
  const from = same ? [...prev].filter(ch => DIGIT.test(ch)).map(Number) : digits.map(() => 0);
  [...root.querySelectorAll('.d > span')].forEach((col, i) => {
    const to = `translateY(${-digits[i] * 1.1}em)`;
    const start = `translateY(${-from[i] * 1.1}em)`;
    col.getAnimations().forEach(a => a.cancel());
    col.style.transform = to;
    if (reduce || prev === text || start === to) return;
    col.animate([{ transform: start }, { transform: to }],
                { duration: 650 + i * 70, easing: 'cubic-bezier(.22, 1.25, .36, 1)' });
  });
}
"""

# ---------------- spring meter (shadcn Progress pattern) ----------------
_METER_CSS = """
:host {display: block;}
.t {position: relative; overflow: hidden; border-radius: 999px;}
.t i {position: absolute; top: 0; bottom: 0; left: 0; border-radius: 999px;}
.t b {position: absolute; top: -3px; bottom: -3px; width: 2px; border-radius: 2px;}
"""
_METER_JS = """
export default function (c) {
  const { data, parentElement: host } = c;
  const reduce = !data.force && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  let t = host.querySelector('.t');
  if (!t) { t = document.createElement('div'); t.className = 't'; host.appendChild(t); }
  t.style.height = (data.height || 10) + 'px';
  t.style.background = data.track || 'var(--mist, #E7ECE5)';
  t.setAttribute('role', 'img');
  t.setAttribute('aria-label', data.label || '');
  const segs = data.segments || [];
  const prev = host.__segs || data.prev || segs.map(() => [0, 0]);
  let x = 0;
  const now = segs.map(([w]) => { const s = [x, Math.max(0, Math.min(1, w)) ]; x += s[1]; return s; });
  while (t.querySelectorAll('i').length < segs.length) t.appendChild(document.createElement('i'));
  [...t.querySelectorAll('i')].forEach((el, k) => {
    if (k >= segs.length) { el.remove(); return; }
    const [left, width] = now[k], [pl, pw] = prev[k] || [left, 0];
    el.style.background = segs[k][1];
    el.getAnimations().forEach(a => a.cancel());
    el.style.left = (left * 100) + '%'; el.style.width = (Math.min(width, 1 - left) * 100) + '%';
    if (reduce || (pl === left && pw === width)) return;
    el.animate([{ left: (pl * 100) + '%', width: (pw * 100) + '%' },
                { left: (left * 100) + '%', width: (Math.min(width, 1 - left) * 100) + '%' }],
               { duration: 750, easing: 'cubic-bezier(.34, 1.4, .64, 1)' });
  });
  let m = t.querySelector('b');
  if (data.marker === null || data.marker === undefined) { if (m) m.remove(); }
  else {
    if (!m) { m = document.createElement('b'); t.appendChild(m); }
    m.style.background = data.markerColor || 'var(--ink, #252923)';
    const pm = host.__marker === undefined ? data.marker : host.__marker;
    m.getAnimations().forEach(a => a.cancel());
    m.style.left = `calc(${data.marker * 100}% - 1px)`;
    if (!reduce && pm !== data.marker)
      m.animate([{ left: `calc(${pm * 100}% - 1px)` }, { left: `calc(${data.marker * 100}% - 1px)` }],
                { duration: 600, easing: 'cubic-bezier(.22, 1, .36, 1)' });
  }
  host.__segs = now; host.__marker = data.marker;
}
"""

# ---------------- sliding tab bar (Vercel Tabs / Sliding Tabs pattern) ----------------
_NAV_CSS = """
:host {display: block;}
.nav {position: relative; display: grid; grid-template-columns: repeat(var(--n, 5), 1fr); gap: 8px;}
.pill, .hover {position: absolute; top: 0; left: 0; height: 100%; border-radius: 12px; pointer-events: none;}
.pill {background: var(--lime, #C7ED72); box-shadow: 0 6px 18px rgba(16, 56, 43, .16); z-index: 0;
       transition: transform 480ms cubic-bezier(.3, 1.35, .5, 1), width 480ms cubic-bezier(.3, 1.35, .5, 1);}
.hover {background: var(--soft, #F3F6F1); opacity: 0; z-index: 0;
        transition: transform 220ms cubic-bezier(.2, .8, .2, 1), width 220ms, opacity 160ms;}
button {position: relative; z-index: 1; display: flex; flex-direction: column; align-items: center; justify-content: center;
        gap: 2px; height: 78px; border-radius: 12px; border: 1px solid var(--line, #E2E6DF); background: transparent;
        font: inherit; color: var(--muted, #5C625A); cursor: pointer; padding: 6px 8px; transition: color 200ms, border-color 200ms;}
button b {font-size: 26px; font-weight: 800; line-height: 1.05; color: var(--forest, #174D3A); letter-spacing: -.02em;}
button span {font-size: 12.5px; font-weight: 700;}
button em {font-style: normal; font-size: 11.5px;}
button[aria-selected="true"] {border-color: transparent; color: var(--deep, #10382B);}
button[aria-selected="true"] b {color: var(--deep, #10382B);}
button:focus-visible {outline: 2px solid var(--forest, #174D3A); outline-offset: 2px;}
@media (max-width: 640px) {
  .nav {gap: 6px;} button {height: 56px;} button span, button em {display: none;} button b {font-size: 22px;}
}
@media (prefers-reduced-motion: reduce) { .nav:not(.force) .pill, .nav:not(.force) .hover {transition: none;} }
"""
_NAV_JS = """
export default function (c) {
  const { data, parentElement: host, setTriggerValue } = c;
  let nav = host.querySelector('.nav');
  const items = data.items || [];
  const key = items.map(i => i.id + ':' + i.name).join('|');
  if (!nav || host.__key !== key) {
    if (nav) nav.remove();
    nav = document.createElement('div'); nav.className = 'nav'; nav.setAttribute('role', 'tablist');
    nav.setAttribute('aria-label', data.label || 'Tools');
    nav.style.setProperty('--n', items.length);
    nav.innerHTML = '<div class="hover"></div><div class="pill"></div>';
    items.forEach((it, k) => {
      const b = document.createElement('button');
      b.type = 'button'; b.setAttribute('role', 'tab'); b.dataset.id = it.id;
      b.innerHTML = '<b></b><span></span><em></em>';
      b.querySelector('b').textContent = it.letter; b.querySelector('span').textContent = it.name;
      b.onclick = () => { place(nav, b, '.pill'); setSelected(nav, it.id); setTriggerValue('select', it.id); };
      b.onmouseenter = () => { place(nav, b, '.hover'); nav.querySelector('.hover').style.opacity = 1; };
      b.onkeydown = (e) => {
        const bs = [...nav.querySelectorAll('button')];
        const j = bs.indexOf(b) + (e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0);
        if (j !== bs.indexOf(b) && bs[j]) { e.preventDefault(); bs[j].focus(); }
      };
      nav.appendChild(b);
    });
    nav.onmouseleave = () => { nav.querySelector('.hover').style.opacity = 0; };
    host.appendChild(nav);
    host.__key = key;
    new ResizeObserver(() => { const a = nav.querySelector('button[aria-selected="true"]'); if (a) place(nav, a, '.pill', true); })
      .observe(nav);
  }
  items.forEach(it => {
    const b = nav.querySelector(`button[data-id="${it.id}"]`);
    b.querySelector('em').textContent = it.badge || '';
    b.setAttribute('aria-label', `${it.letter} · ${it.name}${it.badge ? ' · ' + it.badge : ''}`);
  });
  nav.classList.toggle('force', !!data.force);
  setSelected(nav, data.active);
  const active = nav.querySelector(`button[data-id="${data.active}"]`);
  if (active) place(nav, active, '.pill', !host.__placed);
  host.__placed = true;
}
function setSelected(nav, id) {
  nav.querySelectorAll('button').forEach(b => {
    const on = b.dataset.id === id;
    b.setAttribute('aria-selected', on ? 'true' : 'false'); b.tabIndex = on ? 0 : -1;
  });
}
function place(nav, b, sel, instant) {
  const el = nav.querySelector(sel);
  if (instant) { el.style.transition = 'none'; }
  el.style.width = b.offsetWidth + 'px';
  el.style.transform = `translateX(${b.offsetLeft}px)`;
  if (instant) { el.getBoundingClientRect(); el.style.transition = ''; }
}
"""

_NUMBER = _METER = _NAV = None
if _component is not None:
    try:
        _NUMBER = _component("laris_number", css=_NUMBER_CSS, js=_NUMBER_JS)
        _METER = _component("laris_meter", css=_METER_CSS, js=_METER_JS)
        _NAV = _component("laris_nav", css=_NAV_CSS, js=_NAV_JS)
    except Exception:
        _component = None


def number(text, key, label=None, size="40px", color=None, weight=800, align="flex-start"):
    """A figure whose digits roll from the last value shown to this one (e.g. 'RM 1,384'). Static fallback: plain text."""
    prev, _ = ui.track(f"fx:{key}", text)
    if not enabled() or _NUMBER is None:
        st.markdown(f'<div class="lr-fxnum" style="font-size:{size};font-weight:{weight};text-align:'
                    f'{"right" if align == "flex-end" else "left"};{"color:" + color if color else ""}">'
                    f'{escape(str(text))}</div>', unsafe_allow_html=True)
        return
    _NUMBER(key=f"fx_{key}", data={"text": str(text), "prev": prev, "label": label or str(text), "size": size,
                                   "color": color, "weight": weight, "align": align, "force": ui.motion_forced()})


def meter(segments, key, marker=None, height=10, track=None, label="", marker_color=None):
    """A bar of consecutive segments [(fraction 0..1, css colour)] that springs to new widths when they change.
    Static fallback: laris_ui.segments."""
    segs = [[max(0.0, float(w)), c] for w, c in segments]
    prev, _ = ui.track(f"fxm:{key}", json.dumps(segs))
    if not enabled() or _METER is None:
        st.markdown(ui.segments([(w, "") for w, _ in segs], 1.0, label, marker=marker), unsafe_allow_html=True)
        return
    prev_segs = None
    if prev:
        x, prev_segs = 0.0, []
        for w, _ in json.loads(prev):
            prev_segs.append([x, w])
            x += w
    _METER(key=f"fx_{key}", data={"segments": segs, "marker": marker, "height": height, "track": track,
                                  "label": label, "prev": prev_segs, "markerColor": marker_color,
                                  "force": ui.motion_forced()})


def nav(items, active, key, on_select, label="LARIS tools"):
    """The sliding tab bar. items: [{id, letter, name, badge}]. on_select(id) runs before the page redraws.
    Returns False when the animated version isn't available, so the caller draws its own buttons."""
    if not enabled() or _NAV is None:
        return False

    def _changed():
        v = st.session_state.get(f"fx_{key}")
        sel = v.get("select") if isinstance(v, dict) else getattr(v, "select", None)
        if sel:
            on_select(sel)

    _NAV(key=f"fx_{key}", data={"items": items, "active": active, "label": label, "force": ui.motion_forced()}, on_select_change=_changed)
    return True

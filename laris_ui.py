"""LARIS look and feel: one design system plus small shared components, so every page looks and behaves the same.
Business numbers never come from here; they come from the shared context (laris_core) and planning.py.

Design tokens live as CSS variables at the top of CSS (brand forest/deep/lime on cream, white surfaces, status colours
that always travel with a text label and an icon). Motion follows a few rules: transform and opacity only, short
durations, nothing loops, entrance animations play once per page per session (first_view / enter), and everything
that moves sits inside @media (prefers-reduced-motion: no-preference). Animations only ever reflect real state:
counters and change chips compare actual figures across reruns, and success feedback is shown by the callers only
after their write has happened.
"""
import re
from html import escape

import altair as alt
import pandas as pd
import streamlit as st

import planning

GREEN, DARK, LIME, CREAM, CHARCOAL, MUTED, MIST, RISK = ("#174D3A", "#10382B", "#C7ED72", "#F7F5EE", "#252923",
                                                       "#626860", "#E7ECE5", "#A04A2A")
WARN = "#8A5A00"
Z90 = 1.645
ACTIONS = ("RESTOCK", "REDUCE", "STOP", "MAINTAIN")

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&family=JetBrains+Mono:wght@500;700&display=swap');
:root {
  --forest: #174D3A; --deep: #10382B; --lime: #C7ED72; --lime-hover: #B8E25A;
  --cream: #F7F5EE; --surface: #FFFFFF; --line: #E2E6DF; --line-strong: #C9D1C6; --mist: #E7ECE5; --soft: #F3F6F1;
  --ink: #252923; --muted: #5C625A; --on-dark: #C9D7CE;
  --risk: #A04A2A; --risk-bg: #F6E3DA; --warn: #7A4A00; --warn-bg: #FCEBCF; --info: #4A5048; --info-bg: #EEF1EC;
  --ok: #174D3A; --ok-bg: #E7ECE5;
  --r-card: 10px; --r-ctl: 8px; --r-pill: 999px;
  --shadow-hover: 0 6px 18px rgba(16, 56, 43, .08); --shadow-hero: 0 10px 28px rgba(16, 56, 43, .18);
  --ease: cubic-bezier(.2, .8, .2, 1); --t-micro: 120ms; --t-small: 180ms; --t-enter: 240ms;
  --stone: #F1F0EA; --sage: #9AA397; --risk-light: #F4B79B; --hero-line: #3B6E5B; --amber: #C98A1B; --wa-dark: #075E54; --wa-bubble: #D9FDD3; --risk-line: #E8B8A6; --seg2: #7FA392; --hatch: #E9B98A; --wa-bg: #EFE7DD; --wa-ink: #111B21; --wa-meta: #667781; --shimmer: #F4F7F2;
  --font: 'Manrope', sans-serif; --mono: 'JetBrains Mono', monospace;
}
html, body, .stApp, .stMarkdown, button, input, textarea, label, [data-testid="stWidgetLabel"] p {font-family: var(--font);}
[data-testid="stIconMaterial"], [data-testid="stIconMaterial"] * {font-family: 'Material Symbols Rounded' !important;}
.stApp {background: var(--cream); color: var(--ink);}
.block-container {padding: 5rem 2rem 4rem; max-width: 1240px;}
/* header: no Streamlit 'Running… Stop' text or Deploy button; a slim lime line shows work in progress */
[data-testid="stAppDeployButton"], [data-testid="stMainMenu"] {display: none !important;}
[data-testid="stStatusWidget"] {position: fixed !important; top: 3.75rem; left: 0; right: 0; height: 3px;
  overflow: hidden; z-index: 999990; background: linear-gradient(90deg, transparent, var(--lime), transparent);
  background-size: 40% 100%; background-repeat: no-repeat; background-position: 50% 0;}
[data-testid="stStatusWidget"] * {display: none !important;}
@keyframes lr-loading {from {background-position: -40% 0;} to {background-position: 140% 0;}}
.lr-contextbar {display: flex; flex-wrap: wrap; gap: 4px 18px; align-items: center; font-size: 12.5px; color: var(--muted);
                padding: 2px 0 10px; border-bottom: 1px solid var(--line); margin-bottom: 14px;}
.lr-contextbar b {color: var(--ink);}

/* ---------- header and top navigation ---------- */
header[data-testid="stHeader"] {background: var(--deep); border-bottom: none; height: 3.75rem;}
[data-testid="stTopNavLink"], [data-testid="stTopNavSection"] {border-radius: var(--r-ctl);
  transition: background var(--t-micro) var(--ease);}
[data-testid="stTopNavLink"] *, [data-testid="stTopNavSection"] * {color: var(--on-dark) !important;}
[data-testid="stTopNavLink"]:hover, [data-testid="stTopNavSection"]:hover {background: var(--forest);}
[data-testid="stTopNavLink"][aria-current="page"] {background: var(--forest); box-shadow: inset 0 -2px 0 var(--lime);}
[data-testid="stTopNavLink"][aria-current="page"] * {color: var(--cream) !important; font-weight: 700;}
[data-testid="stTopNavLink"][href$="/product"] {display: none;}   /* the product page opens from a product */
[data-testid="stToolbarActions"] *, [data-testid="stMainMenu"] *, [data-testid="stAppDeployButton"] button,
[data-testid="stBaseButton-header"] {color: var(--cream) !important;}

/* ---------- buttons: one lime primary per area; quiet white secondary ---------- */
.stButton > button, .stLinkButton a, .stDownloadButton > button, .stFormSubmitButton > button,
[data-testid="stPopover"] button {border-radius: var(--r-ctl); font-weight: 700; border: 1px solid var(--line-strong);
  background: var(--surface); color: var(--forest);
  transition: border-color var(--t-micro) var(--ease), background var(--t-micro) var(--ease), transform var(--t-micro) var(--ease);}
.stButton > button:hover, .stLinkButton a:hover, [data-testid="stPopover"] button:hover
  {border-color: var(--forest); color: var(--forest); background: var(--soft);}
.stButton > button[kind="primary"], .stLinkButton a[kind="primary"], .stFormSubmitButton > button[kind="primary"],
.stDownloadButton > button[kind="primary"] {background: var(--lime); color: var(--deep); border: none; font-weight: 800;}
.stButton > button[kind="primary"]:hover, .stLinkButton a[kind="primary"]:hover,
.stFormSubmitButton > button[kind="primary"]:hover {background: var(--lime-hover); color: var(--deep);}
.stButton > button:disabled, .stLinkButton a[disabled] {opacity: .5;}

/* pills and segmented controls (st.pills / st.segmented_control) */
[data-testid="stButtonGroup"] button {border-radius: var(--r-pill); font-weight: 700;
  transition: background var(--t-small) var(--ease), color var(--t-small) var(--ease), border-color var(--t-small) var(--ease);}
[data-testid^="stBaseButton-pills"], [data-testid^="stBaseButton-segmented_control"]
  {background: var(--surface); border: 1px solid var(--line-strong); color: var(--forest);}
[data-testid="stBaseButton-pillsActive"], [data-testid="stBaseButton-segmented_controlActive"]
  {background: var(--forest) !important; border-color: var(--forest) !important; color: var(--cream) !important;}
[data-testid="stBaseButton-pillsActive"] *, [data-testid="stBaseButton-segmented_controlActive"] * {color: var(--cream) !important;}

/* single choices (ui.choice): a horizontal radio drawn as a row of pills */
[class*="st-key-seg_"] [role="radiogroup"] {display: flex; flex-wrap: wrap; gap: 6px;}
[class*="st-key-seg_"] [role="radiogroup"] label {margin: 0; padding: 5px 13px; border: 1px solid var(--line-strong);
  border-radius: var(--r-pill); background: var(--surface); cursor: pointer; min-height: 32px; align-items: center;
  transition: background var(--t-small) var(--ease), border-color var(--t-small) var(--ease), color var(--t-small) var(--ease);}
[class*="st-key-seg_"] [role="radiogroup"] label > div:first-child {display: none;}
[class*="st-key-seg_"] [role="radiogroup"] label p {font-size: 13px; font-weight: 700; color: var(--forest);}
[class*="st-key-seg_"] [role="radiogroup"] label:hover {border-color: var(--forest); background: var(--soft);}
[class*="st-key-seg_"] [role="radiogroup"] label:has(input:checked) {background: var(--forest); border-color: var(--forest);}
[class*="st-key-seg_"] [role="radiogroup"] label:has(input:checked) p {color: var(--cream);}
[class*="st-key-seg_"] [role="radiogroup"] label:has(input:focus-visible) {outline: 2px solid var(--forest); outline-offset: 2px;}

/* focus: always visible for keyboard users */
button:focus-visible, a:focus-visible, input:focus-visible, textarea:focus-visible, [role="tab"]:focus-visible,
[role="radio"]:focus-visible, [role="checkbox"]:focus-visible, summary:focus-visible
  {outline: 2px solid var(--forest) !important; outline-offset: 2px;}
header button:focus-visible, header a:focus-visible, .lr-hero a:focus-visible {outline-color: var(--lime) !important;}

/* ---------- surfaces ---------- */
div[data-testid="stExpander"] details {background: var(--surface); border: 1px solid var(--line); border-radius: var(--r-card);}
div[data-testid="stExpander"] summary p {font-weight: 700; color: var(--forest);}
[data-testid="stDataFrame"], [data-testid="stDataEditor"] {border: 1px solid var(--line); border-radius: var(--r-card);}
[class*="st-key-card_"] {padding: 18px 20px !important; background: var(--surface); transition: box-shadow var(--t-micro) var(--ease), border-color var(--t-micro) var(--ease);}
[class*="st-key-card_"]:hover {box-shadow: var(--shadow-hover); border-color: var(--line-strong);}
[class*="st-key-card_"].lr-done, [class*="st-key-done_"] {opacity: .85;}

/* ---------- type ---------- */
.lr-eyebrow {font-family: var(--mono); color: var(--forest); font-size: 12px; font-weight: 700; letter-spacing: .06em;
             margin-bottom: 2px; text-transform: uppercase;}
[data-testid="stMarkdownContainer"] p.lr-title {font-size: 30px; line-height: 1.15; font-weight: 800; color: var(--forest);
                                                letter-spacing: -.025em; margin: 0;}
.lr-title mark {background: none; color: inherit; padding: 0 2px; position: relative; white-space: nowrap;
                background-image: linear-gradient(var(--lime), var(--lime)); background-repeat: no-repeat;
                background-size: 100% .32em; background-position: 0 92%;}
.lr-sub {font-size: 14px; color: var(--muted); margin: 4px 0 12px;}
.lr-section {font-size: 17px; font-weight: 800; color: var(--forest); margin: 36px 0 4px;}
.lr-help {font-size: 13px; color: var(--muted); margin: 0 0 8px;}
.lr-muted {color: var(--muted); font-size: 13px;}
.lr-impact {font-size: 13px; font-weight: 700; color: var(--forest);}
.lr-big {font-size: 28px; font-weight: 800; color: var(--forest); line-height: 1.1; font-variant-numeric: tabular-nums;}
.lr-big small {font-size: 14px; font-weight: 600; color: var(--muted);}
.lr-shopline {font-size: 13px; color: var(--ink); line-height: 1.4;}
.lr-shopline b {font-size: 14px;}
.lr-shopline span {color: var(--muted);}
.lr-num, .lr-kpi .v, .lr-qty, .lr-hero .big, .lr-hero .stats b {font-variant-numeric: tabular-nums;}
.lr-sr {position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0 0 0 0);
        white-space: nowrap; border: 0;}

/* ---------- chips and labels: always text + icon, never colour alone ---------- */
.lr-chip {display: inline-flex; align-items: center; gap: 4px; padding: 2px 9px; border-radius: var(--r-pill);
          font-size: 11px; font-weight: 800; letter-spacing: .03em; margin: 0 6px 2px 0; white-space: nowrap;
          text-transform: uppercase; vertical-align: 1px;}
.lr-chip .i {font-size: 11px; line-height: 1;}
.lr-a-restock {background: var(--lime); color: var(--deep);}
.lr-a-reduce {background: var(--mist); color: var(--forest);}
.lr-a-stop {background: var(--stone); color: var(--muted); border: 1px solid var(--line-strong);}
.lr-a-maintain {background: var(--surface); color: var(--muted); border: 1px dashed var(--sage);}
.lr-s-urgent {background: var(--risk-bg); color: var(--risk);}
.lr-s-warning, .lr-s-soon, .lr-s-expiry {background: var(--warn-bg); color: var(--warn);}
.lr-s-monitor, .lr-s-info, .lr-s-excess, .lr-s-muted {background: var(--info-bg); color: var(--info);}
.lr-s-ok, .lr-s-handled, .lr-s-new {background: var(--ok-bg); color: var(--ok);}
.lr-must {background: var(--surface); color: var(--forest); border: 1px solid var(--forest);}
.lr-label {display: inline-block; font-family: var(--mono); font-size: 10.5px; font-weight: 700; padding: 1px 7px;
           border-radius: 4px; margin-right: 6px; vertical-align: 1px;}
.lr-measured, .lr-model {background: var(--mist); color: var(--forest);}
.lr-estimated, .lr-baseline {background: var(--info-bg); color: var(--info);}
.lr-simulated {background: var(--warn-bg); color: var(--warn);}
.lr-placeholder {background: var(--stone); color: var(--muted);}
.lr-planned, .lr-unavailable {background: var(--surface); color: var(--muted); border: 1px dashed var(--sage);}
.lr-delta {display: inline-block; margin-left: 8px; padding: 1px 7px; border-radius: var(--r-pill); font-size: 12px;
           font-weight: 800; vertical-align: middle; font-variant-numeric: tabular-nums;}
.lr-delta.up {background: var(--mist); color: var(--forest);}
.lr-delta.down {background: var(--risk-bg); color: var(--risk);}
.lr-hero .lr-delta.up {background: var(--lime); color: var(--deep);}
.lr-hero .lr-delta.down {background: var(--risk-light); color: var(--deep);}

/* ---------- hero panel ---------- */
.lr-hero {background: var(--forest); color: var(--cream); border-radius: 14px; padding: 30px 34px;
          box-shadow: var(--shadow-hero); margin: 6px 0 18px;}
.lr-hero .eyebrow {font-family: var(--mono); font-size: 12px; font-weight: 700; color: var(--lime); letter-spacing: .06em;}
.lr-hero .top {display: flex; flex-wrap: wrap; justify-content: space-between; gap: 12px; align-items: flex-start;}
.lr-hero .lead {font-size: 15px; color: var(--on-dark); margin-top: 4px;}
.lr-hero .big {font-size: 40px; font-weight: 800; letter-spacing: -.03em; line-height: 1.05; text-align: right;}
.lr-hero .big small {display: block; font-size: 12px; font-weight: 500; color: var(--on-dark); letter-spacing: 0;}
.lr-hero .lr-meter {background: var(--deep); margin: 16px 0 6px; height: 12px;}
.lr-hero .lr-meter i {background: var(--lime);}
.lr-hero .lr-meter b {background: var(--cream);}
.lr-hero .legend {font-size: 12px; color: var(--on-dark);}
.lr-hero .stats {display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); border-top: 1px solid var(--hero-line);
                 margin-top: 16px;}
.lr-hero .stats > div {padding: 16px 18px 4px; border-left: 1px solid var(--hero-line);}
.lr-hero .stats > div:first-child {border-left: none; padding-left: 0;}
.lr-hero .stats > div > span {display: block; font-size: 12px; color: var(--on-dark);}
.lr-hero .stats > div > b {display: block; font-size: 22px; font-weight: 800; line-height: 1.2;}
.lr-hero .stats > div > em {display: block; font-style: normal; font-size: 12px; color: var(--on-dark);}
.lr-hero .stats b.lime {color: var(--lime);}
.lr-hero .stats b.risk {color: var(--risk-light);}

/* live hero (laris_fx): the same panel as a container, so its number and bar can animate */
.st-key-hero_box {background: var(--forest); color: var(--cream); border-radius: 14px; padding: 30px 34px 30px;
                  box-shadow: var(--shadow-hero); margin: 8px 0 22px; gap: .5rem;}
.lr-hero.lr-hero-flat {background: none; box-shadow: none; padding: 0; margin: 0; border-radius: 0;}
.lr-hero .note {display: block; font-size: 12px; font-weight: 500; color: var(--on-dark); text-align: right;
                padding-bottom: 1.1rem;}

/* ---------- LARIS letter strip ---------- */
[class*="st-key-letter_"] button {height: 78px; flex-direction: column; background: var(--surface); border: 1px solid var(--line);
                                  color: var(--muted); font-weight: 600; border-radius: var(--r-card);}
[class*="st-key-letter_"] button p {font-size: 12px; line-height: 1.25; margin: 0;}
[class*="st-key-letter_"] button strong {display: block; font-size: 26px; font-weight: 800; color: var(--forest);
                                         letter-spacing: -.02em; line-height: 1.1;}
[class*="st-key-letter_"] button:hover {border-color: var(--forest); background: var(--soft);}
[class*="st-key-letter_"] button[kind="primary"] {background: var(--lime); border-color: var(--lime); color: var(--deep);
                                                  box-shadow: 0 4px 14px rgba(16, 56, 43, .12);}
[class*="st-key-letter_"] button[kind="primary"] strong {color: var(--deep);}
[class*="st-key-letter_"] button[kind="primary"] p {font-weight: 800;}

/* ---------- rows, KPIs, cards ---------- */
[class*="st-key-row_"] {border-top: 1px solid var(--info-bg); padding: 8px 4px 8px; transition: background var(--t-micro) var(--ease);}
[class*="st-key-row_"]:hover {background: var(--soft);}
.lr-name {font-weight: 700; font-size: 14.5px; color: var(--ink);}
.lr-qty {font-family: var(--mono); font-size: 14px; font-weight: 700; color: var(--ink);}
.lr-qty span {font-family: var(--font); font-weight: 500; color: var(--muted); font-size: 12.5px;}
.lr-card {background: var(--surface); border: 1px solid var(--line); border-radius: var(--r-card); padding: 18px 20px; height: 100%;
          transition: box-shadow var(--t-micro) var(--ease), border-color var(--t-micro) var(--ease);}
.lr-kpi .k {font-family: var(--mono); font-size: 11px; font-weight: 700; color: var(--muted); text-transform: uppercase;}
.lr-kpi .v {font-size: 24px; font-weight: 800; color: var(--forest); line-height: 1.25;}
.lr-kpi .v.bad {color: var(--risk);} .lr-kpi .v.warn {color: var(--warn);}
.lr-kpi .s {font-size: 12px; color: var(--muted);}
.lr-kpi .s.bad {color: var(--risk);} .lr-kpi .s.warn {color: var(--warn);} .lr-kpi .s.good {color: var(--forest);}
.lr-insight {display: flex; align-items: center; gap: 8px; padding: 10px 14px; border-left: 3px solid var(--line-strong);
             background: var(--surface); margin-bottom: 6px; border-radius: 0 var(--r-ctl) var(--r-ctl) 0; font-size: 14px;
             min-height: 42px;}
.lr-insight.urgent {border-left-color: var(--risk);}
.lr-insight.warning {border-left-color: var(--amber);}
.lr-insight.info {border-left-color: var(--forest);}
.lr-tagbox {display: inline-block; font-family: var(--mono); font-size: 10.5px; padding: 1px 6px; border-radius: 4px;
            margin-right: 6px; border: 1px solid var(--line-strong); color: var(--muted); background: var(--cream);
            min-width: 84px; text-align: center;}
.lr-why {background: var(--cream); border-radius: var(--r-ctl); padding: 14px 16px; line-height: 1.55;}
.lr-why h4 {font-family: var(--mono); font-size: 11px; letter-spacing: .06em; margin: 12px 0 2px; color: var(--forest);
            text-transform: uppercase;}
.lr-why h4:first-child {margin-top: 0;}
.lr-why p {margin: 0 0 4px;}

/* tertiary buttons are text links (Back, reset) */
.stButton > button[kind="tertiary"] {border: none; background: none; padding-left: 0; padding-right: 0; color: var(--forest);
  font-weight: 700; min-height: 0;}
.stButton > button[kind="tertiary"]:hover {background: none; text-decoration: underline;}

/* product detail */
.lr-avatar-lg {flex-basis: 56px; height: 56px; font-size: 28px; border-radius: 14px;}
.lr-crumb {font-size: 12px; font-weight: 700; color: var(--muted); letter-spacing: .02em;}
[data-testid="stMarkdownContainer"] p.lr-title.lr-title-md {font-size: 26px;}
.lr-decision {font-size: 16px; font-weight: 700; color: var(--ink); margin: 12px 0 4px; line-height: 1.4;}
.lr-statgrid {display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; margin: 10px 0 6px;}
.lr-statgrid > div {background: var(--cream); border-radius: var(--r-ctl); padding: 8px 10px;}
.lr-statgrid span {display: block; font-size: 12px; color: var(--muted);}
.lr-statgrid b {display: block; font-size: 18px; font-weight: 800; color: var(--forest); font-variant-numeric: tabular-nums;}
.lr-statgrid b.bad {color: var(--risk);}
.lr-statgrid em {display: block; font-style: normal; font-size: 12px; color: var(--muted);}

/* product card (catalogue) */
.lr-pc {display: flex; gap: 12px; align-items: flex-start;}
.lr-avatar {flex: 0 0 40px; height: 40px; border-radius: 10px; background: var(--soft); display: flex; align-items: center;
            justify-content: center; font-size: 20px;}
.lr-pc .meta {font-size: 12px; color: var(--muted);}
.lr-pc .figs {font-size: 13px; color: var(--ink); margin-top: 6px;}

/* meters: stock cover, budget, sell-through */
.lr-meter {position: relative; height: 8px; background: var(--mist); border-radius: var(--r-pill); overflow: hidden; margin: 8px 0 4px;}
.lr-meter i {position: absolute; top: 0; bottom: 0; left: 0; background: var(--forest); border-radius: var(--r-pill);
             transform-origin: left center;}
.lr-meter i.risk {background: var(--risk);} .lr-meter i.warn {background: var(--amber);} .lr-meter i.lime {background: var(--lime);}
.lr-meter i.seg2 {background: var(--seg2);}
.lr-meter i.hatch {background: repeating-linear-gradient(-45deg, var(--hatch) 0 4px, var(--warn-bg) 4px 8px);}
.lr-meter b {position: absolute; top: -2px; bottom: -2px; width: 2px; background: var(--ink);}
.lr-meter-legend {display: flex; justify-content: space-between; gap: 8px; font-size: 12px; color: var(--muted); flex-wrap: wrap;}

.lr-cat {font-size: 12.5px; color: var(--ink); margin-top: 4px;}
.lr-cat i {font-style: italic; color: var(--muted); margin-left: 4px;}
.lr-cat b {color: var(--risk);}
/* run-out timeline (A) */
.lr-tl {position: relative; height: 34px; margin: 10px 0 2px;}
.lr-tl .track {position: absolute; left: 0; right: 0; top: 14px; height: 6px; background: var(--mist); border-radius: var(--r-pill);}
.lr-tl .stock {position: absolute; top: 14px; height: 6px; background: var(--forest); border-radius: var(--r-pill); left: 0;
               transform-origin: left center;}
.lr-tl .band {position: absolute; top: 10px; height: 14px; background: var(--risk-bg); border: 1px solid var(--risk);
              border-radius: var(--r-pill);}
.lr-tl .mark {position: absolute; top: 4px; bottom: 4px; width: 2px; background: var(--ink);}
.lr-tl-legend {display: flex; justify-content: space-between; font-size: 12px; color: var(--muted); gap: 8px; flex-wrap: wrap;}
.lr-tl-legend b {color: var(--ink);}

/* stepper (S) */
.lr-steps {display: grid; grid-template-columns: repeat(4, 1fr); gap: 6px; margin: 4px 0 12px; counter-reset: step;}
.lr-steps div {position: relative; padding: 10px 12px; border-radius: var(--r-ctl); background: var(--surface);
               border: 1px solid var(--line); font-size: 13px; color: var(--muted);
               transition: background var(--t-small) var(--ease), border-color var(--t-small) var(--ease);}
.lr-steps div b {display: block; font-size: 14px; color: var(--ink);}
.lr-steps div.done {background: var(--mist); border-color: var(--mist);}
.lr-steps div.done b::before {content: "✓ "; color: var(--forest);}
.lr-steps div.now {background: var(--lime); border-color: var(--lime); color: var(--deep);}
.lr-steps div.now b {color: var(--deep);}

/* WhatsApp-style draft preview (S) */
.lr-wa {border-radius: 14px; overflow: hidden; border: 1px solid var(--line); max-width: 460px; background: var(--wa-bg);}
.lr-wa .top {display: flex; align-items: center; gap: 10px; background: var(--wa-dark); color: var(--surface); padding: 10px 14px;
             font-size: 14px;}
.lr-wa .av {width: 30px; height: 30px; border-radius: 50%; background: var(--wa-bubble); color: var(--wa-dark); display: flex;
            align-items: center; justify-content: center; font-weight: 800;}
.lr-wa .chat {padding: 14px; display: flex; justify-content: flex-end;}
.lr-wa .bubble {background: var(--wa-bubble); color: var(--wa-ink); border-radius: 10px 0 10px 10px; padding: 8px 10px 4px; font-size: 13.5px;
                line-height: 1.45; max-width: 92%; box-shadow: 0 1px 1px rgba(0, 0, 0, .1);}
.lr-wa .meta {display: block; text-align: right; font-size: 11px; color: var(--wa-meta); margin-top: 2px;}

/* prediction and decision signatures */
.lr-ai {display: inline-flex; align-items: center; gap: 5px; padding: 2px 9px; border-radius: var(--r-pill); font-size: 11px;
        font-weight: 800; letter-spacing: .05em; background: linear-gradient(90deg, var(--forest), #2B6B52); color: var(--lime);
        margin-right: 6px; vertical-align: 1px;}
.lr-decides {display: inline-flex; align-items: center; gap: 5px; padding: 2px 9px; border-radius: var(--r-pill);
             font-size: 11px; font-weight: 800; letter-spacing: .05em; background: var(--lime); color: var(--deep);
             margin-right: 6px; vertical-align: 1px;}
.lr-spark {display: block; max-width: 100%; height: auto;}
.lr-stage {display: flex; align-items: baseline; gap: 12px; margin: 40px 0 10px; flex-wrap: wrap;}
.lr-stage .no {display: inline-flex; align-items: center; justify-content: center; width: 30px; height: 30px; border-radius: 50%;
               background: var(--forest); color: var(--lime); font-weight: 800; font-size: 15px; align-self: center;}
.lr-stage .t {font-size: 22px; font-weight: 800; color: var(--forest); letter-spacing: -.02em;}
.lr-stage .sub {font-size: 13.5px; color: var(--muted);}
.lr-range {font-size: 26px; font-weight: 800; color: var(--forest); font-variant-numeric: tabular-nums; line-height: 1.1;}
.lr-range small {font-size: 12.5px; font-weight: 600; color: var(--muted); margin-left: 4px;}
.lr-predrow {display: grid; grid-template-columns: 1fr auto; gap: 4px 14px; align-items: center; padding: 10px 0;
             border-top: 1px solid var(--line);}
.lr-predrow:first-child {border-top: none;}
.lr-predrow .what {font-size: 13.5px; color: var(--ink);}
.lr-predrow .what b {font-weight: 800;}
.lr-predrow .when {font-size: 12.5px; color: var(--risk); font-weight: 700;}
.lr-predrow .when.waste {color: var(--warn);}
[class*="st-key-decide_"] {background: var(--surface); border-left: 4px solid var(--lime) !important;}

/* forecast heat table (L) */
.lr-heatwrap {overflow-x: auto; border-radius: var(--r-card);}
.lr-heat {width: 100%; border-collapse: separate; border-spacing: 2px; font-size: 13px; font-variant-numeric: tabular-nums;}
.lr-heat th {font-weight: 700; color: var(--muted); font-size: 11.5px; text-align: center; padding: 4px 6px; white-space: nowrap;}
.lr-heat tbody th {text-align: left; color: var(--ink); font-size: 13px; font-weight: 700; white-space: nowrap; padding-right: 10px;}
.lr-heat tbody th .must {font-size: 10px; font-weight: 800; color: var(--forest); border: 1px solid var(--forest);
                         border-radius: var(--r-pill); padding: 0 5px; margin-left: 4px;}
.lr-heat td {text-align: center; padding: 6px 4px; border-radius: 6px; min-width: 38px;}
.lr-heat td.tot {background: var(--mist); font-weight: 800; color: var(--forest); min-width: 70px;}
.lr-heat td.chg {font-weight: 700; color: var(--muted);}
.lr-heat td.chg.up {color: var(--forest);} .lr-heat td.chg.down {color: var(--risk);}
.lr-heat tr.sel th {color: var(--forest);}
.lr-heat tr.sel td.tot {background: var(--lime); color: var(--deep);}
.lr-drivers {display: grid; gap: 6px; margin-top: 6px;}
.lr-drv {display: grid; grid-template-columns: 130px 1fr 90px; gap: 8px; align-items: center; font-size: 13px;}
.lr-drv i {display: block; height: 10px; border-radius: var(--r-pill); background: var(--forest);}
.lr-drv i.down {background: var(--risk);}
.lr-drv b {text-align: right; font-variant-numeric: tabular-nums;}

/* empty state and skeleton */
.lr-empty {text-align: center; padding: 26px 16px; background: var(--surface); border: 1px dashed var(--line-strong);
           border-radius: var(--r-card); color: var(--muted);}
.lr-empty .ic {font-size: 26px; line-height: 1;}
.lr-empty b {display: block; color: var(--ink); font-size: 15px; margin: 6px 0 2px;}
.lr-skel {display: block; height: 12px; border-radius: 6px; background: var(--mist); margin: 8px 0;}
.lr-skel.w60 {width: 60%;} .lr-skel.w80 {width: 80%;} .lr-skel.w40 {width: 40%;}

/* chat */
[data-testid="stChatMessage"] {background: transparent; padding: 6px 0;}
[data-testid="stChatInput"] textarea {font-size: 14px;}
[class*="st-key-sugg_"] button {border-radius: 12px; font-weight: 600; font-size: 13px; padding: 4px 12px;
                                min-height: 0; background: var(--soft); border-color: var(--line);}

/* ---------- counters (integer counts only; the real number is also in an .lr-sr span) ---------- */
@property --lr-n {syntax: '<integer>'; inherits: false; initial-value: 0;}
.lr-num {--lr-n: var(--to); counter-reset: lrn var(--lr-n);}
.lr-num::after {content: counter(lrn);}

/* ---------- motion: everything that moves lives here ---------- */
@media (prefers-reduced-motion: no-preference) {
  .stButton > button:active, .stLinkButton a:active, [data-testid="stButtonGroup"] button:active {transform: scale(.98);}
  [class*="st-key-card_"]:hover, .lr-card.hover:hover {transform: translateY(-1px);}
  .lr-in {animation: lr-in var(--t-enter) var(--ease) both;}
  .lr-grow {animation: lr-grow 420ms var(--ease) both;}
  .lr-num.lr-run {animation: lr-count 520ms var(--ease) both;}
  .lr-pop {animation: lr-pop var(--t-small) var(--ease) both;}
  .lr-pulse {animation: lr-pulse 600ms var(--ease) 2;}
  [data-testid="stStatusWidget"] {animation: lr-loading 1.1s linear infinite;}
  .lr-skel {background: linear-gradient(90deg, var(--mist) 25%, var(--shimmer) 50%, var(--mist) 75%); background-size: 200% 100%;
            animation: lr-shimmer 1.2s linear infinite;}
}
@keyframes lr-in {from {opacity: 0; transform: translateY(6px);} to {opacity: 1; transform: none;}}
@keyframes lr-grow {from {transform: scaleX(0);} to {transform: scaleX(1);}}
@keyframes lr-count {from {--lr-n: var(--from);} to {--lr-n: var(--to);}}
@keyframes lr-pop {from {opacity: 0; transform: translateY(3px);} to {opacity: 1; transform: none;}}
@keyframes lr-pulse {0% {box-shadow: 0 0 0 0 rgba(160, 74, 42, .45);} 100% {box-shadow: 0 0 0 10px rgba(160, 74, 42, 0);}}
@keyframes lr-shimmer {from {background-position: 200% 0;} to {background-position: -200% 0;}}

/* ---------- responsive ---------- */
@media (max-width: 1024px) {
  .lr-hero .big {font-size: 34px;}
}
@media (max-width: 640px) {
  .block-container {padding-left: 1rem; padding-right: 1rem; padding-top: 4.6rem;}
  .st-key-hero_box {padding: 22px 20px;}
  [data-testid="stMarkdownContainer"] p.lr-title {font-size: 24px;}
  .lr-hero {padding: 18px 18px;}
  .lr-hero .big {font-size: 30px; text-align: left;}
  .lr-hero .stats > div {border-left: none; padding-left: 0;}
  .lr-steps {grid-template-columns: repeat(2, 1fr);}
  /* the five letters stay in one compact row; names stay in the accessible label and the header below */
  .st-key-letters [data-testid="stHorizontalBlock"] {flex-wrap: nowrap !important; gap: 6px !important;}
  .st-key-letters [data-testid="stColumn"] {min-width: 0 !important; width: auto !important; flex: 1 1 0 !important;}
  [class*="st-key-letter_"] button {height: 56px; padding: 0;}
  [class*="st-key-letter_"] button p {font-size: 0;}
  [class*="st-key-letter_"] button strong {font-size: 22px;}
  /* KPI rows become a 2 x 2 grid instead of a tall stack */
  [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] .lr-kpi) {flex-direction: row !important;
    flex-wrap: wrap !important; column-gap: 8px !important; row-gap: calc(8px + 1rem) !important;}
  [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] .lr-kpi) > [data-testid="stColumn"]
    {flex: 1 1 calc(50% - 8px) !important; min-width: calc(50% - 8px) !important; width: auto !important;}
  .lr-kpi {padding: 10px 12px;}
  .lr-kpi .v {font-size: 20px;}
}
</style>
"""


def plural(n, word):
    """'1 product', '5 products'."""
    return f"{word}" if int(n) == 1 else f"{word}s"


MOTION_RULES = """  .stButton > button:active, .stLinkButton a:active, [data-testid="stButtonGroup"] button:active {transform: scale(.98);}
  [class*="st-key-card_"]:hover, .lr-card.hover:hover {transform: translateY(-1px);}
  .lr-in {animation: lr-in var(--t-enter) var(--ease) both;}
  .lr-grow {animation: lr-grow 420ms var(--ease) both;}
  .lr-num.lr-run {animation: lr-count 520ms var(--ease) both;}
  .lr-pop {animation: lr-pop var(--t-small) var(--ease) both;}
  .lr-pulse {animation: lr-pulse 600ms var(--ease) 2;}
  [data-testid="stStatusWidget"] {animation: lr-loading 1.1s linear infinite;}
  .lr-skel {background: linear-gradient(90deg, var(--mist) 25%, var(--shimmer) 50%, var(--mist) 75%); background-size: 200% 100%;
            animation: lr-shimmer 1.2s linear infinite;
"""


def motion_forced():
    """True when the owner chose 'Animations: always on' (Settings), e.g. on a demo laptop whose system setting asks
    for reduced motion. The default follows the system setting."""
    return st.session_state.get("motion") == "always"


def force_motion_css():
    """The motion rules without the reduced-motion guard, for 'always on'."""
    return f"<style>{MOTION_RULES}</style>"


def money(x, dp=0):
    return "RM –" if x is None or pd.isna(x) else f"RM {x:,.{dp}f}"


# ---------------- chips and labels ----------------
STATUS_ICON = {"URGENT": "⚠", "WARNING": "◔", "SOON": "◔", "MONITOR": "◷", "INFO": "ⓘ", "OK": "✓", "EXPIRY": "⌛",
               "EXCESS": "▣", "MUTED": "🔕", "HANDLED": "✓", "NEW": "●"}


def chip(text, cls, icon=None):
    ic = f'<span class="i" aria-hidden="true">{escape(icon)}</span>' if icon else ""
    return f'<span class="lr-chip {cls}">{ic}{escape(str(text))}</span>'


def action_chip(action):
    return chip(planning.ACTION_LABEL[action], f"lr-a-{action.lower()}")


def status_chip(level):
    key = str(level).upper()
    return chip(level, f"lr-s-{str(level).lower().replace(' ', '-')}", STATUS_ICON.get(key))


def must_chip(must):
    return chip("Must-have", "lr-must") if must else ""


def label(text, kind):
    """Provenance badge: measured / estimated / simulated / placeholder / planned / model / baseline / unavailable."""
    return f'<span class="lr-label lr-{kind}">{escape(text)}</span>'


def source_label(source, is_mock=False):
    """Where a forecast comes from, as a badge."""
    text = {"model": "AI MODEL FORECAST", "baseline": "BASELINE · LAST WEEK'S SALES",
            "unavailable": "NO FORECAST"}.get(source, str(source).upper())
    return label(text, source)


# ---------------- figures that remember their last value (counters and change chips) ----------------
def _prev():
    return st.session_state.setdefault("_ui_prev", {})


def track(key, value):
    """Remember a figure across reruns. Returns (previous value or None on first sight, changed?)."""
    store = _prev()
    prev = store.get(key)
    store[key] = value
    try:
        changed = prev is not None and abs(float(value) - float(prev)) > 1e-9
    except (TypeError, ValueError):
        changed = prev is not None and prev != value
    return prev, changed


def count(value, key):
    """An integer count that counts up on first sight and from the old value when it changes (CSS only).
    The real number is always present as text for screen readers and tests."""
    v = int(round(float(value)))
    prev, changed = track(f"n:{key}", v)
    run = prev is None or changed
    start = 0 if prev is None else int(prev)
    return (f'<span class="lr-num{" lr-run" if run else ""}" style="--from:{start};--to:{v}" aria-hidden="true">'
            f'</span><span class="lr-sr">{v:,}</span>')


def delta_chip(key, value, fmt=lambda x: money(x)):
    """'▲ RM 40' beside a figure after it changes, kept until it changes again. Empty on first sight."""
    prev, changed = track(f"d:{key}", value)
    last = st.session_state.setdefault("_ui_delta", {})
    if changed:
        last[key] = (float(value) - float(prev), float(value))
    d = last.get(key)
    if not d or abs(d[1] - float(value)) > 1e-9 or abs(d[0]) < 0.5:
        return ""
    up = d[0] > 0
    return (f'<span class="lr-delta {"up" if up else "down"}{" lr-pop" if changed else ""}" '
            f'title="Change since your last edit">{"▲" if up else "▼"} {escape(fmt(abs(d[0])))}</span>')


# ---------------- entrance motion, once per page or tool per session ----------------
def safe_key(text):
    """A widget/container key that is also a valid CSS class fragment (product ids can hold spaces and slashes)."""
    return re.sub(r"[^A-Za-z0-9_-]", "_", str(text))


def first_view(scope):
    """True the first time a page or tool is drawn in this session (entrance animations play only then)."""
    seen = st.session_state.setdefault("_ui_seen", set())
    if scope in seen:
        return False
    seen.add(scope)
    return True


def enter(keys, anim, pulse=()):
    """Staggered entrance for keyed containers (st.container(key=...)), emitted as a style block; `pulse` keys get
    two attention pulses (newly urgent items). Always emits a block (empty when nothing moves) so the element tree
    keeps the same shape across reruns."""
    rules = "".join(f".st-key-{k}{{animation: lr-in var(--t-enter) var(--ease) {i * 40}ms both;}}"
                    for i, k in enumerate(list(keys)[:6])) if anim else ""
    rules += "".join(f".st-key-{k}{{animation: lr-pulse 600ms var(--ease) 2;}}" for k in pulse)
    wrap = "{rules}" if motion_forced() else "@media (prefers-reduced-motion: no-preference){{{rules}}}"
    st.markdown("<style>" + wrap.format(rules=rules) + "</style>", unsafe_allow_html=True)


def newly(key, items):
    """Items in `items` that weren't there on the previous run (empty on first sight, so nothing pulses on load)."""
    prev, _ = track(f"set:{key}", sorted(items))
    return set() if prev is None else set(items) - set(prev)


def flash(msg):
    """Queue a toast for the next run (app.py shows it). Callers use it only after their state change succeeded."""
    st.session_state.setdefault("flash", []).append(msg)


# ---------------- building blocks ----------------
def kpi(k, v, s="", tone=None, count_value=None, key=None, extra=""):
    """KPI tile. tone: None / 'bad' / 'warn' / 'good'. count_value + key: animate an integer count (v is its unit,
    e.g. ' products', made singular for 1)."""
    if count_value is not None and key:
        unit = v[:-1] if int(round(float(count_value))) == 1 and v.endswith("s") else v
        val = count(count_value, key) + escape(unit)
    else:
        val = escape(v)
    cls = f" {tone}" if tone in ("bad", "warn") else ""
    return (f'<div class="lr-card lr-kpi"><div class="k">{escape(k)}</div><div class="v{cls}">{val}{extra}</div>'
            f'<div class="s {tone or ""}">{escape(s)}</div></div>')


def page_header(eyebrow, title, subtitle, mark=None):
    """mark: a phrase inside title to underline in lime (the one key fact on the page)."""
    top = f'<div class="lr-eyebrow">{escape(eyebrow)}</div>' if eyebrow else ""
    sub = f'<p class="lr-sub">{escape(subtitle)}</p>' if subtitle else ""
    t = escape(title)
    if mark and escape(mark) in t:
        t = t.replace(escape(mark), f"<mark>{escape(mark)}</mark>", 1)
    return f'{top}<p class="lr-title">{t}</p>{sub}'


def section(title, helptext=None):
    st.markdown(f'<div class="lr-section">{escape(title)}</div>'
                + (f'<p class="lr-help">{escape(helptext)}</p>' if helptext else ""), unsafe_allow_html=True)


def evidence(pairs):
    return "<br>".join(f'<span class="lr-tagbox">{escape(t)}</span>{escape(x)}' for t, x in pairs)


def empty(icon, title, hint=""):
    return (f'<div class="lr-empty"><div class="ic" aria-hidden="true">{escape(icon)}</div><b>{escape(title)}</b>'
            f'{escape(hint)}</div>')


def skeleton():
    return ('<div aria-label="Loading" role="status"><span class="lr-skel w80"></span><span class="lr-skel w60"></span>'
            '<span class="lr-skel w40"></span></div>')


def meter(frac, text, tone="", marker=None, anim=False, legend=None):
    """A thin bar with a text alternative. frac/marker: 0..1. legend: (left text, right text)."""
    f = max(0.0, min(1.0, float(frac))) if pd.notna(frac) else 0.0
    mk = f'<b style="left:calc({max(0, min(1, marker)) * 100:.1f}% - 1px)"></b>' if marker is not None else ""
    leg = (f'<div class="lr-meter-legend"><span>{escape(legend[0])}</span><span>{escape(legend[1])}</span></div>'
           if legend else "")
    return (f'<div class="lr-meter" role="img" aria-label="{escape(text)}"><i class="{tone}{" lr-grow" if anim else ""}" '
            f'style="width:{f * 100:.1f}%"></i>{mk}</div>{leg}')


def segments(parts, total, text, marker=None, anim=False):
    """A bar made of consecutive segments: parts = [(value, css class)], scaled to `total`."""
    total = max(float(total), 1e-9)
    x, html = 0.0, ""
    for v, cls in parts:
        w = max(0.0, float(v)) / total * 100
        html += (f'<i class="{cls}{" lr-grow" if anim else ""}" style="left:{min(x, 100):.1f}%;'
                 f'width:{max(0.0, min(w, 100 - x)):.1f}%"></i>')
        x += w
    mk = f'<b style="left:calc({max(0, min(1, marker)) * 100:.1f}% - 1px)"></b>' if marker is not None else ""
    return f'<div class="lr-meter" style="height:12px" role="img" aria-label="{escape(text)}">{html}{mk}</div>'


def timeline(cover, lo, hi, lead, horizon, anim=False):
    """A: today -> stock lasts (bar) -> likely run-out range (band) -> delivery if ordered today (marker), in days."""
    h = max(float(horizon), 1.0)
    pos = lambda d: max(0.0, min(1.0, float(d) / h)) * 100 if pd.notna(d) and d != float("inf") else 100.0
    band = (f'<div class="band" style="left:{pos(lo):.1f}%;width:{max(1.5, pos(hi) - pos(lo)):.1f}%"></div>'
            if pd.notna(lo) and lo != float("inf") else "")
    text = (f"Stock lasts about {cover:.1f} days; delivery in {lead} days" if pd.notna(cover) and cover != float("inf")
            else f"No sales expected; delivery in {lead} days")
    return (f'<div class="lr-tl" role="img" aria-label="{escape(text)}"><div class="track"></div>'
            f'<div class="stock{" lr-grow" if anim else ""}" style="width:{pos(cover):.1f}%"></div>{band}'
            f'<div class="mark" style="left:calc({pos(lead):.1f}% - 1px)"></div></div>')


def stepper(steps, current):
    """S: steps = list of (title, note); current = index of the step in progress (len(steps) = all done)."""
    cells = "".join(f'<div class="{"done" if i < current else "now" if i == current else ""}">'
                    f'<b>{escape(t)}</b>{escape(n)}</div>' for i, (t, n) in enumerate(steps))
    return f'<div class="lr-steps" role="list" aria-label="Order progress">{cells}</div>'


def whatsapp_preview(message, to, phone=""):
    """The supplier message as a WhatsApp-style draft (a picture of the draft, not a sent message)."""
    lines = "<br>".join(escape(x) for x in str(message).splitlines())
    who = escape(to) + (f" · +{escape(phone)}" if phone else "")
    return (f'<div class="lr-wa" role="img" aria-label="Draft WhatsApp message to {escape(to)}, not sent">'
            f'<div class="top"><span class="av">{escape(str(to)[:1].upper() or "S")}</span><b>{who}</b></div>'
            f'<div class="chat"><div class="bubble">{lines}<span class="meta">Draft · not sent</span></div></div></div>')


# ---------------- products: display-only category and avatar ----------------
CATEGORIES = ["Fresh Ingredients", "Dairy & Beverages", "Snacks & Confectionery", "Pantry & Groceries", "Personal Care",
              "Healthcare", "Household & Daily Essentials", "Other"]
FAMILY_CATEGORY = {  # display grouping for the sample shop's data families (no effect on any calculation)
    "GROCERY I": "Pantry & Groceries", "BEVERAGES": "Dairy & Beverages", "DAIRY": "Dairy & Beverages",
    "BREAD/BAKERY": "Fresh Ingredients", "EGGS": "Fresh Ingredients", "POULTRY": "Fresh Ingredients",
    "PRODUCE": "Fresh Ingredients", "MEATS": "Fresh Ingredients", "FROZEN FOODS": "Fresh Ingredients",
    "DELI": "Fresh Ingredients", "CLEANING": "Household & Daily Essentials", "PERSONAL CARE": "Personal Care",
}


def split_name(name):
    """('🥛', 'Fresh milk 1L') from '🥛 Fresh milk 1L'; a product without a leading emoji gets a box."""
    s = str(name).strip()
    head, _, rest = s.partition(" ")
    if head and rest and not any(ch.isalnum() for ch in head):
        return head, rest
    return "📦", s


def category_of(product, inputs=None):
    """A product's category: the 'Category' column when the product list has one, else the sample family's group."""
    if inputs is not None and "Category" in inputs:
        c = inputs.loc[inputs["product"] == product, "Category"]
        if len(c) and isinstance(c.iloc[0], str) and c.iloc[0]:
            return c.iloc[0]
    return FAMILY_CATEGORY.get(product, "Other")


def choice(label, options, key, default=None, format_func=str, where=None, keep=False, help=None):
    """A single choice drawn as a row of pills (a horizontal radio styled by CSS: keyboard-friendly, always has a
    value). keep=True makes the choice survive tool switches (like sticky)."""
    ss, opts = st.session_state, list(options)
    default = default if default in opts else opts[0]
    if keep:
        kw = sticky(key, default)
        if ss.get(key) not in opts:
            ss[key] = default
        idx = {}
    else:
        kw = {"key": key}
        if key in ss and ss[key] not in opts:
            del ss[key]
        idx = {} if key in ss else {"index": opts.index(default)}
    with (where or st).container(key=f"seg_{safe_key(key)}"):
        return st.radio(label, opts, format_func=format_func, horizontal=True, label_visibility="collapsed",
                        help=help, **idx, **kw)


def match(df, query="", cats=(), inputs=None):
    """Rows of df (columns: product, name) whose name, product id or brand contains `query` (case-insensitive) and
    whose category is in `cats` (empty = all). Pure, so it can be tested without Streamlit."""
    if df is None or not len(df):
        return df
    out = df
    q = str(query or "").strip().lower()
    if q:
        brand = {}
        if inputs is not None and "Brand" in inputs:
            brand = dict(zip(inputs["product"], inputs["Brand"].fillna("").astype(str)))
        hay = (out["name"].astype(str) + " " + out["product"].astype(str) + " "
               + out["product"].map(brand).fillna("")).str.lower()
        out = out[hay.str.contains(q, regex=False)]
    if cats:
        out = out[out["product"].map(lambda p: category_of(p, inputs)).isin(set(cats))]
    return out


def filter_bar(prefix, ctx, placeholder="Search by name, brand or SKU"):
    """Search box + category pills (only categories present in the shop). Returns a function that filters a frame
    with product/name columns. Selections survive tool switches."""
    inputs = ctx.get("inputs")
    present = {category_of(p, inputs) for p in ctx["plan"]["product"]}
    cats = [c for c in CATEGORIES if c in present]
    a, b = st.columns([1.4, 3], vertical_alignment="center")
    q = a.text_input("Search products", placeholder=placeholder, label_visibility="collapsed", **sticky(f"{prefix}_q", ""))
    with b:
        chosen = st.pills("Category", cats, selection_mode="multi", label_visibility="collapsed",
                          **sticky(f"{prefix}_cat", [])) or []
    chosen = [c for c in chosen if c in cats]
    return lambda frame: match(frame, q, chosen, inputs)


def require_plan(ctx):
    """Every planning page needs at least one product."""
    if ctx["empty"]:
        st.markdown(empty("🧺", "No products yet", "Add them in Products, then LARIS can plan your order."),
                    unsafe_allow_html=True)
        st.page_link("views/products.py", label="Go to Products", icon=":material/inventory_2:")
        st.stop()


# ---------------- state that survives page and tool switches ----------------
def sticky(key, default=None):
    """Widget kwargs whose value survives the widget being off-screen (Streamlit drops widget state when a widget
    isn't drawn, e.g. after switching LARIS tools). Usage: st.text_input("Search", **ui.sticky("lu_q", ""))."""
    ss, keep = st.session_state, f"_keep_{key}"
    if key not in ss:
        ss[key] = ss.get(keep, default)
    return {"key": key, "on_change": lambda: ss.__setitem__(keep, ss[key])}


def bind(widget_key, state_key, on_change=None):
    """Widget kwargs for a widget that edits a plain session value (state_key) shared across pages."""
    ss = st.session_state
    ss[widget_key] = ss.get(state_key)

    def _sync():
        ss[state_key] = ss[widget_key]
        if on_change:
            on_change()
    return {"key": widget_key, "on_change": _sync}


# ---------------- navigation and order helpers (callbacks; app.py performs page switches) ----------------
def _open(product, back):
    st.session_state.update(sel=product, back_to=back, goto="views/product.py")


def why_button(product, back, key, label="Why?"):
    st.button(label, key=key, on_click=_open, args=(product, back), width="stretch")


def goto(path):
    st.session_state["goto"] = path


def open_tool(letter):
    """Jump to a LARIS tool from anywhere (Home, assistant links)."""
    st.session_state.update(tool=letter, goto="views/laris.py")


def tool_button(letter, label, key, primary=False):
    st.button(label, key=key, on_click=open_tool, args=(letter,), width="stretch",
              type="primary" if primary else "secondary")


def set_qty_value(product, qty):
    """Owner's quantity override for the shared order; the recommendation itself is kept."""
    st.session_state.setdefault("order_adj", {})[product] = float(qty)


def set_qty_from(product, key):
    set_qty_value(product, st.session_state[key])


def clear_qty(product):
    st.session_state.setdefault("order_adj", {}).pop(product, None)


# ---------------- hero panel ----------------
def hero_stats(stats):
    """The stat cells of the hero panel: (label, value, note, tone); value may be ('html', s)."""
    cell = lambda v: v[1] if isinstance(v, tuple) and v[0] == "html" else escape(v)
    return "".join(f'<div><span>{escape(k)}</span><b class="{tone or ""}">{cell(v)}</b><em>{escape(n)}</em></div>'
                   for k, v, n, tone in stats)


def hero(eyebrow, lead, big, big_note, fill=None, marker=None, legend="", stats=(), anim=False, extra=""):
    """The deep-green panel. fill/marker: 0..1 positions on the bar (e.g. order vs budget). stats: (label, value,
    note, tone) with tone in {None, 'lime', 'risk'}; a value may be pre-rendered HTML when passed as ('html', s).
    All plain text is escaped. extra: pre-rendered HTML placed after the big figure (e.g. a change chip)."""
    bar = ""
    if fill is not None:
        bar = meter(fill, legend or "Order vs budget", marker=marker, anim=anim) + f'<div class="legend">{escape(legend)}</div>'
    cells = hero_stats(stats)
    return (f'<div class="lr-hero{" lr-in" if anim else ""}"><div class="top"><div><div class="eyebrow">{escape(eyebrow)}'
            f'</div><div class="lead">{escape(lead)}</div></div><div class="big">{escape(big)}{extra}<small>'
            f'{escape(big_note)}</small></div></div>{bar}<div class="stats">{cells}</div></div>')


# ---------------- prediction and decision signatures ----------------
def series(ctx, product, days=28):
    """Recorded daily sales (last `days` days, scaled to the shop) and the 7-day forecast with its ~90% range: the same
    numbers forecast_chart draws. Returns (history list, forecast list, low list, high list)."""
    r, week = ctx["rows"].set_index("product").loc[product], ctx["week"]
    fc = [float(x) for x in planning.daily_forecast(ctx, product)]
    hist = []
    if r["forecast_source"] == "model":
        sub = week["sub"]
        h = sub[(sub["product"] == product) & (sub["date"] >= week["as_of"] - pd.Timedelta(days=days))
                & (sub["date"] < week["as_of"])].sort_values("date")
        hist = [float(x) * ctx["scale"] * float(r["ratio"]) for x in h["y"].fillna(0)]
    band = Z90 * float(r["sigma"]) if r["forecast_source"] != "unavailable" else 0.0
    return hist, fc, [max(0.0, x - band) for x in fc], [x + band for x in fc]


def forecast_range(ctx, product):
    """'27–35' style 7-day forecast range (from the measured error), or None."""
    r = ctx["rows"].set_index("product").loc[product]
    if r["forecast_source"] == "unavailable":
        return None
    fc7, b = float(r["demand_7d"]), float(r["band_pct"]) if pd.notna(r["band_pct"]) else 0.0
    if not (b < 5):
        return f"{fc7:,.0f}"
    lo, hi = max(0.0, fc7 * (1 - b)), fc7 * (1 + b)
    return f"{lo:,.0f}–{hi:,.0f}"


def sparkline(hist, fc, lo, hi, width=180, height=44, label=""):
    """A tiny inline SVG: recorded sales in grey, the forecast as a dashed green line with its range shaded, and a
    marker at 'today'. Drawn in Python, no dependency."""
    pts = list(hist) + list(fc)
    top = max([*pts, *hi, 1e-9])
    n = max(len(pts) - 1, 1)
    x = lambda i: 2 + (width - 4) * i / n
    y = lambda v: height - 3 - (height - 6) * (float(v) / top)
    h0 = len(hist)
    path = lambda vals, start: " ".join(f"{'M' if k == 0 else 'L'}{x(start + k):.1f},{y(v):.1f}" for k, v in enumerate(vals))
    band = ""
    if fc:
        up = [f"{x(h0 + k):.1f},{y(v):.1f}" for k, v in enumerate(hi)]
        down = [f"{x(h0 + k):.1f},{y(v):.1f}" for k, v in reversed(list(enumerate(lo)))]
        band = f'<polygon points="{" ".join(up + down)}" fill="#174D3A" fill-opacity=".14"/>'
    hist_line = (f'<path d="{path(hist, 0)}" fill="none" stroke="#9AA397" stroke-width="1.5" stroke-linejoin="round"/>'
                 if len(hist) > 1 else "")
    joined = ([hist[-1]] if hist else []) + list(fc)
    fc_line = (f'<path d="{path(joined, h0 - (1 if hist else 0))}" fill="none" stroke="#174D3A" stroke-width="2" '
               f'stroke-dasharray="4 3" stroke-linejoin="round"/>' if len(joined) > 1 else "")
    today = f'<line x1="{x(h0):.1f}" x2="{x(h0):.1f}" y1="2" y2="{height - 2}" stroke="#C9D1C6" stroke-width="1"/>' if hist else ""
    return (f'<svg class="lr-spark" viewBox="0 0 {width} {height}" width="{width}" height="{height}" role="img" '
            f'aria-label="{escape(label or "Recorded sales and 7-day forecast")}">{today}{band}{hist_line}{fc_line}</svg>')


def product_spark(ctx, product, width=180, height=44):
    hist, fc, lo, hi = series(ctx, product)
    name = split_name(ctx["plan"].set_index("product").at[product, "name"])[1]
    rng = forecast_range(ctx, product)
    return sparkline(hist, fc, lo, hi, width, height,
                     f"{name}: last 28 days of sales and the 7-day forecast" + (f" ({rng} units)" if rng else ""))


def prediction_badge(text="AI FORECAST"):
    return f'<span class="lr-ai"><span aria-hidden="true">✦</span> {escape(text)}</span>'


def decision_badge(text="LARIS DECIDES"):
    return f'<span class="lr-decides"><span aria-hidden="true">◆</span> {escape(text)}</span>'


def stage(n, title, subtitle=""):
    """A numbered stage heading: 1 · LARIS predicts, 2 · LARIS decides, 3 · You act."""
    sub = f'<span class="sub">{escape(subtitle)}</span>' if subtitle else ""
    st.markdown(f'<div class="lr-stage"><span class="no">{int(n)}</span><span class="t">{escape(title)}</span>{sub}</div>',
                unsafe_allow_html=True)


def heat_table(grid, day_cols, ctx, selected=None):
    """The 7-day forecast as a heat map: each cell's shade is that day's units relative to the product's busiest day,
    so the shape of the week stands out. Values are always printed (never colour alone)."""
    head = "".join(f"<th>{escape(c)}</th>" for c in day_cols)
    body = []
    for r in grid.itertuples(index=False):
        vals = [r[2 + i] for i in range(len(day_cols))]   # day columns follow product, name
        top = max(vals + [1e-9])
        cells = "".join(f'<td style="background:rgba(23,77,58,{0.06 + 0.5 * v / top:.2f});'
                        f'color:{"#FFFFFF" if v / top > 0.72 else "var(--ink)"}">{v:,.0f}</td>' for v in vals)
        rng = forecast_range(ctx, r.product) or "–"
        ch = "–" if not r.last7 else f"{r.change:+.0%}"
        tone = "up" if r.change > 0.1 else "down" if r.change < -0.1 else ""
        must = ' <span class="must">must-have</span>' if r.must_have else ""
        sel = ' class="sel"' if r.product == selected else ""
        body.append(f'<tr{sel}><th scope="row">{escape(split_name(r.name)[1])}{must}</th>{cells}'
                    f'<td class="tot">{escape(rng)}</td><td class="chg {tone}">{escape(ch)}</td></tr>')
    return (f'<div class="lr-heatwrap"><table class="lr-heat"><caption class="lr-sr">Forecast units per day for the next '
            f'7 days</caption><thead><tr><th>Product</th>{head}<th>Next 7 days</th><th>vs last wk</th></tr></thead>'
            f'<tbody>{"".join(body)}</tbody></table></div>')


def drivers(ctx, product):
    """What the model says moved this week's forecast: the same model re-run without payday / holiday / promotion
    (rows.effects). HTML bars, or a note when nothing stands out."""
    r = ctx["rows"].set_index("product").loc[product]
    fx = r["effects"] if isinstance(r["effects"], dict) else {}
    names = {"payday": "Payday", "holiday": "Public holiday", "promo": "Planned promotion"}
    items = [(names.get(k, k), float(v)) for k, v in fx.items() if abs(float(v)) >= 0.5]
    if not items:
        return '<span class="lr-muted">No payday, holiday or promotion effect stands out this week.</span>'
    top = max(abs(v) for _, v in items)
    rows = "".join(f'<div class="lr-drv"><span>{escape(n)}</span><i style="width:{abs(v) / top * 100:.0f}%" '
                   f'class="{"up" if v > 0 else "down"}"></i><b>{v:+,.0f} units</b></div>' for n, v in items)
    return f'<div class="lr-drivers">{rows}</div>'


def allocation_chart(ctx):
    """How the budget is spent: one bar per product, the part in this week's order vs the part the budget cut,
    must-haves first. From plan.ideal / plan.qty (the optimiser's own numbers). None when nothing is needed."""
    need = ctx["plan"][ctx["plan"]["ideal"] > 0].copy()
    if need.empty:
        return None
    need["name_s"] = need["name"].map(lambda n: split_name(n)[1])
    need["funded"] = need["qty"] * need["unit_cost"]
    need["cut"] = (need["ideal"] - need["qty"]).clip(lower=0) * need["unit_cost"]
    need["group"] = need["must_have"].map({True: "Must-have", False: "Other"})
    long = need.melt(["name_s", "group", "must_have"], ["funded", "cut"], "part", "rm")
    long["part"] = long["part"].map({"funded": "In the order", "cut": "Cut by the budget"})
    order = list(need.sort_values(["must_have", "funded"], ascending=[False, False])["name_s"])
    chart = alt.Chart(long).mark_bar(cornerRadiusEnd=3).encode(
        y=alt.Y("name_s:N", sort=order, title=None, axis=alt.Axis(labelLimit=200, labelOverlap=False)),
        x=alt.X("sum(rm):Q", title="RM", stack="zero"),
        color=alt.Color("part:N", scale=alt.Scale(domain=["In the order", "Cut by the budget"], range=[GREEN, "#F2C79B"]),
                        legend=alt.Legend(orient="top", title=None)),
        tooltip=["name_s", "group", "part", alt.Tooltip("sum(rm):Q", format=",.0f", title="RM")])
    return chart.properties(height=max(220, 32 * len(need))).configure_view(strokeWidth=0)


# ---------------- forecast chart (Look Ahead, Product detail) ----------------
def range_note(ctx):
    cov = ctx["metrics"].get("band_coverage_90")
    note = ("Shaded band: approximate range (forecast ± 1.645 × the model's typical daily error on validation weeks), "
            "not a guaranteed interval.")
    if cov is not None:
        note += f" On held-out test weeks, {cov:.0%} of actual days fell inside a band built this way."
    return note


def actual_week(ctx, product):
    """What really sold in the planning week (a past week, so it's known), scaled the same way as the forecast (None when the product has no
    model history or the data has no actuals). Returns (daily actuals, actual 7-day total, forecast 7-day total)."""
    r, week = ctx["rows"].set_index("product").loc[product], ctx["week"]
    if r["forecast_source"] != "model" or product not in week["act_wide"]:
        return None
    act = week["act_wide"][product] * r["ratio"]
    if act.isna().all():
        return None
    fc = planning.daily_forecast(ctx, product)
    return act, float(act.sum(skipna=True)), float(fc.sum())


def reveal_note(ctx, product):
    """One line comparing the forecast with what really sold in the planning week (HTML), or an explanation."""
    got = actual_week(ctx, product)
    if got is None:
        return '<span class="lr-muted">No recorded sales to compare for this product (it has no model history).</span>'
    _, actual, forecast = got
    err = (forecast - actual) / actual if actual > 0 else None
    verdict = ("" if err is None else
               f" · forecast was {abs(err):.0%} {'high' if err > 0 else 'low'}" if abs(err) >= 0.005 else " · spot on")
    return (label("BACKTEST · ACTUAL SALES", "measured") + f'<span class="lr-muted">This week actually sold '
            f'<b>{actual:,.0f}</b> vs <b>{forecast:,.0f}</b> forecast{verdict}. Orange dashed line = what actually '
            "sold; the model had not seen these days.</span>")


def forecast_chart(ctx, product, height=260, reveal=False):
    r, week = ctx["rows"].set_index("product").loc[product], ctx["week"]
    source = r["forecast_source"]
    daily = planning.daily_forecast(ctx, product)
    if source == "model":
        sub = week["sub"]
        h = sub[(sub["product"] == product) & (sub["date"] >= week["as_of"] - pd.Timedelta(days=28))
                & (sub["date"] < week["as_of"])]
        hist = pd.DataFrame({"date": h["date"], "units": h["y"] * ctx["scale"] * r["ratio"], "series": "Recorded sales"})
    else:
        hist = pd.DataFrame({"date": pd.Series(dtype="datetime64[ns]"), "units": pd.Series(dtype=float),
                             "series": pd.Series(dtype=str)})
    fut = pd.DataFrame({"date": pd.date_range(week["as_of"], week["end"]), "units": daily, "series": "Forecast"})
    fut["lo"], fut["hi"] = (fut["units"] - Z90 * r["sigma"]).clip(lower=0), fut["units"] + Z90 * r["sigma"]
    color = alt.Color("series:N", scale=alt.Scale(domain=["Recorded sales", "Forecast"], range=["#9AA397", GREEN]),
                      legend=alt.Legend(orient="top", title=None))
    x = alt.X("date:T", title=None, axis=alt.Axis(format="%d %b", grid=False))
    layers = [alt.Chart(pd.concat([hist, fut[["date", "units", "series"]]])).mark_line(point=True).encode(
        x=x, y=alt.Y("units:Q", title="Units per day"), color=color,
        tooltip=[alt.Tooltip("date:T", format="%a %d %b"), alt.Tooltip("units:Q", format=",.1f"), "series"])]
    if source != "unavailable":
        layers.insert(0, alt.Chart(fut).mark_area(opacity=0.16, color=GREEN).encode(x=x, y="lo:Q", y2="hi:Q"))
    got = actual_week(ctx, product) if reveal else None
    if got is not None:
        act = pd.DataFrame({"date": got[0].index, "units": got[0].to_numpy(), "series": "What actually sold"})
        layers.append(alt.Chart(act).mark_line(point=alt.OverlayMarkDef(shape="diamond", size=70), strokeDash=[5, 3],
                                               color="#C2662D").encode(
            x=x, y="units:Q", tooltip=[alt.Tooltip("date:T", format="%a %d %b"), alt.Tooltip("units:Q", format=",.1f"),
                                       "series"]))
    note = {"model": range_note(ctx),
            "baseline": "No model forecast for this product: the forecast repeats last week's sales, so treat it as rough.",
            "unavailable": "Forecast unavailable: no sales history and nothing recorded as sold last week."}[source]
    return alt.layer(*layers).properties(height=height).configure_view(strokeWidth=0), note

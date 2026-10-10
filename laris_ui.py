"""LARIS look and feel: one design system plus small shared components, so every page looks and behaves the same.
Business numbers never come from here; they come from the shared context (laris_core) and planning.py.

Two modes share one set of rules (CSS variables): dark (deep green #0F2E24 ground, glass panels, cream text, lime
accents) and light (cream #F7F5EE ground, white glass panels, charcoal text, forest accents, lime primary buttons).
The owner's choice is saved in prefs["theme"]; .streamlit/config.toml holds the matching native palettes, which
theme_script() selects in the browser so tables and inputs follow the same mode.
"""
import json
import time
from html import escape
from math import ceil

import altair as alt
import pandas as pd
import streamlit as st

import planning
import store

Z90 = 1.645
ACTIONS = ("RESTOCK", "REDUCE", "STOP", "MAINTAIN")

VARS = {
    "dark": {
        "bg": "#0F2E24", "dot": "rgba(243,241,234,.16)", "fade": "rgba(15,46,36,.75)", "text": "#F3F1EA",
        "text2": "#D5E0D9", "muted": "#A9BFB3", "placeholder": "#93AE9F", "accent": "#C8E66E",
        "primary": "#C8E66E", "primary-fg": "#0F2E24", "primary-hover": "#E4F5A8",
        "glass": "rgba(11,36,28,.72)", "glass-border": "rgba(243,241,234,.1)", "shadow": "0 30px 80px rgba(0,0,0,.35)",
        "tile": "rgba(243,241,234,.05)", "row": "rgba(243,241,234,.04)", "line": "rgba(243,241,234,.1)",
        "hover": "rgba(243,241,234,.06)", "btn-border": "rgba(243,241,234,.25)", "header": "rgba(15,46,36,.72)",
        "nav": "#C9D6CE", "nav-active": "rgba(243,241,234,.1)", "neutral-bg": "rgba(243,241,234,.14)",
        "neutral-fg": "#F3F1EA", "soft-bg": "rgba(200,230,110,.14)", "soft-fg": "#DDEFA0", "risk": "#F2B49C",
        "warn": "#F6D58A", "good": "#C8E66E", "risk-row": "rgba(242,180,156,.1)", "warn-row": "rgba(246,231,194,.07)",
        "mock-bg": "rgba(242,170,150,.12)", "mock-border": "rgba(242,170,150,.3)", "mock-fg": "#F5C3B4",
        "ribbon": ".95"},
    "light": {
        "bg": "#F7F5EE", "dot": "rgba(23,77,58,.13)", "fade": "rgba(247,245,238,.7)", "text": "#252923",
        "text2": "#3E4A43", "muted": "#5C645D", "placeholder": "#7B857E", "accent": "#174D3A",
        "primary": "#C7ED72", "primary-fg": "#10382B", "primary-hover": "#B8E25A",
        "glass": "rgba(255,255,255,.8)", "glass-border": "rgba(23,77,58,.12)",
        "shadow": "0 18px 50px rgba(16,56,43,.10)", "tile": "rgba(23,77,58,.05)", "row": "rgba(23,77,58,.04)",
        "line": "rgba(23,77,58,.12)", "hover": "rgba(23,77,58,.06)", "btn-border": "rgba(23,77,58,.3)",
        "header": "rgba(247,245,238,.85)", "nav": "#3E4A43", "nav-active": "rgba(23,77,58,.1)",
        "neutral-bg": "rgba(23,77,58,.09)", "neutral-fg": "#174D3A", "soft-bg": "#E6F4BF", "soft-fg": "#174D3A",
        "risk": "#A04A2A", "warn": "#7A4A00", "good": "#2F6B1F", "risk-row": "rgba(160,74,42,.07)",
        "warn-row": "rgba(201,138,27,.08)", "mock-bg": "#FBE9E3", "mock-border": "#F0C3B4", "mock-fg": "#8A2E1E",
        "ribbon": ".5"},
}
# chart colours per mode (Altair draws on canvas/SVG, so it needs real colours, not CSS variables)
CHART = {"dark": {"line": "#C8E66E", "band": "#3FA37A", "hist": "#A9BFB3", "bar": "#3FA37A", "bar2": "#C8E66E",
                  "text": "#F3F1EA"},
         "light": {"line": "#174D3A", "band": "#3FA37A", "hist": "#8A938B", "bar": "#174D3A", "bar2": "#8DBF2F",
                   "text": "#252923"}}
LIME, LIME2, GLOW = "#C8E66E", "#E4F5A8", "#3FA37A"


def mode():
    return st.session_state.get("theme", "dark")


def chart_colors():
    return CHART[mode()]


RULES = """
html, body, .stApp, .stMarkdown, button, input, textarea, label, [data-testid="stWidgetLabel"] p
  {font-family: 'Manrope', sans-serif;}
[data-testid="stIconMaterial"], [data-testid="stIconMaterial"] * {font-family: 'Material Symbols Rounded' !important;}

/* ground: plain colour with a dot grid that fades toward the bottom */
html, body {background-color: var(--bg);
        background-image: linear-gradient(to bottom, transparent 0%, var(--fade) 100%),
                          radial-gradient(var(--dot) 1px, transparent 1.2px);
        background-size: 100% 100%, 22px 22px; background-attachment: fixed;}
.stApp {color: var(--text); background: transparent;}
[data-testid="stMain"] {overflow-x: clip;}
.block-container {padding-top: 4.9rem; padding-bottom: 2.5rem; max-width: 1240px;}

/* top nav: see-through over the page, pill for the active link */
header[data-testid="stHeader"] {background: var(--header); backdrop-filter: blur(14px);
                                border-bottom: 1px solid var(--line); height: 4rem;}
[data-testid="stTopNavLink"], [data-testid="stTopNavSection"] {border-radius: 999px; min-height: 44px; padding: 0 14px;}
[data-testid="stTopNavLink"] *, [data-testid="stTopNavSection"] * {color: var(--nav) !important;}
[data-testid="stTopNavLink"]:hover, [data-testid="stTopNavSection"]:hover {background: var(--hover);}
[data-testid="stTopNavLink"][aria-current="page"] {background: var(--nav-active);}
[data-testid="stTopNavLink"][aria-current="page"] * {color: var(--text) !important; font-weight: 700;}
[data-testid="stAppDeployButton"], [data-testid="stStatusWidget"] {display: none;}   /* LARIS shows its own */
[data-testid="stToolbarActions"] *, [data-testid="stMainMenu"] *, [data-testid="stBaseButton-header"]
  {color: var(--text) !important;}
[data-testid="stSidebarNavLink"], [data-baseweb="input"], [data-baseweb="select"] > div {min-height: 44px;}

/* top-right: shop pill + light/dark switch, pinned into the nav bar */
.st-key-topbar {position: fixed; top: 10px; right: 60px; z-index: 999991; width: auto !important;
                align-items: center; gap: 8px;}
.st-key-topbar [data-testid="stElementContainer"], .st-key-topbar .stMarkdown {margin: 0; width: auto;}
.st-key-topbar [data-testid="stMarkdownContainer"] {margin: 0;}
.lr-shoppill {display: flex; align-items: center; gap: 8px; min-height: 44px; padding: 0 8px 0 16px;
              border: 1px solid var(--glass-border); border-radius: 999px; font-size: 14px; color: var(--text);
              background: var(--glass); white-space: nowrap;}
.lr-shoppill .lr-badge {background: var(--soft-bg); color: var(--soft-fg); margin: 0;}
.st-key-theme_btn button {width: 44px; height: 44px; min-width: 44px; padding: 0; background: var(--glass);
                          border-color: var(--glass-border);}
.st-key-theme_btn button p {position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0);}

/* buttons: lime pill primary; outlined pill secondary; all 44px tall */
.stButton > button, .stLinkButton a, .stDownloadButton > button, .stFormSubmitButton > button,
[data-testid="stPopover"] button
  {min-height: 44px; border-radius: 999px; font-weight: 600; border: 1px solid var(--btn-border);
   background: transparent; color: var(--text); transition: border-color .12s, background .12s;}
.stButton > button:hover, .stLinkButton a:hover, [data-testid="stPopover"] button:hover,
.stDownloadButton > button:hover, .stFormSubmitButton > button:hover
  {border-color: var(--accent); color: var(--text); background: var(--hover);}
[data-testid^="stBaseButton-primary"], .stFormSubmitButton > button
  {background: var(--primary) !important; color: var(--primary-fg) !important; border: none !important;
   font-weight: 800;}
[data-testid^="stBaseButton-primary"] *, .stFormSubmitButton > button * {color: var(--primary-fg) !important;}
[data-testid^="stBaseButton-primary"]:hover, .stFormSubmitButton > button:hover
  {background: var(--primary-hover) !important;}

/* surfaces: glass panels (bordered containers, keyed glass_* containers), expanders, forms */
[data-testid="stVerticalBlockBorderWrapper"]:has(> div > [data-testid="stVerticalBlock"]),
[class*="st-key-glass_"]
  {background: var(--glass); backdrop-filter: blur(18px); border: 1px solid var(--glass-border);
   border-radius: 28px; box-shadow: var(--shadow);}
[class*="st-key-glass_"] {padding: 28px 32px;}
.st-key-glass_page {padding: 28px 32px 32px; margin-top: 6px;}
div[data-testid="stExpander"] details {background: var(--tile); border: 1px solid var(--glass-border);
                                       border-radius: 18px;}
div[data-testid="stExpander"] summary {min-height: 44px;}
div[data-testid="stExpander"] summary p {font-weight: 700; color: var(--text);}
[data-testid="stDataFrame"], [data-testid="stDataEditor"] {border: 1px solid var(--glass-border); border-radius: 14px;
                                                          overflow: hidden;}
[data-baseweb="input"], [data-baseweb="select"] > div, [data-baseweb="textarea"] {border-radius: 12px;}
[data-testid="stForm"] {border: 1px solid var(--glass-border); border-radius: 18px; background: var(--tile);}
[data-testid="stAlert"] {border-radius: 14px;}
hr {border-color: var(--line) !important;}

/* type */
.lr-eyebrow {color: var(--accent); font-size: 14px; font-weight: 700; letter-spacing: 0.16em; text-transform: uppercase;
             margin-bottom: 6px;}
[data-testid="stMarkdownContainer"] p.lr-title {font-size: clamp(34px, 4.2vw, 52px); line-height: 1.12; font-weight: 700;
                                                color: var(--text); letter-spacing: -0.025em; margin: 0 0 6px;}
[data-testid="stMarkdownContainer"] p.lr-title.sm {font-size: clamp(28px, 3vw, 38px);}
.lr-sub {font-size: clamp(16px, 1.4vw, 18px); color: var(--text2); margin: 4px 0 16px; max-width: 760px;}
.lr-section {font-size: 17px; font-weight: 800; color: var(--text); margin: 22px 0 2px;}
.lr-help {font-size: 14px; color: var(--muted); margin: 0 0 8px;}
.lr-muted {color: var(--muted); font-size: 14px;}
.lr-impact {font-size: 14px; font-weight: 700; color: var(--accent);}
.lr-big {font-size: 32px; font-weight: 700; color: var(--text); line-height: 1.1;}
.lr-big small {font-size: 15px; font-weight: 500; color: var(--muted);}
.lr-chips {display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin: 4px 0 10px;}
.lr-chips .lr-chip, .lr-chips .lr-label {margin: 0;}

/* chips: always carry text, never colour alone */
.lr-chip, .lr-badge {display: inline-block; padding: 3px 9px; border-radius: 8px; font-size: 12px; font-weight: 700;
                     letter-spacing: 0.04em; margin: 0 6px 2px 0; white-space: nowrap; text-transform: uppercase;}
.lr-a-restock {background: var(--primary); color: var(--primary-fg);}
.lr-a-reduce {background: var(--neutral-bg); color: var(--neutral-fg);}
.lr-a-stop {background: transparent; color: var(--text2); border: 1px solid var(--btn-border);}
.lr-a-maintain {background: transparent; color: var(--text2); border: 1px dashed var(--btn-border);}
.lr-s-urgent {background: #F3D9D2; color: #8A2E1E;}
.lr-s-warning {background: #F6E7C2; color: #6E4A0C;}
.lr-s-monitor, .lr-s-info {background: var(--neutral-bg); color: var(--neutral-fg);}
.lr-s-ok {background: var(--soft-bg); color: var(--soft-fg);}
.lr-must {background: transparent; color: var(--accent); border: 1px solid var(--accent);}
.lr-cat {background: var(--tile); color: var(--text2); border: 1px solid var(--line); text-transform: none;
         letter-spacing: 0; font-weight: 600;}
.lr-label {display: inline-block; font-size: 11px; font-weight: 700; letter-spacing: .06em; padding: 2px 8px;
           border-radius: 6px; margin-right: 6px; vertical-align: 1px;}
.lr-measured, .lr-placeholder {background: var(--soft-bg); color: var(--soft-fg);}
.lr-estimated {background: var(--neutral-bg); color: var(--neutral-fg);}
.lr-simulated {background: #F6E7C2; color: #6E4A0C;}
.lr-planned {background: transparent; color: var(--text2); border: 1px dashed var(--btn-border);}
.lr-mock {display: inline-flex; align-items: center; gap: 8px; padding: 6px 14px; border-radius: 999px; font-size: 13.5px;
          background: var(--mock-bg); border: 1px solid var(--mock-border); color: var(--mock-fg); margin: 2px 0 10px;}

/* KPI cards: one grid row, equal heights */
.lr-kpis {display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px; margin: 6px 0 14px;}
.lr-card {background: var(--tile); border-radius: 18px; padding: 16px 18px;}
.lr-kpi .k {font-size: 13px; font-weight: 700; color: var(--muted); text-transform: uppercase; letter-spacing: .06em;}
.lr-kpi .v {font-size: 24px; font-weight: 700; color: var(--text); line-height: 1.3;}
.lr-kpi .s {font-size: 13px; color: var(--muted);}
.lr-kpi .s.bad {color: var(--risk);} .lr-kpi .s.warn {color: var(--warn);} .lr-kpi .s.good {color: var(--good);}

/* Home: compact hero, order panel, Ask LARIS beside it */
.lr-hero {padding: 0 0 14px; text-align: center;}
.lr-hero-top {display: flex; flex-wrap: wrap; align-items: center; justify-content: center; gap: 6px 14px;}
.lr-hero-top .lr-mock {margin: 0; padding: 3px 12px; font-size: 12.5px;}
.lr-hero .lr-eyebrow {font-size: 13px; margin-bottom: 4px;}
[data-testid="stMarkdownContainer"] h1.lr-h1 {font-weight: 700; padding: 0; font-size: clamp(32px, 3.6vw, 50px);
        line-height: 1.1; letter-spacing: -0.03em; color: var(--text); margin: 6px 0 0; text-align: center;}
.lr-hero .lr-sub {font-size: 17px; margin: 4px auto 0;}
.lr-hero [data-testid="stHeaderActionElements"] {display: none;}
.lr-ph {display: flex; flex-wrap: wrap; justify-content: space-between; gap: 8px 24px; align-items: flex-end;}
.lr-ph > div:first-child {flex: 1 1 280px; min-width: 0;}
.lr-ph .lead {font-size: 15px; color: var(--text2); margin-top: 2px;}
.lr-ph .total {font-size: 40px; font-weight: 700; letter-spacing: -0.03em; line-height: 1; text-align: right;}
.lr-ph .total small {display: block; font-size: 13px; font-weight: 500; color: var(--muted); letter-spacing: 0;
                     margin-top: 4px;}
.lr-left {font-size: 13px; color: var(--muted); margin-top: -14px;}
.lr-ph {margin-bottom: 18px;}
.lr-tiles {display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 10px; margin: 10px 0 2px;}
.lr-tiles > div {background: var(--tile); border-radius: 16px; padding: 12px 14px;}
.lr-tiles span {display: block; font-size: 12.5px; font-weight: 700; color: var(--muted);}
.lr-tiles b {display: block; font-size: 19px; font-weight: 700; line-height: 1.3; color: var(--text);
             white-space: nowrap; overflow: hidden; text-overflow: ellipsis;}
.lr-tiles em {display: block; font-style: normal; font-size: 12px; color: var(--muted);}
.lr-tiles b.lime {color: var(--good);}
.lr-tiles b.risk {color: var(--risk);}
.lr-attn {border-top: 1px solid var(--line); margin-top: 12px; padding-top: 12px; font-size: 14px; font-weight: 800;
          color: var(--text2);}
/* "Needs your attention" cards: one flex row each -> [badge | description] (grows) + Review (fixed, right) */
[class*="st-key-attn_"] {background: var(--row); border-radius: 14px; padding: 10px 12px 10px 14px;
                         min-height: 64px; flex-wrap: nowrap; align-items: center;}
[class*="st-key-attn_"] > [data-testid="stElementContainer"]:has(.lr-attn-row) {flex: 1 1 0; min-width: 0;}
[class*="st-key-attn_"] > [data-testid="stElementContainer"]:has(button) {flex: 0 0 96px;}
[class*="st-key-attn_"] .stMarkdown, [class*="st-key-attn_"] [data-testid="stMarkdownContainer"] {margin: 0;}
.lr-attn-row {display: grid; grid-template-columns: 76px minmax(0, 1fr); column-gap: 12px; align-items: center;
              font-size: 13.5px; line-height: 1.45; color: var(--text);}
.lr-attn-row .lr-chip {width: 76px; box-sizing: border-box; text-align: center; margin: 0; font-size: 10.5px;
                       padding: 3px 0;}
.lr-attn-row span:last-child {min-width: 0; overflow-wrap: anywhere;}
[class*="st-key-ins_"] button {width: 96px; min-height: 36px; padding: 0 10px; font-size: 13px;}
@media (max-width: 480px) {   /* phones: Review drops under the text instead of squeezing it */
  [class*="st-key-attn_"] {flex-wrap: wrap;}
  [class*="st-key-attn_"] > [data-testid="stElementContainer"]:has(.lr-attn-row) {flex-basis: 100%;}
  [class*="st-key-attn_"] > [data-testid="stElementContainer"]:has(button) {margin-left: auto;}
}
[class*="st-key-glass_panel"] [data-testid="stSlider"] [data-testid="stWidgetLabel"] p {font-size: 13px; color: var(--muted);}
.st-key-glass_panel {padding: 24px 28px;}
.st-key-glass_ask {padding: 22px 22px 18px;}
[data-testid="stLayoutWrapper"]:has(> .st-key-glass_panel), [data-testid="stLayoutWrapper"]:has(> .st-key-glass_ask)
  {flex: 1 1 auto; display: flex; flex-direction: column;}
.st-key-glass_panel, .st-key-glass_ask {flex: 1 1 auto;}
.st-key-glass_ask {display: flex; flex-direction: column;}
.st-key-glass_ask > div:has(.st-key-chatlog), .st-key-chatlog {flex: 1 1 0; min-height: 120px;}
.st-key-chatlog {height: auto !important; max-height: none !important; overflow-y: auto;}
.st-key-chatlog [data-testid="stChatMessage"] {padding: 6px 0; gap: 10px;}
.st-key-chatlog [data-testid="stChatMessage"] p {font-size: 14px;}
.st-key-chatlog [data-testid="stSpinner"] {font-size: 12px; color: var(--muted); gap: 6px; padding: 2px 0 4px 44px;}
.st-key-chatlog [data-testid="stSpinner"] p {font-size: 12px; margin: 0;}
.st-key-chatlog [data-testid="stSpinnerIcon"] {transform: scale(.45); transform-origin: center;}
.st-key-chat_clear button {min-height: 30px; padding: 0 10px; font-size: 12px;}
.st-key-chat_clear button p {font-size: 12px;}
.st-key-glass_ask [data-testid="stChatInput"], .st-key-glass_ask [data-testid="stChatInput"] > div
  {background: var(--tile); border: 1px solid var(--line); border-radius: 18px; box-shadow: none;}
.st-key-glass_ask [data-testid="stChatInput"] textarea {font-size: 15px; min-height: 52px; color: var(--text);}
.st-key-glass_ask [data-testid="stChatInput"] textarea::placeholder {color: var(--placeholder); opacity: 1;}
[data-testid="stChatInputSubmitButton"] {width: 44px; height: 44px; min-width: 44px; border-radius: 999px;
                                         background: var(--primary) !important; align-self: flex-end;}
[data-testid="stChatInputSubmitButton"] svg {fill: var(--primary-fg); color: var(--primary-fg);}
[data-testid="stChatInputSubmitButton"]:disabled {opacity: .6;}
.st-key-chips {flex-wrap: wrap; gap: 6px !important;}
.st-key-chips [data-testid="stElementContainer"] {width: auto !important; max-width: 100%;}
.st-key-chips button {min-height: 34px; padding: 4px 12px; font-size: 12.5px; font-weight: 500;
                      background: var(--glass); border-color: var(--glass-border); border-radius: 999px;}
.st-key-chips button p {font-size: 12.5px;}
.st-key-chips button [data-testid="stIconMaterial"] {color: var(--accent);}
[data-testid="stChatMessage"] {background: transparent; padding: 8px 0;}
.lr-ribbon {position: relative; height: 0; pointer-events: none; opacity: var(--ribbon);}
.lr-ribbon svg {position: absolute; left: -30%; width: 160%; height: 640px; z-index: -1;}
.lr-center {text-align: center;}
[data-testid="stMarkdownContainer"] p.lr-disclaimer {text-align: center; font-size: 12px; color: var(--muted);
                                                     margin: 14px 0 0;}

/* letter strip: five tiles; lime when active */
[class*="st-key-letter_"] button {height: 74px; flex-direction: column; border-radius: 18px; background: var(--glass);
                                  border: 1px solid var(--glass-border); color: var(--muted); font-weight: 600;}
[class*="st-key-letter_"] button p {font-size: 13px; line-height: 1.25; margin: 0;}
[class*="st-key-letter_"] button strong {display: block; font-size: 26px; font-weight: 700; color: var(--text);
                                         letter-spacing: -0.02em; line-height: 1.1;}
[class*="st-key-letter_"] button:hover {border-color: var(--accent);}
[class*="st-key-letter_"] [data-testid^="stBaseButton-primary"] strong,
[class*="st-key-letter_"] [data-testid^="stBaseButton-primary"] p {color: var(--primary-fg);}

/* tiles inside a page card (product detail) */
[class*="st-key-tile_"] {background: var(--tile); border-radius: 20px; padding: 18px 20px; margin-bottom: 4px;}

/* rows and product cards */
[class*="st-key-row_"] {border-top: 1px solid var(--line); padding: 10px 6px; border-radius: 14px;}
[class*="st-key-row_"]:hover {background: var(--row);}
[class*="st-key-pcard_"] {background: var(--tile); border: 1px solid var(--line); border-radius: 18px; padding: 16px 18px;
                          height: 100%;}
[class*="st-key-pcard_"]:hover {border-color: var(--accent);}
.lr-pc-top {display: flex; justify-content: space-between; gap: 8px; align-items: flex-start;}
.lr-pc-name {font-weight: 700; font-size: 16px; color: var(--text); line-height: 1.3;}
.lr-pc-rank {font-size: 12px; color: var(--muted); white-space: nowrap;}
.lr-pc-grid {display: grid; grid-template-columns: 1fr 1fr; gap: 6px 12px; margin: 10px 0 4px; font-size: 13px;
             color: var(--muted);}
.lr-pc-grid b {display: block; font-size: 16px; color: var(--text);}
.lr-name {font-weight: 700; font-size: 15px; color: var(--text);}
.lr-qty {font-size: 16px; font-weight: 700; color: var(--text); font-variant-numeric: tabular-nums;}
.lr-qty span {font-weight: 500; color: var(--muted); font-size: 13px;}
.lr-insight {padding: 12px 16px; background: var(--row); margin-bottom: 8px; border-radius: 16px; font-size: 15px;
             color: var(--text);}
.lr-insight.urgent {background: var(--risk-row);}
.lr-insight.warning {background: var(--warn-row);}
.lr-tagbox {display: inline-block; font-size: 11px; font-weight: 700; letter-spacing: .04em; padding: 2px 8px;
            border-radius: 6px; margin-right: 6px; color: var(--text2); background: var(--neutral-bg);
            min-width: 84px; text-align: center;}
.lr-why {line-height: 1.6; color: var(--text);}
.lr-why h4 {font-size: 13px; letter-spacing: .14em; margin: 16px 0 4px; color: var(--accent); text-transform: uppercase;
            padding: 0;}
.lr-why h4:first-child {margin-top: 0;}
.lr-why p {margin: 0 0 4px;}
.lr-why [data-testid="stHeaderActionElements"] {display: none;}

@media (max-width: 1100px) {
  .lr-tiles {grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));}
}
@media (max-width: 900px) {
  .st-key-topbar {position: static; margin-bottom: 8px;}
}
@media (max-width: 720px) {
  .block-container {padding-left: 16px; padding-right: 16px;}
  [class*="st-key-glass_"], .st-key-glass_page {padding: 18px 14px;}
  .lr-ph .total {font-size: 34px; text-align: left;}
}
"""


def css(m=None):
    """The stylesheet for mode m (default: the current mode): that mode's variables + the shared rules."""
    v = VARS[m or mode()]
    root = ":root {" + " ".join(f"--{k}: {x};" for k, x in v.items()) + "}"
    return f"<style>{root}\n{RULES}</style>"


# ---------------- light / dark ----------------
SNAP_KEYS = ("budget_rm", "order_adj", "strategy", "tool", "chat", "chat_mem", "as_of", "store")


def toggle_theme():
    """Switch mode and save it. The browser reloads to apply Streamlit's own palette (theme_script), which starts
    a new session, so the work in progress is saved here and restored by restore_snapshot() right after."""
    ss = st.session_state
    new = "light" if mode() == "dark" else "dark"
    store.put("prefs", {**store.get("prefs", {}), "theme": new})
    snap = {k: ss[k] for k in SNAP_KEYS if k in ss}
    if ss.get("inputs_dirty") and "inputs" in ss:   # an edited product list travels with its markers
        snap.update(inputs=ss["inputs"].to_dict("records"), inputs_dirty=True, inputs_key=ss.get("inputs_key"))
    store.put("snapshot", {"at": time.time(), "state": json.loads(json.dumps(snap, default=str))})
    ss["theme"] = new


def restore_snapshot(columns):
    """Once per new session: bring back the state saved by toggle_theme (only if saved in the last minute)."""
    ss = st.session_state
    if ss.get("_booted"):
        return
    ss["_booted"] = True
    snap = store.get("snapshot")
    if not snap:
        return
    store.put("snapshot", None)
    if time.time() - snap.get("at", 0) > 60:
        return
    for k, v in snap["state"].items():
        if k == "inputs":
            ss["inputs"] = pd.DataFrame(v, columns=columns)
        elif k == "as_of":
            ss["as_of"] = pd.Timestamp(v)
        elif k == "inputs_key":
            ss["inputs_key"] = tuple(v)
        else:
            ss[k] = v


def theme_script(m):
    """Make Streamlit's native widgets (tables, inputs) use the same mode: set the browser's saved theme for every
    LARIS page and reload once if this page was showing the other one."""
    want = json.dumps("Light" if m == "light" else "Dark")
    return """<script>(function () {
  const want = JSON.stringify(%s), pages = ["", "laris", "products", "orders", "settings", "product"];
  const seg = location.pathname.split("/").filter(Boolean);
  const base = seg.length && pages.includes(seg[seg.length - 1]) ? seg.slice(0, -1) : seg;
  let here = false;
  try {
    for (const p of pages) {
      const path = "/" + base.concat(p ? [p] : []).join("/");
      const key = "stActiveTheme-" + path + "-v2";
      if (localStorage.getItem(key) !== want) {
        localStorage.setItem(key, want);
        if (path === location.pathname || path + "/" === location.pathname) here = true;
      }
    }
  } catch (e) { return; }
  const mark = want + location.pathname;   // reload at most once per switch, even if storage is blocked
  if (!here) { sessionStorage.removeItem("laris-theme"); return; }
  if (sessionStorage.getItem("laris-theme") !== mark) {
    sessionStorage.setItem("laris-theme", mark);
    location.reload();
  }
})();</script>""" % want


def topbar(name, place):
    """Shop pill + light/dark switch, pinned to the right of the top nav (in the page flow on narrow screens)."""
    with st.container(key="topbar", horizontal=True):
        st.markdown(f'<div class="lr-shoppill">{escape(name)} · {escape(place)}'
                    f'<span class="lr-badge">Sample shop</span></div>', unsafe_allow_html=True)
        dark = mode() == "dark"
        st.button("Switch to light mode" if dark else "Switch to dark mode", key="theme_btn",
                  icon=":material/light_mode:" if dark else ":material/dark_mode:", on_click=toggle_theme,
                  help="Switch to light mode" if dark else "Switch to dark mode")


def money(x, dp=0):
    return "RM –" if x is None or pd.isna(x) else f"RM {x:,.{dp}f}"


def chip(text, cls):
    return f'<span class="lr-chip {cls}">{escape(str(text))}</span>'


def action_chip(action):
    return chip(planning.ACTION_LABEL[action], f"lr-a-{action.lower()}")


def status_chip(level):
    return chip(level, f"lr-s-{level.lower().replace(' ', '-')}")


def must_chip(must):
    return chip("Must-have", "lr-must") if must else ""


def label(text, kind):
    """Provenance badge: measured / estimated / simulated / placeholder / planned."""
    return f'<span class="lr-label lr-{kind}">{escape(text)}</span>'


def kpi(k, v, s="", tone=None):
    """One KPI card; tone colours the note: 'bad', 'warn' or 'good'. Put several in kpi_row() so they line up."""
    return (f'<div class="lr-card lr-kpi"><div class="k">{escape(k)}</div><div class="v">{escape(v)}</div>'
            f'<div class="s {tone or ""}">{escape(s)}</div></div>')


def kpi_row(*cards):
    """KPI cards in one grid row: equal heights, reflowing on narrow screens."""
    st.markdown(f'<div class="lr-kpis">{"".join(cards)}</div>', unsafe_allow_html=True)


def page_header(eyebrow, title, subtitle, small=False):
    top = f'<div class="lr-eyebrow">{escape(eyebrow)}</div>' if eyebrow else ""
    sub = f'<p class="lr-sub">{escape(subtitle)}</p>' if subtitle else ""
    return f'{top}<p class="lr-title{" sm" if small else ""}">{escape(title)}</p>{sub}'


def cat_chip(group):
    return chip(group, "lr-cat")


def section(title, helptext=None):
    st.markdown(f'<div class="lr-section">{escape(title)}</div>'
                + (f'<p class="lr-help">{escape(helptext)}</p>' if helptext else ""), unsafe_allow_html=True)


def evidence(pairs):
    return "<br>".join(f'<span class="lr-tagbox">{escape(t)}</span>{escape(x)}' for t, x in pairs)


def require_plan(ctx):
    """Every planning page needs at least one product."""
    if ctx["empty"]:
        st.info("You have no products yet. Add them in Products, then LARIS can plan your order.")
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
    st.button(label, key=key, on_click=_open, args=(product, back), use_container_width=True)


def goto(path):
    st.session_state["goto"] = path


def open_tool(letter):
    """Jump to a LARIS tool from anywhere (Home insights, assistant links)."""
    st.session_state.update(tool=letter, goto="views/laris.py")


def tool_button(letter, label, key, width="stretch"):
    st.button(label, key=key, on_click=open_tool, args=(letter,), width=width)


def set_qty_value(product, qty):
    """Owner's quantity override for the shared order; the recommendation itself is kept."""
    st.session_state.setdefault("order_adj", {})[product] = float(qty)


def set_qty_from(product, key):
    set_qty_value(product, st.session_state[key])


def clear_qty(product):
    st.session_state.setdefault("order_adj", {}).pop(product, None)


# ---------------- product lists: category filter, click a row for details ----------------
def categories(ctx):
    """Categories used by this shop's products, in the standard order."""
    import laris_core as core
    used = set(ctx["plan"]["group"]) if len(ctx["plan"]) else set()
    return [c for c in core.CATEGORIES if c in used] + sorted(used - set(core.CATEGORIES))


def category_filter(ctx, key):
    """Category pills ('All' + this shop's categories). Returns the chosen one; use in_category() to filter."""
    pick = st.pills("Category", ["All"] + categories(ctx), label_visibility="collapsed",
                    **sticky(key, "All")) or "All"
    return pick


def in_category(df, pick, col="group"):
    return df if pick == "All" or not len(df) else df[df[col] == pick]


def product_table(df, key, back, **kwargs):
    """A read-only product table where clicking any cell opens that product's detail page (no row checkboxes).
    df needs a 'product' column (hidden)."""
    ss = st.session_state
    ver = ss.get("_pt_ver", 0)
    kwargs.setdefault("column_config", {})["product"] = None
    event = st.dataframe(df.reset_index(drop=True), key=f"{key}_{ver}", on_select="rerun",
                         selection_mode="single-cell", hide_index=True, use_container_width=True, **kwargs)
    cells = event.selection.cells if event is not None and event.selection else []
    if cells:
        ss["_pt_ver"] = ver + 1
        _open(df["product"].iloc[cells[0][0]], back)
        st.rerun()


# ---------------- shared pieces of the new layout ----------------
def mock_pill():
    return ('<div class="lr-mock" role="note"><span aria-hidden="true">ⓘ</span>'
            "Mock data for development only. Do not present these numbers.</div>")


def ribbon(uid, top=0):
    """Decorative S-curve glow: wide lime haze, mid green, thin light line. Sits behind the content."""
    d = "M-120 430 C 260 140, 560 600, 920 330 S 1460 110, 1600 240"
    blur = "".join(f'<filter id="{uid}{i}" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur '
                   f'stdDeviation="{s}"/></filter>' for i, s in enumerate((46, 18, 3)))
    strokes = "".join(f'<path d="{d}" fill="none" stroke="{c}" stroke-width="{w}" stroke-linecap="round" '
                      f'opacity="{o}" filter="url(#{uid}{i})"/>'
                      for i, (c, w, o) in enumerate(((LIME, 150, .22), (GLOW, 56, .45), (LIME2, 4, .55))))
    return (f'<div class="lr-ribbon" aria-hidden="true"><svg style="top:{top}px" viewBox="0 0 1440 640" '
            f'preserveAspectRatio="none" focusable="false"><defs>{blur}</defs>{strokes}</svg></div>')


def budget_slider(ctx, key, label="Budget (RM)", label_visibility="visible"):
    """The shared weekly budget as a slider: 0 up to 1.5 × the full recommended order (or the current budget if
    higher). Moving it updates ss.budget_rm, which app.py uses to rebuild the plan for every page."""
    ss = st.session_state
    hi = float(max(ceil(ctx["ideal_rm"] * 1.5 / 50) * 50, ceil(ss["budget_rm"] / 50) * 50, 50))
    ss[key] = float(ss["budget_rm"])
    st.slider(label, 0.0, hi, step=10.0, format="RM %d", key=key, label_visibility=label_visibility,
              on_change=lambda: ss.update(budget_rm=float(ss[key])))


def panel_head(eyebrow, lead, total, note):
    return (f'<div class="lr-ph"><div><div class="lr-eyebrow">{escape(eyebrow)}</div><div class="lead">'
            f'{escape(lead)}</div></div><div class="total">{escape(total)}<small>{escape(note)}</small></div></div>')


def tiles(stats):
    """stats: (label, value, note, tone) with tone in {None, 'lime', 'risk'}. All text is escaped."""
    cells = "".join(f'<div><span>{escape(k)}</span><b class="{tone or ""}">{escape(v)}</b><em>{escape(n)}</em></div>'
                    for k, v, n, tone in stats)
    return f'<div class="lr-tiles">{cells}</div>'


# ---------------- forecast chart (Look Up, Product detail) ----------------
def range_note(ctx):
    cov = ctx["metrics"].get("band_coverage_90")
    note = ("Shaded band: approximate range (forecast ± 1.645 × the model's typical daily error on validation weeks), "
            "not a guaranteed interval.")
    if cov is not None:
        note += f" On held-out test weeks, {cov:.0%} of actual days fell inside a band built this way."
    return note


def forecast_chart(ctx, product, height=260):
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
    cc = chart_colors()
    fut["lo"], fut["hi"] = (fut["units"] - Z90 * r["sigma"]).clip(lower=0), fut["units"] + Z90 * r["sigma"]
    color = alt.Color("series:N", scale=alt.Scale(domain=["Recorded sales", "Forecast"], range=[cc["hist"], cc["line"]]),
                      legend=alt.Legend(orient="top", title=None))
    x = alt.X("date:T", title=None, axis=alt.Axis(format="%d %b", grid=False))
    layers = [alt.Chart(pd.concat([hist, fut[["date", "units", "series"]]])).mark_line(point=True).encode(
        x=x, y=alt.Y("units:Q", title="Units per day"), color=color,
        tooltip=[alt.Tooltip("date:T", format="%a %d %b"), alt.Tooltip("units:Q", format=",.1f"), "series"])]
    if source != "unavailable":
        layers.insert(0, alt.Chart(fut).mark_area(opacity=0.2, color=cc["band"]).encode(x=x, y="lo:Q", y2="hi:Q"))
    note = {"model": range_note(ctx),
            "baseline": "No model forecast for this product: the forecast repeats last week's sales, so treat it as rough.",
            "unavailable": "Forecast unavailable: no sales history and nothing recorded as sold last week."}[source]
    return (alt.layer(*layers).properties(height=height, background="transparent").configure_view(strokeWidth=0),
            note)

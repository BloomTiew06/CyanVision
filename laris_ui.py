"""LARIS look and feel: CSS plus small HTML helpers for the Streamlit pages (green theme)."""
from html import escape

GREEN = "#0F6B45"
DARK = "#0B3B2C"

CSS = """
<style>
[data-testid="stSidebar"] {background: #0B3B2C;}
[data-testid="stSidebar"] [data-testid="stSidebarNavLink"] span {color: #E8F3EC;}
[data-testid="stSidebar"] [data-testid="stSidebarNavLink"][aria-current="page"] {background: #145C43;}
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
[data-testid="stSidebar"] label {color: #E8F3EC;}
.block-container {padding-top: 3.2rem;}
header[data-testid="stHeader"] {background: transparent;}
.lr-brand {font-size: 24px; font-weight: 700; letter-spacing: 1px; color: #FFFFFF; margin: 4px 0 0;}
.lr-tag {font-size: 12px; color: #A9CDBB; margin-bottom: 6px;}
.lr-card {background: #FFFFFF; border: 1px solid #E2EAE5; border-radius: 14px; padding: 14px 16px;
          box-shadow: 0 1px 2px rgba(16, 40, 30, .05); height: 100%;}
.lr-kpi .k {font-size: 13px; color: #5B6B62;}
.lr-kpi .v {font-size: 26px; font-weight: 700; color: #14261D; line-height: 1.25;}
.lr-kpi .s {font-size: 12px; color: #5B6B62;}
.lr-hero {background: #0E4A36; color: #FFFFFF; border-radius: 16px; padding: 18px 22px; margin: 6px 0 14px;}
.lr-hero h3 {color: #FFFFFF; margin: 0 0 4px; font-size: 22px;}
.lr-hero p {color: #CFE6DA; margin: 0; font-size: 14px;}
.lr-chip {display: inline-block; padding: 2px 10px; border-radius: 999px; font-size: 12px; font-weight: 600;
          margin-right: 6px; white-space: nowrap;}
.lr-act {background: #FDE8E7; color: #B42318;}
.lr-order {background: #FFF1DB; color: #9A5B00;}
.lr-watch {background: #E8F0FE; color: #1D4ED8;}
.lr-ok {background: #E7F5EC; color: #146C43;}
.lr-cat {background: #EEF2EF; color: #33463B;}
.lr-tagbox {display: inline-block; font-size: 11px; padding: 1px 7px; border-radius: 6px; margin-right: 6px;
            border: 1px solid #CFDCD4; color: #3E5247; background: #F6FAF7; min-width: 78px; text-align: center;}
.lr-letter {display: inline-block; background: #E2F1E8; color: #0F6B45; border-radius: 8px; padding: 2px 10px;
            font-size: 12px; font-weight: 700; margin-bottom: 4px;}
.lr-title {font-size: 26px; font-weight: 700; color: #14261D; margin: 0;}
.lr-sub {font-size: 14px; color: #5B6B62; margin: 0 0 6px;}
.lr-label {display: inline-block; font-size: 11px; font-weight: 700; padding: 1px 8px; border-radius: 6px;}
.lr-measured {background: #E7F5EC; color: #146C43;}
.lr-simulated {background: #FFF1DB; color: #9A5B00;}
.lr-placeholder {background: #F1EFE8; color: #5F5E5A;}
.lr-shop {background: #124D3A; border-radius: 12px; padding: 10px 12px; color: #E8F3EC; font-size: 13px;}
</style>
"""

TIER_CLASS = {"Act today": "lr-act", "This order": "lr-order", "Watch": "lr-watch", "OK": "lr-ok"}


def chip(text, cls="lr-cat"):
    return f'<span class="lr-chip {cls}">{escape(str(text))}</span>'


def tier_chip(tier):
    return chip(tier, TIER_CLASS.get(tier, "lr-cat"))


def label(text, kind):
    """MEASURED / SIMULATED / PLACEHOLDER badge."""
    return f'<span class="lr-label lr-{kind}">{escape(text)}</span>'


def kpi(k, v, s="", tone=None):
    color = {"bad": "#B42318", "warn": "#9A5B00", "good": "#146C43"}.get(tone, "#5B6B62")
    return (f'<div class="lr-card lr-kpi"><div class="k">{escape(k)}</div><div class="v">{escape(v)}</div>'
            f'<div class="s" style="color:{color}">{escape(s)}</div></div>')


def page_header(letter, malay, title, subtitle):
    top = f'<div class="lr-letter">{escape(letter)} · {escape(malay)}</div>' if letter else ""
    return f'{top}<p class="lr-title">{escape(title)}</p><p class="lr-sub">{escape(subtitle)}</p>'


def brand():
    return ('<div class="lr-brand">L·A·R·I·S</div>'
            '<div class="lr-tag">Biar laris, jangan habis.</div>')


def shop_card(name, place):
    return f'<div class="lr-shop"><b>{escape(name)}</b><br>{escape(place)}<br><i>demo profile</i></div>'


def evidence(pairs):
    """Explanation lines with source tags."""
    return "<br>".join(f'<span class="lr-tagbox">{escape(t)}</span>{escape(x)}' for t, x in pairs)

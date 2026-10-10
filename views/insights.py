"""Insights: one place for what has happened (sales, gross profit, trends, best sellers), so these figures aren't
repeated across the LARIS tools. Every figure comes from planning.sales_summary and friends."""
import streamlit as st

import laris_ui as ui
from workspace import analyse, sales

ctx = st.session_state["ctx"]
ui.require_plan(ctx)
ui.section("Trends", "The last weeks at a glance.")
analyse.render(ctx)
ui.section("Revenue and profit by product", "Pick a period; products link to their details.")
sales.render(ctx)

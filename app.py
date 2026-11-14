import streamlit as st
import asyncio
import time
import pandas as pd
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
import re
from agent.masking import MOBILE_RE
from agent.campaign import (
    CampaignSpec, draft_spec_llm, draft_spec_offline,
    new_campaign_id, save_campaign, list_campaigns,
)
from agent.pipeline import Pipeline
from agent import db
from agent.llm_gateway import LLMGateway
from agent.config import settings
from agent.match_runner import (
    run_all_matches, get_matches_for_display, update_match_outcome, update_match_status
)
from agent.db import save_manual_order
from agent.dedup import deduplicate_database
from agent.caller_lookup import lookup_caller
from agent.outreach import (
    format_wa_url,
    draft_farmer_outreach_for_match,
    draft_farmer_outreach_for_lead,
    draft_buyer_outreach_for_lead,
    draft_buyer_outreach_for_match,
    build_matches_export_dataframe,
)
from agent.compliance import is_do_not_contact, register_opt_out_contact, is_within_operating_hours
from agent.handover import evaluate_inbound_message
from agent.sales_agent import (
    generate_initial_outreach,
    generate_conversational_reply,
    summarize_conversation,
    calculate_sales_metrics,
    build_conversations_export_dataframe,
)
from agent.cadence import get_due_followups, generate_followup_message, advance_followup, calculate_due_date

# ================= PAGE CONFIG =================
st.set_page_config(
    page_title="GoTani Lead Engine | Apify Console",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ================= CUSTOM CSS: APIFY CONSOLE DESIGN SYSTEM =================
st.markdown("""
<style>
    /* Google Fonts Inter */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

    #MainMenu {visibility: hidden;}
    /* Cegah tooltip nyangkut/freeze yang memblokir klik mouse pada tombol */
    div[data-baseweb="tooltip"],
    div[role="tooltip"],
    div[data-testid="stTooltipContent"] {
        pointer-events: none !important;
    }
    footer {visibility: hidden;}

    /* Base canvas */
    html, body, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
        color: #101828;
    }
    
    .stApp {
        background-color: #f8fafc;
    }

    /* Top Breadcrumb Header */
    .apify-breadcrumb {
        display: flex;
        align-items: center;
        gap: 8px;
        font-size: 13px;
        color: #64748b;
        margin-bottom: 8px;
        font-weight: 500;
    }
    .apify-breadcrumb a {
        color: #0284c7;
        text-decoration: none;
    }

    /* Apify Status Bar */
    .apify-status-bar {
        background: #ffffff;
        border: 1px solid #eaecf0;
        border-radius: 8px;
        padding: 10px 16px;
        display: flex;
        align-items: center;
        justify-content: space-between;
        flex-wrap: wrap;
        gap: 12px;
        margin-bottom: 20px;
        box-shadow: 0 1px 2px rgba(16, 24, 40, 0.04);
    }
    .apify-status-left {
        display: flex;
        align-items: center;
        gap: 12px;
        flex-wrap: wrap;
    }
    .apify-meta-item {
        font-size: 12px;
        color: #475467;
        font-weight: 500;
        padding-left: 12px;
        border-left: 1px solid #e4e7ec;
    }

    /* Status Pills (Apify Style) */
    .apify-pill {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 3px 10px;
        border-radius: 12px;
        font-size: 12px;
        font-weight: 500;
        line-height: 1.2;
    }
    .apify-pill-success {
        background-color: #ecfdf3;
        color: #027a48;
        border: 1px solid #abefc6;
    }
    .apify-pill-review {
        background-color: #fffaeb;
        color: #b54708;
        border: 1px solid #fedf89;
    }
    .apify-pill-ignored {
        background-color: #f2f4f7;
        color: #344054;
        border: 1px solid #eaecf0;
    }
    .apify-pill-pool {
        background-color: #eff8ff;
        color: #175cd3;
        border: 1px solid #b2ddff;
    }
    .apify-pill-single {
        background-color: #f8fafc;
        color: #344054;
        border: 1px solid #eaecf0;
    }
    .dot {
        width: 6px;
        height: 6px;
        border-radius: 50%;
        display: inline-block;
    }
    .dot-success { background-color: #12b76a; }
    .dot-review { background-color: #f79009; }
    .dot-ignored { background-color: #98a2b3; }

    /* Apify Card Container */
    .apify-card {
        background-color: #ffffff;
        border: 1px solid #eaecf0;
        border-radius: 8px;
        padding: 18px;
        margin-bottom: 14px;
        box-shadow: 0 1px 2px rgba(16, 24, 40, 0.04);
        transition: border-color 0.15s ease-in-out;
    }
    .apify-card:hover {
        border-color: #cbd5e1;
    }

    /* Metric Cards */
    div[data-testid="stMetric"] {
        background: #ffffff;
        border: 1px solid #eaecf0;
        border-radius: 8px;
        padding: 14px 18px;
        box-shadow: 0 1px 2px rgba(16, 24, 40, 0.04);
    }
    div[data-testid="stMetricValue"] {
        font-size: 1.6rem;
        font-weight: 700;
        color: #101828;
        letter-spacing: -0.02em;
    }
    div[data-testid="stMetricLabel"] {
        font-size: 0.78rem;
        font-weight: 600;
        color: #475467;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }

    /* Buttons: Apify Primary Blue & Clean Secondary */
    .stButton>button {
        border-radius: 6px;
        font-weight: 500;
        font-size: 0.88rem;
        padding: 0.45rem 1rem;
        transition: all 0.15s ease;
    }
    button[kind="primary"] {
        background-color: #0284c7 !important;
        color: #ffffff !important;
        border: 1px solid #0284c7 !important;
        box-shadow: 0 1px 2px rgba(16, 24, 40, 0.05);
    }
    button[kind="primary"]:hover {
        background-color: #0369a1 !important;
        border-color: #0369a1 !important;
    }
    button[kind="secondary"] {
        background-color: #ffffff !important;
        color: #344054 !important;
        border: 1px solid #d0d5dd !important;
        box-shadow: 0 1px 2px rgba(16, 24, 40, 0.05);
    }
    button[kind="secondary"]:hover {
        background-color: #f8fafc !important;
        border-color: #98a2b3 !important;
        color: #101828 !important;
    }

    /* Embedded Dismissable Notification Alert (Inside Area) */
    div[data-testid="stHorizontalBlock"]:has(.notify-marker-success) {
        background-color: #ecfdf3 !important;
        border: 1px solid #abefc6 !important;
        border-radius: 6px !important;
        padding: 8px 14px !important;
        margin-bottom: 16px !important;
        align-items: center !important;
    }
    div[data-testid="stHorizontalBlock"]:has(.notify-marker-info) {
        background-color: #eff8ff !important;
        border: 1px solid #b2ddff !important;
        border-radius: 6px !important;
        padding: 8px 14px !important;
        margin-bottom: 16px !important;
        align-items: center !important;
    }
    div[data-testid="stHorizontalBlock"]:has(.notify-marker-warning) {
        background-color: #fffaeb !important;
        border: 1px solid #fedf89 !important;
        border-radius: 6px !important;
        padding: 8px 14px !important;
        margin-bottom: 16px !important;
        align-items: center !important;
    }
    div[data-testid="column"]:has(.notify-marker-success),
    div[data-testid="column"]:has(.notify-marker-info),
    div[data-testid="column"]:has(.notify-marker-warning),
    div[data-testid="stColumn"]:has(.notify-marker-success),
    div[data-testid="stColumn"]:has(.notify-marker-info),
    div[data-testid="stColumn"]:has(.notify-marker-warning) {
        display: flex !important;
        align-items: center !important;
    }
    div[data-testid="stHorizontalBlock"]:has(.notify-marker-success) div[data-testid="stVerticalBlock"],
    div[data-testid="stHorizontalBlock"]:has(.notify-marker-info) div[data-testid="stVerticalBlock"],
    div[data-testid="stHorizontalBlock"]:has(.notify-marker-warning) div[data-testid="stVerticalBlock"] {
        gap: 0 !important;
    }

    /* Target close button column */
    div[data-testid="column"]:has(.notify-close-marker),
    div[data-testid="stColumn"]:has(.notify-close-marker) {
        display: flex !important;
        justify-content: flex-end !important;
        align-items: center !important;
        min-width: 32px !important;
    }
    div[data-testid="column"]:has(.notify-close-marker) .stButton,
    div[data-testid="stColumn"]:has(.notify-close-marker) .stButton,
    div[data-testid="column"]:has(.notify-close-marker) div[data-testid="stButton"],
    div[data-testid="stColumn"]:has(.notify-close-marker) div[data-testid="stButton"] {
        width: auto !important;
        margin: 0 !important;
        padding: 0 !important;
    }

    /* Completely strip white background, border, and shadow from the close '✕' button */
    div[data-testid="stHorizontalBlock"]:has(.notify-marker-success) button,
    div[data-testid="stHorizontalBlock"]:has(.notify-marker-info) button,
    div[data-testid="stHorizontalBlock"]:has(.notify-marker-warning) button,
    div[data-testid="column"]:has(.notify-close-marker) button,
    div[data-testid="stColumn"]:has(.notify-close-marker) button {
        background: transparent !important;
        background-color: transparent !important;
        border: none !important;
        border-color: transparent !important;
        box-shadow: none !important;
        outline: none !important;
        padding: 0 !important;
        margin: 0 !important;
        min-height: 26px !important;
        height: 26px !important;
        min-width: 26px !important;
        width: 26px !important;
        border-radius: 4px !important;
        line-height: 1 !important;
        cursor: pointer !important;
        display: inline-flex !important;
        align-items: center !important;
        justify-content: center !important;
        transition: all 0.15s ease !important;
    }

    div[data-testid="stHorizontalBlock"]:has(.notify-marker-success) button {
        color: #027a48 !important;
    }
    div[data-testid="stHorizontalBlock"]:has(.notify-marker-success) button:hover {
        background-color: rgba(2, 122, 72, 0.12) !important;
        color: #054f31 !important;
    }

    div[data-testid="stHorizontalBlock"]:has(.notify-marker-info) button {
        color: #175cd3 !important;
    }
    div[data-testid="stHorizontalBlock"]:has(.notify-marker-info) button:hover {
        background-color: rgba(23, 92, 211, 0.12) !important;
        color: #0b3273 !important;
    }

    div[data-testid="stHorizontalBlock"]:has(.notify-marker-warning) button {
        color: #b54708 !important;
    }
    div[data-testid="stHorizontalBlock"]:has(.notify-marker-warning) button:hover {
        background-color: rgba(181, 71, 8, 0.12) !important;
        color: #7a2e05 !important;
    }

    div[data-testid="stHorizontalBlock"]:has(.notify-marker-success) button:active,
    div[data-testid="stHorizontalBlock"]:has(.notify-marker-info) button:active,
    div[data-testid="stHorizontalBlock"]:has(.notify-marker-warning) button:active,
    div[data-testid="stHorizontalBlock"]:has(.notify-marker-success) button:focus,
    div[data-testid="stHorizontalBlock"]:has(.notify-marker-info) button:focus,
    div[data-testid="stHorizontalBlock"]:has(.notify-marker-warning) button:focus {
        background: transparent !important;
        border: none !important;
        box-shadow: none !important;
        outline: none !important;
    }

    /* Crisp, centered and visible cross glyph */
    div[data-testid="stHorizontalBlock"]:has(.notify-marker-success) button p,
    div[data-testid="stHorizontalBlock"]:has(.notify-marker-info) button p,
    div[data-testid="stHorizontalBlock"]:has(.notify-marker-warning) button p,
    div[data-testid="column"]:has(.notify-close-marker) button p,
    div[data-testid="stColumn"]:has(.notify-close-marker) button p,
    div[data-testid="column"]:has(.notify-close-marker) button div[data-testid="stMarkdownContainer"],
    div[data-testid="stColumn"]:has(.notify-close-marker) button div[data-testid="stMarkdownContainer"] {
        font-size: 16px !important;
        font-weight: 700 !important;
        line-height: 1 !important;
        margin: 0 !important;
        padding: 0 !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
    }


    /* Matchmaking Stepper */
    .match-stepper {
        display: flex;
        align-items: stretch;
        gap: 0;
        margin-bottom: 20px;
        background: #ffffff;
        border: 1px solid #eaecf0;
        border-radius: 8px;
        overflow: hidden;
        box-shadow: 0 1px 2px rgba(16, 24, 40, 0.04);
    }
    .match-step {
        flex: 1;
        padding: 14px 18px;
        position: relative;
        display: flex;
        flex-direction: column;
        gap: 4px;
        border-right: 1px solid #eaecf0;
    }
    .match-step:last-child {
        border-right: none;
    }
    .match-step-num {
        font-size: 11px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        color: #98a2b3;
    }
    .match-step-title {
        font-size: 14px;
        font-weight: 600;
        color: #101828;
        line-height: 1.3;
    }
    .match-step-detail {
        font-size: 12px;
        color: #475467;
        line-height: 1.4;
    }
    .match-step.step-done {
        background-color: #f0fdf4;
        border-bottom: 3px solid #22c55e;
    }
    .match-step.step-done .match-step-num {
        color: #16a34a;
    }
    .match-step.step-active {
        background-color: #eff6ff;
        border-bottom: 3px solid #3b82f6;
    }
    .match-step.step-active .match-step-num {
        color: #2563eb;
    }
    .match-step.step-pending {
        background-color: #fafafa;
        border-bottom: 3px solid #e5e7eb;
    }
    .match-step-badge {
        display: inline-flex;
        align-items: center;
        gap: 4px;
        padding: 2px 8px;
        border-radius: 10px;
        font-size: 11px;
        font-weight: 600;
        width: fit-content;
        margin-top: 2px;
    }
    .badge-done {
        background-color: #dcfce7;
        color: #15803d;
    }
    .badge-warning {
        background-color: #fef3c7;
        color: #92400e;
    }
    .badge-empty {
        background-color: #f3f4f6;
        color: #6b7280;
    }
    .badge-count {
        background-color: #dbeafe;
        color: #1d4ed8;
    }

    /* Guide Box */
    .match-guide-box {
        background: #ffffff;
        border: 1px solid #e0e7ff;
        border-radius: 8px;
        padding: 20px 24px;
        margin-bottom: 16px;
    }
    .match-guide-box h4 {
        margin: 0 0 12px 0;
        color: #1e40af;
        font-size: 15px;
    }
    .match-guide-box ol {
        margin: 0;
        padding-left: 20px;
        color: #374151;
        font-size: 13px;
        line-height: 1.8;
    }
    .match-guide-box ol li {
        margin-bottom: 4px;
    }
    .match-guide-box ol li strong {
        color: #111827;
    }


    /* CRM Status Cards */
    .crm-status-strip {
        display: flex;
        gap: 8px;
        margin-bottom: 16px;
    }
    .crm-status-card {
        flex: 1;
        background: #ffffff;
        border: 1px solid #eaecf0;
        border-radius: 8px;
        padding: 12px 16px;
        box-shadow: 0 1px 2px rgba(16, 24, 40, 0.04);
    }
    .crm-status-card-title {
        font-size: 11px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: #475467;
        margin-bottom: 4px;
    }
    .crm-status-card-value {
        font-size: 1.5rem;
        font-weight: 700;
        color: #101828;
        line-height: 1.2;
    }
    .crm-status-card-sub {
        font-size: 11px;
        color: #64748b;
        margin-top: 2px;
    }
    .crm-status-card.card-highlight {
        border-left: 3px solid #f59e0b;
        background-color: #fffbeb;
    }
    .crm-status-card.card-success {
        border-left: 3px solid #22c55e;
        background-color: #f0fdf4;
    }

    /* CRM Flow Guide */
    .crm-flow-guide {
        background: #ffffff;
        border: 1px solid #e0e7ff;
        border-radius: 8px;
        padding: 20px 24px;
        margin-bottom: 16px;
    }
    .crm-flow-guide h4 {
        margin: 0 0 10px 0;
        color: #1e40af;
        font-size: 14px;
    }
    .crm-flow-guide .flow-steps {
        display: flex;
        align-items: center;
        gap: 0;
        flex-wrap: wrap;
    }
    .crm-flow-guide .flow-step {
        display: flex;
        align-items: center;
        gap: 8px;
        padding: 8px 14px;
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 6px;
        font-size: 12px;
        color: #334155;
        font-weight: 500;
    }
    .crm-flow-guide .flow-arrow {
        font-size: 16px;
        color: #94a3b8;
        padding: 0 6px;
    }
    .crm-flow-guide .flow-step .step-num {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 20px;
        height: 20px;
        background: #3b82f6;
        color: #ffffff;
        border-radius: 50%;
        font-size: 11px;
        font-weight: 700;
    }

    /* Chat thread improvements */
    .chat-bubble-outbound {
        background-color: #ecfdf3;
        border: 1px solid #d1fadf;
        border-radius: 8px 8px 2px 8px;
        padding: 10px 14px;
        margin-bottom: 8px;
        color: #027a48;
        font-size: 13px;
        line-height: 1.5;
        max-width: 85%;
    }
    .chat-bubble-inbound {
        background-color: #f2f4f7;
        border: 1px solid #eaecf0;
        border-radius: 8px 8px 8px 2px;
        padding: 10px 14px;
        margin-bottom: 8px;
        color: #344054;
        font-size: 13px;
        line-height: 1.5;
        max-width: 85%;
    }

    /* Sidebar Styling */
    section[data-testid="stSidebar"] {
        background-color: #ffffff;
        border-right: 1px solid #eaecf0;
    }
    .user-chip {
        display: flex;
        align-items: center;
        gap: 10px;
        padding: 8px 10px;
        background: #f8fafc;
        border: 1px solid #eaecf0;
        border-radius: 6px;
        margin-bottom: 14px;
    }
    .user-avatar {
        width: 28px;
        height: 28px;
        border-radius: 50%;
        background: #0284c7;
        color: #ffffff;
        display: flex;
        align-items: center;
        justify-content: center;
        font-weight: 600;
        font-size: 11px;
    }

    /* Tabs Styling (Apify Pill Style) */
    div[data-baseweb="tab-list"] {
        gap: 6px;
        border-bottom: 1px solid #eaecf0;
        margin-bottom: 18px;
    }
    button[data-baseweb="tab"] {
        border-radius: 6px 6px 0 0;
        padding: 8px 16px;
        font-size: 13px;
        font-weight: 500;
        color: #475467;
    }
    button[data-baseweb="tab"][aria-selected="true"] {
        color: #0284c7 !important;
        font-weight: 600;
        border-bottom: 2px solid #0284c7 !important;
    }

    /* Phase 3 CRM Badges & Chat Bubbles */
    .apify-badge-drafted { background-color: #f1f5f9; color: #475569; border: 1px solid #cbd5e1; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 500; }
    .apify-badge-sent { background-color: #eff6ff; color: #1d4ed8; border: 1px solid #bfdbfe; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 500; }
    .apify-badge-followup1, .apify-badge-followup2 { background-color: #fefce8; color: #854d0e; border: 1px solid #fef08a; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 500; }
    .apify-badge-active { background-color: #f0fdf4; color: #15803d; border: 1px solid #bbf7d0; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 500; }
    .apify-badge-handover { background-color: #fff7ed; color: #c2410c; border: 1px solid #fed7aa; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; }
    .apify-badge-won { background-color: #ecfdf5; color: #047857; border: 1px solid #a7f3d0; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; }
    .apify-badge-lost { background-color: #f8fafc; color: #94a3b8; border: 1px solid #e2e8f0; padding: 2px 8px; border-radius: 4px; font-size: 11px; }
    .apify-badge-optout { background-color: #fef2f2; color: #b91c1c; border: 1px solid #fecaca; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 500; }
    
    .chat-bubble-outbound {
        background-color: #ecfdf3;
        border: 1px solid #d1fadf;
        border-radius: 8px 8px 2px 8px;
        padding: 10px 14px;
        margin-bottom: 8px;
        color: #027a48;
        font-size: 13px;
        line-height: 1.5;
        max-width: 85%;
    }
    .chat-bubble-inbound {
        background-color: #f2f4f7;
        border: 1px solid #eaecf0;
        border-radius: 8px 8px 8px 2px;
        padding: 10px 14px;
        margin-bottom: 8px;
        color: #344054;
        font-size: 13px;
        line-height: 1.4;
    }

    /* Links in Tables */
    a {
        color: #0284c7;
        text-decoration: none;
        font-weight: 500;
    }
    a:hover {
        text-decoration: underline;
    }

    /* Spacing */
    .block-container {
        padding-top: 1.5rem;
        padding-bottom: 2rem;
    }
    hr {
        margin: 1.2rem 0;
        border-color: #eaecf0;
    }
</style>
""", unsafe_allow_html=True)

# ================= INIT DATABASE & GATEWAY =================
conn = db.connect()
gateway = LLMGateway(conn)

# ================= SIDEBAR (APIFY CONSOLE STYLE) =================
with st.sidebar:
    # User / Organization Chip (seperti di screenshot Apify)
    st.markdown("""
        <div class="user-chip">
            <div class="user-avatar">GT</div>
            <div>
                <div style="font-size:12px; font-weight:600; color:#101828;">GoTani Lead Agent</div>
                <div style="font-size:11px; color:#64748b;">Production Console</div>
            </div>
        </div>
    """, unsafe_allow_html=True)

    # --- Section: Quick Start ---
    st.markdown("<div style='font-size:11px; font-weight:600; color:#94a3b8; text-transform:uppercase; margin-bottom:8px;'>Quick Actions</div>", unsafe_allow_html=True)
    if st.button("Load Demo Dataset", use_container_width=True):
        with st.spinner("Loading demo dataset..."):
            subprocess.run([sys.executable, "seed_demo.py"], cwd=str(Path(__file__).parent))
            st.session_state["notify_success"] = "Demo dataset loaded successfully! Farmer, buyer, and smart pool data are ready to test."
            st.toast("Demo dataset loaded!", icon="✅")
            st.rerun()

    c_btn2, c_btn3 = st.columns(2)
    with c_btn2:
        if st.button("Reset All Data", use_container_width=True):
            tables = ["messages", "conversations", "match_items", "matches", "listings", "raw_items", "runs"]
            for t in tables:
                try:
                    conn.execute(f"DELETE FROM {t}")
                except Exception:
                    pass
            conn.commit()
            try:
                conn.execute("VACUUM")
            except Exception:
                pass
            for k in ["spec_notice", "notify_success", "notify_info"]:
                st.session_state.pop(k, None)
            st.session_state["notify_success"] = "All leads, raw scraped data, matches, and CRM conversations have been cleared."
            st.toast("Database cleared successfully!", icon="🗑️")
            st.rerun()
    with c_btn3:
        if st.button("Deduplicate", use_container_width=True):
            with st.spinner("Checking duplicates..."):
                d_res = deduplicate_database(conn)
                st.session_state["notify_info"] = f"Deduplication complete: {d_res['duplicates_marked']} duplicate entries hidden."
                st.toast("Deduplication check complete!", icon="🔍")
            st.rerun()

    st.divider()

    # --- Section: New Campaign Spec ---
    st.markdown("<div style='font-size:11px; font-weight:700; color:#475569; text-transform:uppercase; letter-spacing:0.5px; margin-bottom:10px;'>Marketplace Intelligence</div>", unsafe_allow_html=True)

    # Inisialisasi template bawaan jika belum ada
    if "draft_spec" not in st.session_state:
        default_cid = new_campaign_id(conn)
        default_spec = CampaignSpec(
            campaign_id=default_cid,
            goal="find_supply",
            target_entity="petani / kelompok tani",
            business_context="Pencarian pasokan panen",
        )
        default_spec.product.name = "Melon"
        default_spec.product.synonyms = ["melon", "madesta", "golden"]
        default_spec.location.include = ["Jawa Timur"]
        default_spec.location.priority = ["Jombang", "Kediri", "Blitar", "Malang"]
        default_spec.volume.min = 500.0
        st.session_state["draft_spec"] = default_spec.to_json()

    from agent.campaign import KNOWN_COMMODITIES

    commodity_list = sorted(KNOWN_COMMODITIES.keys())
    commodity_display = [k.title() for k in commodity_list]

    province_options = [
        "Jawa Timur", "Jawa Tengah", "Jawa Barat", "DKI Jakarta",
        "Banten", "DI Yogyakarta", "Bali", "NTB", "NTT",
        "Sumatera Utara", "Sumatera Barat", "Sumatera Selatan", "Riau",
        "Lampung", "Kalimantan Selatan", "Kalimantan Timur",
        "Sulawesi Selatan", "Sulawesi Utara", "Papua",
    ]

    # Session defaults (kunci unik agar state tidak mental / jumping)
    goal_options = ["Find Supply (Farmers)", "Find Demand (Buyers)"]
    if "marketplace_goal" not in st.session_state:
        st.session_state["marketplace_goal"] = goal_options[0]

    # 1. Kategori Transaksi (Radio vertikal stabil dengan key bawaan Streamlit)
    goal_choice = st.radio(
        "Market Category",
        options=goal_options,
        key="marketplace_goal",
        label_visibility="collapsed",
    )

    # 2. Input Komoditas Utama (Search bar ala marketplace)
    if "marketplace_commodity" not in st.session_state:
        st.session_state["marketplace_commodity"] = "Melon"
    if st.session_state["marketplace_commodity"] not in commodity_display:
        st.session_state["marketplace_commodity"] = commodity_display[0]

    selected_commodity = st.selectbox(
        "Commodity",
        options=commodity_display,
        key="marketplace_commodity",
        help="Type or select the agricultural commodity to search.",
    )

    # 3. Filter Wilayah
    if "marketplace_provinces" not in st.session_state:
        st.session_state["marketplace_provinces"] = ["Jawa Timur"]

    selected_provinces = st.multiselect(
        "Target Regions",
        options=province_options,
        key="marketplace_provinces",
        help="Select regions for lead search.",
    )

    # 4. Filter Lanjutan (Collapsible, rapi seperti filter marketplace)
    with st.expander("Advanced Filters", expanded=False):
        com_key = selected_commodity.lower()
        synonyms = KNOWN_COMMODITIES.get(com_key, [])
        variety_options = [s.title() for s in synonyms if s.lower() != com_key]

        if variety_options:
            selected_varieties = st.multiselect(
                "Specific Varieties",
                options=variety_options,
                key=f"marketplace_var_{com_key}",
                help="Leave empty to search all varieties.",
            )
        else:
            selected_varieties = []

        min_volume = st.number_input(
            "Min Volume (kg)",
            min_value=0,
            max_value=1_000_000,
            value=0,
            step=100,
            key="marketplace_min_vol",
            help="Minimum volume filter. Set 0 for no limit.",
        )

        max_price = st.number_input(
            "Max Price Limit (Rp/kg)",
            min_value=0,
            max_value=10_000_000,
            value=0,
            step=1000,
            key="marketplace_max_price",
            help="Set 0 for no price limit.",
        )

        freshness_days = st.slider(
            "Post Freshness (days)",
            min_value=7,
            max_value=90,
            value=30,
            step=1,
            key="marketplace_freshness",
            help="Only display posts from the last X days. Default: 30 days.",
        )

    # 5. Tombol Pencarian Marketplace
    if st.button("Search Leads", type="primary", use_container_width=True):
        cid = new_campaign_id(conn)
        goal_val = "find_supply" if "Supply" in goal_choice or "Petani" in goal_choice else "find_demand"
        target_entity_val = "petani / kelompok tani" if goal_val == "find_supply" else "toko buah / distributor / pengepul"

        spec = CampaignSpec(
            campaign_id=cid,
            goal=goal_val,
            target_entity=target_entity_val,
            business_context=f"Pencarian {'pasokan' if goal_val == 'find_supply' else 'permintaan'} {selected_commodity}",
        )
        spec.product.name = selected_commodity
        com_key = selected_commodity.lower()
        syns = KNOWN_COMMODITIES.get(com_key, [])
        spec.product.synonyms = [s.lower() for s in syns] if syns else [com_key]
        if 'selected_varieties' in locals() and selected_varieties:
            spec.product.attributes["variety"] = [v.lower() for v in selected_varieties]
        spec.location.include = selected_provinces  # Kosong = seluruh Indonesia
        
        min_v = min_volume if 'min_volume' in locals() else 0
        spec.volume.min = float(min_v) if min_v > 0 else None
        
        max_p = max_price if 'max_price' in locals() else 0
        if max_p > 0:
            spec.price.max = float(max_p)
        
        fd = freshness_days if 'freshness_days' in locals() else 30
        spec.freshness_days = fd

        st.session_state["draft_spec"] = spec.to_json()
        st.session_state["spec_notice"] = {
            "product": spec.product.name,
            "goal": "Find Supply" if goal_val == "find_supply" else "Find Demand",
            "location": ", ".join(spec.location.include),
            "volume": f"{spec.volume.min:g} kg" if spec.volume.min else "Any",
            "mode": "Market Search",
            "fallback": False,
        }

        save_campaign(conn, spec)
        try:
            with st.status("Running Market Intelligence Pipeline...", expanded=True) as status_box:
                def on_progress(step_title: str, detail_text: str):
                    status_box.write(f"[{datetime.now().strftime('%H:%M:%S')}] **{step_title}**: {detail_text}")

                pipe = Pipeline(spec, progress_callback=on_progress)
                pipe_res = asyncio.run(pipe.run()) or {}
                raw_cnt = pipe_res.get("raw_items_saved", 0)
                lead_cnt = pipe_res.get("new_leads_saved", 0)
                status_box.update(label="Search Complete", state="complete", expanded=False)
                if raw_cnt == 0:
                    st.session_state["notify_info"] = f"Search completed for '{spec.product.name}'. No new posts found within 35 days. Click 'Load Demo Dataset' to inspect simulated leads."
                else:
                    st.session_state["notify_success"] = f"Search successful. Found {raw_cnt} raw posts and {lead_cnt} verified leads for '{spec.product.name}'."
                time.sleep(1)
                st.rerun()
        except Exception as e:
            st.error(f"Pipeline execution error: {e}")

    # Indikator ringkas spesifikasi aktif
    notice = st.session_state.get("spec_notice")
    if notice:
        st.markdown(f"""
        <div style="background:#f8fafc; border:1px solid #e2e8f0; border-radius:6px; padding:8px 10px; margin-top:8px; margin-bottom:8px; font-size:11px; color:#334155; line-height:1.5;">
            <div style="font-weight:600; color:#0f172a; margin-bottom:2px;">Active Filter:</div>
            Commodity: <b>{notice['product']}</b> ({notice['goal']})<br>
            Regions: {notice['location']} | Min. {notice['volume']}
        </div>
        """, unsafe_allow_html=True)

    # --- Section: Handoff Detection ---
    st.divider()
    handoff_flag = Path("./data/HANDOFF_WAITING")
    if handoff_flag.exists():
        st.error("Manual Verification Required")
        st.caption(handoff_flag.read_text(encoding="utf-8"))
        if st.button("Resume System"):
            handoff_flag.unlink(missing_ok=True)
            st.success("Confirmation received, system resumed.")
            st.rerun()

    # --- Section: Inbound Call Assistant (Caller ID) ---
    st.markdown("<div style='font-size:11px; font-weight:600; color:#94a3b8; text-transform:uppercase; margin-bottom:8px;'>Inbound Call Assistant</div>", unsafe_allow_html=True)
    st.caption("Instant caller intelligence and profile lookup for sales.")
    caller_input = st.text_input("Phone Number", placeholder="e.g. 081234567890", key="side_caller_phone", label_visibility="collapsed")
    if caller_input:
        caller_res = lookup_caller(conn, caller_input)
        if not caller_res:
            st.warning("Invalid phone number format.")
        elif not caller_res.get("found"):
            if caller_res.get("is_opted_out"):
                st.error("⛔ DNC / OPT-OUT: This contact requested Do-Not-Contact!")
            st.info(caller_res.get("message"))
            with st.expander("Talking Points (New Contact)", expanded=True):
                for p in caller_res["talking_points"]:
                    st.markdown(f"- {p}")
        else:
            if caller_res.get("is_opted_out"):
                st.error("⛔ DNC / OPT-OUT: This number is listed in suppression registry!")
            
            c_info = caller_res.get("conversation")
            st.success(f"{caller_res['name']} ({caller_res['role']})")
            st.caption(f"Commodity: {caller_res['product']} | Location: {caller_res['location']}")
            
            if c_info:
                c_st = c_info.get("state", "").upper()
                if c_info.get("state") == "handover_pending":
                    st.error(f"🚨 CRM: HANDOVER PENDING · {c_info.get('summary_text', '')}")
                else:
                    st.info(f"CRM Status: `{c_st}` · {c_info.get('summary_text') or 'Conversation recorded'}")

            with st.expander("Caller Talking Points", expanded=True):
                for pt in caller_res["talking_points"]:
                    st.markdown(f"- {pt}")

    # --- Section: Usage & Resource Meter (Sesuai Screenshot Apify) ---
    st.divider()
    try:
        usage = gateway.usage_today()
        cost_val = usage["cost_usd"]
        budget_val = settings.llm_daily_budget_usd
        st.markdown(f"""
            <div style="background:#f8fafc; border:1px solid #eaecf0; border-radius:6px; padding:10px; font-size:12px;">
                <div style="display:flex; justify-content:space-between; margin-bottom:4px;">
                    <span style="color:#64748b;">Usage</span>
                    <span style="font-weight:600; color:#0f172a;">${cost_val:.3f} / ${budget_val:.2f}</span>
                </div>
                <div style="display:flex; justify-content:space-between; color:#64748b; margin-bottom:6px;">
                    <span>Requests</span>
                    <span>{usage['requests']} calls</span>
                </div>
                <div style="font-size:11px; color:#0284c7; font-weight:600;">Plan: Free Developer Tier</div>
            </div>
        """, unsafe_allow_html=True)
    except Exception:
        pass


# ================= MAIN AREA: CONSOLE VIEW =================

# 1. Breadcrumb Bar (Apify Console style)
st.markdown("""
    <div class="apify-breadcrumb">
        <span>GoTani Console</span>
        <span>/</span>
        <span>Actors</span>
        <span>/</span>
        <span style="color:#0f172a; font-weight:600;">Google Search Results & FB Lead Engine</span>
        <span class="apify-pill apify-pill-single" style="font-size:11px;">Actor</span>
    </div>
""", unsafe_allow_html=True)

# 2. Status Bar Strip (Sesuai Screenshot 1 & 3 Apify)
try:
    total_raw = conn.execute("SELECT COUNT(*) FROM raw_items").fetchone()[0]
    total_leads = conn.execute("SELECT COUNT(*) FROM listings WHERE duplicate_of IS NULL").fetchone()[0]
    high_conf = conn.execute("SELECT COUNT(*) FROM listings WHERE confidence >= 80 AND duplicate_of IS NULL").fetchone()[0]
    total_matches = conn.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
    total_convs = conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
    total_handovers = conn.execute("SELECT COUNT(*) FROM conversations WHERE state = 'handover_pending'").fetchone()[0]
    total_won = conn.execute("SELECT COUNT(*) FROM conversations WHERE state = 'closed_won'").fetchone()[0]
    usage = gateway.usage_today()
except Exception:
    total_raw, total_leads, high_conf, total_matches, total_convs, total_handovers, total_won = 0, 0, 0, 0, 0, 0, 0
    usage = {"cost_usd": 0.0, "requests": 0}

last_run_time = datetime.now().strftime("%Y-%m-%d %H:%M")

st.markdown(f"""
    <div class="apify-status-bar">
        <div class="apify-status-left">
            <span class="apify-pill apify-pill-success">
                Succeeded
            </span>
            <span style="font-size:13px; font-weight:600; color:#101828;">Dataset Ready</span>
            <span class="apify-meta-item">Total Posts: <b>{total_raw}</b></span>
            <span class="apify-meta-item">Valid Leads: <b>{total_leads}</b></span>
            <span class="apify-meta-item">Matches: <b>{total_matches}</b></span>
            <span class="apify-meta-item">CRM Convs: <b>{total_convs}</b></span>
            <span class="apify-meta-item">Cost: <b>${usage['cost_usd']:.3f}</b></span>
            <span class="apify-meta-item">Time: <b>{last_run_time}</b></span>
        </div>
        <div>
            <span style="font-size:12px; color:#0284c7; font-weight:600;">Status: Operational Normal</span>
        </div>
    </div>
""", unsafe_allow_html=True)

# Notifikasi Aksi (Dismissable dengan tombol ✕ di dalam area alert)
if st.session_state.get("notify_success"):
    c_alert, c_btn = st.columns([0.96, 0.04])
    with c_alert:
        st.markdown(
            f'<div class="notify-marker-success" style="display:none;"></div>'
            f'<div style="color:#027a48; font-size:13px; font-weight:500; line-height:1.4;">'
            f'{st.session_state["notify_success"]}'
            f'</div>',
            unsafe_allow_html=True,
        )
    with c_btn:
        st.markdown('<div class="notify-close-marker" style="display:none;"></div>', unsafe_allow_html=True)
        if st.button("✕", key="btn_close_notify_success", help="Dismiss notification"):
            del st.session_state["notify_success"]
            st.rerun()

if st.session_state.get("notify_info"):
    c_alert, c_btn = st.columns([0.96, 0.04])
    with c_alert:
        st.markdown(
            f'<div class="notify-marker-info" style="display:none;"></div>'
            f'<div style="color:#175cd3; font-size:13px; font-weight:500; line-height:1.4;">'
            f'{st.session_state["notify_info"]}'
            f'</div>',
            unsafe_allow_html=True,
        )
    with c_btn:
        st.markdown('<div class="notify-close-marker" style="display:none;"></div>', unsafe_allow_html=True)
        if st.button("✕", key="btn_close_notify_info", help="Dismiss notification"):
            del st.session_state["notify_info"]
            st.rerun()

if st.session_state.get("notify_match"):
    c_alert, c_btn = st.columns([0.96, 0.04])
    with c_alert:
        st.markdown(
            f'<div class="notify-marker-success" style="display:none;"></div>'
            f'<div style="color:#027a48; font-size:13px; font-weight:500; line-height:1.4;">'
            f'{st.session_state["notify_match"]}'
            f'</div>',
            unsafe_allow_html=True,
        )
    with c_btn:
        st.markdown('<div class="notify-close-marker" style="display:none;"></div>', unsafe_allow_html=True)
        if st.button("✕", key="btn_close_notify_match_global", help="Dismiss notification"):
            del st.session_state["notify_match"]
            st.rerun()

if st.session_state.get("notify_match_warning"):
    c_alert, c_btn = st.columns([0.96, 0.04])
    with c_alert:
        st.markdown(
            f'<div class="notify-marker-warning" style="display:none;"></div>'
            f'<div style="color:#b54708; font-size:13px; font-weight:500; line-height:1.4;">'
            f'{st.session_state["notify_match_warning"]}'
            f'</div>',
            unsafe_allow_html=True,
        )
    with c_btn:
        st.markdown('<div class="notify-close-marker" style="display:none;"></div>', unsafe_allow_html=True)
        if st.button("✕", key="btn_close_notify_match_warn", help="Dismiss notification"):
            del st.session_state["notify_match_warning"]
            st.rerun()

# 3. Metric Summary Cards (Apify Dashboard Widget Style)
col_m1, col_m2, col_m3, col_m4, col_m5 = st.columns(5)
col_m1.metric("Raw Posts", f"{total_raw:,}", help="Total raw posts scraped from Google Search Scraper.")
col_m2.metric("Valid Leads", f"{total_leads:,}", help="Total validated and normalized lead profiles.")
col_m3.metric("High Conf", f"{high_conf:,}", help="Verified leads with confidence score ≥ 80%.")
col_m4.metric("Matches", f"{total_matches:,}", help="Identified supply and demand matchmaking recommendations.")
col_m5.metric("Sales CRM", f"{total_convs:,}", help="Active conversation threads in Sales CRM.")

st.write("") # Spacer

# 4. Main Tabs Navigation (Apify Output Style)
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    f"Verified Leads ({total_leads})",
    f"Matchmaking & Pooling ({total_matches})",
    f"Sales Inbox CRM ({total_convs})",
    f"Raw Data Log ({total_raw})",
    "Campaign History",
])


# ================= TAB 1: VERIFIED LEADS =================
with tab1:
    fc1, fc2, fc3, fc4 = st.columns([1.5, 1.5, 1, 1])
    with fc1:
        min_rel = st.slider("Min Relevance Score", 0, 100, 65, 5)
    with fc2:
        min_conf = st.slider("Min Confidence Score", 0, 100, 50, 5)
    with fc3:
        status_filter = st.selectbox("Review Status", ["All", "pending", "approved", "rejected"], index=0)
    with fc4:
        platform_filter = st.selectbox("Data Source", ["All", "Google Maps", "Facebook"], index=0)
    st.caption("Displaying high-quality verified leads (Relevance ≥ 65%, Confidence ≥ 50%). Move sliders to 0 to inspect all raw records.")

    query_str = """
        SELECT
            l.id,
            l.entity_name AS Nama,
            l.intent AS Intent,
            l.product AS Komoditas,
            l.attributes_json AS Atribut,
            l.volume_kg AS Volume_Kg,
            l.volume_unit AS Volume_Unit,
            l.price_per_kg AS Harga_Kg,
            l.price_unit AS Price_Unit,
            l.location_text AS Lokasi,
            l.contact_phone AS Telepon,
            l.relevance AS Rel_Score,
            l.confidence AS Conf_Score,
            l.score_reasons_json AS Alasan_Skor,
            l.review_status AS Review,
            l.extractor AS Extractor,
            r.platform AS Platform,
            r.posted_at AS Tgl_Post,
            r.url AS URL
        FROM listings l
        JOIN raw_items r ON l.raw_item_id = r.id
        WHERE l.relevance >= ? AND l.confidence >= ? AND l.duplicate_of IS NULL
          AND (r.posted_at IS NULL OR r.posted_at >= date('now', '-' || ? || ' days'))
    """
    # Dynamic: filter tahun stale HANYA untuk data Facebook (bukan Google Maps)
    # Alasan: alamat bisnis Google Maps bisa mengandung angka tahun (misal "Jl. Raya 2020")
    _cur_yr_app = datetime.now().year
    for _sy in range(2018, _cur_yr_app):
        query_str += f" AND (r.platform = 'google_maps' OR r.raw_text NOT LIKE '%{_sy}%')"
    query_str += """
    """
    _fd_val = freshness_days if 'freshness_days' in locals() else 30
    params = [min_rel, min_conf, str(_fd_val)]
    if status_filter != "All" and status_filter != "Semua":
        query_str += " AND l.review_status = ?"
        params.append(status_filter)
    if platform_filter == "Google Maps":
        query_str += " AND r.platform = 'google_maps'"
    elif platform_filter == "Facebook":
        query_str += " AND r.platform = 'facebook'"
    query_str += " ORDER BY l.relevance DESC, l.confidence DESC"

    df_leads = pd.read_sql_query(query_str, conn, params=tuple(params))

    if df_leads.empty:
        st.info("No leads currently match the active filter criteria.")
    else:
        def format_display_phone(phone_raw):
            import re
            if phone_raw is None or pd.isna(phone_raw):
                return "-"
            p = str(phone_raw).strip()
            if not p or p.lower() in ("none", "nan", "null", ""):
                return "-"
            # Jika ada beberapa nomor (dipisah koma), ambil nomor pertama
            first_p = p.split(",")[0].strip()
            digits = re.sub(r"\D", "", first_p)
            if digits.startswith("62") and len(digits) >= 10:
                digits = "0" + digits[2:]
            if len(digits) == 10:
                return f"{digits[:4]}-{digits[4:7]}-{digits[7:]}"
            elif len(digits) == 11:
                return f"{digits[:4]}-{digits[4:7]}-{digits[7:]}"
            elif len(digits) >= 12:
                return f"{digits[:4]}-{digits[4:8]}-{digits[8:12]}"
            return first_p

        df_leads["Kontak"] = df_leads["Telepon"].apply(format_display_phone)

        # Format volume + unit asli (jika ada)
        def format_volume(row):
            vol = row.get("Volume_Kg")
            unit = row.get("Volume_Unit")
            if vol is None or (hasattr(vol, '__class__') and vol.__class__.__name__ != 'str' and pd.isna(vol)):
                return "-"
            try:
                v = float(vol)
                if v <= 0:
                    return "-"
            except (ValueError, TypeError):
                return "-"
            u = str(unit).strip() if (unit is not None and not pd.isna(unit) and str(unit).lower() not in ("none", "nan", "")) else "kg"
            return f"{v:g} {u}"

        df_leads["Volume"] = df_leads.apply(format_volume, axis=1)

        # Format harga + unit asli (jika ada)
        def format_harga(row):
            price = row.get("Harga_Kg")
            unit = row.get("Price_Unit")
            if price is None or (hasattr(price, '__class__') and price.__class__.__name__ != 'str' and pd.isna(price)):
                # Cek apakah ada harga non-kg di attributes
                return "-"
            try:
                p = float(price)
                if p <= 0:
                    return "-"
            except (ValueError, TypeError):
                return "-"
            u = str(unit).strip() if (unit is not None and not pd.isna(unit) and str(unit).lower() not in ("none", "nan", "")) else "kg"
            return f"Rp {p:,.0f}/{u}"

        df_leads["Harga"] = df_leads.apply(format_harga, axis=1)
        # Format tanggal posting (human-readable)
        def format_tgl_post(dt_str):
            if dt_str is None or pd.isna(dt_str) or str(dt_str).strip() in ("", "None", "nan"):
                return "-"
            s = str(dt_str).strip()[:10]
            try:
                from datetime import datetime as _dtp
                dt = _dtp.strptime(s, "%Y-%m-%d")
                # Format: "21 Okt 2026"
                bulan = ["Jan","Feb","Mar","Apr","Mei","Jun","Jul","Agt","Sep","Okt","Nov","Des"]
                return f"{dt.day} {bulan[dt.month-1]} {dt.year}"
            except Exception:
                return s
        df_leads["Tgl_Post"] = df_leads["Tgl_Post"].apply(format_tgl_post)

        df_leads["Nama"] = df_leads["Nama"].apply(lambda n: str(n).strip() if (n is not None and not pd.isna(n) and str(n).lower() not in ("none", "nan", "")) else "-")
        df_leads["Lokasi"] = df_leads["Lokasi"].apply(lambda l: str(l).strip() if (l is not None and not pd.isna(l) and str(l).lower() not in ("none", "nan", "")) else "-")

        def make_lead_wa_link(row):
            phone = row.get("Telepon")
            if phone is None or pd.isna(phone):
                return None
            phone_str = str(phone).strip()
            if not phone_str or phone_str.lower() in ("nan", "none", "null", "-", ""):
                return None
            
            raw_name = row.get("Nama")
            name_val = str(raw_name).strip() if (raw_name and raw_name != "-") else None
            
            raw_loc = row.get("Lokasi")
            loc_val = str(raw_loc).strip() if (raw_loc and raw_loc != "-") else None
            
            raw_prod = row.get("Commodity")
            prod_val = str(raw_prod).strip() if (raw_prod is not None and not pd.isna(raw_prod)) else "hasil tani"
            
            raw_vol = row.get("Volume_Kg")
            vol_val = None
            if raw_vol is not None and not pd.isna(raw_vol):
                try:
                    vol_val = float(raw_vol) if float(raw_vol) > 0 else None
                except (ValueError, TypeError):
                    vol_val = None
            
            raw_price = row.get("Harga_Kg")
            price_val = None
            if raw_price is not None and not pd.isna(raw_price):
                try:
                    price_val = float(raw_price) if float(raw_price) > 0 else None
                except (ValueError, TypeError):
                    price_val = None

            # Pilih template outreach berdasarkan kategori lead
            intent_val = row.get("Intent", "")
            platform_val = row.get("Platform", "")
            
            if intent_val == "demand" or platform_val == "google_maps":
                # Data pembeli (toko/distributor dari Google Maps)
                attrs = db.loads(row.get("Atribut", "{}"), default={})
                gmeta = attrs.get("_gmaps_meta", {}) if isinstance(attrs, dict) else {}
                msg = draft_buyer_outreach_for_lead(
                    buyer_name=name_val,
                    commodity=prod_val,
                    buyer_location=loc_val,
                    buyer_category=gmeta.get("category"),
                    rating=gmeta.get("rating"),
                )
            else:
                # Data petani/penjual (dari Facebook/web)
                msg = draft_farmer_outreach_for_lead(
                    farmer_name=name_val,
                    commodity=prod_val,
                    farmer_location=loc_val,
                    volume_kg=vol_val,
                    price_per_kg=price_val,
                )
            return format_wa_url(phone_str, msg)
        
        df_leads["Chat_WA"] = df_leads.apply(make_lead_wa_link, axis=1)
        
        def extract_variety(attr_json):
            data = db.loads(attr_json, default={})
            if not data or not isinstance(data, dict):
                return ""
            variety = data.get("variety", [])
            grade = data.get("grade")
            res = []
            if variety: res.append(f"Varietas: {', '.join(variety)}")
            if grade: res.append(f"Grade: {grade}")
            return " | ".join(res)
                
        df_leads["Kualitas"] = df_leads["Atribut"].apply(extract_variety)
        
        def detect_link_label(url_str):
            if not url_str or not isinstance(url_str, str): return "Buka Sumber"
            u = str(url_str).lower()
            if "/posts/" in u or "/permalink/" in u or "story.php" in u:
                return "Postingan Spesifik"
            elif "/groups/" in u:
                return "Grup Komunitas"
            return "Buka Sumber"
            
        df_leads["Label_Sumber"] = df_leads["URL"].apply(detect_link_label)

        # Format sumber data (Google Maps vs Facebook)
        def format_sumber(row):
            platform = row.get("Platform", "")
            if platform == "google_maps":
                # Cek rating dari attributes_json
                attrs = db.loads(row.get("Atribut", "{}"), default={})
                meta = attrs.get("_gmaps_meta", {}) if isinstance(attrs, dict) else {}
                rating = meta.get("rating")
                reviews = meta.get("reviews")
                parts = ["Google Maps"]
                if rating:
                    parts.append(f"{rating}/5")
                if reviews and reviews > 0:
                    parts.append(f"({reviews} ulasan)")
                return " ".join(parts)
            elif platform == "facebook":
                return "Facebook"
            return platform or "-"
        df_leads["Sumber"] = df_leads.apply(format_sumber, axis=1)

        # ================= TAB 1 VIEW: REVIEW QUEUE vs TABEL DATA =================
        pending_leads = df_leads[df_leads["Review"] == "pending"]
        approved_count = len(df_leads[df_leads["Review"] == "approved"])
        rejected_count = len(df_leads[df_leads["Review"] == "rejected"])
        pending_count = len(pending_leads)

        # Cek jika ada notifikasi review (toast)
        if "review_feedback" in st.session_state:
            st.toast(st.session_state.pop("review_feedback"))

        # Switcher Mode: Kartu Review (default jika ada pending) vs Tabel Data
        v_col1, v_col2 = st.columns([2.5, 1.5])
        with v_col1:
            view_mode = st.radio(
                "View Mode",
                ["Review Queue (Card Focus)", "Full Data Table"],
                horizontal=True,
                label_visibility="collapsed",
                key="lead_view_mode_selection",
            )

        display_cols = [
            "id", "Commodity", "Kategori", "Volume", "Harga", "Tgl_Post", 
            "Lokasi", "Nama", "Kontak", "Chat_WA", "Sumber", "Rel_Score", "Conf_Score", "Review", "URL"
        ]
        df_leads_display = df_leads.copy()
        df_leads_display["Kategori"] = df_leads_display["Intent"]
        final_cols = [c for c in display_cols if c in df_leads_display.columns]

        # ----------------------------------------------------
        # MODE 1: KARTU REVIEW (FOKUS SELEKSI CEPAT)
        # ----------------------------------------------------
        if view_mode in ["Review Queue (Card Focus)", "Kartu Review (Fokus Seleksi)"]:
            # Statistik ringkas
            st.markdown(f"""
                <div style="display:flex; gap:12px; margin:10px 0 12px 0;">
                    <div style="padding:6px 14px; border-radius:6px; background:#f0fdf4; border:1px solid #bbf7d0;">
                        <span style="font-size:12px; color:#15803d; font-weight:600;">Approved: {approved_count}</span>
                    </div>
                    <div style="padding:6px 14px; border-radius:6px; background:#fef2f2; border:1px solid #fecaca;">
                        <span style="font-size:12px; color:#dc2626; font-weight:600;">Rejected: {rejected_count}</span>
                    </div>
                    <div style="padding:6px 14px; border-radius:6px; background:#fffbeb; border:1px solid #fde68a;">
                        <span style="font-size:12px; color:#d97706; font-weight:600;">Pending: {pending_count}</span>
                    </div>
                </div>
            """, unsafe_allow_html=True)

            # Batch action bar
            ba_c1, ba_c2, ba_c3 = st.columns([1.5, 1.5, 2])
            with ba_c1:
                if st.button("Auto-Approve (Confidence ≥ 80%)", use_container_width=True, help="Automatically approve all pending leads with confidence ≥ 80%"):
                    high_conf_ids = pending_leads[pending_leads["Conf_Score"] >= 80]["id"].tolist()
                    count = 0
                    for lid in high_conf_ids:
                        db.update_review_status(conn, int(lid), "approved", "Auto-approved (confidence >= 80%)")
                        count += 1
                    if count > 0:
                        st.session_state["review_feedback"] = f"{count} leads auto-approved."
                    else:
                        st.session_state["review_feedback"] = "No pending leads with confidence ≥ 80% found."
                    st.rerun()
            with ba_c2:
                if pending_count > 0:
                    if st.button("Reject All Score 0", use_container_width=True, help="Automatically reject all leads with relevance score 0"):
                        zero_ids = pending_leads[pending_leads["Rel_Score"] == 0]["id"].tolist()
                        count = 0
                        for lid in zero_ids:
                            db.update_review_status(conn, int(lid), "rejected", "Auto-rejected (relevansi 0)")
                            count += 1
                        if count > 0:
                            st.session_state["review_feedback"] = f"{count} irrelevant leads auto-rejected."
                        else:
                            st.session_state["review_feedback"] = "No pending leads with score 0 found."
                        st.rerun()

            # Kartu Review Lead
            if pending_count > 0:
                if "review_idx" not in st.session_state:
                    st.session_state["review_idx"] = 0
                if st.session_state["review_idx"] >= pending_count:
                    st.session_state["review_idx"] = 0

                idx = st.session_state["review_idx"]
                current_lead = pending_leads.iloc[idx]
                lead_id = int(current_lead["id"])

                # Progress review
                total_reviewable = len(df_leads)
                reviewed = approved_count + rejected_count
                if total_reviewable > 0:
                    st.progress(reviewed / total_reviewable, text=f"Review Progress: {reviewed}/{total_reviewable} leads ({pending_count} pending remaining)")

                rel_pct = current_lead.get("Rel_Score", 0)
                conf_pct = current_lead.get("Conf_Score", 0)
                rel_color = "#15803d" if rel_pct >= 60 else "#d97706" if rel_pct >= 30 else "#dc2626"
                conf_color = "#15803d" if conf_pct >= 60 else "#d97706" if conf_pct >= 30 else "#dc2626"

                st.markdown(f"""
                    <div style="border:1px solid #e2e8f0; border-radius:12px; padding:18px 22px; margin:8px 0; background:white; box-shadow: 0 1px 3px rgba(0,0,0,0.06);">
                        <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:12px;">
                            <div>
                                <span style="font-size:12px; color:#475569; font-weight:700;">LEAD #{lead_id}</span>
                                <span style="margin-left:8px; padding:2px 8px; border-radius:4px; background:#fef9c3; color:#a16207; font-size:11px; font-weight:600;">PENDING REVIEW</span>
                                <span style="margin-left:8px; font-size:12px; color:#64748b;">Antrean {idx + 1} dari {pending_count}</span>
                            </div>
                            <div style="display:flex; gap:16px;">
                                <div style="text-align:center;">
                                    <div style="font-size:22px; font-weight:700; color:{rel_color}; line-height:1;">{rel_pct}%</div>
                                    <div style="font-size:10px; color:#94a3b8; font-weight:500;">Relevance</div>
                                </div>
                                <div style="text-align:center;">
                                    <div style="font-size:22px; font-weight:700; color:{conf_color}; line-height:1;">{conf_pct}%</div>
                                    <div style="font-size:10px; color:#94a3b8; font-weight:500;">Confidence</div>
                                </div>
                            </div>
                        </div>
                        <div style="font-size:17px; font-weight:700; color:#0f172a; margin-bottom:8px;">
                            {current_lead.get("Nama", "-")}
                        </div>
                        <div style="display:flex; flex-wrap:wrap; gap:8px 20px; margin-bottom:10px; font-size:13px; color:#334155;">
                            <span><b>Commodity:</b> {current_lead.get("Commodity", "-")}</span>
                            <span><b>Volume:</b> {current_lead.get("Volume", "-")}</span>
                            <span><b>Price:</b> {current_lead.get("Harga", "-")}</span>
                            <span><b>Location:</b> {current_lead.get("Lokasi", "-")}</span>
                            <span><b>Contact:</b> {current_lead.get("Kontak", "-")}</span>
                            <span><b>Posted Date:</b> {current_lead.get("Tgl_Post", "-")}</span>
                            <span><b>Source:</b> {current_lead.get("Sumber", "-")}</span>
                        </div>
                    </div>
                """, unsafe_allow_html=True)

                # Preview teks asli (collapsible)
                raw_preview = conn.execute(
                    "SELECT raw_text FROM raw_items WHERE id = (SELECT raw_item_id FROM listings WHERE id = ?)",
                    (lead_id,)
                ).fetchone()
                if raw_preview:
                    preview_text = str(raw_preview[0])[:600]
                    with st.expander("Original Post Content", expanded=False):
                        st.text(preview_text)

                # Skor detail (collapsible)
                raw_reasons = current_lead.get("Alasan_Skor")
                reasons = db.loads(raw_reasons, default={})
                if reasons and isinstance(reasons, dict):
                    with st.expander("Score Breakdown Details", expanded=False):
                        sc_c1, sc_c2 = st.columns(2)
                        with sc_c1:
                            st.markdown("**Relevance Factors:**")
                            for r in reasons.get("relevance", []):
                                st.caption(r)
                        with sc_c2:
                            st.markdown("**Confidence Factors:**")
                            for c_item in reasons.get("confidence", []):
                                st.caption(c_item)

                # Tombol aksi
                act_c1, act_c2, act_c3, act_c4 = st.columns([1.5, 1.5, 1.5, 1])
                with act_c1:
                    if st.button("REJECT", key=f"rv_reject_{lead_id}", use_container_width=True,
                                 help="Reject lead — invalid or irrelevant data"):
                        db.update_review_status(conn, lead_id, "rejected", "")
                        st.session_state["review_feedback"] = f"Lead #{lead_id} rejected."
                        st.rerun()
                with act_c2:
                    if st.button("SKIP", key=f"rv_skip_{lead_id}", use_container_width=True,
                                 help="Skip to review later"):
                        st.session_state["review_idx"] = (idx + 1) % max(pending_count, 1)
                        st.rerun()
                with act_c3:
                    if st.button("APPROVE", key=f"rv_approve_{lead_id}", type="primary", use_container_width=True,
                                 help="Approve lead — verified data ready for sales"):
                        db.update_review_status(conn, lead_id, "approved", "")
                        st.session_state["review_feedback"] = f"Lead #{lead_id} approved."
                        st.rerun()
                with act_c4:
                    wa_link = current_lead.get("Chat_WA")
                    if wa_link and str(wa_link).startswith("http"):
                        st.markdown(f"[Chat WA]({wa_link})")

                # Expander opsional untuk mengintip tabel di bawah
                with st.expander(f"View Complete Data Table ({len(df_leads)} Leads)", expanded=False):
                    csv_leads = df_leads.drop(columns=["Alasan_Skor", "Atribut"], errors="ignore").to_csv(index=False).encode("utf-8")
                    st.download_button(
                        "Export Dataset (CSV)", csv_leads,
                        file_name=f"apify_leads_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                        mime="text/csv",
                        key="btn_dl_csv_inside_card_mode",
                    )
                    st.dataframe(
                        df_leads_display[final_cols],
                        use_container_width=True,
                        hide_index=True,
                    )

            else:
                st.markdown("""
                    <div style="text-align:center; padding:28px; border:1px dashed #d1d5db; border-radius:10px; background:#f9fafb; margin:14px 0;">
                        <div style="font-size:15px; font-weight:600; color:#059669;">All leads matching criteria have been reviewed</div>
                        <div style="font-size:12px; color:#6b7280; margin-top:6px;">Switch to 'Full Data Table' mode above to view full history or export data.</div>
                    </div>
                """, unsafe_allow_html=True)
                st.dataframe(
                    df_leads_display[final_cols],
                    use_container_width=True,
                    hide_index=True,
                )

        # ----------------------------------------------------
        # MODE 2: TABEL DATA LENGKAP (GRID VIEW)
        # ----------------------------------------------------
        else:
            top_c1, top_c2 = st.columns([1.5, 3.5])
            with top_c1:
                csv_leads = df_leads.drop(columns=["Alasan_Skor", "Atribut"], errors="ignore").to_csv(index=False).encode("utf-8")
                st.download_button(
                    "Export Dataset (CSV)", csv_leads,
                    file_name=f"apify_leads_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                    mime="text/csv",
                    key="btn_dl_csv_table_mode",
                )

            st.dataframe(
                df_leads_display[final_cols],
                use_container_width=True,
                hide_index=True,
                column_config={
                    "id": st.column_config.NumberColumn("ID", width="small"),
                    "Komoditas": st.column_config.TextColumn("Commodity", width="small"),
                    "Kategori": st.column_config.TextColumn("Intent", width="small"),
                    "Volume": st.column_config.TextColumn("Volume", width="small"),
                    "Harga": st.column_config.TextColumn("Price", width="small"),
                    "Lokasi": st.column_config.TextColumn("Location", width="medium"),
                    "Nama": st.column_config.TextColumn("Author / Business", width="medium"),
                    "Kontak": st.column_config.TextColumn("Contact Phone", width="medium"),
                    "Chat_WA": st.column_config.LinkColumn("Action", display_text="Chat WA", width="small"),
                    "Rel_Score": st.column_config.ProgressColumn("Relevance", min_value=0, max_value=100, format="%d%%", width="small"),
                    "Conf_Score": st.column_config.ProgressColumn("Confidence", min_value=0, max_value=100, format="%d%%", width="small"),
                    "Tgl_Post": st.column_config.TextColumn("Posted Date", width="small"),
                    "Sumber": st.column_config.TextColumn("Data Source", width="medium"),
                    "Review": st.column_config.TextColumn("Review Status", width="small"),
                    "URL": st.column_config.LinkColumn("Source Link", display_text="Open Link", width="small"),
                },
            )

            with st.expander("Score Calculation Breakdown"):
                for _, row in df_leads.iterrows():
                    raw_reasons = row.get("Alasan_Skor")
                    reasons = db.loads(raw_reasons, default={})
                    if reasons and isinstance(reasons, dict):
                        st.markdown(f"**Data #{row['id']}** | {row['Komoditas']} ({row['Lokasi']}) | Status: `{row['Review']}`")
                        col_r, col_c = st.columns(2)
                        with col_r:
                            st.markdown("**Relevance Breakdown:**")
                            for r in reasons.get("relevance", []):
                                st.caption(r)
                        with col_c:
                            st.markdown("**Confidence Breakdown:**")
                            for c in reasons.get("confidence", []):
                                st.caption(c)
                        st.divider()

# ================= TAB 2: MATCHMAKING & POOLING =================
with tab2:
    st.markdown("### Matchmaking & Smart Pooling Engine")
    st.caption("Two-sided algorithmic matching (Supply ↔ Demand) and nearest multi-farmer aggregation (PRD §7.6)")

    # --- Hitung statistik untuk stepper ---
    _st_supply_cnt = conn.execute("SELECT COUNT(*) FROM listings WHERE intent = 'supply' AND duplicate_of IS NULL").fetchone()[0]
    _st_demand_cnt = conn.execute("SELECT COUNT(*) FROM listings WHERE intent = 'demand' AND duplicate_of IS NULL").fetchone()[0]
    _st_match_cnt = conn.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
    _st_approved_sup = conn.execute("SELECT COUNT(*) FROM listings WHERE intent = 'supply' AND review_status = 'approved'").fetchone()[0]

    # Step 1 state
    if _st_supply_cnt > 0:
        _s1_class = "step-done"
        _s1_badge_class = "badge-done"
        _s1_badge_text = f"{_st_supply_cnt} farmers available"
        if _st_approved_sup > 0:
            _s1_badge_text += f" ({_st_approved_sup} approved)"
    else:
        _s1_class = "step-pending"
        _s1_badge_class = "badge-empty"
        _s1_badge_text = "No data yet"

    # Step 2 state
    if _st_demand_cnt > 0:
        _s2_class = "step-done"
        _s2_badge_class = "badge-done"
        _s2_badge_text = f"{_st_demand_cnt} orders available"
    else:
        _s2_class = "step-active" if _st_supply_cnt > 0 else "step-pending"
        _s2_badge_class = "badge-warning" if _st_supply_cnt > 0 else "badge-empty"
        _s2_badge_text = "Fill form below" if _st_supply_cnt > 0 else "No data yet"

    # Step 3 state
    if _st_match_cnt > 0:
        _s3_class = "step-done"
        _s3_badge_class = "badge-count"
        _s3_badge_text = f"{_st_match_cnt} matches found"
    elif _st_supply_cnt > 0 and _st_demand_cnt > 0:
        _s3_class = "step-active"
        _s3_badge_class = "badge-warning"
        _s3_badge_text = "Ready to run"
    else:
        _s3_class = "step-pending"
        _s3_badge_class = "badge-empty"
        _s3_badge_text = "Waiting for data"

    st.markdown(f"""
        <div class="match-stepper">
            <div class="match-step {_s1_class}">
                <span class="match-step-num">Step 1</span>
                <span class="match-step-title">Supply Data (Farmers)</span>
                <span class="match-step-detail">Search farmers via sidebar or load demo data</span>
                <span class="match-step-badge {_s1_badge_class}">{_s1_badge_text}</span>
            </div>
            <div class="match-step {_s2_class}">
                <span class="match-step-num">Step 2</span>
                <span class="match-step-title">Demand Data (Buyers)</span>
                <span class="match-step-detail">Add buyer demand orders via form below</span>
                <span class="match-step-badge {_s2_badge_class}">{_s2_badge_text}</span>
            </div>
            <div class="match-step {_s3_class}">
                <span class="match-step-num">Step 3</span>
                <span class="match-step-title">Run Matchmaking</span>
                <span class="match-step-detail">Calculate match scores & recommendations</span>
                <span class="match-step-badge {_s3_badge_class}">{_s3_badge_text}</span>
            </div>
        </div>
    """, unsafe_allow_html=True)

    # --- Quick-start guide ketika belum ada data ---
    if _st_supply_cnt == 0 and _st_demand_cnt == 0:
        st.markdown("""
            <div class="match-guide-box">
                <h4>Quick Start Guide</h4>
                <ol>
                    <li><strong>Find Farmers first</strong> — Open left sidebar, choose commodity, click "Search Leads"</li>
                    <li><strong>Review leads</strong> — In "Verified Leads" tab, approve verified farmer records</li>
                    <li><strong>Add buyer order</strong> — Return here, fill the "Add New Buyer Order" form below</li>
                    <li><strong>Run matchmaking</strong> — Click "Run Matchmaking Engine" to view recommendations</li>
                </ol>
            </div>
        """, unsafe_allow_html=True)

    # --- Notifikasi matchmaking ---
    if "notify_match" in st.session_state:
        st.toast(st.session_state.pop("notify_match"), icon="✅")
    if "notify_match_warning" in st.session_state:
        st.warning(st.session_state.pop("notify_match_warning"))

    # --- Action bar ---
    m_act1, m_act2, m_act3 = st.columns([2, 1.5, 1.5])
    with m_act2:
        tier_select = st.selectbox("Tier Filter", ["All", "outreach", "review", "ignored"], index=0, help="outreach (score ≥80), review (50-79), ignored (<50)")

    with m_act3:
        include_pending = st.checkbox("Include high-scoring pending leads", value=True, help="Include unapproved farmers with relevance ≥70 and confidence ≥60")

    with m_act1:
        _btn_disabled = (_st_supply_cnt == 0 or _st_demand_cnt == 0)
        _btn_help = "Calculate match scores for all buyer orders against available farmer supplies"
        if _btn_disabled:
            _btn_help = "Requires at least 1 supply (farmer) AND 1 demand (buyer) to run matchmaking"
        if st.button("Run Matchmaking", type="primary", help=_btn_help, disabled=_btn_disabled):
            with st.spinner(f"Matching {_st_demand_cnt} buyer orders with {_st_supply_cnt} farmer supplies..."):
                m_stats = run_all_matches(conn, include_pending_high_score=include_pending)
                if m_stats["matches_created"] == 0 and m_stats["pools_created"] == 0:
                    st.session_state["notify_match_warning"] = (
                        f"Calculation finished for {m_stats['total_demand']} buyer orders and {_st_supply_cnt} farmer offers, "
                        "but no pairs met the minimum score criteria (different commodities or price/distance tolerances not met)."
                    )
                else:
                    st.session_state["notify_match"] = (
                        f"Matchmaking complete! Found {m_stats['matches_created']} direct matches "
                        f"and {m_stats['pools_created']} smart pools across {m_stats['total_demand']} buyer orders."
                    )
                st.rerun()

    # --- Form Input Pembeli (auto-expand jika demand kosong) ---
    _demand_form_expanded = (_st_demand_cnt == 0 and _st_supply_cnt > 0)
    with st.expander("Add New Buyer Order (Demand)", expanded=_demand_form_expanded):
        if _st_demand_cnt == 0:
            st.info("No buyer demand records yet. Fill the form below to add your first buyer order.")
        st.caption("Add a new buyer order to immediately pair with farmer supplies in the database.")
        with st.form("form_manual_order"):
            fo_c1, fo_c2 = st.columns(2)
            with fo_c1:
                b_name = st.text_input("Business / Buyer Name *", placeholder="e.g. PT Sumber Berkah Buah")
                b_prod = st.text_input("Commodity *", placeholder="e.g. melon, watermelon, banana")
                b_vol = st.number_input("Required Volume (Kg) *", min_value=1.0, value=500.0, step=50.0)
                b_price = st.number_input("Budget Limit (Rp/Kg)", min_value=0.0, value=9000.0, step=500.0)
            with fo_c2:
                b_loc = st.text_input("Delivery Destination (City/Regency) *", placeholder="e.g. Surabaya, Sidoarjo, Kediri")
                b_date = st.date_input("Target Delivery Date", value=datetime.now())
                b_phone = st.text_input("Buyer Contact Phone", placeholder="e.g. +6281234567890")
                b_var = st.text_input("Specific Variety (Optional)", placeholder="e.g. madesta, golden, or leave blank")

            submitted_order = st.form_submit_button("Save Buyer Order", type="secondary")
            if submitted_order:
                if not b_name or not b_prod or not b_loc:
                    st.error("Buyer name, commodity, and delivery location are required.")
                else:
                    new_id = save_manual_order(
                        conn,
                        buyer_name=b_name,
                        product=b_prod,
                        volume_kg=b_vol,
                        max_price_per_kg=b_price if b_price > 0 else None,
                        kabupaten=b_loc,
                        needed_date=b_date.isoformat(),
                        contact_phone=b_phone,
                        variety=b_var,
                    )
                    st.success(f"Order #{new_id} for '{b_name}' saved successfully.")
                    st.rerun()

    matches_list = get_matches_for_display(conn, tier_filter=tier_select)

    if not matches_list:
        if _st_demand_cnt == 0 and _st_supply_cnt == 0:
            pass  # Guide box sudah ditampilkan di atas
        elif _st_demand_cnt == 0:
            st.info(
                f"Farmer supply data is ready ({_st_supply_cnt} listings). "
                "Now add buyer demand using the form above, then click 'Run Matchmaking'."
            )
        elif _st_supply_cnt == 0:
            st.info(
                f"Buyer demand data is ready ({_st_demand_cnt} orders). "
                "Run 'Find Supply' in the sidebar to scrape farmer data, then click 'Run Matchmaking'."
            )
        else:
            st.info(
                f"Database ready: {_st_supply_cnt} farmers and {_st_demand_cnt} buyers. "
                "Click 'Run Matchmaking' above to calculate recommendation matches."
            )
    else:
        top_exp1, top_exp2 = st.columns([3, 1.3])
        with top_exp1:
            st.caption(f"Displaying {len(matches_list)} matching recommendation pairs:")
        with top_exp2:
            df_export = build_matches_export_dataframe(matches_list)
            csv_matches = df_export.to_csv(index=False).encode("utf-8")
            st.download_button(
                "Export Match Report (CSV)",
                data=csv_matches,
                file_name=f"matchmaking_report_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                mime="text/csv",
                use_container_width=True,
            )

        for m in matches_list:
            is_pool = (m["kind"] == "pool")
            tier_class = "apify-pill-success" if m["tier"] == "outreach" else ("apify-pill-review" if m["tier"] == "review" else "apify-pill-ignored")
            tier_label = "Outreach Priority" if m["tier"] == "outreach" else ("Needs Review" if m["tier"] == "review" else "Ignored")
            kind_class = "apify-pill-pool" if is_pool else "apify-pill-single"
            kind_label = "Smart Pooling" if is_pool else "Match Tunggal"

            # Apify Card Style
            st.markdown(f"""
                <div class="apify-card">
                    <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:8px;">
                        <div>
                            <span class="apify-pill {kind_class}">{kind_label}</span>
                            <span class="apify-pill {tier_class}">{tier_label}</span>
                            <h4 style="margin:8px 0 2px 0; color:#101828;">{m['buyer_name']} ({m['buyer_location']})</h4>
                            <span style="font-size:12px; color:#64748b;">
                                Commodity: <b>{(m.get('product') or 'Commodity').title()}</b> | 
                                Required: <b>{f"{m['buyer_vol']:g} kg" if m.get('buyer_vol') is not None else "Unspecified"}</b> | 
                                Max Budget: <b>{f"Rp {float(m['buyer_max_price']):,.0f}/kg" if m.get('buyer_max_price') is not None else 'Unspecified'}</b>
                            </span>
                        </div>
                        <div style="text-align:right;">
                            <div style="font-size:1.8rem; font-weight:700; color:#101828; line-height:1;">
                                {m.get('score', 0)}<span style="font-size:12px; color:#64748b; font-weight:500;">/100</span>
                            </div>
                            <div style="font-size:11px; color:#0284c7; font-weight:600; margin-top:2px;">Coverage: {f"{m['coverage_pct']:g}%" if m.get('coverage_pct') is not None else "-"}</div>
                        </div>
                    </div>
                </div>
            """, unsafe_allow_html=True)

            with st.container(border=True):
                st.markdown("**Recommended Farmers:**")
                items = m.get("items", [])
                if items:
                    f_cols = st.columns(len(items)) if len(items) <= 3 else [st.container()]
                    for idx, it in enumerate(items):
                        target_col = f_cols[idx] if len(items) <= 3 else st
                        with target_col:
                            st.markdown(f"**{it.get('farmer_name') or 'Farmer'}** ({it.get('farmer_location') or '-'})")
                            f_pr = it.get('farmer_price')
                            price_str = f"Rp {float(f_pr):,.0f}/kg" if f_pr is not None else "Not listed"
                            al_kg = it.get('allocated_kg')
                            alloc_str = f"{float(al_kg):g} kg" if al_kg is not None else "-"
                            st.caption(f"Allocation: {alloc_str} | Price: {price_str}")
                            if it.get("distance_km"):
                                st.caption(f"Estimated Distance: {it['distance_km']} km")
                            
                            farmer_draft = draft_farmer_outreach_for_match(
                                farmer_name=it.get('farmer_name'),
                                commodity=m['product'],
                                farmer_location=it.get('farmer_location'),
                                buyer_name=m['buyer_name'],
                                buyer_location=m['buyer_location'],
                                needed_vol_kg=it.get('allocated_kg') or m['buyer_vol'],
                                farmer_price=it.get('farmer_price'),
                            )
                            farmer_wa_url = format_wa_url(it.get('farmer_phone') or it.get('farmer_wa'), farmer_draft)
                            if farmer_wa_url:
                                st.markdown(f"[Contact via WhatsApp]({farmer_wa_url})")
                                with st.popover("Outreach Draft & CRM"):
                                    st.caption("Auto-generated WhatsApp outreach draft:")
                                    st.code(farmer_draft, language="text")
                                    if st.button("Register to Sales CRM", key=f"btn_reg_crm_f_{m['match_id']}_{it['supply_id']}"):
                                        existing_c = db.get_conversation_by_listing(conn, it['supply_id'])
                                        if not existing_c:
                                            new_c_id = db.create_conversation(
                                                conn,
                                                listing_id=it['supply_id'],
                                                campaign_id="cmp-sales-match",
                                                contact_phone=it.get('farmer_phone') or it.get('farmer_wa'),
                                                role="farmer",
                                                match_id=m['match_id'],
                                                contact_name=it.get('farmer_name'),
                                                initial_state="drafted",
                                                followup_due_at=calculate_due_date(days_ahead=3),
                                            )
                                            db.add_message(conn, new_c_id, "outbound", "ai", farmer_draft, delivery_status="draft")
                                            st.session_state["notify_success"] = f"Farmer '{it.get('farmer_name')}' enrolled into Sales CRM #{new_c_id}!"
                                        else:
                                            st.session_state["notify_info"] = f"Farmer '{it.get('farmer_name')}' already exists in Sales CRM #{existing_c['id']}."
                                        st.rerun()
                            elif it.get("farmer_phone"):
                                st.caption(f"Phone: {it['farmer_phone']}")

                if is_pool:
                    disclaimer_text = m.get("breakdown", {}).get("disclaimer")
                    if disclaimer_text:
                        st.info(f"Aggregation Note: {disclaimer_text}")

                margin_info = m.get("margin")
                if margin_info and (margin_info.get("est_gross_margin_rp") or 0) > 0:
                    m_pct = margin_info.get('margin_pct') or 0.1
                    m_gross = margin_info.get('est_gross_margin_rp') or 0
                    f_price = margin_info.get('farmer_price') or 0
                    s_price = margin_info.get('suggested_price') or 0
                    st.markdown(
                        f"**Estimated GoTani Margin ({m_pct:.0%}):** "
                        f"Rp {m_gross:,.0f} "
                        f"(Farmer Price: Rp {f_price:,.0f}/kg, Suggested Offer: Rp {s_price:,.0f}/kg)"
                    )

                gaps = m.get("gaps", [])
                if gaps:
                    with st.expander("Data Gaps & Validation Notes", expanded=False):
                        for g in gaps:
                            st.caption(f"- {g}")

                act_c1, act_c2, act_c3 = st.columns([1.8, 1.8, 2.4])
                with act_c1:
                    margin_info = m.get("margin", {}) or {}
                    suggested_price = margin_info.get("suggested_price") or m.get("buyer_max_price")
                    farmer_locations = [it.get("farmer_location") for it in m.get("items", [])]
                    buyer_draft = draft_buyer_outreach_for_match(
                        buyer_name=m['buyer_name'],
                        commodity=m['product'],
                        buyer_location=m['buyer_location'],
                        needed_vol_kg=m['buyer_vol'],
                        suggested_price=suggested_price,
                        is_pool=is_pool,
                        num_farmers=len(m.get("items", [])),
                        farmer_locations=farmer_locations,
                    )
                    buyer_wa_url = format_wa_url(m.get("buyer_phone") or m.get("buyer_wa"), buyer_draft)
                    if buyer_wa_url:
                        st.markdown(f"[Contact Buyer via WhatsApp]({buyer_wa_url})")
                        with st.popover("Offer Draft & CRM"):
                            st.caption("Auto-generated offer draft for buyer:")
                            st.code(buyer_draft, language="text")
                            if st.button("Register Buyer to Sales CRM", key=f"btn_reg_crm_b_{m['match_id']}"):
                                existing_cb = db.get_conversation_by_listing(conn, m['demand_id'])
                                if not existing_cb:
                                    new_cb_id = db.create_conversation(
                                        conn,
                                        listing_id=m['demand_id'],
                                        campaign_id="cmp-sales-buyer",
                                        contact_phone=m.get('buyer_phone') or m.get('buyer_wa'),
                                        role="buyer",
                                        match_id=m['match_id'],
                                        contact_name=m['buyer_name'],
                                        initial_state="drafted",
                                        followup_due_at=calculate_due_date(days_ahead=3),
                                    )
                                    db.add_message(conn, new_cb_id, "outbound", "ai", buyer_draft, delivery_status="draft")
                                    st.session_state["notify_success"] = f"Buyer '{m['buyer_name']}' enrolled into Sales CRM #{new_cb_id}!"
                                else:
                                    st.session_state["notify_info"] = f"Buyer '{m['buyer_name']}' already exists in Sales CRM #{existing_cb['id']}."
                                st.rerun()
                    else:
                        st.caption("Buyer contact phone not available")


                with act_c2:
                    if m["status"] == "open":
                        if st.button("Confirm Outreach", key=f"conf_{m['match_id']}"):
                            update_match_status(conn, m["match_id"], "confirmed")
                            st.success("Match status updated to confirmed.")
                            st.rerun()
                    else:
                        st.caption(f"Workflow Status: {m['status'].upper()}")

                with act_c3:
                    if m["status"] != "closed":
                        with st.popover("Record Deal Outcome"):
                            out_choice = st.radio("Deal Outcome", ["deal", "no_deal"], key=f"rad_{m['match_id']}")
                            out_note = st.text_input("Outcome Notes", placeholder="e.g. Price agreement reached, harvest schedule aligned", key=f"note_{m['match_id']}")
                            if st.button("Save Outcome", key=f"btn_out_{m['match_id']}"):
                                update_match_outcome(conn, m["match_id"], out_choice, out_note)
                                st.success("Transaction outcome saved.")
                                st.rerun()
                    else:
                        st.caption(f"Final Outcome: {str(m.get('outcome')).upper()} ({m.get('outcome_reason') or '-'})")



# ================= TAB 3: SALES INBOX & OUTREACH CRM (FASE 3) =================
with tab3:
    st.markdown("### Sales Inbox & Outreach CRM")
    st.caption("Personalized outreach command center, automated cadence follow-ups, smart handover escalation, and PDP compliance (PRD §7.8)")

    # 1. Metrics & Action bar
    s_metrics = calculate_sales_metrics(conn)
    _crm_total = s_metrics["total_convs"]
    _crm_handover = s_metrics["handover_count"]
    _crm_won = s_metrics["won_count"]
    _crm_outreach = s_metrics["total_outreach"]

    # CRM Status Strip (visual cards)
    _ho_class = "card-highlight" if _crm_handover > 0 else ""
    _won_class = "card-success" if _crm_won > 0 else ""
    st.markdown(f"""
        <div class="crm-status-strip">
            <div class="crm-status-card">
                <div class="crm-status-card-title">Total Conversations</div>
                <div class="crm-status-card-value">{_crm_total}</div>
                <div class="crm-status-card-sub">All active & archived CRM threads</div>
            </div>
            <div class="crm-status-card">
                <div class="crm-status-card-title">Outreach Sent</div>
                <div class="crm-status-card-value">{_crm_outreach}</div>
                <div class="crm-status-card-sub">Initial outreach messages delivered</div>
            </div>
            <div class="crm-status-card {_ho_class}">
                <div class="crm-status-card-title">Needs Handover</div>
                <div class="crm-status-card-value">{_crm_handover}</div>
                <div class="crm-status-card-sub">Escalated to human sales team</div>
            </div>
            <div class="crm-status-card {_won_class}">
                <div class="crm-status-card-title">Deals Won</div>
                <div class="crm-status-card-value">{_crm_won}</div>
                <div class="crm-status-card-sub">Transactions successfully closed</div>
            </div>
        </div>
    """, unsafe_allow_html=True)

    # Empty state: Flow guide jika belum ada percakapan
    if _crm_total == 0:
        st.markdown("""
            <div class="crm-flow-guide">
                <h4>How to Use Sales CRM</h4>
                <div class="flow-steps">
                    <div class="flow-step"><span class="step-num">1</span> Scrape leads via sidebar</div>
                    <span class="flow-arrow">→</span>
                    <div class="flow-step"><span class="step-num">2</span> Approve leads in Tab 1</div>
                    <span class="flow-arrow">→</span>
                    <div class="flow-step"><span class="step-num">3</span> Run Matchmaking in Tab 2</div>
                    <span class="flow-arrow">→</span>
                    <div class="flow-step"><span class="step-num">4</span> Click "Register to CRM" on matches</div>
                    <span class="flow-arrow">→</span>
                    <div class="flow-step"><span class="step-num">5</span> Manage conversations here</div>
                </div>
                <p style="font-size:12px; color:#64748b; margin-top:12px;">
                    Or click "Initiate New Lead Outreach" below to start outreach directly for verified leads with contact numbers.
                </p>
            </div>
        """, unsafe_allow_html=True)

    # Export button
    _exp_c1, _exp_c2 = st.columns([3.5, 1])
    with _exp_c2:
        df_export_crm = build_conversations_export_dataframe(conn)
        csv_crm = df_export_crm.to_csv(index=False).encode("utf-8")
        st.download_button(
            "Export CRM Report (CSV)",
            csv_crm,
            file_name=f"sales_crm_report_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv",
            help="Download comprehensive report of sales outreach performance and interaction history.",
            use_container_width=True,
        )

    # Funnel Konversi Sales (PRD §7.8 / F8.10)
    with st.expander("Sales AI Conversion Funnel & Performance Metrics (PRD F8.10)", expanded=False):
        f_m1, f_m2, f_m3, f_m4 = st.columns(4)
        f_m1.metric("Reply Rate", f"{s_metrics['reply_rate_pct']}%", help="Percentage of leads who replied to outreach messages.")
        f_m2.metric("Handover Rate", f"{s_metrics['handover_rate_pct']}%", help="Percentage of conversations requiring human sales assistance.")
        f_m3.metric("Conversion (Win) Rate", f"{s_metrics['conversion_rate_pct']}%", help="Percentage of closed deals relative to total outreach.")
        f_m4.metric("Opt-Out (DNC) Rate", f"{s_metrics['opt_out_rate_pct']}%", help="Percentage of contacts opting out (Target: < 5%).")

    # 2. Check Cadence Follow-Up Due
    due_followups = get_due_followups(conn)
    if due_followups:
        st.warning(f"There are {len(due_followups)} conversations due for follow-up.")
        with st.expander(f"View Due Follow-Up Reminders ({len(due_followups)})", expanded=True):
            for df_row in due_followups:
                df_c1, df_c2 = st.columns([3, 1])
                with df_c1:
                    st.markdown(f"**{df_row['contact_name'] or 'Contact'}** ({df_row['contact_phone']}) - Commodity: {df_row['product']}")
                    st.caption(f"Status: {df_row['state']} | Follow-up #{df_row['followup_count'] + 1} due at {df_row['followup_due_at']}")
                with df_c2:
                    fu_msg = generate_followup_message(conn, df_row['id'])
                    fu_url = format_wa_url(df_row['contact_phone'], fu_msg)
                    if fu_url:
                        st.markdown(f"[Send Follow-Up via WhatsApp]({fu_url})")
                    if st.button(f"Mark Sent #{df_row['id']}", key=f"btn_send_fu_{df_row['id']}"):
                        db.add_message(conn, df_row['id'], "outbound", "ai", fu_msg, delivery_status="sent")
                        advance_followup(conn, df_row['id'])
                        st.success(f"Follow-up for #{df_row['id']} recorded successfully!")
                        st.rerun()

    st.write("")
    # 3. Filter controls
    f_c1, f_c2, f_c3 = st.columns([1.5, 1.5, 2])
    with f_c1:
        crm_state_filter = st.selectbox(
            "Filter Conversation State",
            ["All", "drafted", "sent", "followup_1", "active", "handover_pending", "closed_won", "closed_lost", "opt_out"],
            index=0,
            key="crm_filter_state"
        )
    with f_c2:
        crm_role_filter = st.selectbox(
            "Filter Prospect Role",
            ["All", "farmer", "buyer"],
            index=0,
            key="crm_filter_role"
        )

    # Inisiasi Percakapan Baru dari Listing Approved
    with f_c3:
        st.markdown("<div style='height:28px;'></div>", unsafe_allow_html=True)
        with st.popover("Initiate New Lead Outreach"):
            st.caption("Select a verified lead to generate initial outreach draft:")
            avail_leads = conn.execute("""
                SELECT id, entity_name, product, intent, contact_phone, kabupaten
                FROM listings
                WHERE contact_phone IS NOT NULL
                  AND duplicate_of IS NULL
                  AND id NOT IN (SELECT listing_id FROM conversations)
                ORDER BY relevance DESC, confidence DESC LIMIT 15
            """).fetchall()
            if not avail_leads:
                st.caption("All leads with contact details already have active conversation sessions.")
            else:
                lead_choices = {f"#{l['id']} - {l['entity_name'] or 'Anonymous'} ({l['product']}, {l['intent']}, {l['kabupaten']})": l for l in avail_leads}
                sel_lead_key = st.selectbox("Select Lead", list(lead_choices.keys()))
                if st.button("Create Conversation Session", type="primary"):
                    sel_l = lead_choices[sel_lead_key]
                    role_val = "farmer" if sel_l["intent"] == "supply" else "buyer"
                    # Buat percakapan
                    c_id = db.create_conversation(
                        conn,
                        listing_id=sel_l["id"],
                        campaign_id="cmp-sales",
                        contact_phone=sel_l["contact_phone"],
                        role=role_val,
                        contact_name=sel_l["entity_name"],
                        initial_state="drafted",
                        followup_due_at=calculate_due_date(days_ahead=3),
                    )
                    # Buat draf pesan awal
                    init_draft = generate_initial_outreach(conn, sel_l["id"], gateway=gateway)
                    db.add_message(conn, c_id, "outbound", "ai", init_draft, delivery_status="draft")
                    st.session_state["notify_success"] = f"Conversation #{c_id} for '{sel_l['entity_name']}' initiated successfully!"
                    st.rerun()

    # 4. Tampilkan daftar percakapan
    conversations_list = db.list_conversations(conn, state=crm_state_filter, role=crm_role_filter)
    if not conversations_list:
        if _crm_total == 0:
            st.info(
                "No conversation sessions yet. Start by enrolling leads from matchmaking results (Tab 2) "
                "or click 'Initiate New Lead Outreach' above to start a new outreach thread."
            )
        else:
            st.info("No conversations match the selected filter. Try changing the status or role filter above.")
    else:
        st.caption(f"Displaying {len(conversations_list)} conversation sessions:")
        for c in conversations_list:
            c_dict = dict(c)
            c_id = c_dict["id"]
            c_state = c_dict["state"]
            c_name = c_dict["contact_name"] or "Unnamed Contact"
            c_phone = c_dict["contact_phone"]
            c_role = "Farmer (Supply)" if c_dict["role"] == "farmer" else "Buyer (Demand)"
            c_prod = (c_dict.get("product") or "commodity").title()
            c_vol = f"{c_dict.get('volume_kg'):g} kg" if c_dict.get('volume_kg') else ""
            c_loc = c_dict.get("kabupaten") or c_dict.get("location_text") or "-"

            # State styling badge
            badge_class = f"apify-badge-{c_state.replace('_', '')}"
            if c_state == "handover_pending":
                badge_class = "apify-badge-handover"
            elif c_state == "closed_won":
                badge_class = "apify-badge-won"
            elif c_state == "closed_lost":
                badge_class = "apify-badge-lost"
            elif c_state == "opt_out":
                badge_class = "apify-badge-optout"

            with st.container():
                st.markdown(f"""
                    <div style="border: 1px solid #e2e8f0; border-radius: 8px; padding: 12px 14px; margin-bottom: 8px; background-color: #ffffff;">
                        <div style="display:flex; justify-content:space-between; align-items:center;">
                            <div>
                                <span style="font-size:14px; font-weight:600; color:#0f172a;">#{c_id} {c_name}</span>
                                <span style="font-size:12px; color:#64748b; margin-left:8px;">({c_role} · {c_prod} {c_vol} · {c_loc})</span>
                            </div>
                            <div>
                                <span class="{badge_class}">{c_state.upper()}</span>
                            </div>
                        </div>
                    </div>
                """, unsafe_allow_html=True)

                # Banner Handover jika pending
                if c_state == "handover_pending":
                    st.error(
                        f"🚨 **SALES HANDOVER ESCALATION:** This conversation requires direct GoTani staff attention! "
                        f"Reason: {c_dict.get('summary_text') or 'Lead replied with a specific inquiry or negotiation.'}"
                    )
                    h_act1, h_act2, h_act3 = st.columns(3)
                    with h_act1:
                        if st.button("Take Over (Human CS)", key=f"btn_takeover_{c_id}", type="primary"):
                            db.update_conversation(conn, c_id, state="active", assigned_sales="Active Staff")
                            st.success(f"Conversation #{c_id} handed over to human sales team.")
                            st.rerun()
                    with h_act2:
                        if st.button("Mark Deal (Closed Won)", key=f"btn_won_{c_id}"):
                            db.update_conversation(conn, c_id, state="closed_won", summary_text="Deal agreement reached.")
                            st.success(f"Deal #{c_id} marked as Closed Won!")
                            st.rerun()
                    with h_act3:
                        if st.button("Close (Closed Lost)", key=f"btn_lost_{c_id}"):
                            db.update_conversation(conn, c_id, state="closed_lost", summary_text="No agreement reached.")
                            st.info(f"Conversation #{c_id} closed as Lost.")
                            st.rerun()

                # Riwayat Pesan (Thread Expander)
                msgs = db.get_messages(conn, c_id)
                with st.expander(f"Message History Thread ({len(msgs)} messages)", expanded=(c_state in ("drafted", "handover_pending"))):
                    for m in msgs:
                        m_dict = dict(m)
                        if m_dict["direction"] == "outbound":
                            st.markdown(
                                f"""<div style="display:flex; justify-content:flex-end;">
                                    <div class="chat-bubble-outbound">
                                        <b>GoTani ({m_dict['sender_type'].upper()})</b> · <span style="font-size:11px; color:#039855;">{m_dict['created_at']}</span><br>
                                        {m_dict['content']}
                                    </div>
                                </div>""",
                                unsafe_allow_html=True
                            )
                        else:
                            st.markdown(
                                f"""<div style="display:flex; justify-content:flex-start;">
                                    <div class="chat-bubble-inbound">
                                        <b>{c_name} (Lead)</b> · <span style="font-size:11px; color:#667085;">{m_dict['created_at']}</span><br>
                                        {m_dict['content']}
                                    </div>
                                </div>""",
                                unsafe_allow_html=True
                            )

                    # Action Panel Percakapan
                    st.divider()
                    act_col1, act_col2 = st.columns([1.5, 2])
                    
                    with act_col1:
                        # WhatsApp 1-Click Link
                        latest_outbound = next((m["content"] for m in reversed(msgs) if m["direction"] == "outbound"), "")
                        wa_url = format_wa_url(c_phone, latest_outbound)
                        if wa_url and not is_do_not_contact(conn, c_phone):
                            st.markdown(f"**[Open WhatsApp Web / App]({wa_url})**")
                        elif is_do_not_contact(conn, c_phone):
                            st.caption("This contact opted out (Do-Not-Contact). Messaging is disabled.")

                        if c_state == "drafted":
                            if st.button("Mark Initial Message Sent", key=f"btn_mark_sent_{c_id}"):
                                db.update_conversation(conn, c_id, state="sent", followup_due_at=calculate_due_date(days_ahead=3))
                                st.success("Conversation status updated to 'sent' (Day+3 follow-up scheduled).")
                                st.rerun()

                    with act_col2:
                        # Form input balasan masuk dari lead
                        if c_state not in ("closed_won", "closed_lost", "opt_out"):
                            with st.form(key=f"form_inbound_{c_id}"):
                                in_text = st.text_input("Input inbound WhatsApp reply from lead:", placeholder="e.g. 1 ton available, what is your best price?")
                                submit_inbound = st.form_submit_button("Process Lead Reply")
                                if submit_inbound and in_text.strip():
                                    # 1. Catat inbound message
                                    db.add_message(conn, c_id, "inbound", "lead", in_text.strip(), delivery_status="received")
                                    
                                    # 2. Evaluasi Handover & Kepatuhan
                                    eval_res = evaluate_inbound_message(in_text.strip())
                                    
                                    if eval_res["trigger_type"] == "opt_out":
                                        register_opt_out_contact(conn, c_phone, reason="user_stop", source_message=in_text.strip())
                                        st.warning("Lead requested to stop contact. Number automatically registered to Do-Not-Contact suppression list.")
                                    elif eval_res["needs_handover"]:
                                        db.update_conversation(conn, c_id, state="handover_pending", summary_text=eval_res["reason"])
                                        st.error(f"Human Handover Escalation Detected: {eval_res['reason']}")
                                    else:
                                        # Hasilkan respon AI rutin
                                        ai_reply = generate_conversational_reply(conn, c_id, in_text.strip(), gateway=gateway)
                                        db.add_message(conn, c_id, "outbound", "ai", ai_reply, delivery_status="draft")
                                        db.update_conversation(conn, c_id, state="active", summary_text="AI generated response draft.")
                                        st.success("Reply analyzed! AI response draft added to the conversation thread.")
                                    st.rerun()

    # 5. Tabel Supresi Kepatuhan UU PDP (Opt-Out Registry)
    with st.expander("Do-Not-Contact & Suppression Registry (PDP Compliance - G5)", expanded=False):
        st.caption("List of contact numbers requesting to opt out or stop communication:")
        opt_rows = conn.execute("SELECT contact_phone, reason, source_message, opted_out_at FROM opt_outs ORDER BY opted_out_at DESC").fetchall()
        if opt_rows:
            st.dataframe(
                pd.DataFrame([dict(r) for r in opt_rows]),
                use_container_width=True,
                hide_index=True,
                column_config={
                    "contact_phone": "Contact Phone",
                    "reason": "Suppression Reason",
                    "source_message": "Last Lead Message",
                    "opted_out_at": "Opt-Out Date"
                }
            )
        else:
            st.caption("No contacts have requested opt-out yet.")


# ================= TAB 4: RAW DATA LOG =================
with tab4:
    df_raw = pd.read_sql_query("""
        SELECT
            r.id AS ID,
            r.platform AS Platform,
            r.campaign_id AS Campaign,
            COALESCE(NULLIF(r.author_name, ''), 'Anonymous / Public') AS Poster,
            (SELECT l.contact_phone FROM listings l WHERE l.raw_item_id = r.id AND l.contact_phone IS NOT NULL LIMIT 1) AS Listing_Phone,
            r.raw_text AS Original_Text,
            r.url AS URL,
            r.fetched_at AS Scraped_At,
            r.processed AS Processed
        FROM raw_items r
        ORDER BY r.id DESC LIMIT 200
    """, conn)

    if df_raw.empty:
        st.caption("Raw scraping log is currently empty.")
    else:
        # Ekstraksi dan format nomor kontak faktual dari data listing atau teks postingan mentah
        def _get_raw_contact(row):
            import re
            c = row.get("Listing_Phone")
            if pd.notna(c) and str(c).strip() and str(c).strip() != "-":
                raw_c = str(c).strip()
            else:
                text = str(row.get("Original_Text", ""))
                matches = MOBILE_RE.findall(text)
                raw_c = matches[0].strip() if matches else None

            if not raw_c:
                return "-"

            digits = re.sub(r"\D", "", raw_c)
            if digits.startswith("628"):
                digits = "08" + digits[3:]
            elif digits.startswith("8"):
                digits = "08" + digits[1:]

            if len(digits) >= 10:
                if len(digits) == 10:
                    return f"{digits[:4]}-{digits[4:7]}-{digits[7:]}"
                elif len(digits) == 11:
                    return f"{digits[:4]}-{digits[4:7]}-{digits[7:]}"
                elif len(digits) == 12:
                    return f"{digits[:4]}-{digits[4:8]}-{digits[8:]}"
                else:
                    return f"{digits[:4]}-{digits[4:8]}-{digits[8:]}"
            return raw_c or "-"

        df_raw["Contact"] = df_raw.apply(_get_raw_contact, axis=1)
        df_raw = df_raw.drop(columns=["Listing_Phone"])

        cols_order = ["ID", "Platform", "Poster", "Contact", "Campaign", "URL", "Original_Text", "Scraped_At", "Processed"]
        df_raw = df_raw[[c for c in cols_order if c in df_raw.columns]]

        csv_raw = df_raw.to_csv(index=False).encode("utf-8")
        st.download_button(
            "Export Raw Log (CSV)", csv_raw,
            file_name=f"raw_data_log_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv",
        )
        st.dataframe(
            df_raw,
            use_container_width=True,
            hide_index=True,
            column_config={
                "ID": st.column_config.NumberColumn("#", width="small"),
                "Platform": st.column_config.TextColumn("Source", width="small"),
                "Poster": st.column_config.TextColumn("Poster / Author", width="medium"),
                "Contact": st.column_config.TextColumn("Contact / Phone", width="medium"),
                "Campaign": st.column_config.TextColumn("Campaign", width="medium"),
                "URL": st.column_config.LinkColumn("Source URL", display_text="Open Link", width="medium"),
                "Original_Text": st.column_config.TextColumn("Original Post Text", width="large"),
                "Scraped_At": st.column_config.TextColumn("Scraped At", width="small"),
                "Processed": st.column_config.CheckboxColumn("Processed"),
            },
        )


# ================= TAB 5: RIWAYAT KAMPANYE & RUN LOG =================
with tab5:
    st.markdown("##### Search Campaign History")
    try:
        campaigns = list_campaigns(conn)
        if campaigns:
            df_camp = pd.DataFrame(
                [(c["id"], c["goal"], c["status"], c["created_at"]) for c in campaigns],
                columns=["ID", "Goal", "Status", "Created At"],
            )
            st.dataframe(df_camp, use_container_width=True, hide_index=True)
        else:
            st.caption("No campaign history found.")
    except Exception:
        st.caption("No campaign history found.")

    st.write("")
    st.markdown("##### Pipeline Execution Logs (Apify & AI Runs)")
    try:
        df_runs = pd.read_sql_query("""
            SELECT
                id AS Run_ID,
                campaign_id AS Campaign,
                step AS Step,
                platform AS Platform,
                status AS Status,
                items_found AS Items_Found,
                started_at AS Started_At,
                finished_at AS Finished_At,
                error AS Error_Details
            FROM runs
            ORDER BY id DESC LIMIT 50
        """, conn)

        if not df_runs.empty:
            st.dataframe(
                df_runs,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Run_ID": st.column_config.NumberColumn("#", width="small"),
                    "Campaign": st.column_config.TextColumn("Campaign", width="medium"),
                    "Step": st.column_config.TextColumn("Step", width="small"),
                    "Platform": st.column_config.TextColumn("Platform", width="small"),
                    "Status": st.column_config.TextColumn("Status", width="small"),
                    "Items_Found": st.column_config.NumberColumn("Items Found", width="small"),
                    "Started_At": st.column_config.TextColumn("Started At", width="medium"),
                    "Finished_At": st.column_config.TextColumn("Finished At", width="medium"),
                    "Error_Details": st.column_config.TextColumn("Error / Details", width="large"),
                }
            )
        else:
            st.caption("No pipeline execution logs found.")
    except Exception as e:
        st.caption(f"Failed to load run logs: {e}")

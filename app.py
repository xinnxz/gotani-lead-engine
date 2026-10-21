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
        padding: 8px 12px;
        margin-bottom: 8px;
        color: #027a48;
        font-size: 13px;
        line-height: 1.4;
    }
    .chat-bubble-inbound {
        background-color: #f2f4f7;
        border: 1px solid #eaecf0;
        border-radius: 8px 8px 8px 2px;
        padding: 8px 12px;
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
    st.markdown("<div style='font-size:11px; font-weight:600; color:#94a3b8; text-transform:uppercase; margin-bottom:8px;'>Aksi Cepat</div>", unsafe_allow_html=True)
    if st.button("Muat Demo Komprehensif", use_container_width=True):
        with st.spinner("Memuat dataset demo..."):
            subprocess.run([sys.executable, "seed_demo.py"], cwd=str(Path(__file__).parent))
            st.session_state["notify_success"] = "Dataset demo berhasil dimuat! Data petani, pembeli, dan smart pool siap diuji."
            st.toast("Dataset demo berhasil dimuat!", icon="✅")
            st.rerun()

    c_btn2, c_btn3 = st.columns(2)
    with c_btn2:
        if st.button("Hapus Semua Data", use_container_width=True):
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
            st.session_state["notify_success"] = "Seluruh data prospek, log scraping mentah, match, dan riwayat CRM berhasil dikosongkan total!"
            st.toast("Database berhasil dikosongkan!", icon="🗑️")
            st.rerun()
    with c_btn3:
        if st.button("Anti-Duplikat", use_container_width=True):
            with st.spinner("Memeriksa duplikasi..."):
                d_res = deduplicate_database(conn)
                st.session_state["notify_info"] = f"Deduplikasi selesai: {d_res['duplicates_marked']} entri duplikat berhasil disembunyikan."
                st.toast("Pemeriksaan duplikasi selesai!", icon="🔍")
            st.rerun()

    st.divider()

    # --- Section: New Campaign Spec ---
    st.markdown("<div style='font-size:11px; font-weight:700; color:#475569; text-transform:uppercase; letter-spacing:0.5px; margin-bottom:10px;'>Pencarian Pasar</div>", unsafe_allow_html=True)

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
    goal_options = ["Cari Petani", "Cari Pembeli"]
    if "marketplace_goal" not in st.session_state:
        st.session_state["marketplace_goal"] = goal_options[0]

    # 1. Kategori Transaksi (Radio vertikal stabil dengan key bawaan Streamlit)
    goal_choice = st.radio(
        "Kategori Pasar",
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
        "Komoditas",
        options=commodity_display,
        key="marketplace_commodity",
        help="Ketik atau pilih komoditas hasil tani yang ingin dicari.",
    )

    # 3. Filter Wilayah
    if "marketplace_provinces" not in st.session_state:
        st.session_state["marketplace_provinces"] = ["Jawa Timur"]

    selected_provinces = st.multiselect(
        "Lokasi Wilayah",
        options=province_options,
        key="marketplace_provinces",
        help="Pilih wilayah target pencarian data.",
    )

    # 4. Filter Lanjutan (Collapsible, rapi seperti filter marketplace)
    with st.expander("Filter Tambahan", expanded=False):
        com_key = selected_commodity.lower()
        synonyms = KNOWN_COMMODITIES.get(com_key, [])
        variety_options = [s.title() for s in synonyms if s.lower() != com_key]

        if variety_options:
            selected_varieties = st.multiselect(
                "Varietas Spesifik",
                options=variety_options,
                key=f"marketplace_var_{com_key}",
                help="Kosongkan jika mencari semua varietas.",
            )
        else:
            selected_varieties = []

        min_volume = st.number_input(
            "Minimal Volume (kg)",
            min_value=0,
            max_value=1_000_000,
            value=500,
            step=100,
            key="marketplace_min_vol",
            help="Batas minimal volume. Isi 0 untuk tanpa batas.",
        )

        max_price = st.number_input(
            "Batas Harga Tertinggi (Rp/kg)",
            min_value=0,
            max_value=10_000_000,
            value=0,
            step=1000,
            key="marketplace_max_price",
            help="Isi 0 jika tidak membatasi harga.",
        )

    # 5. Tombol Pencarian Marketplace
    if st.button("Cari Prospek", type="primary", use_container_width=True):
        cid = new_campaign_id(conn)
        goal_val = "find_supply" if "Petani" in goal_choice else "find_demand"
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

        st.session_state["draft_spec"] = spec.to_json()
        st.session_state["spec_notice"] = {
            "product": spec.product.name,
            "goal": "Cari Petani" if goal_val == "find_supply" else "Permintaan Pembeli",
            "location": ", ".join(spec.location.include),
            "volume": f"{spec.volume.min:g} kg" if spec.volume.min else "Bebas",
            "mode": "Pencarian Pasar",
            "fallback": False,
        }

        save_campaign(conn, spec)
        try:
            with st.status("Menjalankan Pipeline Inteligensi Pasar...", expanded=True) as status_box:
                def on_progress(step_title: str, detail_text: str):
                    status_box.write(f"[{datetime.now().strftime('%H:%M:%S')}] **{step_title}**: {detail_text}")

                pipe = Pipeline(spec, progress_callback=on_progress)
                pipe_res = asyncio.run(pipe.run()) or {}
                raw_cnt = pipe_res.get("raw_items_saved", 0)
                lead_cnt = pipe_res.get("new_leads_saved", 0)
                status_box.update(label="Pencarian Selesai", state="complete", expanded=False)
                if raw_cnt == 0:
                    st.session_state["notify_info"] = f"Pencarian selesai untuk '{spec.product.name}'. Tidak ditemukan postingan baru dalam 35 hari terakhir. Silakan gunakan tombol 'Muat Demo Komprehensif' di menu database untuk melihat simulasi lengkap."
                else:
                    st.session_state["notify_success"] = f"Pencarian berhasil. Ditemukan {raw_cnt} postingan mentah dan {lead_cnt} prospek terverifikasi untuk '{spec.product.name}'."
                time.sleep(1)
                st.rerun()
        except Exception as e:
            st.error(f"Kesalahan pada eksekusi pipeline: {e}")

    # Indikator ringkas spesifikasi aktif
    notice = st.session_state.get("spec_notice")
    if notice:
        st.markdown(f"""
        <div style="background:#f8fafc; border:1px solid #e2e8f0; border-radius:6px; padding:8px 10px; margin-top:8px; margin-bottom:8px; font-size:11px; color:#334155; line-height:1.5;">
            <div style="font-weight:600; color:#0f172a; margin-bottom:2px;">Filter Aktif:</div>
            Komoditas: <b>{notice['product']}</b> ({notice['goal']})<br>
            Wilayah: {notice['location']} | Min. {notice['volume']}
        </div>
        """, unsafe_allow_html=True)

    # --- Section: Handoff Detection ---
    st.divider()
    handoff_flag = Path("./data/HANDOFF_WAITING")
    if handoff_flag.exists():
        st.error("Intervensi Verifikasi Diperlukan")
        st.caption(handoff_flag.read_text(encoding="utf-8"))
        if st.button("Lanjutkan Sistem"):
            handoff_flag.unlink(missing_ok=True)
            st.success("Konfirmasi diterima, sistem dilanjutkan.")
            st.rerun()

    # --- Section: Inbound Call Assistant (Caller ID) ---
    st.markdown("<div style='font-size:11px; font-weight:600; color:#94a3b8; text-transform:uppercase; margin-bottom:8px;'>Inbound Call Assistant</div>", unsafe_allow_html=True)
    st.caption("Pencarian instan data profil penelepon untuk sales.")
    caller_input = st.text_input("Nomor Telepon", placeholder="Contoh: 081234567890", key="side_caller_phone", label_visibility="collapsed")
    if caller_input:
        caller_res = lookup_caller(conn, caller_input)
        if not caller_res:
            st.warning("Format nomor telepon tidak valid.")
        elif not caller_res.get("found"):
            if caller_res.get("is_opted_out"):
                st.error("⛔ DNC / OPT-OUT: Nomor ini meminta tidak dihubungi!")
            st.info(caller_res.get("message"))
            with st.expander("Panduan Bicara (Kontak Baru)", expanded=True):
                for p in caller_res["talking_points"]:
                    st.markdown(f"- {p}")
        else:
            if caller_res.get("is_opted_out"):
                st.error("⛔ DNC / OPT-OUT: Nomor ini tercatat di registri supresi!")
            
            c_info = caller_res.get("conversation")
            st.success(f"{caller_res['name']} ({caller_res['role']})")
            st.caption(f"Komoditas: {caller_res['product']} | Lokasi: {caller_res['location']}")
            
            if c_info:
                c_st = c_info.get("state", "").upper()
                if c_info.get("state") == "handover_pending":
                    st.error(f"🚨 CRM: HANDOVER PENDING · {c_info.get('summary_text', '')}")
                else:
                    st.info(f"CRM Status: `{c_st}` · {c_info.get('summary_text') or 'Percakapan tercatat'}")

            with st.expander("Panduan Bicara Penelepon", expanded=True):
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
            <span style="font-size:13px; font-weight:600; color:#101828;">Dataset Siap</span>
            <span class="apify-meta-item">Total Posts: <b>{total_raw}</b></span>
            <span class="apify-meta-item">Valid Leads: <b>{total_leads}</b></span>
            <span class="apify-meta-item">Matches: <b>{total_matches}</b></span>
            <span class="apify-meta-item">CRM Convs: <b>{total_convs}</b></span>
            <span class="apify-meta-item">Biaya: <b>${usage['cost_usd']:.3f}</b></span>
            <span class="apify-meta-item">Waktu: <b>{last_run_time}</b></span>
        </div>
        <div>
            <span style="font-size:12px; color:#0284c7; font-weight:600;">Status Operasional Normal</span>
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
        if st.button("✕", key="btn_close_notify_success", help="Tutup notifikasi"):
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
        if st.button("✕", key="btn_close_notify_info", help="Tutup notifikasi"):
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
        if st.button("✕", key="btn_close_notify_match_global", help="Tutup notifikasi"):
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
        if st.button("✕", key="btn_close_notify_match_warn", help="Tutup notifikasi"):
            del st.session_state["notify_match_warning"]
            st.rerun()

# 3. Metric Summary Cards (Apify Dashboard Widget Style)
col_m1, col_m2, col_m3, col_m4, col_m5 = st.columns(5)
col_m1.metric("Raw Posts", f"{total_raw:,}", help="Jumlah postingan yang tersimpan dari penelusuran Google Search Scraper.")
col_m2.metric("Valid Leads", f"{total_leads:,}", help="Jumlah data lead yang berhasil diekstrak dan dinormalisasi.")
col_m3.metric("High Conf", f"{high_conf:,}", help="Prospek terverifikasi dengan tingkat keyakinan data ≥ 80%.")
col_m4.metric("Matches", f"{total_matches:,}", help="Jumlah rekomendasi kecocokan pasokan dan permintaan yang teridentifikasi.")
col_m5.metric("Sales CRM", f"{total_convs:,}", help="Jumlah sesi percakapan prospek aktif di Sales CRM Fase 3.")

st.write("") # Spacer

# 4. Main Tabs Navigation (Apify Output Style)
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    f"Verified Leads ({total_leads})",
    f"Matchmaking & Pooling ({total_matches})",
    f"Sales Inbox CRM ({total_convs})",
    f"Raw Data Log ({total_raw})",
    "Riwayat Kampanye",
])


# ================= TAB 1: VERIFIED LEADS =================
with tab1:
    fc1, fc2, fc3 = st.columns([1.5, 1.5, 1.2])
    with fc1:
        min_rel = st.slider("Batas Minimum Relevansi", 0, 100, 65, 5)
    with fc2:
        min_conf = st.slider("Batas Minimum Confidence", 0, 100, 50, 5)
    with fc3:
        status_filter = st.selectbox("Status Verifikasi", ["Semua", "pending", "approved", "rejected"], index=0)
    st.caption("Menampilkan prospek terverifikasi berkualitas tinggi (Relevansi ≥ 65%, Confidence ≥ 50% sesuai PRD §7.5). Geser slider ke 0 jika ingin meninjau seluruh data mentah.")

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
            r.posted_at AS Tgl_Post,
            r.url AS URL
        FROM listings l
        JOIN raw_items r ON l.raw_item_id = r.id
        WHERE l.relevance >= ? AND l.confidence >= ? AND l.duplicate_of IS NULL
          AND (r.posted_at IS NULL OR r.posted_at >= date('now', '-35 days'))
    """
    # Dynamic: tambahkan filter tahun stale (sebelum tahun ini)
    _cur_yr_app = datetime.now().year
    for _sy in range(2018, _cur_yr_app):
        query_str += f" AND r.raw_text NOT LIKE '%{_sy}%'"
    query_str += """
    """
    params = [min_rel, min_conf]
    if status_filter != "Semua":
        query_str += " AND l.review_status = ?"
        params.append(status_filter)
    query_str += " ORDER BY l.relevance DESC, l.confidence DESC"

    df_leads = pd.read_sql_query(query_str, conn, params=tuple(params))

    if df_leads.empty:
        st.info("Belum ada data prospek yang memenuhi kriteria filter saat ini.")
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
            
            raw_prod = row.get("Komoditas")
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

        # Header Export Row (Apify style)
        top_c1, top_c2 = st.columns([1, 4])
        with top_c1:
            csv_leads = df_leads.drop(columns=["Alasan_Skor", "Atribut"], errors="ignore").to_csv(index=False).encode("utf-8")
            st.download_button(
                "Export Dataset (CSV)", csv_leads,
                file_name=f"apify_leads_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                mime="text/csv",
            )

        display_cols = [
            "id", "Komoditas", "Kategori", "Volume", "Harga", "Tgl_Post", 
            "Lokasi", "Nama", "Kontak", "Chat_WA", "Rel_Score", "Conf_Score", "Review", "Label_Sumber", "URL"
        ]
        
        df_leads_display = df_leads.copy()
        df_leads_display["Kategori"] = df_leads_display["Intent"]
        final_cols = [c for c in display_cols if c in df_leads_display.columns]

        st.dataframe(
            df_leads_display[final_cols],
            use_container_width=True,
            hide_index=True,
            column_config={
                "id": st.column_config.NumberColumn("ID", width="small"),
                "Komoditas": st.column_config.TextColumn("Komoditas", width="small"),
                "Kategori": st.column_config.TextColumn("Kategori", width="small"),
                "Volume": st.column_config.TextColumn("Volume", width="small", help="Volume asli dengan unit (kg, kresek, ikat, dll). Jika unit non-standar, tidak dikonversi ke kg"),
                "Harga": st.column_config.TextColumn("Harga", width="small", help="Harga asli dengan unit per satuan sebenarnya (per kg, per kresek, per ikat, dll)"),
                "Lokasi": st.column_config.TextColumn("Lokasi", width="medium"),
                "Nama": st.column_config.TextColumn("Pemosting", width="medium"),
                "Kontak": st.column_config.TextColumn("Kontak / No. HP", width="medium", help="Nomor telepon/WhatsApp riil hasil ekstraksi dari postingan. Tampil '-' jika postingan tidak memuat kontak"),
                "Chat_WA": st.column_config.LinkColumn("Aksi", display_text="Chat WhatsApp", width="small", help="Tautan langsung untuk chat WhatsApp. Kosong bila kontak tidak tersedia"),
                "Rel_Score": st.column_config.ProgressColumn("Relevansi", min_value=0, max_value=100, format="%d%%", width="small"),
                "Conf_Score": st.column_config.ProgressColumn("Confidence", min_value=0, max_value=100, format="%d%%", width="small"),
                "Tgl_Post": st.column_config.TextColumn("Tgl Post", width="small", help="Tanggal postingan asli ditemukan oleh Google. Maksimal 1 bulan dari sekarang."),
                "Review": st.column_config.TextColumn("Status", width="small"),
                "Label_Sumber": st.column_config.TextColumn("Tipe Sumber", width="small"),
                "URL": st.column_config.LinkColumn("Tautan", display_text="Buka Tautan", width="small"),
            },
        )

        with st.expander("Panel Verifikasi Reviewer", expanded=False):
            st.caption("Verifikasi keaslian dan kelayakan prospek sebelum diteruskan ke tim Sales.")
            rev_col1, rev_col2, rev_col3 = st.columns([1.5, 2, 2])
            
            with rev_col1:
                selectable_ids = df_leads["id"].tolist()
                target_id = st.selectbox("Pilih ID Lead", selectable_ids)
            
            with rev_col2:
                review_note = st.text_input("Catatan Reviewer", placeholder="Contoh: Nomor kontak aktif, data valid")
            
            with rev_col3:
                st.write("")
                btn_c1, btn_c2 = st.columns(2)
                with btn_c1:
                    if st.button("Approve"):
                        db.update_review_status(conn, target_id, "approved", review_note)
                        st.success(f"Lead #{target_id} disetujui.")
                        st.rerun()
                with btn_c2:
                    if st.button("Reject"):
                        db.update_review_status(conn, target_id, "rejected", review_note)
                        st.warning(f"Lead #{target_id} ditolak.")
                        st.rerun()

        with st.expander("Rincian Kalkulasi Skor"):
            for _, row in df_leads.iterrows():
                raw_reasons = row.get("Alasan_Skor")
                reasons = db.loads(raw_reasons, default={})
                if reasons and isinstance(reasons, dict):
                    st.markdown(f"**Data #{row['id']}** | {row['Komoditas']} ({row['Lokasi']}) | Status: `{row['Review']}`")
                    col_r, col_c = st.columns(2)
                    with col_r:
                        st.markdown("**Komponen Relevansi:**")
                        for r in reasons.get("relevance", []):
                            st.caption(r)
                    with col_c:
                        st.markdown("**Komponen Confidence:**")
                        for c in reasons.get("confidence", []):
                            st.caption(c)
                    st.divider()


# ================= TAB 2: MATCHMAKING & POOLING =================
with tab2:
    st.markdown("### Matchmaking dan Smart Pooling Engine")
    st.caption("Algoritma pencocokan dua sisi (Supply ↔ Demand) dan agregasi multi-petani terdekat (PRD §7.6)")

    m_act1, m_act2, m_act3 = st.columns([2, 1.5, 1.5])
    with m_act2:
        tier_select = st.selectbox("Filter Tier", ["Semua", "outreach", "review", "ignored"], index=0, help="outreach (skor ≥80), review (50-79), ignored (<50)")

    with m_act3:
        include_pending = st.checkbox("Sertakan lead pending berskor tinggi", value=True, help="Menyertakan petani yang belum di-approve tapi relevance ≥70 dan confidence ≥60")

    with m_act1:
        if st.button("Jalankan Matchmaking", type="primary", help="Hitung skor kecocokan semua order pembeli terhadap penawaran petani"):
            c_demand_cnt = conn.execute("SELECT COUNT(*) FROM listings WHERE intent = 'demand' AND duplicate_of IS NULL").fetchone()[0]
            c_supply_cnt = conn.execute("SELECT COUNT(*) FROM listings WHERE intent = 'supply' AND duplicate_of IS NULL").fetchone()[0]

            if c_demand_cnt == 0:
                st.session_state["notify_match_warning"] = (
                    "Data Permintaan Pembeli (Demand) belum ada di database. "
                    "Matchmaking memerlukan data penawaran petani (supply) DAN kebutuhan pembeli (demand). "
                    "Silakan masukkan pesanan pembeli pada formulir 'Input Permintaan Pembeli Baru (Demand)' di bawah, "
                    "atau klik tombol 'Muat Demo' pada sidebar."
                )
                st.rerun()
            elif c_supply_cnt == 0:
                st.session_state["notify_match_warning"] = (
                    "Data Penawaran Petani (Supply) belum ada di database. "
                    "Silakan jalankan pipeline pencarian petani terlebih dahulu atau klik tombol 'Muat Demo' pada sidebar."
                )
                st.rerun()
            else:
                with st.spinner(f"Menghitung kecocokan {c_demand_cnt} pesanan pembeli terhadap {c_supply_cnt} penawaran petani..."):
                    m_stats = run_all_matches(conn, include_pending_high_score=include_pending)
                    if m_stats["matches_created"] == 0 and m_stats["pools_created"] == 0:
                        st.session_state["notify_match_warning"] = (
                            f"Kalkulasi selesai untuk {m_stats['total_demand']} permintaan pembeli dan {c_supply_cnt} penawaran petani, "
                            "namun belum ada pasangan yang memenuhi skor minimal (komoditas berbeda atau kriteria toleransi harga/jarak tidak terpenuhi)."
                        )
                    else:
                        st.session_state["notify_match"] = (
                            f"Matchmaking Berhasil Dihitung! Ditemukan {m_stats['matches_created']} match tunggal "
                            f"dan {m_stats['pools_created']} smart pool aktif dari {m_stats['total_demand']} permintaan pembeli."
                        )
                    st.rerun()


    with st.expander("Input Permintaan Pembeli Baru (Demand)", expanded=False):
        st.caption("Tambahkan pesanan pembeli baru untuk langsung dipasangkan dengan petani di database.")
        with st.form("form_manual_order"):
            fo_c1, fo_c2 = st.columns(2)
            with fo_c1:
                b_name = st.text_input("Nama Usaha / Pembeli *", placeholder="Contoh: PT Sumber Berkah Buah")
                b_prod = st.text_input("Komoditas *", placeholder="Contoh: melon, semangka, pisang")
                b_vol = st.number_input("Volume Kebutuhan (Kg) *", min_value=1.0, value=500.0, step=50.0)
                b_price = st.number_input("Batas Anggaran Maksimal (Rp/Kg)", min_value=0.0, value=9000.0, step=500.0)
            with fo_c2:
                b_loc = st.text_input("Titik Pengiriman (Kabupaten/Kota) *", placeholder="Contoh: Kota Surabaya, Sidoarjo, Kediri")
                b_date = st.date_input("Tenggat Kebutuhan", value=datetime.now())
                b_phone = st.text_input("Nomor Kontak Pembeli", placeholder="Contoh: 081234567890")
                b_var = st.text_input("Varietas Khusus (Opsional)", placeholder="Contoh: madesta, golden, atau kosongkan")

            submitted_order = st.form_submit_button("Simpan Permintaan Pembeli", type="secondary")
            if submitted_order:
                if not b_name or not b_prod or not b_loc:
                    st.error("Nama pembeli, komoditas, dan lokasi pengiriman wajib diisi.")
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
                    st.success(f"Permintaan #{new_id} untuk '{b_name}' berhasil disimpan.")
                    st.rerun()

    matches_list = get_matches_for_display(conn, tier_filter=tier_select)

    if not matches_list:
        cur_dem = conn.execute("SELECT COUNT(*) FROM listings WHERE intent = 'demand' AND duplicate_of IS NULL").fetchone()[0]
        cur_sup = conn.execute("SELECT COUNT(*) FROM listings WHERE intent = 'supply' AND duplicate_of IS NULL").fetchone()[0]
        if cur_dem == 0:
            st.info(
                f"Belum ada data permintaan pembeli (Demand: 0, Supply: {cur_sup}). "
                "Tambahkan pesanan pembeli lewat form 'Input Permintaan Pembeli Baru' di atas atau klik 'Muat Demo' pada sidebar, "
                "lalu klik tombol 'Jalankan Matchmaking'."
            )
        else:
            st.info(
                f"Database memiliki {cur_sup} penawaran petani dan {cur_dem} permintaan pembeli. "
                "Klik tombol 'Jalankan Matchmaking' di atas untuk menghitung kecocokan."
            )
    else:
        top_exp1, top_exp2 = st.columns([3, 1.3])
        with top_exp1:
            st.caption(f"Menampilkan {len(matches_list)} hasil rekomendasi pasangan:")
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
            tier_label = "Prioritas Outreach" if m["tier"] == "outreach" else ("Perlu Review" if m["tier"] == "review" else "Diabaikan")
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
                                Komoditas: <b>{(m.get('product') or 'Komoditas').title()}</b> | 
                                Kebutuhan: <b>{f"{m['buyer_vol']:g} kg" if m.get('buyer_vol') is not None else "Tidak ditentukan"}</b> | 
                                Anggaran Maksimal: <b>{f"Rp {float(m['buyer_max_price']):,.0f}/kg" if m.get('buyer_max_price') is not None else 'Belum ditentukan'}</b>
                            </span>
                        </div>
                        <div style="text-align:right;">
                            <div style="font-size:1.8rem; font-weight:700; color:#101828; line-height:1;">
                                {m.get('score', 0)}<span style="font-size:12px; color:#64748b; font-weight:500;">/100</span>
                            </div>
                            <div style="font-size:11px; color:#0284c7; font-weight:600; margin-top:2px;">Cakupan: {f"{m['coverage_pct']:g}%" if m.get('coverage_pct') is not None else "-"}</div>
                        </div>
                    </div>
                </div>
            """, unsafe_allow_html=True)

            with st.container(border=True):
                st.markdown("**Petani Rekomendasi:**")
                items = m.get("items", [])
                if items:
                    f_cols = st.columns(len(items)) if len(items) <= 3 else [st.container()]
                    for idx, it in enumerate(items):
                        target_col = f_cols[idx] if len(items) <= 3 else st
                        with target_col:
                            st.markdown(f"**{it.get('farmer_name') or 'Petani'}** ({it.get('farmer_location') or '-'})")
                            f_pr = it.get('farmer_price')
                            price_str = f"Rp {float(f_pr):,.0f}/kg" if f_pr is not None else "Belum tertera"
                            al_kg = it.get('allocated_kg')
                            alloc_str = f"{float(al_kg):g} kg" if al_kg is not None else "-"
                            st.caption(f"Alokasi: {alloc_str} | Harga: {price_str}")
                            if it.get("distance_km"):
                                st.caption(f"Estimasi Jarak: {it['distance_km']} km")
                            
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
                                st.markdown(f"[Hubungi WhatsApp]({farmer_wa_url})")
                                with st.popover("Draf Pesan & CRM"):
                                    st.caption("Draf otomatis yang terisi di WhatsApp:")
                                    st.code(farmer_draft, language="text")
                                    if st.button("Daftarkan ke Sales CRM", key=f"btn_reg_crm_f_{m['match_id']}_{it['supply_id']}"):
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
                                            st.session_state["notify_success"] = f"Petani '{it.get('farmer_name')}' berhasil didaftarkan ke Sales CRM #{new_c_id}!"
                                        else:
                                            st.session_state["notify_info"] = f"Petani '{it.get('farmer_name')}' sudah ada di Sales CRM #{existing_c['id']}."
                                        st.rerun()
                            elif it.get("farmer_phone"):
                                st.caption(f"Telp: {it['farmer_phone']}")

                if is_pool:
                    disclaimer_text = m.get("breakdown", {}).get("disclaimer")
                    if disclaimer_text:
                        st.info(f"Catatan Agregasi: {disclaimer_text}")

                margin_info = m.get("margin")
                if margin_info and (margin_info.get("est_gross_margin_rp") or 0) > 0:
                    m_pct = margin_info.get('margin_pct') or 0.1
                    m_gross = margin_info.get('est_gross_margin_rp') or 0
                    f_price = margin_info.get('farmer_price') or 0
                    s_price = margin_info.get('suggested_price') or 0
                    st.markdown(
                        f"**Estimasi Margin GoTani ({m_pct:.0%}):** "
                        f"Rp {m_gross:,.0f} "
                        f"(Harga Petani: Rp {f_price:,.0f}/kg, Rekomendasi Penawaran: Rp {s_price:,.0f}/kg)"
                    )

                gaps = m.get("gaps", [])
                if gaps:
                    with st.expander("Catatan Validasi & Kekurangan Data", expanded=False):
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
                        st.markdown(f"[Hubungi Pembeli via WhatsApp]({buyer_wa_url})")
                        with st.popover("Draf Penawaran & CRM"):
                            st.caption("Draf penawaran otomatis untuk pembeli:")
                            st.code(buyer_draft, language="text")
                            if st.button("Daftarkan Pembeli ke CRM", key=f"btn_reg_crm_b_{m['match_id']}"):
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
                                    st.session_state["notify_success"] = f"Pembeli '{m['buyer_name']}' berhasil didaftarkan ke Sales CRM #{new_cb_id}!"
                                else:
                                    st.session_state["notify_info"] = f"Pembeli '{m['buyer_name']}' sudah ada di Sales CRM #{existing_cb['id']}."
                                st.rerun()
                    else:
                        st.caption("Kontak pembeli belum tersedia")


                with act_c2:
                    if m["status"] == "open":
                        if st.button("Konfirmasi Outreach", key=f"conf_{m['match_id']}"):
                            update_match_status(conn, m["match_id"], "confirmed")
                            st.success("Status match diperbarui menjadi confirmed.")
                            st.rerun()
                    else:
                        st.caption(f"Status Alur: {m['status'].upper()}")

                with act_c3:
                    if m["status"] != "closed":
                        with st.popover("Catat Hasil Transaksi"):
                            out_choice = st.radio("Hasil Transaksi", ["deal", "no_deal"], key=f"rad_{m['match_id']}")
                            out_note = st.text_input("Keterangan Hasil", placeholder="Contoh: Kesepakatan harga tercapai, jadwal panen cocok", key=f"note_{m['match_id']}")
                            if st.button("Simpan Hasil", key=f"btn_out_{m['match_id']}"):
                                update_match_outcome(conn, m["match_id"], out_choice, out_note)
                                st.success("Hasil transaksi tersimpan.")
                                st.rerun()
                    else:
                        st.caption(f"Hasil Akhir: {str(m.get('outcome')).upper()} ({m.get('outcome_reason') or '-'})")



# ================= TAB 3: SALES INBOX & OUTREACH CRM (FASE 3) =================
with tab3:
    st.markdown("### Sales Inbox & Outreach CRM")
    st.caption("Pusat komando outreach terpersonalisasi, cadence follow-up otomatis, smart handover eskalasi, dan kepatuhan UU PDP (PRD §7.8)")

    # 1. Action bar & Metrics
    s_metrics = calculate_sales_metrics(conn)
    
    m_top1, m_top2 = st.columns([3, 1])
    with m_top1:
        crm_c1, crm_c2, crm_c3, crm_c4 = st.columns(4)
        crm_c1.metric("Total Sesi CRM", s_metrics["total_convs"], help="Jumlah seluruh sesi percakapan prospek.")
        crm_c2.metric("Outreach Aktif", s_metrics["total_outreach"], help="Pesan yang telah dikirimkan ke lead.")
        crm_c3.metric("Butuh Handover", s_metrics["handover_count"], help="Percakapan yang memerlukan eskalasi ke staf manusia.")
        crm_c4.metric("Deals Won", s_metrics["won_count"], help="Transaksi yang berhasil disepakati.")
    with m_top2:
        df_export_crm = build_conversations_export_dataframe(conn)
        csv_crm = df_export_crm.to_csv(index=False).encode("utf-8")
        st.download_button(
            "Export Laporan CRM (CSV)",
            csv_crm,
            file_name=f"sales_crm_report_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv",
            help="Unduh rekapan komprehensif performa sales outreach dan riwayat interaksi."
        )

    # Funnel Konversi Sales (PRD §7.8 / F8.10)
    with st.expander("Funnel Konversi & Metrik Kinerja Sales AI (PRD F8.10)", expanded=False):
        f_m1, f_m2, f_m3, f_m4 = st.columns(4)
        f_m1.metric("Reply Rate", f"{s_metrics['reply_rate_pct']}%", help="Persentase lead yang membalas pesan outreach.")
        f_m2.metric("Handover Rate", f"{s_metrics['handover_rate_pct']}%", help="Persentase percakapan yang membutuhkan bantuan staf manusia.")
        f_m3.metric("Conversion (Win) Rate", f"{s_metrics['conversion_rate_pct']}%", help="Persentase kesepakatan transaksi dari total outreach.")
        f_m4.metric("Opt-Out (DNC) Rate", f"{s_metrics['opt_out_rate_pct']}%", help="Persentase kontak yang menolak (Target: < 5%).")

    # 2. Check Cadence Follow-Up Due
    due_followups = get_due_followups(conn)
    if due_followups:
        st.warning(f"Ada {len(due_followups)} percakapan yang telah jatuh tempo untuk dikirimkan pesan follow-up.")
        with st.expander(f"Lihat Daftar Pengingat Jatuh Tempo ({len(due_followups)})", expanded=True):
            for df_row in due_followups:
                df_c1, df_c2 = st.columns([3, 1])
                with df_c1:
                    st.markdown(f"**{df_row['contact_name'] or 'Kontak'}** ({df_row['contact_phone']}) - Komoditas: {df_row['product']}")
                    st.caption(f"Status: {df_row['state']} | Follow-up ke-{df_row['followup_count'] + 1} jatuh tempo pada {df_row['followup_due_at']}")
                with df_c2:
                    fu_msg = generate_followup_message(conn, df_row['id'])
                    fu_url = format_wa_url(df_row['contact_phone'], fu_msg)
                    if fu_url:
                        st.markdown(f"[Kirim Follow-Up via WA]({fu_url})")
                    if st.button(f"Tandai Terkirim #{df_row['id']}", key=f"btn_send_fu_{df_row['id']}"):
                        db.add_message(conn, df_row['id'], "outbound", "ai", fu_msg, delivery_status="sent")
                        advance_followup(conn, df_row['id'])
                        st.success(f"Follow-up untuk #{df_row['id']} berhasil dicatat!")
                        st.rerun()

    st.write("")
    # 3. Filter controls
    f_c1, f_c2, f_c3 = st.columns([1.5, 1.5, 2])
    with f_c1:
        crm_state_filter = st.selectbox(
            "Filter Status Percakapan",
            ["Semua", "drafted", "sent", "followup_1", "active", "handover_pending", "closed_won", "closed_lost", "opt_out"],
            index=0,
            key="crm_filter_state"
        )
    with f_c2:
        crm_role_filter = st.selectbox(
            "Filter Peran Prospek",
            ["Semua", "farmer", "buyer"],
            index=0,
            key="crm_filter_role"
        )

    # Inisiasi Percakapan Baru dari Listing Approved
    with f_c3:
        st.markdown("<div style='height:28px;'></div>", unsafe_allow_html=True)
        with st.popover("Inisiasi Outreach Lead Baru"):
            st.caption("Pilih lead terverifikasi untuk dibuatkan draf percakapan pertama:")
            avail_leads = conn.execute("""
                SELECT id, entity_name, product, intent, contact_phone, kabupaten
                FROM listings
                WHERE contact_phone IS NOT NULL
                  AND duplicate_of IS NULL
                  AND id NOT IN (SELECT listing_id FROM conversations)
                ORDER BY relevance DESC, confidence DESC LIMIT 15
            """).fetchall()
            if not avail_leads:
                st.caption("Semua lead yang memiliki kontak sudah memiliki sesi percakapan.")
            else:
                lead_choices = {f"#{l['id']} - {l['entity_name'] or 'Anonim'} ({l['product']}, {l['intent']}, {l['kabupaten']})": l for l in avail_leads}
                sel_lead_key = st.selectbox("Pilih Prospek", list(lead_choices.keys()))
                if st.button("Buat Sesi Percakapan", type="primary"):
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
                    st.session_state["notify_success"] = f"Percakapan #{c_id} untuk '{sel_l['entity_name']}' berhasil diinisiasi!"
                    st.rerun()

    # 4. Tampilkan daftar percakapan
    conversations_list = db.list_conversations(conn, state=crm_state_filter, role=crm_role_filter)
    if not conversations_list:
        st.info("Belum ada percakapan yang sesuai dengan filter yang dipilih.")
    else:
        st.caption(f"Menampilkan {len(conversations_list)} sesi percakapan:")
        for c in conversations_list:
            c_dict = dict(c)
            c_id = c_dict["id"]
            c_state = c_dict["state"]
            c_name = c_dict["contact_name"] or "Tanpa Nama"
            c_phone = c_dict["contact_phone"]
            c_role = "Petani (Supply)" if c_dict["role"] == "farmer" else "Pembeli (Demand)"
            c_prod = (c_dict.get("product") or "komoditas").title()
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
                        f"🚨 **ESKALASI HANDOVER SALES:** Percakapan ini membutuhkan respons langsung staf GoTani! "
                        f"Penyebab: {c_dict.get('summary_text') or 'Lead merespons dengan pertanyaan atau negosiasi.'}"
                    )
                    h_act1, h_act2, h_act3 = st.columns(3)
                    with h_act1:
                        if st.button("Ambil Alih (Take Over)", key=f"btn_takeover_{c_id}", type="primary"):
                            db.update_conversation(conn, c_id, state="active", assigned_sales="Staf Aktif")
                            st.success(f"Percakapan #{c_id} dialihkan ke penanganan staf manusia.")
                            st.rerun()
                    with h_act2:
                        if st.button("Tandai Deal (Closed Won)", key=f"btn_won_{c_id}"):
                            db.update_conversation(conn, c_id, state="closed_won", summary_text="Kesepakatan deal tercapai.")
                            st.success(f"Transaksi #{c_id} sukses dicatat sebagai Closed Won!")
                            st.rerun()
                    with h_act3:
                        if st.button("Tutup (Closed Lost)", key=f"btn_lost_{c_id}"):
                            db.update_conversation(conn, c_id, state="closed_lost", summary_text="Tidak tercapai kesepakatan.")
                            st.info(f"Percakapan #{c_id} ditutup.")
                            st.rerun()

                # Riwayat Pesan (Thread Expander)
                msgs = db.get_messages(conn, c_id)
                with st.expander(f"Thread Riwayat Pesan ({len(msgs)} pesan)", expanded=(c_state in ("drafted", "handover_pending"))):
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
                            st.markdown(f"**[Buka WhatsApp Web / App]({wa_url})**")
                        elif is_do_not_contact(conn, c_phone):
                            st.caption("Nomor ini telah Opt-Out (Do-Not-Contact). Pengiriman dinonaktifkan.")

                        if c_state == "drafted":
                            if st.button("Tandai Pesan Awal Terkirim", key=f"btn_mark_sent_{c_id}"):
                                db.update_conversation(conn, c_id, state="sent", followup_due_at=calculate_due_date(days_ahead=3))
                                st.success("Status percakapan diperbarui ke 'sent' (jadwal follow-up H+3 aktif).")
                                st.rerun()

                    with act_col2:
                        # Form input balasan masuk dari lead
                        if c_state not in ("closed_won", "closed_lost", "opt_out"):
                            with st.form(key=f"form_inbound_{c_id}"):
                                in_text = st.text_input("Input balasan pesan WhatsApp dari lead:", placeholder="Contoh: Masih ada 1 ton, harga pas berapa?")
                                submit_inbound = st.form_submit_button("Proses Balasan Lead")
                                if submit_inbound and in_text.strip():
                                    # 1. Catat inbound message
                                    db.add_message(conn, c_id, "inbound", "lead", in_text.strip(), delivery_status="received")
                                    
                                    # 2. Evaluasi Handover & Kepatuhan
                                    eval_res = evaluate_inbound_message(in_text.strip())
                                    
                                    if eval_res["trigger_type"] == "opt_out":
                                        register_opt_out_contact(conn, c_phone, reason="user_stop", source_message=in_text.strip())
                                        st.warning("Lead meminta berhenti dihubungi. Kontak otomatis dimasukkan ke supresi Do-Not-Contact (UU PDP).")
                                    elif eval_res["needs_handover"]:
                                        db.update_conversation(conn, c_id, state="handover_pending", summary_text=eval_res["reason"])
                                        st.error(f"Eskalasi Handover Terdeteksi: {eval_res['reason']}")
                                    else:
                                        # Hasilkan respon AI rutin
                                        ai_reply = generate_conversational_reply(conn, c_id, in_text.strip(), gateway=gateway)
                                        db.add_message(conn, c_id, "outbound", "ai", ai_reply, delivery_status="draft")
                                        db.update_conversation(conn, c_id, state="active", summary_text="AI menyusun draf balasan.")
                                        st.success("Balasan dianalisis! Draf respon AI telah ditambahkan ke thread percakapan.")
                                    st.rerun()

    # 5. Tabel Supresi Kepatuhan UU PDP (Opt-Out Registry)
    with st.expander("Registri Kepatuhan & Supresi Kontak (Do-Not-Contact List - UU PDP G5)", expanded=False):
        st.caption("Daftar nomor telepon yang meminta berhenti dihubungi atau penghapusan data kontak:")
        opt_rows = conn.execute("SELECT contact_phone, reason, source_message, opted_out_at FROM opt_outs ORDER BY opted_out_at DESC").fetchall()
        if opt_rows:
            st.dataframe(
                pd.DataFrame([dict(r) for r in opt_rows]),
                use_container_width=True,
                hide_index=True,
                column_config={
                    "contact_phone": "Nomor Kontak",
                    "reason": "Alasan Supresi",
                    "source_message": "Pesan Terakhir Lead",
                    "opted_out_at": "Waktu Opt-Out"
                }
            )
        else:
            st.caption("Belum ada kontak yang meminta opt-out.")


# ================= TAB 4: RAW DATA LOG =================
with tab4:
    df_raw = pd.read_sql_query("""
        SELECT
            r.id AS ID,
            r.platform AS Platform,
            r.campaign_id AS Campaign,
            COALESCE(NULLIF(r.author_name, ''), 'Anonim / Publik') AS Pemosting,
            (SELECT l.contact_phone FROM listings l WHERE l.raw_item_id = r.id AND l.contact_phone IS NOT NULL LIMIT 1) AS Listing_Phone,
            r.raw_text AS Teks_Original,
            r.url AS URL,
            r.fetched_at AS Waktu_Scrape,
            r.processed AS Diproses
        FROM raw_items r
        ORDER BY r.id DESC LIMIT 200
    """, conn)

    if df_raw.empty:
        st.caption("Data log mentah kosong.")
    else:
        # Ekstraksi dan format nomor kontak faktual dari data listing atau teks postingan mentah
        def _get_raw_contact(row):
            import re
            c = row.get("Listing_Phone")
            if pd.notna(c) and str(c).strip() and str(c).strip() != "-":
                raw_c = str(c).strip()
            else:
                text = str(row.get("Teks_Original", ""))
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

        df_raw["Kontak"] = df_raw.apply(_get_raw_contact, axis=1)
        df_raw = df_raw.drop(columns=["Listing_Phone"])

        cols_order = ["ID", "Platform", "Pemosting", "Kontak", "Campaign", "URL", "Teks_Original", "Waktu_Scrape", "Diproses"]
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
                "Platform": st.column_config.TextColumn("Sumber", width="small"),
                "Pemosting": st.column_config.TextColumn("Pemosting", width="medium"),
                "Kontak": st.column_config.TextColumn("Kontak / No. HP", width="medium"),
                "Campaign": st.column_config.TextColumn("Campaign", width="medium"),
                "URL": st.column_config.LinkColumn("Tautan Sumber", display_text="Buka Tautan", width="medium"),
                "Teks_Original": st.column_config.TextColumn("Teks Postingan Asli", width="large"),
                "Waktu_Scrape": st.column_config.TextColumn("Waktu Scrape", width="small"),
                "Diproses": st.column_config.CheckboxColumn("Diproses"),
            },
        )


# ================= TAB 5: RIWAYAT KAMPANYE & RUN LOG =================
with tab5:
    st.markdown("##### Riwayat Kampanye Pencarian")
    try:
        campaigns = list_campaigns(conn)
        if campaigns:
            df_camp = pd.DataFrame(
                [(c["id"], c["goal"], c["status"], c["created_at"]) for c in campaigns],
                columns=["ID", "Tujuan", "Status", "Dibuat"],
            )
            st.dataframe(df_camp, use_container_width=True, hide_index=True)
        else:
            st.caption("Belum ada riwayat kampanye.")
    except Exception:
        st.caption("Belum ada riwayat kampanye.")

    st.write("")
    st.markdown("##### Log Eksekusi Pipeline (Apify & AI Runs)")
    try:
        df_runs = pd.read_sql_query("""
            SELECT
                id AS Run_ID,
                campaign_id AS Campaign,
                step AS Tahap,
                platform AS Platform,
                status AS Status,
                items_found AS Item_Ditemukan,
                started_at AS Waktu_Mulai,
                finished_at AS Waktu_Selesai,
                error AS Catatan_Error
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
                    "Tahap": st.column_config.TextColumn("Tahap", width="small"),
                    "Platform": st.column_config.TextColumn("Platform", width="small"),
                    "Status": st.column_config.TextColumn("Status", width="small"),
                    "Item_Ditemukan": st.column_config.NumberColumn("Item Ditemukan", width="small"),
                    "Waktu_Mulai": st.column_config.TextColumn("Mulai", width="medium"),
                    "Waktu_Selesai": st.column_config.TextColumn("Selesai", width="medium"),
                    "Catatan_Error": st.column_config.TextColumn("Keterangan", width="large"),
                }
            )
        else:
            st.caption("Belum ada log eksekusi pipeline.")
    except Exception as e:
        st.caption(f"Gagal memuat log runs: {e}")

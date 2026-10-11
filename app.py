import streamlit as st
import asyncio
import time
import pandas as pd
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
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
from agent.caller_lookup import lookup_caller
from agent.outreach import (
    format_wa_url,
    draft_farmer_outreach_for_match,
    draft_farmer_outreach_for_lead,
    draft_buyer_outreach_for_match,
    build_matches_export_dataframe,
)

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
    c_btn1, c_btn2 = st.columns(2)
    with c_btn1:
        if st.button("Muat Demo", help="Mengisi database dengan dataset demo komprehensif"):
            with st.spinner("Memuat dataset demo..."):
                subprocess.run([sys.executable, "seed_demo.py"], cwd=str(Path(__file__).parent))
                st.session_state["notify_success"] = "Dataset demo berhasil dimuat! 38 postingan mentah, 25 prospek terverifikasi, dan 61 match aktif siap diuji."
                st.rerun()
    with c_btn2:
        if st.button("Hapus Data", help="Mengosongkan semua catatan lead dan match"):
            with st.spinner("Mengosongkan database..."):
                conn.execute("DELETE FROM matches")
                conn.execute("DELETE FROM match_items")
                conn.execute("DELETE FROM listings")
                conn.execute("DELETE FROM raw_items")
                conn.commit()
                st.session_state["notify_info"] = "Database berhasil dikosongkan."
            st.rerun()

    st.divider()

    # --- Section: New Campaign Spec ---
    st.markdown("<div style='font-size:11px; font-weight:600; color:#94a3b8; text-transform:uppercase; margin-bottom:8px;'>Kampanye Pencarian</div>", unsafe_allow_html=True)

    # Inisialisasi template JSON bawaan jika session belum ada
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

    spec_mode = st.radio(
        "Metode Konfigurasi",
        ["Manual / JSON Editor", "AI Natural Language"],
        horizontal=True,
        label_visibility="collapsed"
    )

    if spec_mode == "AI Natural Language":
        prompt_text = st.text_area(
            "Kriteria Pencarian",
            placeholder="Contoh: Cari petani melon di Jawa Timur, minimal 500 kg",
            height=70,
            label_visibility="collapsed",
        )
        if st.button("Susun Spesifikasi (AI)"):
            if not prompt_text.strip():
                st.warning("Masukkan kriteria pencarian terlebih dahulu.")
            else:
                with st.spinner("Menyusun spesifikasi kampanye..."):
                    cid = new_campaign_id(conn)
                    spec = None
                    if gateway.available:
                        try:
                            spec, qs = draft_spec_llm(gateway, prompt_text, cid)
                            if qs:
                                for q in qs:
                                    st.info(f"Saran pelengkap: {q}")
                        except Exception as e:
                            st.warning(f"API AI sibuk: {e}")
                    if spec is None:
                        spec = draft_spec_offline(prompt_text, cid)
                    st.session_state["draft_spec"] = spec.to_json()
                    st.rerun()
    else:
        # Pilihan Cepat Preset Template untuk Isi Manual
        c_tpl1, c_tpl2 = st.columns([2.2, 1])
        with c_tpl1:
            tpl_choice = st.selectbox(
                "Preset Template",
                ["Preset: Melon Jatim", "Preset: Cabai Rawit", "Preset: Rempah Jahe & Cengkeh", "Preset: Demand Toko Buah"],
                label_visibility="collapsed"
            )
        with c_tpl2:
            if st.button("Gunakan", help="Muat template ini ke kotak JSON di bawah"):
                cid = new_campaign_id(conn)
                tpl_spec = CampaignSpec(campaign_id=cid)
                if "Melon" in tpl_choice:
                    tpl_spec.product.name = "Melon"
                    tpl_spec.product.synonyms = ["melon", "madesta", "golden"]
                    tpl_spec.location.include = ["Jawa Timur"]
                    tpl_spec.location.priority = ["Jombang", "Kediri", "Blitar"]
                    tpl_spec.volume.min = 500.0
                elif "Cabai" in tpl_choice:
                    tpl_spec.product.name = "Cabai"
                    tpl_spec.product.synonyms = ["cabai rawit", "cabe merah", "lombok"]
                    tpl_spec.location.include = ["Jawa Timur"]
                    tpl_spec.location.priority = ["Kediri", "Blitar", "Banyuwangi"]
                    tpl_spec.volume.min = 200.0
                elif "Rempah" in tpl_choice:
                    tpl_spec.product.name = "Jahe"
                    tpl_spec.product.synonyms = ["jahe gajah", "jahe merah", "cengkeh"]
                    tpl_spec.location.include = ["Jawa Timur"]
                    tpl_spec.location.priority = ["Pacitan", "Trenggalek"]
                    tpl_spec.volume.min = 1000.0
                elif "Demand" in tpl_choice:
                    tpl_spec.goal = "find_demand"
                    tpl_spec.target_entity = "toko buah / distributor"
                    tpl_spec.product.name = "Melon"
                    tpl_spec.location.include = ["Surabaya", "Sidoarjo", "Malang"]
                    tpl_spec.volume.min = 1000.0
                st.session_state["draft_spec"] = tpl_spec.to_json()
                st.rerun()

    # Kotak Konfigurasi JSON SELALU TERSEDIA untuk diedit / ditempel manual
    edited_spec_json = st.text_area(
        "Konfigurasi Spesifikasi (JSON)",
        value=st.session_state.get("draft_spec", "{}"),
        height=220,
        help="Anda dapat mengedit atau menempel JSON kustom secara manual kapan saja."
    )

    if st.button("Jalankan Pipeline", type="primary", help="Mulai penelusuran multi-platform dan ekstraksi AI berdasarkan JSON di atas"):
        try:
            raw_spec = json.loads(edited_spec_json)
            c = CampaignSpec.model_validate(raw_spec)
            save_campaign(conn, c)
            with st.status("Menjalankan Pipeline Inteligensi Pasar...", expanded=True) as status_box:
                def on_progress(step_title: str, detail_text: str):
                    status_box.write(f"[{datetime.now().strftime('%H:%M:%S')}] **{step_title}**: {detail_text}")

                pipe = Pipeline(c, progress_callback=on_progress)
                asyncio.run(pipe.run())
                status_box.update(label="Pipeline Berhasil Selesai!", state="complete", expanded=False)
                st.session_state["notify_success"] = f"Pipeline berhasil diselesaikan! Data prospek baru untuk komoditas '{c.product.name}' berhasil diekstrak dan disimpan ke database."
                time.sleep(1)
                st.rerun()
        except Exception as e:
            st.error(f"Kesalahan pada eksekusi pipeline: {e}")

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
            st.info(caller_res.get("message"))
            with st.expander("Panduan Bicara (Kontak Baru)", expanded=True):
                for p in caller_res["talking_points"]:
                    st.markdown(f"- {p}")
        else:
            st.success(f"{caller_res['name']} ({caller_res['role']})")
            st.caption(f"Komoditas: {caller_res['product']} | Lokasi: {caller_res['location']}")
            with st.expander("Panduan Bicara", expanded=True):
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
    total_leads = conn.execute("SELECT COUNT(*) FROM listings").fetchone()[0]
    high_conf = conn.execute("SELECT COUNT(*) FROM listings WHERE confidence >= 80").fetchone()[0]
    total_matches = conn.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
    usage = gateway.usage_today()
except Exception:
    total_raw, total_leads, high_conf, total_matches = 0, 0, 0, 0
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
            <span class="apify-meta-item">Biaya: <b>${usage['cost_usd']:.3f}</b></span>
            <span class="apify-meta-item">Waktu: <b>{last_run_time}</b></span>
        </div>
        <div>
            <span style="font-size:12px; color:#0284c7; font-weight:600;">Status Operasional Normal</span>
        </div>
    </div>
""", unsafe_allow_html=True)

# Notifikasi Aksi (Persisten setelah rerun)
if "notify_success" in st.session_state:
    st.success(st.session_state.pop("notify_success"))
if "notify_info" in st.session_state:
    st.info(st.session_state.pop("notify_info"))

# 3. Metric Summary Cards (Apify Dashboard Widget Style)
col_m1, col_m2, col_m3, col_m4 = st.columns(4)
col_m1.metric("Raw Scraped Posts", f"{total_raw:,}", help="Jumlah postingan yang tersimpan dari penelusuran Google Search Scraper.")
col_m2.metric("Extracted Leads", f"{total_leads:,}", help="Jumlah data lead yang berhasil diekstrak dan dinormalisasi.")
col_m3.metric("High Confidence", f"{high_conf:,}", help="Prospek terverifikasi dengan tingkat keyakinan data ≥ 80%.")
col_m4.metric("Active Matches", f"{total_matches:,}", help="Jumlah rekomendasi kecocokan pasokan dan permintaan yang teridentifikasi.")

st.write("") # Spacer

# 4. Main Tabs Navigation (Apify Output Style)
tab1, tab2, tab3, tab4 = st.tabs([
    f"Verified Leads ({total_leads})",
    f"Matchmaking & Pooling ({total_matches})",
    f"Raw Data Log ({total_raw})",
    "Riwayat Kampanye",
])


# ================= TAB 1: VERIFIED LEADS =================
with tab1:
    fc1, fc2, fc3 = st.columns([1.5, 1.5, 1.2])
    with fc1:
        min_rel = st.slider("Batas Minimum Relevansi", 0, 100, 0, 5)
    with fc2:
        min_conf = st.slider("Batas Minimum Confidence", 0, 100, 0, 5)
    with fc3:
        status_filter = st.selectbox("Status Verifikasi", ["Semua", "pending", "approved", "rejected"], index=0)

    query_str = """
        SELECT
            l.id,
            l.entity_name AS Nama,
            l.intent AS Intent,
            l.product AS Komoditas,
            l.attributes_json AS Atribut,
            l.volume_kg AS Volume_Kg,
            l.price_per_kg AS Harga_Kg,
            l.location_text AS Lokasi,
            l.contact_phone AS Telepon,
            l.relevance AS Rel_Score,
            l.confidence AS Conf_Score,
            l.score_reasons_json AS Alasan_Skor,
            l.review_status AS Review,
            l.extractor AS Extractor,
            r.url AS URL
        FROM listings l
        JOIN raw_items r ON l.raw_item_id = r.id
        WHERE l.relevance >= ? AND l.confidence >= ?
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
        def make_lead_wa_link(row):
            phone = row.get("Telepon")
            if not phone:
                return None
            msg = draft_farmer_outreach_for_lead(
                farmer_name=row.get("Nama"),
                commodity=str(row.get("Komoditas") or "hasil tani"),
                farmer_location=row.get("Lokasi"),
                volume_kg=row.get("Volume_Kg"),
                price_per_kg=row.get("Harga_Kg"),
            )
            return format_wa_url(phone, msg)
        
        df_leads["Chat_WA"] = df_leads.apply(make_lead_wa_link, axis=1)
        
        def extract_variety(attr_json):
            if not attr_json: return ""
            try:
                data = json.loads(attr_json)
                variety = data.get("variety", [])
                grade = data.get("grade")
                res = []
                if variety: res.append(f"Varietas: {', '.join(variety)}")
                if grade: res.append(f"Grade: {grade}")
                return " | ".join(res)
            except Exception:
                return ""
                
        df_leads["Kualitas"] = df_leads["Atribut"].apply(extract_variety)
        
        def detect_link_label(url_str):
            if not url_str: return "Buka Sumber"
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
            "id", "Komoditas", "Kategori", "Volume_Kg", "Harga_Kg", 
            "Lokasi", "Chat_WA", "Rel_Score", "Review", "Label_Sumber", "URL"
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
                "Volume_Kg": st.column_config.NumberColumn("Volume (Kg)", format="%d", width="small"),
                "Harga_Kg": st.column_config.NumberColumn("Harga/Kg", format="Rp %d", width="small"),
                "Lokasi": st.column_config.TextColumn("Lokasi", width="medium"),
                "Chat_WA": st.column_config.LinkColumn("WhatsApp", display_text="Hubungi WhatsApp", width="medium"),
                "Rel_Score": st.column_config.ProgressColumn("Relevansi", min_value=0, max_value=100, format="%d%%", width="small"),
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
                reasons = json.loads(row["Alasan_Skor"]) if row["Alasan_Skor"] else {}
                if reasons:
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
            with st.spinner("Menghitung kecocokan dan menyusun smart pool..."):
                m_stats = run_all_matches(conn, include_pending_high_score=include_pending)
                st.session_state["notify_match"] = f"Matchmaking Berhasil Dihitung! {m_stats['matches_created']} match tunggal dan {m_stats['pools_created']} smart pool aktif siap dieksekusi."
                st.rerun()

    if "notify_match" in st.session_state:
        st.success(st.session_state.pop("notify_match"))


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
        st.info("Belum ada data match yang memenuhi kriteria filter. Klik tombol 'Jalankan Matchmaking' di atas.")
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
                                Komoditas: <b>{m['product'].title()}</b> | Kebutuhan: <b>{m['buyer_vol']:g} kg</b> | 
                                Anggaran Maksimal: <b>{f'Rp {m["buyer_max_price"]:,.0f}/kg' if m.get('buyer_max_price') else 'Belum ditentukan'}</b>
                            </span>
                        </div>
                        <div style="text-align:right;">
                            <div style="font-size:1.8rem; font-weight:700; color:#101828; line-height:1;">
                                {m['score']}<span style="font-size:12px; color:#64748b; font-weight:500;">/100</span>
                            </div>
                            <div style="font-size:11px; color:#0284c7; font-weight:600; margin-top:2px;">Cakupan: {m['coverage_pct']:g}%</div>
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
                            price_str = f"Rp {it.get('farmer_price', 0):,.0f}/kg" if it.get('farmer_price') else "Belum tertera"
                            st.caption(f"Alokasi: {it.get('allocated_kg', 0):g} kg | Harga: {price_str}")
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
                                with st.popover("Draf Pesan"):
                                    st.caption("Draf otomatis yang terisi di WhatsApp:")
                                    st.code(farmer_draft, language="text")
                            elif it.get("farmer_phone"):
                                st.caption(f"Telp: {it['farmer_phone']}")

                if is_pool:
                    disclaimer_text = m.get("breakdown", {}).get("disclaimer")
                    if disclaimer_text:
                        st.info(f"Catatan Agregasi: {disclaimer_text}")

                margin_info = m.get("margin")
                if margin_info and margin_info.get("est_gross_margin_rp", 0) > 0:
                    st.markdown(
                        f"**Estimasi Margin GoTani ({margin_info.get('margin_pct', 0.1):.0%}):** "
                        f"Rp {margin_info['est_gross_margin_rp']:,.0f} "
                        f"(Harga Petani: Rp {margin_info['farmer_price']:,.0f}/kg, Rekomendasi Penawaran: Rp {margin_info['suggested_price']:,.0f}/kg)"
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
                        with st.popover("Draf Penawaran"):
                            st.caption("Draf penawaran otomatis untuk pembeli:")
                            st.code(buyer_draft, language="text")
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


# ================= TAB 3: RAW DATA LOG =================
with tab3:
    df_raw = pd.read_sql_query("""
        SELECT
            id AS ID,
            platform AS Platform,
            campaign_id AS Campaign,
            url AS URL,
            fetched_at AS Waktu_Scrape,
            raw_text AS Teks_Original,
            processed AS Diproses
        FROM raw_items
        ORDER BY id DESC LIMIT 200
    """, conn)

    if df_raw.empty:
        st.caption("Data log mentah kosong.")
    else:
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
                "Campaign": st.column_config.TextColumn("Campaign", width="medium"),
                "URL": st.column_config.LinkColumn("Tautan Sumber", display_text="Buka Tautan", width="medium"),
                "Teks_Original": st.column_config.TextColumn("Teks Postingan Asli", width="large"),
                "Diproses": st.column_config.CheckboxColumn("Diproses"),
            },
        )


# ================= TAB 4: RIWAYAT KAMPANYE & RUN LOG =================
with tab4:
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

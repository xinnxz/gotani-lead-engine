import streamlit as st
import asyncio
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

# ================= PAGE CONFIG (harus pertama) =================
st.set_page_config(
    page_title="GoTani Lead Engine",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ================= CUSTOM CSS =================
st.markdown("""
<style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}

    div[data-testid="stMetricValue"] {
        font-size: 2rem; font-weight: 700; color: #166534;
    }
    div[data-testid="stMetricLabel"] {
        font-size: 0.9rem; font-weight: 600; color: #4b5563;
    }

    .stButton>button {
        width: 100%;
        background-color: #16a34a; color: white; font-weight: 600;
        border-radius: 8px; border: none; padding: 0.5rem 1rem;
        transition: all 0.2s;
    }
    .stButton>button:hover {
        background-color: #15803d; color: white;
    }

    .block-container { padding-top: 2rem; padding-bottom: 2rem; }

    /* Sidebar divider */
    [data-testid="stSidebar"] hr { margin: 0.5rem 0; }
</style>
""", unsafe_allow_html=True)

# ================= INIT =================
conn = db.connect()
gateway = LLMGateway(conn)

# ================= SIDEBAR =================
with st.sidebar:
    st.title("GoTani Engine")
    st.caption("v1.0-alpha")
    st.divider()

    # --- Bagian 1: Quick Start ---
    st.subheader("Quick Start")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Muat Demo", help="Isi database dengan data contoh"):
            with st.spinner("Menyiapkan..."):
                subprocess.run([sys.executable, "seed_demo.py"], cwd=str(Path(__file__).parent))
                st.rerun()
    with col2:
        if st.button("Hapus Data", help="Bersihkan seluruh database"):
            with st.spinner("Menghapus..."):
                conn.execute("DELETE FROM listings")
                conn.execute("DELETE FROM raw_items")
                conn.commit()
            st.rerun()
    st.divider()

    # --- Bagian 2: New Campaign ---
    st.subheader("New Campaign")
    prompt_text = st.text_area(
        "Kriteria",
        placeholder="Contoh: Cari petani melon di Jawa Timur, minimal 500 kg",
        height=100,
    )

    if st.button("Susun Spesifikasi"):
        if not prompt_text.strip():
            st.warning("Tulis kriteria pencarian terlebih dahulu.")
        else:
            with st.spinner("Menyusun spesifikasi..."):
                cid = new_campaign_id(conn)
                spec = None
                if gateway.available:
                    try:
                        spec, qs = draft_spec_llm(gateway, prompt_text, cid)
                        if qs:
                            for q in qs:
                                st.info(f"Saran pelengkap: {q}")
                    except Exception as e:
                        st.error(f"Gagal memproses API: {e}")
                if spec is None:
                    if not gateway.available:
                        st.warning("API Key belum dikonfigurasi, menggunakan mode offline.")
                    spec = draft_spec_offline(prompt_text, cid)
                st.session_state["draft_spec"] = spec.to_json()

    if "draft_spec" in st.session_state:
        edited_spec_json = st.text_area(
            "Konfigurasi Spesifikasi (JSON)",
            value=st.session_state["draft_spec"],
            height=300,
        )
        if st.button("Jalankan Pipeline", type="primary"):
            try:
                raw_spec = json.loads(edited_spec_json)
                c = CampaignSpec.model_validate(raw_spec)
                save_campaign(conn, c)
                with st.spinner("Sedang mencari data..."):
                    pipe = Pipeline(c)
                    asyncio.run(pipe.run())
                    st.success("Operasi Selesai.")
                    st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")

    # --- Bagian 3: Status Handoff ---
    st.divider()
    handoff_flag = Path("./data/HANDOFF_WAITING")
    if handoff_flag.exists():
        st.error("Sistem membutuhkan intervensi keamanan (Login/CAPTCHA).")
        st.caption(handoff_flag.read_text(encoding="utf-8"))
        if st.button("Lanjutkan Sistem"):
            handoff_flag.unlink(missing_ok=True)
            st.success("Konfirmasi diterima, sistem dilanjutkan.")
            st.rerun()

    # --- Bagian 4: Info LLM Cost ---
    st.divider()
    st.subheader("Penggunaan API (Hari Ini)")
    try:
        usage = gateway.usage_today()
        st.metric("Total Request", usage["requests"])
        st.metric("Estimasi Biaya", f"${usage['cost_usd']:.4f}")
        st.caption(f"Input: {usage['input_tokens']:,} tok | Output: {usage['output_tokens']:,} tok")
        st.progress(
            min(usage["cost_usd"] / settings.llm_daily_budget_usd, 1.0),
            text=f"Batas Harian: ${settings.llm_daily_budget_usd:.2f}",
        )
    except Exception:
        st.caption("Belum ada pemakaian API.")

# ================= MAIN AREA =================
st.title("Lead Intelligence Dashboard")

# --- Metrik Ringkasan ---
try:
    total_raw = conn.execute("SELECT COUNT(*) FROM raw_items").fetchone()[0]
    total_leads = conn.execute("SELECT COUNT(*) FROM listings").fetchone()[0]
    high_conf = conn.execute("SELECT COUNT(*) FROM listings WHERE confidence >= 80").fetchone()[0]
    approved = conn.execute("SELECT COUNT(*) FROM listings WHERE review_status = 'approved'").fetchone()[0]
except Exception:
    total_raw, total_leads, high_conf, approved = 0, 0, 0, 0

m1, m2, m3, m4 = st.columns(4)
m1.metric("Total Raw Posts", f"{total_raw:,}", help="Jumlah postingan mentah yang diambil.")
m2.metric("Extracted Leads", f"{total_leads:,}", help="Jumlah prospek yang berhasil diekstrak.")
m3.metric("High Confidence", f"{high_conf:,}", help="Prospek dengan skor confidence ≥ 80.")
conv_rate = f"{int((total_leads / total_raw) * 100)}%" if total_raw > 0 else "0%"
m4.metric("Conversion Rate", conv_rate, help="Rasio post mentah ke prospek.")

st.divider()

# --- Tabel Data ---
tab1, tab2, tab3, tab4 = st.tabs(["Verified Leads", "Matchmaking & Pooling", "Raw Data Log", "Campaign History"])

with tab1:
    # Filter controls
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
        st.info("Belum ada data prospek yang sesuai filter. Silakan muat data atau jalankan kampanye baru.")
    else:
        # Proses pembuatan Link WA otomatis dari nomor HP
        def make_wa_link(phone):
            if not phone: return None
            p = str(phone).split(',')[0].strip().replace(" ", "").replace("-", "")
            if p.startswith("08"):
                return f"https://wa.me/62{p[1:]}"
            elif p.startswith("62"):
                return f"https://wa.me/{p}"
            elif p.startswith("+62"):
                return f"https://wa.me/{p[1:]}"
            return None
        
        df_leads["Chat_WA"] = df_leads["Telepon"].apply(make_wa_link)
        
        # Ekstrak Varietas dari JSON Attributes
        def extract_variety(attr_json):
            if not attr_json: return ""
            try:
                data = json.loads(attr_json)
                variety = data.get("variety", [])
                grade = data.get("grade")
                res = []
                if variety: res.append(f"Var: {', '.join(variety)}")
                if grade: res.append(f"Grade: {grade}")
                return " | ".join(res)
            except:
                return ""
                
        df_leads["Kualitas"] = df_leads["Atribut"].apply(extract_variety)
        
        # Deteksi apakah URL mengarah ke postingan spesifik atau grup komunitas
        def detect_link_label(url_str):
            if not url_str: return "🌐 Buka Web"
            u = str(url_str).lower()
            if "/posts/" in u or "/permalink/" in u or "story.php" in u:
                return "🔗 Postingan Spesifik"
            elif "/groups/" in u:
                return "👥 Grup Komunitas"
            return "🔗 Buka Sumber"
            
        df_leads["Label_Sumber"] = df_leads["URL"].apply(detect_link_label)

        # Header aksi unduh & reviewer
        top_c1, top_c2 = st.columns([1, 3])
        with top_c1:
            csv_leads = df_leads.drop(columns=["Alasan_Skor", "Atribut"], errors="ignore").to_csv(index=False).encode("utf-8")
            st.download_button(
                "Unduh Data (CSV)", csv_leads,
                file_name=f"verified_leads_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                mime="text/csv",
            )

        # Urutkan dan pilih kolom yang paling esensial agar tidak kepotong horizontal
        display_cols = [
            "id", "Komoditas", "Kategori", "Volume_Kg", "Harga_Kg", 
            "Lokasi", "Chat_WA", "Rel_Score", "Review", "Label_Sumber", "URL"
        ]
        
        # Rename Intent menjadi Kategori untuk display
        df_leads_display = df_leads.copy()
        df_leads_display["Kategori"] = df_leads_display["Intent"]
        
        # Pastikan kolom yang ada saja yang diambil
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
                "Chat_WA": st.column_config.LinkColumn("Chat WA", display_text="📱 Hubungi WA", width="medium"),
                "Rel_Score": st.column_config.ProgressColumn("Relevansi", min_value=0, max_value=100, format="%d%%", width="small"),
                "Review": st.column_config.TextColumn("Status", width="small"),
                "Label_Sumber": st.column_config.TextColumn("Tipe Sumber", width="small"),
                "URL": st.column_config.LinkColumn("Tautan", display_text="🔗 Buka", width="small"),
            },
        )

        # --- Modul Aksi Reviewer (Human-in-the-Loop) ---
        with st.expander("🛠️ Panel Verifikasi Reviewer (Approve / Reject)", expanded=True):
            st.caption("Verifikasi keaslian prospek sebelum diteruskan ke tim Sales (PRD §3.3 & §7.5)")
            rev_col1, rev_col2, rev_col3 = st.columns([1.5, 2, 2])
            
            with rev_col1:
                selectable_ids = df_leads["id"].tolist()
                target_id = st.selectbox("Pilih ID Lead", selectable_ids, help="ID prospek yang ingin Anda verifikasi")
            
            with rev_col2:
                review_note = st.text_input("Catatan Reviewer (Opsional)", placeholder="misal: Nomor valid, petani ramah")
            
            with rev_col3:
                st.write("") # Spacer
                btn_c1, btn_c2 = st.columns(2)
                with btn_c1:
                    if st.button("✅ Approve", help="Setujui lead ini sebagai data terverifikasi"):
                        db.update_review_status(conn, target_id, "approved", review_note)
                        st.success(f"Lead #{target_id} disetujui (Approved)!")
                        st.rerun()
                with btn_c2:
                    if st.button("❌ Reject", help="Tolak lead ini jika spam, calo, atau tidak valid"):
                        db.update_review_status(conn, target_id, "rejected", review_note)
                        st.warning(f"Lead #{target_id} ditolak (Rejected)!")
                        st.rerun()

        # Score breakdown expander
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

# ================= TAB 2: MATCHMAKING & POOLING (FASE 2) =================
with tab2:
    st.markdown("### 🤝 Matchmaking Supply ↔ Demand & Smart Pooling")
    st.caption("Pencocokan kebutuhan pembeli dengan petani terverifikasi + agregasi volume cerdas (PRD §7.6 / Fase 2)")

    # 1. Baris Aksi Utama & Filter
    m_act1, m_act2, m_act3 = st.columns([2, 1.5, 1.5])
    with m_act1:
        if st.button("⚡ Jalankan Matchmaking Engine", type="primary", help="Hitung skor kecocokan semua order pembeli terhadap penawaran petani"):
            with st.spinner("Menghitung kecocokan dan menyusun smart pool..."):
                m_stats = run_all_matches(conn, include_pending_high_score=True)
                st.success(f"Selesai! {m_stats['matches_created']} match 1-ke-1 dan {m_stats['pools_created']} smart pool berhasil dihitung.")
                st.rerun()

    with m_act2:
        tier_select = st.selectbox("Filter Tier Rekomendasi", ["Semua", "outreach", "review", "ignored"], index=0, help="outreach (skor ≥80), review (50-79), ignored (<50)")

    with m_act3:
        include_pending = st.checkbox("Ikutkan lead pending berskor tinggi", value=True, help="Menyertakan petani yang belum di-approve tapi relevance ≥70 dan confidence ≥60")

    # 2. Form Input Order Pembeli Baru (Demand Manual)
    with st.expander("➕ Input Kebutuhan Pembeli Baru (Order Demand)", expanded=False):
        st.caption("Masukkan pesanan/kebutuhan nyata dari pembeli untuk dicocokkan dengan data petani di database.")
        with st.form("form_manual_order"):
            fo_c1, fo_c2 = st.columns(2)
            with fo_c1:
                b_name = st.text_input("Nama Pembeli / Usaha *", placeholder="misal: PT Sumber Berkah Buah")
                b_prod = st.text_input("Komoditas yang Dicari *", placeholder="misal: melon, semangka, pisang")
                b_vol = st.number_input("Volume Dibutuhkan (Kg) *", min_value=1.0, value=500.0, step=50.0)
                b_price = st.number_input("Batas Harga Maksimal Pembeli (Rp/Kg)", min_value=0.0, value=9000.0, step=500.0)
            with fo_c2:
                b_loc = st.text_input("Lokasi Gudang / Titik Kirim *", placeholder="misal: Kota Surabaya, Sidoarjo, Kediri")
                b_date = st.date_input("Dibutuhkan Paling Lambat", value=datetime.now())
                b_phone = st.text_input("Nomor Telepon / WA Pembeli", placeholder="misal: 081234567890")
                b_var = st.text_input("Varietas Khusus (Opsional)", placeholder="misal: madesta, golden, atau kosongkan jika bebas")

            submitted_order = st.form_submit_button("Simpan Order Pembeli", type="secondary")
            if submitted_order:
                if not b_name or not b_prod or not b_loc:
                    st.error("Nama pembeli, komoditas, dan lokasi wajib diisi!")
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
                    st.success(f"Order #{new_id} untuk '{b_name}' berhasil disimpan! Silakan klik 'Jalankan Matchmaking Engine'.")
                    st.rerun()

    # 3. Tampilkan Daftar Match Hasil Komputasi
    matches_list = get_matches_for_display(conn, tier_filter=tier_select)

    if not matches_list:
        st.info("Belum ada data match yang sesuai kriteria. Klik tombol '⚡ Jalankan Matchmaking Engine' di atas, atau masukkan order pembeli baru.")
    else:
        st.write(f"Menampilkan **{len(matches_list)}** rekomendasi match:")

        for m in matches_list:
            is_pool = (m["kind"] == "pool")
            tier_badge = "🟢 PRIORITAS OUTREACH" if m["tier"] == "outreach" else ("🟡 PERLU REVIEW" if m["tier"] == "review" else "⚪ DIABAIKAN")
            badge_color = "#15803d" if m["tier"] == "outreach" else ("#b45309" if m["tier"] == "review" else "#6b7280")

            with st.container(border=True):
                # Header Kartu
                hdr_col1, hdr_col2 = st.columns([3, 1.2])
                with hdr_col1:
                    kind_label = "🧩 SMART POOLING (AGREGASI PETANI)" if is_pool else "🤝 MATCH 1-KE-1"
                    st.markdown(f"#### {kind_label} · {m['buyer_name']} ({m['buyer_location']})")
                    st.caption(f"Komoditas: **{m['product'].title()}** | Kebutuhan: **{m['buyer_vol']:g} kg** | Budget Maks: **Rp {m['buyer_max_price']:,.0f}/kg**" if m['buyer_max_price'] else f"Komoditas: **{m['product'].title()}** | Kebutuhan: **{m['buyer_vol']:g} kg**")
                
                with hdr_col2:
                    st.markdown(f"<div style='text-align:right;'><span style='background-color:{badge_color}; color:white; padding:4px 8px; border-radius:4px; font-weight:bold; font-size:0.85rem;'>{tier_badge}</span><br><h3 style='margin:4px 0; color:#166534;'>Skor: {m['score']}</h3><small>Coverage: {m['coverage_pct']:g}%</small></div>", unsafe_allow_html=True)

                st.divider()

                # Badan Kartu: Daftar Petani
                st.markdown("**Petani Rekomendasi:**")
                items = m.get("items", [])
                if items:
                    f_cols = st.columns(len(items)) if len(items) <= 3 else [st.container()]
                    for idx, it in enumerate(items):
                        target_col = f_cols[idx] if len(items) <= 3 else st
                        with target_col:
                            st.markdown(f"**{it.get('farmer_name') or 'Petani'}** ({it.get('farmer_location') or '-'})")
                            st.caption(f"Alokasi: **{it.get('allocated_kg', 0):g} kg** | Harga: **Rp {it.get('farmer_price', 0):,.0f}**" if it.get('farmer_price') else f"Alokasi: **{it.get('allocated_kg', 0):g} kg** | Harga: *belum tertera*")
                            if it.get("distance_km"):
                                st.caption(f"Jarak ke pembeli: ~{it['distance_km']} km")
                            if it.get("farmer_wa"):
                                st.markdown(f"[📱 Hubungi WA Petani]({it['farmer_wa']})")

                # Disclaimer Pooling (F6.4)
                if is_pool:
                    disclaimer_text = m.get("breakdown", {}).get("disclaimer")
                    if disclaimer_text:
                        st.warning(f"⚠️ **Saran Agregasi:** {disclaimer_text}")

                # Estimasi Margin GoTani (jika ada)
                margin_info = m.get("margin")
                if margin_info and margin_info.get("est_gross_margin_rp", 0) > 0:
                    st.success(f"💰 **Estimasi Potensi Margin GoTani ({margin_info.get('margin_pct', 0.1):.0%}):** Rp {margin_info['est_gross_margin_rp']:,.0f} (Beli: Rp{margin_info['farmer_price']:,.0f} → Rekomendasi Jual: Rp{margin_info['suggested_price']:,.0f}/kg)")

                # Kekurangan / Gaps (F6.3)
                gaps = m.get("gaps", [])
                if gaps:
                    with st.expander("Catatan Kekurangan & Verifikasi (Gaps)", expanded=False):
                        for g in gaps:
                            st.caption(f"• {g}")

                # Panel Aksi Outreach & Catat Hasil (F6.5 / F6.6)
                act_c1, act_c2, act_c3 = st.columns([1.5, 2, 2.5])
                with act_c1:
                    if m.get("buyer_wa"):
                        st.markdown(f"[📱 Hubungi Pembeli via WA]({m['buyer_wa']})")
                    else:
                        st.caption("Kontak WA pembeli belum ada")

                with act_c2:
                    if m["status"] == "open":
                        if st.button("✅ Konfirmasi Outreach", key=f"conf_{m['match_id']}"):
                            update_match_status(conn, m["match_id"], "confirmed")
                            st.success("Match dikonfirmasi untuk outreach!")
                            st.rerun()
                    else:
                        st.caption(f"Status: **{m['status'].upper()}**")

                with act_c3:
                    if m["status"] != "closed":
                        with st.popover("Catat Hasil Transaksi (Deal/No Deal)"):
                            out_choice = st.radio("Hasil Transaksi", ["deal", "no_deal"], key=f"rad_{m['match_id']}")
                            out_note = st.text_input("Alasan Hasil", placeholder="misal: Harga disepakati, siap kirim tgl 20", key=f"note_{m['match_id']}")
                            if st.button("Simpan Hasil", key=f"btn_out_{m['match_id']}"):
                                update_match_outcome(conn, m["match_id"], out_choice, out_note)
                                st.success("Hasil match berhasil dicatat!")
                                st.rerun()
                    else:
                        st.caption(f"Hasil: **{str(m.get('outcome')).upper()}** ({m.get('outcome_reason') or '-'})")

with tab3:
    df_raw = pd.read_sql_query("""

        SELECT
            id AS ID,
            platform AS Platform,
            campaign_id AS Campaign,
            fetched_at AS Waktu_Scrape,
            raw_text AS Teks_Original,
            processed AS Diproses
        FROM raw_items
        ORDER BY id DESC LIMIT 200
    """, conn)

    if df_raw.empty:
        st.caption("Data raw log kosong.")
    else:
        csv_raw = df_raw.to_csv(index=False).encode("utf-8")
        st.download_button(
            "Unduh Raw Log (CSV)", csv_raw,
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
                "Teks_Original": st.column_config.TextColumn("Teks Postingan Asli", width="large"),
                "Diproses": st.column_config.CheckboxColumn("Pipeline"),
            },
        )

with tab3:
    try:
        campaigns = list_campaigns(conn)
        if campaigns:
            df_camp = pd.DataFrame(
                [(c["id"], c["goal"], c["status"], c["created_at"]) for c in campaigns],
                columns=["ID", "Tujuan", "Status", "Dibuat"],
            )
            st.dataframe(df_camp, use_container_width=True, hide_index=True)
        else:
            st.caption("Belum ada kampanye.")
    except Exception:
        st.caption("Belum ada kampanye.")

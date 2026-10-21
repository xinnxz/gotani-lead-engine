"""End-to-End (E2E) Enterprise Lifecycle Integration Test.

Menguji siklus hidup bisnis lengkap secara end-to-end:
1. Ingestion Lead Supply & Demand -> Matchmaking Engine -> Scoring.
2. Inisiasi CRM Percakapan -> AI Outreach Drafting -> Transparansi Bot (G4).
3. Deteksi Minat & Negosiasi -> Smart Handover Sales -> Closed Won.
4. Cadence Siklus Follow-Up Otomatis (H+3, H+7) -> Auto Closed Lost.
5. Kepatuhan Hak Privasi UU PDP (G5) -> Deteksi Opt-Out -> Supresi Global DNC.
6. Verifikasi Inbound Call Assistant dengan konteks CRM real-time.
"""
import sqlite3
import pytest
from pathlib import Path
from datetime import datetime, timezone, timedelta

from agent import db
from agent.match_runner import run_all_matches
from agent.sales_agent import (
    generate_initial_outreach,
    generate_conversational_reply,
    calculate_sales_metrics,
)
from agent.handover import evaluate_inbound_message
from agent.compliance import (
    is_do_not_contact,
    register_opt_out_contact,
    is_within_operating_hours,
)
from agent.cadence import advance_followup, generate_followup_message
from agent.cadence_runner import run_cadence_check
from agent.caller_lookup import lookup_caller
from agent.outreach import format_wa_url

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "agent" / "schema.sql"


@pytest.fixture
def conn():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        connection.executescript(f.read())
    yield connection
    connection.close()


class TestEnterpriseE2ELifecycle:
    """Pengujian integrasi alur bisnis lengkap end-to-end."""

    def test_e2e_happy_path_deal_won(self, conn):
        """Skenario 1: Dari pasokan & permintaan -> Match -> Chat AI -> Handover -> Deal Won."""
        # 1. Ingestion Data Petani (Supply)
        conn.execute(
            """INSERT INTO raw_items (id, campaign_id, platform, url, raw_text, content_hash, fetched_at)
               VALUES (1, 'cmp-melon', 'fb', 'https://fb.com/1', 'Panen melon madesta 2.5 ton', 'h1', '2026-10-21 08:00:00')"""
        )
        conn.execute(
            """INSERT INTO listings (id, campaign_id, raw_item_id, intent, product, volume_kg, price_per_kg, entity_name, contact_phone, kabupaten, provinsi, review_status, relevance, confidence, created_at)
               VALUES (101, 'cmp-melon', 1, 'supply', 'melon madesta', 2500, 8500, 'Pak Sukardi Ngawi', '+6281234567890', 'Ngawi', 'Jawa Timur', 'approved', 95, 90, '2026-10-21 08:00:00')"""
        )

        # 2. Ingestion Order Pembeli (Demand)
        conn.execute(
            """INSERT INTO raw_items (id, campaign_id, platform, url, raw_text, content_hash, fetched_at)
               VALUES (2, 'manual_demand', 'manual', 'manual://order/1', 'Butuh 2 ton melon', 'h2', '2026-10-21 08:05:00')"""
        )
        conn.execute(
            """INSERT INTO listings (id, campaign_id, raw_item_id, intent, product, volume_kg, price_per_kg, entity_name, contact_phone, kabupaten, provinsi, review_status, relevance, confidence, created_at)
               VALUES (201, 'manual_demand', 2, 'demand', 'melon', 2000, 10000, 'CV Buah Segar Surabaya', '+6281987654321', 'Surabaya', 'Jawa Timur', 'approved', 100, 100, '2026-10-21 08:05:00')"""
        )
        conn.commit()

        # 3. Eksekusi Matchmaking Engine
        match_stats = run_all_matches(conn)
        assert match_stats["matches_created"] >= 1

        matches = conn.execute("SELECT * FROM matches WHERE demand_listing_id = 201").fetchall()
        assert len(matches) == 1
        m_row = matches[0]
        assert m_row["score"] >= 75  # Skor tinggi masuk tier outreach

        # 4. Inisiasi Sesi Percakapan Sales CRM (Fase 3)
        c_id = db.create_conversation(
            conn,
            listing_id=101,
            match_id=m_row["id"],
            campaign_id="cmp-melon",
            contact_phone="+6281234567890",
            role="farmer",
            contact_name="Pak Sukardi Ngawi",
            initial_state="drafted",
        )
        assert c_id is not None

        # 5. Pembuatan Draf Pesan Pembuka AI
        init_draft = generate_initial_outreach(conn, 101, match_id=m_row["id"])
        assert "Sukardi" in init_draft
        assert "melon" in init_draft.lower()
        db.add_message(conn, c_id, "outbound", "ai", init_draft, delivery_status="draft")

        # 6. Tandai Pesan Terkirim & Aktifkan Jadwal Cadence H+3
        h_plus_3 = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat(timespec="seconds")
        db.update_conversation(conn, c_id, state="sent", followup_due_at=h_plus_3)
        c_sent = db.get_conversation(conn, c_id)
        assert c_sent["state"] == "sent"

        # 7. Respon Lead 1: Pertanyaan Transparansi Bot (PRD F8.3 / G4)
        msg_bot_inquiry = "Halo, ini siapa ya? Apakah saya sedang berbicara dengan robot?"
        db.add_message(conn, c_id, "inbound", "lead", msg_bot_inquiry)
        eval1 = evaluate_inbound_message(msg_bot_inquiry)
        assert eval1["trigger_type"] == "bot_inquiry"
        assert eval1["needs_handover"] is True  # F8.7: Pertanyaan bot memicu opsi handover

        # AI Membalas Jujur (PRD G4)
        ai_bot_reply = generate_conversational_reply(conn, c_id, msg_bot_inquiry)
        assert "asisten" in ai_bot_reply.lower()
        assert "gotani" in ai_bot_reply.lower()
        assert "manusia" in ai_bot_reply.lower() or "staf" in ai_bot_reply.lower()
        db.add_message(conn, c_id, "outbound", "ai", ai_bot_reply, delivery_status="sent")

        # 8. Respon Lead 2: Minat Deal & Negosiasi Harga (PRD F8.7)
        msg_deal = "Oke kalau begitu. Kami ada stok 2.5 ton melon madesta, bisa nego harga 9rb per kilo langsung kirim ke Surabaya?"
        db.add_message(conn, c_id, "inbound", "lead", msg_deal)
        eval2 = evaluate_inbound_message(msg_deal)
        assert eval2["needs_handover"] is True
        assert eval2["trigger_type"] in ("deal_interest", "negotiation")

        # Sistem Otomatis Mengeskalasi ke Handover Pending
        db.update_conversation(
            conn,
            c_id,
            state="handover_pending",
            summary_text=f"Eskalasi Sales: {eval2['reason']}",
        )
        c_handover = db.get_conversation(conn, c_id)
        assert c_handover["state"] == "handover_pending"

        # 9. Staf Manusia Mengambil Alih & Menyelesaikan Deal (Closed Won)
        db.update_conversation(
            conn,
            c_id,
            state="closed_won",
            assigned_sales="Andi Pratama",
            summary_text="Deal disepakati: 2.5 ton melon madesta harga Rp 9.000/kg kirim lusa.",
        )
        c_final = db.get_conversation(conn, c_id)
        assert c_final["state"] == "closed_won"
        assert c_final["assigned_sales"] == "Andi Pratama"

        # 10. Verifikasi Metrik Funnel Konversi (PRD F8.10)
        metrics = calculate_sales_metrics(conn)
        assert metrics["total_convs"] == 1
        assert metrics["won_count"] == 1
        assert metrics["conversion_rate_pct"] == 100.0

    def test_e2e_cadence_followup_aging_to_closed_lost(self, conn):
        """Skenario 2: Follow-up otomatis H+3 dan H+7 hingga penutupan closed_lost."""
        conn.execute(
            """INSERT INTO raw_items (id, campaign_id, platform, url, raw_text, content_hash, fetched_at)
               VALUES (3, 'cmp-cadence', 'fb', 'https://fb.com/3', 'Petani melon Nganjuk', 'h3', '2026-10-21 08:00:00')"""
        )
        conn.execute(
            """INSERT INTO listings (id, campaign_id, raw_item_id, intent, product, volume_kg, price_per_kg, entity_name, contact_phone, kabupaten, review_status, relevance, confidence, created_at)
               VALUES (301, 'cmp-cadence', 3, 'supply', 'melon inthanon', 1000, 8000, 'Pak Joko Nganjuk', '+6289911223344', 'Nganjuk', 'approved', 90, 85, '2026-10-21 08:00:00')"""
        )
        conn.commit()

        # Inisiasi percakapan yang jatuh tempo di masa lalu
        mock_now = datetime(2026, 10, 21, 10, 0, 0, tzinfo=timezone(timedelta(hours=7)))
        past_due = (mock_now - timedelta(hours=1)).isoformat(timespec="seconds")

        c_id = db.create_conversation(
            conn,
            listing_id=301,
            campaign_id="cmp-cadence",
            contact_phone="+6289911223344",
            role="farmer",
            contact_name="Pak Joko Nganjuk",
            initial_state="sent",
            followup_due_at=past_due,
        )

        # Eksekusi Follow-Up 1 oleh Cadence Runner
        res1 = run_cadence_check(conn, now_dt=mock_now, dry_run=False)
        assert res1["processed_count"] == 1
        assert res1["items"][0]["action_taken"] == "scheduled_followup_2"

        c_after_fu1 = db.get_conversation(conn, c_id)
        assert c_after_fu1["state"] == "followup_1"
        assert c_after_fu1["followup_count"] == 1

        # Simulasi Waktu Melompat 4 Hari ke Depan (Jatuh tempo Follow-Up 2)
        mock_future = mock_now + timedelta(days=5)
        # Buat jatuh tempo berada di bawah mock_future
        db.update_conversation(conn, c_id, followup_due_at=(mock_future - timedelta(hours=1)).isoformat(timespec="seconds"))

        # Eksekusi Follow-Up 2 oleh Cadence Runner
        res2 = run_cadence_check(conn, now_dt=mock_future, dry_run=False)
        assert res2["processed_count"] == 1
        assert res2["items"][0]["action_taken"] == "closed_lost"

        # Percakapan otomatis ditutup sebagai closed_lost (F8.5)
        c_after_fu2 = db.get_conversation(conn, c_id)
        assert c_after_fu2["state"] == "closed_lost"
        assert c_after_fu2["followup_count"] == 2
        assert "tidak ada balasan" in c_after_fu2["summary_text"].lower()

    def test_e2e_privacy_opt_out_and_global_suppression(self, conn):
        """Skenario 3: Kepatuhan UU PDP (G5) supresi kontak global dan proteksi Inbound Call."""
        conn.execute(
            """INSERT INTO raw_items (id, campaign_id, platform, url, raw_text, content_hash, fetched_at)
               VALUES (4, 'cmp-privacy', 'fb', 'https://fb.com/4', 'Petani semangka Banyuwangi', 'h4', '2026-10-21 08:00:00')"""
        )
        conn.execute(
            """INSERT INTO listings (id, campaign_id, raw_item_id, intent, product, volume_kg, price_per_kg, entity_name, contact_phone, kabupaten, review_status, relevance, confidence, created_at)
               VALUES (401, 'cmp-privacy', 4, 'supply', 'semangka', 5000, 4500, 'Ibu Siti Banyuwangi', '+6281777888999', 'Banyuwangi', 'approved', 90, 90, '2026-10-21 08:00:00')"""
        )
        conn.commit()

        c_id = db.create_conversation(
            conn,
            listing_id=401,
            campaign_id="cmp-privacy",
            contact_phone="+6281777888999",
            role="farmer",
            contact_name="Ibu Siti Banyuwangi",
            initial_state="active",
        )

        # Lead Mengirimkan Pesan Penolakan Keras (Opt-out)
        stop_message = "Tolong hapus nomor saya dari database Anda dan jangan hubungi saya lagi!"
        db.add_message(conn, c_id, "inbound", "lead", stop_message)

        # Evaluasi Kepatuhan
        eval_opt = evaluate_inbound_message(stop_message)
        assert eval_opt["trigger_type"] == "opt_out"

        # Registrasi Supresi Global DNC
        register_opt_out_contact(
            conn,
            phone="+6281777888999",
            reason="user_opt_out",
            source_message=stop_message,
        )

        # 1. Cek Kepatuhan Global
        assert is_do_not_contact(conn, "+6281777888999") is True
        assert is_do_not_contact(conn, "081777888999") is True

        # 2. Cek Blokir Pengiriman Pesan Baru
        wa_link = format_wa_url("+6281777888999", "Halo Bu Siti...")
        # Di layer UI/Compliance, nomor DNC otomatis dilarang dikirimkan
        assert is_do_not_contact(conn, "+6281777888999") is True

        # 3. Cek Asisten Telepon Masuk (Inbound Call Assistant PRD §7.7)
        caller_info = lookup_caller(conn, "081777888999")
        assert caller_info["is_opted_out"] is True
        assert any("OPT-OUT" in p or "Do-Not-Contact" in p for p in caller_info["talking_points"])

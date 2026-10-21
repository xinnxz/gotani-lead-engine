"""Unit test untuk modul database percakapan & kepatuhan Fase 3 (PRD §7.8 & §8)."""
import pytest
import sqlite3
from agent import db


@pytest.fixture
def test_conn():
    """Koneksi database in-memory dengan skema lengkap."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(db.SCHEMA_PATH.read_text(encoding="utf-8"))
    
    # Masukkan data dummy campaign & listing
    conn.execute(
        "INSERT INTO campaigns (id, goal, spec_json, status, created_at, updated_at) VALUES ('cmp-test', 'find_supply', '{}', 'active', '2026-10-21T00:00:00', '2026-10-21T00:00:00')"
    )
    conn.execute(
        "INSERT INTO raw_items (campaign_id, platform, raw_text, content_hash, fetched_at) VALUES ('cmp-test', 'facebook', 'dummy', 'hash1', '2026-10-21T00:00:00')"
    )
    conn.execute(
        """INSERT INTO listings (
            campaign_id, raw_item_id, intent, entity_name, product, volume_kg, price_per_kg,
            location_text, kabupaten, provinsi, contact_phone, contact_wa, relevance, confidence, created_at
        ) VALUES (
            'cmp-test', 1, 'supply', 'Pak Tani Joko', 'melon', 500, 7500,
            'Jombang', 'Jombang', 'Jawa Timur', '081234567890', '6281234567890', 90, 85, '2026-10-21T00:00:00'
        )"""
    )
    conn.commit()
    return conn


def test_create_and_get_conversation(test_conn):
    conv_id = db.create_conversation(
        test_conn,
        listing_id=1,
        campaign_id="cmp-test",
        contact_phone="081234567890",
        role="farmer",
        contact_name="Pak Tani Joko",
        initial_state="drafted",
    )
    assert conv_id > 0

    conv = db.get_conversation(test_conn, conv_id)
    assert conv is not None
    assert conv["contact_name"] == "Pak Tani Joko"
    assert conv["state"] == "drafted"
    assert conv["role"] == "farmer"
    assert conv["followup_count"] == 0


def test_add_and_get_messages(test_conn):
    conv_id = db.create_conversation(
        test_conn,
        listing_id=1,
        campaign_id="cmp-test",
        contact_phone="081234567890",
        role="farmer",
    )
    
    # 1. Pesan keluar (outbound AI)
    msg1_id = db.add_message(
        test_conn,
        conversation_id=conv_id,
        direction="outbound",
        sender_type="ai",
        content="Halo Pak Joko, kami melihat penawaran melon Anda...",
        delivery_status="sent",
    )
    assert msg1_id > 0

    # 2. Pesan masuk (inbound lead)
    msg2_id = db.add_message(
        test_conn,
        conversation_id=conv_id,
        direction="inbound",
        sender_type="lead",
        content="Iya mas masih ready 500kg, harga berapa ya?",
        delivery_status="delivered",
    )
    assert msg2_id > 0

    # Ambil riwayat percakapan
    messages = db.get_messages(test_conn, conv_id)
    assert len(messages) == 2
    assert messages[0]["direction"] == "outbound"
    assert messages[1]["direction"] == "inbound"
    assert messages[1]["content"] == "Iya mas masih ready 500kg, harga berapa ya?"


def test_update_conversation_lifecycle(test_conn):
    conv_id = db.create_conversation(
        test_conn,
        listing_id=1,
        campaign_id="cmp-test",
        contact_phone="081234567890",
        role="farmer",
    )
    
    # Update status ke active dan tambahkan ringkasan
    ok = db.update_conversation(
        test_conn,
        conv_id,
        state="active",
        summary_text="Petani mengonfirmasi stok 500kg ready panen.",
        assigned_sales="Staf Budi",
        increment_followup=True,
    )
    assert ok is True

    conv = db.get_conversation(test_conn, conv_id)
    assert conv["state"] == "active"
    assert conv["summary_text"] == "Petani mengonfirmasi stok 500kg ready panen."
    assert conv["assigned_sales"] == "Staf Budi"
    assert conv["followup_count"] == 1


def test_register_and_check_opt_out(test_conn):
    phone = "081234567890"
    conv_id = db.create_conversation(
        test_conn,
        listing_id=1,
        campaign_id="cmp-test",
        contact_phone=phone,
        role="farmer",
        initial_state="active",
    )
    
    assert db.is_opted_out(test_conn, phone) is False

    # Registrasi opt-out
    db.register_opt_out(
        test_conn,
        contact_phone=phone,
        reason="user_request_stop",
        source_message="Tolong jangan hubungi nomor saya lagi.",
    )

    # Verifikasi status supresi
    assert db.is_opted_out(test_conn, phone) is True
    # Format internasional juga harus terdeteksi
    assert db.is_opted_out(test_conn, "6281234567890") is True

    # Percakapan harus otomatis berstatus opt_out
    conv = db.get_conversation(test_conn, conv_id)
    assert conv["state"] == "opt_out"

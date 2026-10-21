import sqlite3
import pytest
from pathlib import Path
from agent import db
from agent.caller_lookup import lookup_caller
from agent.compliance import register_opt_out_contact

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "agent" / "schema.sql"

@pytest.fixture
def conn():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        connection.executescript(f.read())
    yield connection
    connection.close()


def test_caller_lookup_not_found(conn):
    res = lookup_caller(conn, "081999888777")
    assert res is not None
    assert res["found"] is False
    assert len(res["talking_points"]) >= 5


def test_caller_lookup_with_crm_conversation(conn):
    # Buat raw item & listing
    conn.execute(
        """INSERT INTO raw_items (id, campaign_id, platform, url, raw_text, content_hash, fetched_at)
           VALUES (1, 'cmp-melon', 'fb', 'https://fb.com/1', 'Jual melon', 'hash1', '2026-10-21 10:00:00')"""
    )
    conn.execute(
        """INSERT INTO listings (id, campaign_id, raw_item_id, intent, product, volume_kg, price_per_kg, entity_name, contact_phone, kabupaten, review_status, relevance, confidence, created_at)
           VALUES (10, 'cmp-melon', 1, 'supply', 'melon madesta', 2500, 11000, 'Pak Sukardi', '+6281234567890', 'Ngawi', 'approved', 95, 90, '2026-10-21 10:00:00')"""
    )
    conn.commit()

    # Buat percakapan di CRM
    conv_id = db.create_conversation(
        conn,
        listing_id=10,
        campaign_id="cmp-melon",
        contact_phone="+6281234567890",
        role="farmer",
        contact_name="Pak Sukardi",
        initial_state="handover_pending",
        summary_text="Petani menanyakan opsi negosiasi harga dan pembayaran tempo.",
    )
    # Tambah riwayat pesan
    db.add_message(conn, conv_id, "outbound", "ai", "Halo Pak Sukardi, ada pembeli melon dari Surabaya.")
    db.add_message(conn, conv_id, "inbound", "lead", "Bisa nego 10rb/kg dan DP 50%?")

    # Jalankan caller lookup dengan format nomor lokal (081234567890)
    res = lookup_caller(conn, "081234567890")
    assert res is not None
    assert res["found"] is True
    assert res["name"] == "Pak Sukardi"
    assert res["role"] == "Petani / Penjual (Supply)"
    assert res.get("conversation") is not None
    assert res["conversation"]["state"] == "handover_pending"
    assert "Sukardi" in res["talking_points"][0]
    
    # Harus ada poin bicara yang menyorot status percakapan dan handover negosiasi
    crm_points = [p for p in res["talking_points"] if "Handover" in p or "negosiasi" in p.lower() or "percakapan" in p.lower()]
    assert len(crm_points) > 0


def test_caller_lookup_with_opt_out(conn):
    conn.execute(
        """INSERT INTO raw_items (id, campaign_id, platform, url, raw_text, content_hash, fetched_at)
           VALUES (2, 'cmp-semangka', 'fb', 'https://fb.com/2', 'Jual semangka', 'hash2', '2026-10-21 10:00:00')"""
    )
    conn.execute(
        """INSERT INTO listings (id, campaign_id, raw_item_id, intent, product, volume_kg, price_per_kg, entity_name, contact_phone, kabupaten, review_status, relevance, confidence, created_at)
           VALUES (20, 'cmp-semangka', 2, 'supply', 'semangka inul', 5000, 4500, 'Ibu Siti', '+6281987654321', 'Banyuwangi', 'approved', 90, 85, '2026-10-21 10:00:00')"""
    )
    conn.commit()

    # Daftarkan opt-out
    register_opt_out_contact(conn, "+6281987654321", reason="user_stop", source_message="Jangan hubungi saya")

    res = lookup_caller(conn, "081987654321")
    assert res is not None
    assert res["found"] is True
    assert res.get("is_opted_out") is True
    assert any("OPT-OUT" in p or "Do-Not-Contact" in p for p in res["talking_points"])

"""Unit test untuk modul sales agent dan cadence follow-up (PRD §7.8)."""
import pytest
import sqlite3
from datetime import datetime, timedelta, timezone
from agent import db
from agent.sales_agent import generate_initial_outreach, generate_conversational_reply, summarize_conversation
from agent.cadence import get_due_followups, generate_followup_message, advance_followup


@pytest.fixture
def test_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(db.SCHEMA_PATH.read_text(encoding="utf-8"))
    
    conn.execute(
        "INSERT INTO campaigns (id, goal, spec_json, status, created_at, updated_at) VALUES ('cmp-1', 'find_supply', '{}', 'active', '2026-10-21T00:00:00', '2026-10-21T00:00:00')"
    )
    conn.execute(
        "INSERT INTO raw_items (campaign_id, platform, raw_text, content_hash, fetched_at) VALUES ('cmp-1', 'facebook', 'dummy', 'hash1', '2026-10-21T00:00:00')"
    )
    conn.execute(
        """INSERT INTO listings (
            id, campaign_id, raw_item_id, intent, entity_name, product, volume_kg, price_per_kg,
            location_text, kabupaten, provinsi, contact_phone, contact_wa, relevance, confidence, created_at
        ) VALUES (
            1, 'cmp-1', 1, 'supply', 'Pak Sukardi', 'melon', 1000, 8000,
            'Nganjuk', 'Nganjuk', 'Jawa Timur', '081298765432', '6281298765432', 95, 90, '2026-10-21T00:00:00'
        )"""
    )
    conn.commit()
    return conn


def test_initial_outreach_generation(test_conn):
    msg = generate_initial_outreach(test_conn, listing_id=1)
    assert "Sukardi" in msg
    assert "Melon" in msg or "melon" in msg
    assert "GoTani" in msg


def test_conversational_reply_bot_inquiry(test_conn):
    conv_id = db.create_conversation(
        test_conn,
        listing_id=1,
        campaign_id="cmp-1",
        contact_phone="081298765432",
        role="farmer",
        contact_name="Pak Sukardi",
    )
    
    reply = generate_conversational_reply(test_conn, conv_id, inbound_text="Kamu ini robot ya?")
    assert "asisten digital" in reply or "sistem otomatis" in reply
    assert "manusia" in reply


def test_cadence_followup_cycle(test_conn):
    conv_id = db.create_conversation(
        test_conn,
        listing_id=1,
        campaign_id="cmp-1",
        contact_phone="081298765432",
        role="farmer",
        contact_name="Pak Sukardi",
        initial_state="sent",
    )
    
    # Pesan Follow-Up 1
    fu1_msg = generate_followup_message(test_conn, conv_id)
    assert "menindaklanjuti" in fu1_msg
    assert "Pak/Bu Pak Sukardi" in fu1_msg or "Sukardi" in fu1_msg
    
    # Majukan follow-up ke tahap 1
    status1 = advance_followup(test_conn, conv_id)
    assert status1 == "scheduled_followup_2"
    
    conv1 = db.get_conversation(test_conn, conv_id)
    assert conv1["state"] == "followup_1"
    assert conv1["followup_count"] == 1
    
    # Pesan Follow-Up 2
    fu2_msg = generate_followup_message(test_conn, conv_id)
    assert "terakhir kali" in fu2_msg
    
    # Majukan follow-up ke tahap 2 (tutup closed_lost)
    status2 = advance_followup(test_conn, conv_id)
    assert status2 == "closed_lost"
    
    conv2 = db.get_conversation(test_conn, conv_id)
    assert conv2["state"] == "closed_lost"
    assert conv2["followup_count"] == 2

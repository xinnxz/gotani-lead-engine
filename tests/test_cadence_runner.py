import sqlite3
import pytest
from pathlib import Path
from datetime import datetime, timezone, timedelta
from agent import db
from agent.cadence_runner import run_cadence_check

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "agent" / "schema.sql"

@pytest.fixture
def conn():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        connection.executescript(f.read())
    yield connection
    connection.close()


def test_cadence_runner_dry_run(conn):
    # Setup listing & percakapan yang jatuh tempo
    conn.execute(
        """INSERT INTO raw_items (id, campaign_id, platform, url, raw_text, content_hash, fetched_at)
           VALUES (1, 'cmp-melon', 'fb', 'https://fb.com/1', 'Jual melon', 'hash1', '2026-10-21 10:00:00')"""
    )
    conn.execute(
        """INSERT INTO listings (id, campaign_id, raw_item_id, intent, product, volume_kg, price_per_kg, entity_name, contact_phone, kabupaten, review_status, relevance, confidence, created_at)
           VALUES (10, 'cmp-melon', 1, 'supply', 'melon madesta', 2500, 11000, 'Pak Sukardi', '+6281234567890', 'Ngawi', 'approved', 95, 90, '2026-10-21 10:00:00')"""
    )
    conn.commit()

    mock_now = datetime(2026, 10, 21, 10, 0, 0, tzinfo=timezone(timedelta(hours=7)))
    past_due = (mock_now - timedelta(hours=2)).isoformat(timespec="seconds")

    c_id = db.create_conversation(
        conn,
        listing_id=10,
        campaign_id="cmp-melon",
        contact_phone="+6281234567890",
        role="farmer",
        contact_name="Pak Sukardi",
        initial_state="sent",
        followup_due_at=past_due,
    )

    # Jalankan dry-run pada jam kerja operasional (10.00 WIB)
    res = run_cadence_check(conn, now_dt=mock_now, dry_run=True)

    assert res["processed_count"] == 1
    assert res["dry_run"] is True
    assert len(res["items"]) == 1
    assert res["items"][0]["conversation_id"] == c_id
    assert "Sukardi" in res["items"][0]["contact_name"]

    # Status di DB tidak boleh berubah saat dry-run
    conv = db.get_conversation(conn, c_id)
    assert conv["state"] == "sent"
    assert conv["followup_count"] == 0


def test_cadence_runner_active_execution(conn):
    conn.execute(
        """INSERT INTO raw_items (id, campaign_id, platform, url, raw_text, content_hash, fetched_at)
           VALUES (1, 'cmp-melon', 'fb', 'https://fb.com/1', 'Jual melon', 'hash1', '2026-10-21 10:00:00')"""
    )
    conn.execute(
        """INSERT INTO listings (id, campaign_id, raw_item_id, intent, product, volume_kg, price_per_kg, entity_name, contact_phone, kabupaten, review_status, relevance, confidence, created_at)
           VALUES (10, 'cmp-melon', 1, 'supply', 'melon madesta', 2500, 11000, 'Pak Sukardi', '+6281234567890', 'Ngawi', 'approved', 95, 90, '2026-10-21 10:00:00')"""
    )
    conn.commit()

    mock_now = datetime(2026, 10, 21, 10, 0, 0, tzinfo=timezone(timedelta(hours=7)))
    past_due = (mock_now - timedelta(hours=2)).isoformat(timespec="seconds")

    c_id = db.create_conversation(
        conn,
        listing_id=10,
        campaign_id="cmp-melon",
        contact_phone="+6281234567890",
        role="farmer",
        contact_name="Pak Sukardi",
        initial_state="sent",
        followup_due_at=past_due,
    )

    res = run_cadence_check(conn, now_dt=mock_now, dry_run=False)

    assert res["processed_count"] == 1
    assert res["dry_run"] is False

    # Status di DB harus maju ke followup_1 dan bertambah count
    conv = db.get_conversation(conn, c_id)
    assert conv["state"] == "followup_1"
    assert conv["followup_count"] == 1

    # Pesan harus tersimpan di ledger
    msgs = db.get_messages(conn, c_id)
    assert len(msgs) == 1
    assert msgs[0]["direction"] == "outbound"
    assert msgs[0]["sender_type"] == "ai"

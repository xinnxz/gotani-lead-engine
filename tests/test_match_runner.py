"""Unit test untuk orkestrator matchmaking (M2.3)."""
import sqlite3
from pathlib import Path
import pytest

from agent.db import connect
from agent.match_runner import run_all_matches, get_matches_for_display, update_match_outcome


@pytest.fixture
def test_db():
    # In-memory SQLite dengan schema lengkap
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    schema_path = Path(__file__).resolve().parent.parent / "agent" / "schema.sql"
    conn.executescript(schema_path.read_text(encoding="utf-8"))
    return conn


def test_matching_is_idempotent(test_db):
    """Menjalankan matching berulang kali tidak boleh membuat data ganda."""
    conn = test_db

    # 1. Masukkan demand
    conn.execute(
        """INSERT INTO listings (
            campaign_id, raw_item_id, intent, entity_name, product, volume_kg, 
            price_per_kg, kabupaten, available_date, review_status, extractor, created_at
        ) VALUES ('cmp-d1', 1, 'demand', 'PT Pembeli Buah', 'melon', 500, 9000, 'Surabaya', '2026-10-25', 'approved', 'manual', '2026-10-11T10:00:00')"""
    )

    # 2. Masukkan supply
    conn.execute(
        """INSERT INTO listings (
            campaign_id, raw_item_id, intent, entity_name, product, volume_kg, 
            price_per_kg, kabupaten, available_date, review_status, extractor, created_at
        ) VALUES ('cmp-s1', 2, 'supply', 'Petani Pak Budi', 'melon', 600, 7500, 'Jombang', '2026-10-23', 'approved', 'llm', '2026-10-11T10:00:00')"""
    )
    conn.commit()

    # Jalankan run pertama
    stats1 = run_all_matches(conn)
    assert stats1["matches_created"] >= 1
    count1 = conn.execute("SELECT COUNT(*) FROM matches").fetchone()[0]

    # Jalankan run kedua (harus idempoten, count tidak bertambah)
    stats2 = run_all_matches(conn)
    count2 = conn.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
    assert count1 == count2

    # Uji display
    matches = get_matches_for_display(conn)
    assert len(matches) == count1
    assert matches[0]["buyer_name"] == "PT Pembeli Buah"
    assert len(matches[0]["items"]) >= 1

    # Uji catat hasil (outcome)
    match_id = matches[0]["match_id"]
    ok = update_match_outcome(conn, match_id, "deal", "Harga disepakati Rp8.500/kg")
    assert ok is True
    row = conn.execute("SELECT outcome, outcome_reason, status FROM matches WHERE id = ?", (match_id,)).fetchone()
    assert row["outcome"] == "deal"
    assert row["status"] == "closed"

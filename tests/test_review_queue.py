"""Tests for review status updates and numpy.int64 compatibility."""
import sqlite3
import numpy as np
import pytest
from agent import db


@pytest.fixture
def test_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(db.SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.execute(
        "INSERT INTO campaigns (id, goal, spec_json, status, created_at, updated_at) "
        "VALUES ('c-test', 'find_supply', '{}', 'active', '2026-10-22', '2026-10-22')"
    )
    conn.execute(
        "INSERT INTO raw_items (id, campaign_id, platform, raw_text, content_hash, fetched_at) "
        "VALUES (1, 'c-test', 'facebook', 'dummy', 'hash1', '2026-10-22')"
    )
    conn.execute(
        """INSERT INTO listings (
            id, campaign_id, raw_item_id, intent, entity_name, product,
            relevance, confidence, review_status, created_at
        ) VALUES (
            281, 'c-test', 1, 'supply', 'Petani Durian', 'durian',
            95, 55, 'pending', '2026-10-22'
        )"""
    )
    conn.commit()
    return conn


def test_update_review_status_with_numpy_int64(test_conn):
    """Pastikan numpy.int64 dari pandas dataframe berhasil mengubah status di SQLite."""
    np_id = np.int64(281)
    ok = db.update_review_status(test_conn, np_id, "rejected", "Tolak data tidak valid")
    assert ok is True

    row = test_conn.execute("SELECT review_status, review_note FROM listings WHERE id = 281").fetchone()
    assert row["review_status"] == "rejected"
    assert row["review_note"] == "Tolak data tidak valid"


def test_update_review_status_with_standard_int(test_conn):
    """Pastikan standard int juga berhasil approve."""
    ok = db.update_review_status(test_conn, 281, "approved", "Valid")
    assert ok is True

    row = test_conn.execute("SELECT review_status FROM listings WHERE id = 281").fetchone()
    assert row["review_status"] == "approved"

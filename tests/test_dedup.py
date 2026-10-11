"""Unit tests untuk deduplikasi dan pencegahan data ganda (PRD F3.5)."""
import sqlite3
from pathlib import Path
import pytest

from agent.db import save_raw_item, connect
from agent.dedup import find_duplicate, deduplicate_database


@pytest.fixture
def test_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    schema_path = Path(__file__).resolve().parent.parent / "agent" / "schema.sql"
    conn.executescript(schema_path.read_text(encoding="utf-8"))
    return conn


def test_save_raw_item_blocks_duplicate_url_globally(test_db):
    """URL yang sama persis tidak boleh disimpan ulang walau campaign berbeda."""
    conn = test_db
    url = "https://www.facebook.com/groups/petanimelon/posts/999888777/"
    text1 = "Petani melon golden panen raya siap pasok 2 ton ke pasar induk"
    text2 = "Petani melon madesta panen raya siap kirim 3 ton"

    # Simpan pertama kali (sukses)
    ok1 = save_raw_item(conn, campaign_id="cmp-01", platform="facebook", raw_text=text1, url=url)
    assert ok1 is True

    # Simpan kedua kali dengan URL sama (walau teks berbeda dan campaign berbeda) -> harus ditolak
    ok2 = save_raw_item(conn, campaign_id="cmp-02", platform="facebook", raw_text=text2, url=url)
    assert ok2 is False

    # Simpan dengan URL yang hanya beda trailing slash -> harus ditolak
    ok3 = save_raw_item(conn, campaign_id="cmp-03", platform="facebook", raw_text=text2, url=url.rstrip("/"))
    assert ok3 is False


def test_save_raw_item_blocks_duplicate_content_globally(test_db):
    """Konten teks yang identik tidak boleh disimpan ulang walau URL berbeda."""
    conn = test_db
    text = "Panen melon golden 2 ton siap kirim area Jawa Timur hubungi 081234567890"

    ok1 = save_raw_item(conn, campaign_id="cmp-01", platform="facebook", raw_text=text, url="https://fb.com/p1")
    assert ok1 is True

    # Postingan repost identik dengan URL berbeda -> harus ditolak
    ok2 = save_raw_item(conn, campaign_id="cmp-02", platform="facebook", raw_text=text, url="https://fb.com/p2")
    assert ok2 is False


def test_find_duplicate_by_phone(test_db):
    """Dua listing dengan nomor telepon sama dan komoditas sama harus terdeteksi duplikat."""
    conn = test_db
    conn.execute(
        """INSERT INTO listings (
            campaign_id, raw_item_id, intent, entity_name, product, volume_kg,
            price_per_kg, kabupaten, contact_phone, review_status, extractor, created_at
        ) VALUES ('cmp-01', 1, 'supply', 'Pak Joko', 'Melon', 1000, 8000, 'Jombang', '0812-3456-7890', 'approved', 'llm', '2026-10-11T10:00:00')"""
    )
    conn.commit()

    # Nomor berformat +62 harus cocok dengan 0812...
    dup_id, dup_why = find_duplicate(
        conn,
        product="Melon Madesta",
        kabupaten="Kediri",
        contact_phone="+62 812-3456-7890",
        source_url=None,
        entity_name="Joko Tani",
    )
    assert dup_id == 1
    assert "Nomor telepon sama" in dup_why


def test_find_duplicate_by_source_url(test_db):
    """URL sumber yang sama persis harus terdeteksi duplikat lintas platform."""
    conn = test_db
    test_url = "https://maps.google.com/?cid=123456789"
    conn.execute("INSERT INTO raw_items (campaign_id, platform, url, fetched_at, raw_text, content_hash) VALUES ('c1', 'web', ?, '2026-10-11', 'Toko buah segar', 'h1')", (test_url,))
    raw_id = conn.execute("SELECT id FROM raw_items WHERE url = ?", (test_url,)).fetchone()[0]

    conn.execute(
        """INSERT INTO listings (
            campaign_id, raw_item_id, intent, entity_name, product, volume_kg,
            price_per_kg, kabupaten, contact_phone, review_status, extractor, created_at
        ) VALUES ('cmp-01', ?, 'supply', 'CV Tani Buah', 'Melon', 500, 8000, 'Malang', '08999999', 'approved', 'llm', '2026-10-11T10:00:00')""",
        (raw_id,)
    )
    conn.commit()

    dup_id, dup_why = find_duplicate(
        conn,
        product="Melon",
        kabupaten="Malang",
        contact_phone=None,
        source_url=test_url,
        entity_name="CV Tani Buah Baru",
    )
    assert dup_id == 1
    assert "URL sumber postingan sama" in dup_why


def test_deduplicate_database_batch(test_db):
    """deduplicate_database harus menandai entri duplikat dan menautkan ke listing pertama."""
    conn = test_db
    url = "https://facebook.com/post/999"

    # 1. Buat 2 raw items dengan URL sama (simulasi data historis)
    conn.execute("INSERT INTO raw_items (campaign_id, platform, url, fetched_at, raw_text, content_hash) VALUES ('c1', 'fb', ?, '2026-10-11', 'Text 1', 'h1')", (url,))
    raw1 = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute("INSERT INTO raw_items (campaign_id, platform, url, fetched_at, raw_text, content_hash) VALUES ('c2', 'fb', ?, '2026-10-11', 'Text 2', 'h2')", (url,))
    raw2 = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    # 2. Buat 2 listings untuk raw item tersebut
    conn.execute(
        """INSERT INTO listings (campaign_id, raw_item_id, intent, entity_name, product, volume_kg, price_per_kg, kabupaten, contact_phone, created_at)
           VALUES ('c1', ?, 'supply', 'Petani A', 'Melon', 1000, 8000, 'Nganjuk', '08111111', '2026-10-11T10:00:00')""",
        (raw1,)
    )
    list1 = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    conn.execute(
        """INSERT INTO listings (campaign_id, raw_item_id, intent, entity_name, product, volume_kg, price_per_kg, kabupaten, contact_phone, created_at)
           VALUES ('c2', ?, 'supply', 'Petani A', 'Melon', 1000, 8000, 'Nganjuk', '08111111', '2026-10-11T10:05:00')""",
        (raw2,)
    )
    list2 = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()

    # Jalankan deduplikasi
    res = deduplicate_database(conn)
    assert res["duplicates_marked"] >= 1

    # Periksa listing kedua sekarang berstatus duplicate_of = list1
    row2 = conn.execute("SELECT duplicate_of FROM listings WHERE id = ?", (list2,)).fetchone()
    assert row2["duplicate_of"] == list1

    # Query listings unik hanya mengembalikan 1 baris
    unique_rows = conn.execute("SELECT id FROM listings WHERE duplicate_of IS NULL").fetchall()
    assert len(unique_rows) == 1
    assert unique_rows[0]["id"] == list1

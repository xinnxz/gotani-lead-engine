"""Akses database SQLite."""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import settings

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def now_iso() -> str:
    """Waktu sekarang (zona waktu lokal) dalam format ISO."""
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def connect(path: str | Path | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path or settings.db_path), timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")  # baca & tulis bisa jalan bersamaan
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    # Migrasi: tambah kolom baru jika belum ada (backward-compatible)
    for col, typ in [("volume_unit", "TEXT"), ("price_unit", "TEXT")]:
        try:
            conn.execute(f"ALTER TABLE listings ADD COLUMN {col} {typ}")
        except Exception:
            pass  # Kolom sudah ada
    return conn


def log_event(conn: sqlite3.Connection, message: str, level: str = "info", campaign_id: str | None = None) -> None:
    conn.execute(
        "INSERT INTO events (ts, level, campaign_id, message) VALUES (?, ?, ?, ?)",
        (now_iso(), level, campaign_id, message),
    )
    conn.commit()
    print(f"[{level.upper()}] {message}", flush=True)


def content_hash(text: str) -> str:
    """Hash teks yang sudah dinormalisasi; repost identik dianggap item yang sama."""
    norm = re.sub(r"\s+", " ", text.lower()).strip()
    return hashlib.sha1(norm.encode("utf-8")).hexdigest()


def save_raw_item(
    conn: sqlite3.Connection,
    campaign_id: str,
    platform: str,
    raw_text: str,
    *,
    url: str | None = None,
    posted_at: str | None = None,
    author_name: str | None = None,
    author_url: str | None = None,
    source_id: int | None = None,
    run_id: int | None = None,
) -> bool:
    """Simpan item mentah. Return False kalau teks atau URL yang sama sudah ada di database."""
    raw_text = (raw_text or "").strip()
    if len(raw_text) < 15:
        return False

    # 1. Pengecekan URL global: jika URL sudah ada di raw_items, lewati (anti-duplikasi multi-run)
    if url and len(url.strip()) > 10:
        clean_url = url.strip()
        url_slash = clean_url.rstrip("/")
        existing_url = conn.execute(
            "SELECT id FROM raw_items WHERE url = ? OR url = ? OR url = ?",
            (clean_url, url_slash, url_slash + "/"),
        ).fetchone()
        if existing_url:
            return False

    # 2. Pengecekan konten teks global: jika konten identik sudah ada, lewati
    c_hash = content_hash(raw_text)
    existing_hash = conn.execute(
        "SELECT id FROM raw_items WHERE content_hash = ?",
        (c_hash,),
    ).fetchone()
    if existing_hash:
        return False

    cur = conn.execute(
        """INSERT OR IGNORE INTO raw_items
           (run_id, campaign_id, source_id, platform, url, fetched_at, posted_at,
            author_name, author_url, raw_text, content_hash)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (run_id, campaign_id, source_id, platform, url, now_iso(), posted_at,
         author_name, author_url, raw_text, c_hash),
    )
    conn.commit()
    return cur.rowcount > 0


def start_run(conn: sqlite3.Connection, campaign_id: str | None, kind: str,
              platform: str | None = None, account: str | None = None) -> int:
    cur = conn.execute(
        "INSERT INTO runs (campaign_id, kind, platform, account, started_at) VALUES (?, ?, ?, ?, ?)",
        (campaign_id, kind, platform, account, now_iso()),
    )
    conn.commit()
    return int(cur.lastrowid)


def finish_run(conn: sqlite3.Connection, run_id: int, status: str, items: int = 0, error: str | None = None) -> None:
    conn.execute(
        "UPDATE runs SET finished_at=?, status=?, items_found=?, error=? WHERE id=?",
        (now_iso(), status, items, error, run_id),
    )
    conn.commit()


def add_handoff(conn: sqlite3.Connection, kind: str, detail: str, *, url: str | None = None,
                platform: str | None = None, account: str | None = None, campaign_id: str | None = None) -> None:
    conn.execute(
        "INSERT INTO handoffs (ts, campaign_id, platform, account, kind, detail, url) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (now_iso(), campaign_id, platform, account, kind, detail, url),
    )
    conn.commit()
    log_event(conn, f"HANDOFF ({kind}): {detail} {url or ''}", "warning", campaign_id)


def dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False)


def loads(text: str | None, default: Any = None) -> Any:
    if not text:
        return default
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return default


def update_review_status(conn: sqlite3.Connection, listing_id: int, status: str, note: str | None = None) -> bool:
    """Memperbarui status review listing (pending, approved, rejected) dan mencatat waktu review."""
    cur = conn.execute(
        "UPDATE listings SET review_status=?, review_note=?, reviewed_at=? WHERE id=?",
        (status, note, now_iso(), int(listing_id)),
    )
    conn.commit()
    return cur.rowcount > 0


def save_manual_order(
    conn: sqlite3.Connection,
    buyer_name: str,
    product: str,
    volume_kg: float,
    max_price_per_kg: float | None,
    kabupaten: str,
    needed_date: str | None,
    contact_phone: str | None = None,
    variety: str | None = None,
    note: str | None = None,
) -> int:
    """Simpan kebutuhan pembeli yang diinput manual oleh staf/operator GoTani.

    Otomatis berstatus approved dengan relevance & confidence 100 karena data resmi.
    """
    ts = now_iso()
    # Buat raw_item virtual agar foreign key listing tetap konsisten
    cur_raw = conn.execute(
        """INSERT INTO raw_items (campaign_id, platform, raw_text, content_hash, fetched_at, author_name)
           VALUES (?, 'manual', ?, ?, ?, ?)""",
        ("manual_demand", f"Order Pembeli: {buyer_name} butuh {product} {volume_kg}kg", content_hash(f"{buyer_name}_{product}_{ts}"), ts, buyer_name),
    )
    raw_id = cur_raw.lastrowid

    norm_phone = None
    if contact_phone:
        from .normalize import normalize_phone
        norm_phone = normalize_phone(contact_phone)

    attr = {"variety": [variety.strip()] if variety and variety.strip() else [], "source": "manual_order", "note": note}

    cur = conn.execute(
        """INSERT INTO listings (
            campaign_id, raw_item_id, intent, entity_name, product,
            volume_kg, price_per_kg, location_text, kabupaten, provinsi,
            available_text, available_date, contact_phone, contact_wa,
            attributes_json, relevance, confidence, review_status,
            extractor, created_at
        ) VALUES (
            'manual_demand', ?, 'demand', ?, ?,
            ?, ?, ?, ?, 'Jawa Timur',
            ?, ?, ?, ?,
            ?, 100, 100, 'approved',
            'manual', ?
        )""",
        (
            raw_id, buyer_name, product.lower().strip(),
            volume_kg, max_price_per_kg, kabupaten, kabupaten,
            f"Dibutuhkan: {needed_date or 'segera'}", needed_date, contact_phone, norm_phone,
            dumps(attr), ts,
        ),
    )
    conn.commit()
    return int(cur.lastrowid)



# ============================================================================
# FASE 3: HELPER DATABASE PERCAKAPAN & KEPATUHAN (PRD §7.8 & §8)
# ============================================================================

def create_conversation(
    conn: sqlite3.Connection,
    listing_id: int,
    campaign_id: str,
    contact_phone: str,
    role: str,
    *,
    match_id: int | None = None,
    contact_name: str | None = None,
    channel: str = "whatsapp",
    closing_def: str = "lead_interested",
    summary_text: str | None = None,
    assigned_sales: str | None = None,
    initial_state: str = "drafted",
    followup_due_at: str | None = None,
) -> int:
    """Buat sesi percakapan baru untuk lead penawaran (farmer) atau permintaan (buyer)."""
    ts = now_iso()
    cur = conn.execute(
        """INSERT INTO conversations (
            match_id, listing_id, campaign_id, channel, contact_phone,
            contact_name, role, state, closing_def, summary_text,
            assigned_sales, followup_due_at, followup_count, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)""",
        (
            match_id, listing_id, campaign_id, channel, contact_phone,
            contact_name, role, initial_state, closing_def, summary_text,
            assigned_sales, followup_due_at, ts, ts
        ),
    )
    conn.commit()
    return int(cur.lastrowid)


def get_conversation(conn: sqlite3.Connection, conversation_id: int) -> sqlite3.Row | None:
    """Ambil data percakapan berdasarkan ID."""
    return conn.execute("SELECT * FROM conversations WHERE id = ?", (int(conversation_id),)).fetchone()


def get_conversation_by_listing(conn: sqlite3.Connection, listing_id: int) -> sqlite3.Row | None:
    """Cari percakapan aktif terakhir yang terkait dengan suatu listing."""
    return conn.execute(
        "SELECT * FROM conversations WHERE listing_id = ? ORDER BY created_at DESC LIMIT 1",
        (int(listing_id),),
    ).fetchone()


def list_conversations(
    conn: sqlite3.Connection,
    state: str | None = None,
    role: str | None = None,
    limit: int = 100,
) -> list[sqlite3.Row]:
    """Daftar percakapan dengan filter status dan peran, diurutkan dari yang terbaru."""
    query = """
        SELECT c.*, l.product, l.volume_kg, l.price_per_kg, l.kabupaten, l.location_text
        FROM conversations c
        LEFT JOIN listings l ON c.listing_id = l.id
    """
    clauses = []
    params = []

    if state and state != "Semua":
        clauses.append("c.state = ?")
        params.append(state)

    if role and role != "Semua":
        clauses.append("c.role = ?")
        params.append(role)

    if clauses:
        query += " WHERE " + " AND ".join(clauses)

    query += " ORDER BY c.updated_at DESC LIMIT ?"
    params.append(limit)

    return conn.execute(query, params).fetchall()


def update_conversation(
    conn: sqlite3.Connection,
    conversation_id: int,
    *,
    state: str | None = None,
    summary_text: str | None = None,
    assigned_sales: str | None = None,
    followup_due_at: str | None = None,
    increment_followup: bool = False,
) -> bool:
    """Perbarui status percakapan, ringkasan, atau penugasan staf."""
    fields = ["updated_at = ?"]
    params = [now_iso()]

    if state is not None:
        fields.append("state = ?")
        params.append(state)
    if summary_text is not None:
        fields.append("summary_text = ?")
        params.append(summary_text)
    if assigned_sales is not None:
        fields.append("assigned_sales = ?")
        params.append(assigned_sales)
    if followup_due_at is not None:
        fields.append("followup_due_at = ?")
        params.append(followup_due_at)
    if increment_followup:
        fields.append("followup_count = followup_count + 1")

    params.append(conversation_id)
    sql = f"UPDATE conversations SET {', '.join(fields)} WHERE id = ?"
    cur = conn.execute(sql, params)
    conn.commit()
    return cur.rowcount > 0


def add_message(
    conn: sqlite3.Connection,
    conversation_id: int,
    direction: str,
    sender_type: str,
    content: str,
    *,
    sender_name: str | None = None,
    delivery_status: str = "draft",
    channel_msg_id: str | None = None,
    sent_at: str | None = None,
) -> int:
    """Catat pesan baru (inbound/outbound) ke ledger messages."""
    ts = now_iso()
    cur = conn.execute(
        """INSERT INTO messages (
            conversation_id, direction, sender_type, sender_name,
            content, delivery_status, channel_msg_id, sent_at, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            conversation_id, direction, sender_type, sender_name,
            content, delivery_status, channel_msg_id, sent_at or (ts if delivery_status == "sent" else None), ts
        ),
    )
    conn.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (ts, conversation_id))
    conn.commit()
    return int(cur.lastrowid)


def get_messages(conn: sqlite3.Connection, conversation_id: int) -> list[sqlite3.Row]:
    """Ambil seluruh riwayat pesan suatu percakapan secara kronologis."""
    return conn.execute(
        "SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at ASC",
        (conversation_id,),
    ).fetchall()


def register_opt_out(
    conn: sqlite3.Connection,
    contact_phone: str,
    reason: str | None = None,
    source_message: str | None = None,
) -> bool:
    """Daftarkan nomor ke supresi Do-Not-Contact global dan update percakapan terkait."""
    from .normalize import normalize_phone
    clean_p = normalize_phone(contact_phone) or contact_phone.strip()
    ts = now_iso()

    conn.execute(
        """INSERT INTO opt_outs (contact_phone, reason, source_message, opted_out_at)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(contact_phone) DO UPDATE SET
               reason = excluded.reason,
               source_message = excluded.source_message,
               opted_out_at = excluded.opted_out_at""",
        (clean_p, reason or "user_request", source_message, ts),
    )

    conn.execute(
        "UPDATE conversations SET state = 'opt_out', updated_at = ? WHERE contact_phone = ? OR contact_phone LIKE ?",
        (ts, clean_p, f"%{clean_p[-10:]}"),
    )
    conn.commit()
    return True


def is_opted_out(conn: sqlite3.Connection, contact_phone: str) -> bool:
    """Periksa apakah nomor telepon ada di daftar supresi Do-Not-Contact."""
    if not contact_phone:
        return False
    from .normalize import normalize_phone
    clean_p = normalize_phone(contact_phone) or contact_phone.strip()
    row = conn.execute(
        "SELECT id FROM opt_outs WHERE contact_phone = ? OR contact_phone LIKE ?",
        (clean_p, f"%{clean_p[-10:]}"),
    ).fetchone()
    return bool(row)

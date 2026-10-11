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
    """Simpan item mentah. Return False kalau teks yang sama sudah ada."""
    raw_text = (raw_text or "").strip()
    if len(raw_text) < 15:
        return False
    cur = conn.execute(
        """INSERT OR IGNORE INTO raw_items
           (run_id, campaign_id, source_id, platform, url, fetched_at, posted_at,
            author_name, author_url, raw_text, content_hash)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (run_id, campaign_id, source_id, platform, url, now_iso(), posted_at,
         author_name, author_url, raw_text, content_hash(raw_text)),
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
        (status, note, now_iso(), listing_id),
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


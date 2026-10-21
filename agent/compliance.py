"""Modul Kepatuhan Regulasi & Perlindungan Data Pribadi (UU PDP No. 27/2022 / PRD §10).

Fungsi utama:
1. Pengecekan daftar supresi Do-Not-Contact (DNC) global (F8.9 / G5).
2. Deteksi niat opt-out / penolakan dari teks balasan lead.
3. Penegakan batasan jam kerja sopan (07.00 - 20.00 WIB, F8.6).
4. Pembersihan dan sanitasi data pribadi.
"""
from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from typing import Any

from . import db
from .normalize import normalize_phone


# Pola regex deteksi permintaan opt-out / berhenti / hapus data (UU PDP G5)
OPT_OUT_PATTERNS = [
    r"\b(jangan\s*(wa|chat|hubungi|kontak|kirim|pesan|ganggu)\s*(lagi|terus)?)\b",
    r"\b(hapus\s*(nomor|data|kontak)\s*(saya|kami)?)\b",
    r"\b(unsub|unsubscribe|stop\s*(wa|pesan|promo)?)\b",
    r"\b(salah\s*sambung|salah\s*orang|salah\s*nomor)\b",
    r"\b(blokir|laporkan|spam|tidak\s*berkenan|tidak\s*minat|gak\s*minat)\b",
    r"\b(bukan\s*(petani|penjual|pembeli|toko|tengkulak))\b",
]

COMPILED_OPT_OUT = [re.compile(p, re.IGNORECASE) for p in OPT_OUT_PATTERNS]


def detect_opt_out_intent(text: str | None) -> tuple[bool, str | None]:
    """Deteksi apakah teks balasan dari lead mengindikasikan permintaan berhenti / opt-out.

    Mengembalikan (is_opt_out: bool, reason: str | None).
    """
    if not text or not isinstance(text, str):
        return False, None

    cleaned = text.strip().lower()

    # Kata pendek tegas
    if cleaned in {"stop", "berhenti", "batal", "jangan", "blokir", "unsub"}:
        return True, "kata_kunci_tegas"

    for pattern in COMPILED_OPT_OUT:
        match = pattern.search(cleaned)
        if match:
            return True, match.group(0)

    return False, None


def is_do_not_contact(conn: sqlite3.Connection, phone: str | None) -> bool:
    """Periksa apakah nomor telepon terdaftar di blacklist supresi Do-Not-Contact."""
    if not phone:
        return False
    return db.is_opted_out(conn, phone)


def register_opt_out_contact(
    conn: sqlite3.Connection,
    phone: str,
    reason: str | None = None,
    source_message: str | None = None,
) -> bool:
    """Tambahkan nomor ke daftar supresi global dan nonaktifkan percakapan terkait."""
    if not phone:
        return False
    return db.register_opt_out(conn, phone, reason=reason, source_message=source_message)


def is_within_operating_hours(
    now_dt: datetime | None = None,
    start_hour: int = 7,
    end_hour: int = 20,
    tz_name: str = "Asia/Jakarta",
) -> bool:
    """Pastikan pengiriman pesan hanya terjadi pada jam kerja sopan (default: 07.00 - 20.00 WIB, F8.6)."""
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = timezone.utc

    current_dt = now_dt or datetime.now(tz)
    hour = current_dt.hour
    return start_hour <= hour < end_hour

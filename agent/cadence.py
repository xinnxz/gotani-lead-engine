"""Modul Cadence & Penjadwalan Follow-Up Terstruktur (PRD §7.8 / F8.5 & F8.6).

Aturan Cadence (F8.5):
1. Jika pesan belum dibalas, kirim maksimal 2 kali follow-up (Hari ke-3 dan Hari ke-7), lalu berhenti.
2. Pengiriman hanya dieksekusi pada jam kerja sopan (07.00 - 20.00 WIB).
3. Jika lead tidak merespons setelah 2x follow-up, status otomatis dialihkan ke 'closed_lost'.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

from . import db
from .compliance import is_within_operating_hours
from .outreach import _clean_str


def calculate_due_date(days_ahead: int = 3) -> str:
    """Hitung tanggal jatuh tempo ISO masa depan."""
    now_dt = datetime.now(timezone.utc).astimezone()
    due_dt = now_dt + timedelta(days=days_ahead)
    return due_dt.isoformat(timespec="seconds")


def get_due_followups(
    conn: sqlite3.Connection,
    now_dt: datetime | None = None,
) -> list[sqlite3.Row]:
    """Ambil daftar percakapan yang sudah jatuh tempo untuk dikirimkan pesan follow-up.

    Hanya mengembalikan data jika saat ini berada dalam jam operasional wajar (07.00 - 20.00).
    """
    if not is_within_operating_hours(now_dt):
        return []

    now_iso = (now_dt or datetime.now(timezone.utc).astimezone()).isoformat(timespec="seconds")

    query = """
        SELECT c.*, l.product, l.volume_kg, l.kabupaten
        FROM conversations c
        JOIN listings l ON c.listing_id = l.id
        WHERE c.state IN ('sent', 'followup_1')
          AND c.followup_due_at IS NOT NULL
          AND c.followup_due_at <= ?
          AND c.followup_count < 2
        ORDER BY c.followup_due_at ASC
    """
    return conn.execute(query, (now_iso,)).fetchall()


def generate_followup_message(
    conn: sqlite3.Connection,
    conversation_id: int,
) -> str:
    """Susun pesan follow-up santun berdasarkan urutan pengingat (ke-1 atau ke-2)."""
    conv = db.get_conversation(conn, conversation_id)
    if not conv:
        return "Halo, sekadar menindaklanjuti pesan kami sebelumnya. Terima kasih."

    listing = conn.execute("SELECT * FROM listings WHERE id = ?", (conv["listing_id"],)).fetchone()
    l_dict = dict(listing) if listing else {}

    c_name = _clean_str(conv["contact_name"]) or "Bapak/Ibu"
    prod = (l_dict.get("product") or "hasil tani").title()
    count = conv["followup_count"]

    if count == 0:
        # Follow-Up ke-1 (Hari ke-3): Pengingat santun
        return (
            f"Halo Pak/Bu {c_name}, salam dari GoTani. Sekadar menindaklanjuti pesan kami beberapa hari lalu "
            f"mengenai ketersediaan pasokan {prod}.\n\n"
            "Apakah komoditas tersebut saat ini masih tersedia? Jika ada kapasitas panen baru, "
            "kami siap menyambungkannya dengan permintaan mitra pembeli terverifikasi kami. Terima kasih."
        )
    else:
        # Follow-Up ke-2 (Hari ke-7): Penawaran terakhir & penutupan sopan
        return (
            f"Halo Pak/Bu {c_name}, mohon izin menyapa untuk terakhir kali mengenai penawaran {prod}.\n\n"
            "Apabila pasokan saat ini belum tersedia atau Bapak/Ibu belum berkenan bermitra, tidak apa-apa sama sekali. "
            "Data kontak Anda akan kami simpan untuk penawaran musim mendatang. Sukses selalu untuk usahanya."
        )


def advance_followup(
    conn: sqlite3.Connection,
    conversation_id: int,
) -> str:
    """Tingkatkan tahapan follow-up atau tutup percakapan jika sudah mencapai batas maksimal."""
    conv = db.get_conversation(conn, conversation_id)
    if not conv:
        return "not_found"

    current_count = conv["followup_count"]

    if current_count == 0:
        # Masuk ke follow-up 1 -> jadwalkan follow-up 2 untuk 4 hari ke depan (total H+7 dari awal)
        next_due = calculate_due_date(days_ahead=4)
        db.update_conversation(
            conn,
            conversation_id,
            state="followup_1",
            followup_due_at=next_due,
            increment_followup=True,
        )
        return "scheduled_followup_2"
    else:
        # Sudah 2 kali follow-up tanpa respons -> tandai closed_lost
        db.update_conversation(
            conn,
            conversation_id,
            state="closed_lost",
            followup_due_at=None,
            increment_followup=True,
            summary_text="Ditutup otomatis: tidak ada balasan setelah 2 kali follow-up (H+3 & H+7).",
        )
        return "closed_lost"

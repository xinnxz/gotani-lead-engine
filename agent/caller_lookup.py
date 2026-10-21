"""Modul Bantuan Telepon Masuk / Inbound Call Assistant (PRD §7.7 / F7).

Ketika ada telepon masuk dari petani atau pembeli, staf GoTani cukup memasukkan nomor HP.
Sistem otomatis menampilkan profil penelepon, komoditas, riwayat, status percakapan CRM (Fase 3),
rekomendasi match, dan 5-7 poin panduan bicara untuk staf sales/CS.
"""
from __future__ import annotations

import sqlite3
from typing import Any

from .db import loads
from .normalize import normalize_phone


def lookup_caller(conn: sqlite3.Connection, raw_phone: str) -> dict[str, Any] | None:
    """Cari informasi penelepon berdasarkan nomor HP dan susun poin bicara (5-7 poin ringkas)."""
    norm_phone = normalize_phone(raw_phone)
    if not norm_phone:
        return None

    last_8 = raw_phone.strip()[-8:]

    # 1. Cek Kepatuhan Opt-Out (Do-Not-Contact / UU PDP G5)
    opt_row = conn.execute(
        """SELECT * FROM opt_outs 
           WHERE contact_phone = ? OR contact_phone = ? OR contact_phone LIKE ?
           ORDER BY opted_out_at DESC LIMIT 1""",
        (norm_phone, raw_phone.strip(), f"%{last_8}%"),
    ).fetchone()
    is_opted_out = opt_row is not None
    opt_out_detail = dict(opt_row) if opt_row else None

    # 2. Cek Riwayat Percakapan CRM Terkini (Fase 3 / PRD §7.8)
    conv_row = conn.execute(
        """SELECT * FROM conversations 
           WHERE contact_phone = ? OR contact_phone = ? OR contact_phone LIKE ?
           ORDER BY updated_at DESC LIMIT 1""",
        (norm_phone, raw_phone.strip(), f"%{last_8}%"),
    ).fetchone()

    conv_dict = None
    last_msg_dict = None
    if conv_row:
        conv_dict = dict(conv_row)
        msg_row = conn.execute(
            """SELECT * FROM messages 
               WHERE conversation_id = ? 
               ORDER BY id DESC LIMIT 1""",
            (conv_dict["id"],),
        ).fetchone()
        if msg_row:
            last_msg_dict = dict(msg_row)
        conv_dict["last_message"] = last_msg_dict

    # 3. Cari listing yang memiliki nomor kontak ini (bisa format mentah atau ternormalisasi)
    rows = conn.execute(
        """SELECT * FROM listings 
           WHERE (contact_phone LIKE ? OR contact_wa = ? OR contact_phone = ?) 
           ORDER BY created_at DESC""",
        (f"%{last_8}%", norm_phone, norm_phone),
    ).fetchall()

    if not rows and not conv_dict:
        # Nomor belum pernah terdata sama sekali
        talking_points = [
            "Sapa ramah dan tanyakan nama serta lokasi usaha beliau.",
            "Tanyakan apakah beliau bermaksud menjual hasil panen (Petani) atau mencari pasokan (Pembeli).",
            "Tanyakan komoditas yang ingin ditransaksikan, estimasi volume (kg/ton), dan harga yang diharapkan.",
            "Catat jadwal panen atau kebutuhan pengiriman (tanggal ketersediaan).",
            "Input data beliau ke sistem melalui Form Order Pembeli atau jalankan kampanye pencarian baru.",
        ]
        if is_opted_out:
            talking_points.insert(
                0,
                f"[PERINGATAN OPT-OUT] Nomor ini tercatat di Do-Not-Contact sejak {opt_out_detail.get('opted_out_at')}. "
                "Hanya layani informasi yang diminta langsung oleh penelepon, jangan tawarkan promosi."
            )

        return {
            "found": False,
            "phone": norm_phone,
            "is_opted_out": is_opted_out,
            "opt_out_detail": opt_out_detail,
            "message": f"Nomor {norm_phone} belum terdaftar di database GoTani. Perlakukan sebagai mitra baru.",
            "talking_points": talking_points,
        }

    # Ambil listing terbaru sebagai profil utama
    primary = dict(rows[0]) if rows else {}
    listing_id = primary.get("id")

    # Ambil atribut profil
    if primary:
        role = "Petani / Penjual (Supply)" if primary.get("intent") == "supply" else "Pembeli / Pengepul (Demand)"
        name = primary.get("entity_name") or "Mitra GoTani"
        prod = (primary.get("product") or "-").title()
        vol = f"{primary['volume_kg']:g} kg" if primary.get("volume_kg") else "Volume belum tercatat"
        price = f"Rp {primary['price_per_kg']:,.0f}/kg" if primary.get("price_per_kg") else "Harga belum tercatat"
        loc = primary.get("kabupaten") or primary.get("location_text") or "Lokasi belum spesifik"
        date_info = primary.get("available_date") or primary.get("available_text") or "Jadwal belum pasti"
        status_review = primary.get("review_status", "pending")
    else:
        # Fallback jika hanya ada di data percakapan
        role = "Petani / Penjual (Supply)" if conv_dict.get("role") == "farmer" else "Pembeli / Pengepul (Demand)"
        name = conv_dict.get("contact_name") or "Mitra GoTani"
        prod = "-"
        vol = "Belum tercatat"
        price = "Belum tercatat"
        loc = "Belum tercatat"
        date_info = "Belum tercatat"
        status_review = "unreviewed"

    # Cek apakah ada rekomendasi match terkait
    match_points = []
    if listing_id:
        if primary.get("intent") == "supply":
            match_rows = conn.execute(
                """SELECT m.*, d.entity_name AS buyer_name, d.price_per_kg AS buyer_budget, d.kabupaten AS buyer_loc
                   FROM match_items mi
                   JOIN matches m ON mi.match_id = m.id
                   JOIN listings d ON m.demand_listing_id = d.id
                   WHERE mi.supply_listing_id = ?
                   ORDER BY m.score DESC LIMIT 2""",
                (listing_id,),
            ).fetchall()
        else:
            match_rows = conn.execute(
                """SELECT m.*, s.entity_name AS farmer_name, s.price_per_kg AS farmer_price, s.kabupaten AS farmer_loc
                   FROM matches m
                   JOIN match_items mi ON m.id = mi.match_id
                   JOIN listings s ON mi.supply_listing_id = s.id
                   WHERE m.demand_listing_id = ?
                   ORDER BY m.score DESC LIMIT 2""",
                (listing_id,),
            ).fetchall()

        for mr in match_rows:
            m_dict = dict(mr)
            if primary.get("intent") == "supply":
                match_points.append(
                    f"Ada pembeli cocok: {m_dict.get('buyer_name')} ({m_dict.get('buyer_loc')}) dengan skor {m_dict['score']} (Budget: Rp {m_dict.get('buyer_budget', 0):,.0f})"
                )
            else:
                match_points.append(
                    f"Ada petani cocok: {m_dict.get('farmer_name')} ({m_dict.get('farmer_loc')}) dengan skor {m_dict['score']}"
                )

    # 4. Susun 5-7 poin bicara ringkas untuk Sales / CS
    talking_points = [
        f"**Identitas:** {name} · Peran: {role}.",
        f"**Komoditas & Volume:** {prod} ({vol}) · Catatan Harga: {price}.",
        f"**Lokasi Usaha:** {loc} · Jadwal Ketersediaan: {date_info}.",
    ]

    # Poin Status Percakapan CRM & Kepatuhan
    if is_opted_out:
        talking_points.insert(
            0,
            f"**[PERINGATAN OPT-OUT]** Nomor ini tercatat di Do-Not-Contact (UU PDP). Jangan tawarkan produk komersial secara proaktif; dengarkan keluhan/kebutuhan beliau terlebih dahulu."
        )

    if conv_dict:
        c_state = conv_dict["state"]
        c_summary = conv_dict.get("summary_text") or "Tidak ada catatan khusus."
        if c_state == "handover_pending":
            talking_points.append(
                f"**[ESKALASI HANDOVER SALES]** Percakapan WhatsApp sebelumnya memerlukan bantuan staf: '{c_summary}'. Diskusikan negosiasi atau pertanyaan tersebut sekarang di telepon."
            )
        elif c_state == "active":
            msg_snippet = ""
            if last_msg_dict:
                msg_snippet = f" Terakhir ({last_msg_dict['direction']}): \"{last_msg_dict['content'][:60]}...\""
            talking_points.append(
                f"**[STATUS CRM: AKTIF]** Percakapan via WhatsApp sedang berlangsung.{msg_snippet}"
            )
        elif c_state == "closed_won":
            talking_points.append(
                "**[STATUS CRM: CLOSED WON]** Beliau telah mencapai kesepakatan transaksi sebelumnya. Sambut sebagai mitra terpercaya GoTani."
            )
        elif c_state == "closed_lost":
            talking_points.append(
                f"**[STATUS CRM: CLOSED LOST]** Percakapan sebelumnya ditutup ({c_summary}). Tanyakan apakah ada kapasitas panen atau kebutuhan baru."
            )
        elif c_state == "drafted":
            talking_points.append(
                "**[STATUS CRM: DRAF DISIAPKAN]** AI sudah menyusun draf penawaran awal di WhatsApp. Anda dapat langsung menyampaikan isi penawaran tersebut."
            )
        elif c_state in ("sent", "followup_1", "followup_2"):
            talking_points.append(
                f"**[STATUS CRM: MENUNGGU RESPON]** Pesan penawaran/follow-up ke-{conv_dict['followup_count']} sudah dikirim via WhatsApp. Konfirmasi apakah pesan sudah terbaca."
            )

    if primary:
        talking_points.append(
            f"**Status Verifikasi Database:** `{status_review}` (Skor Relevansi: {primary.get('relevance')}%, Confidence: {primary.get('confidence')}%)."
        )

    if match_points:
        talking_points.append(f"**Peluang Transaksi Cepat:** {'; '.join(match_points)}.")
        talking_points.append("Tawarkan langsung untuk menghubungkan beliau dengan calon mitra di atas.")
    else:
        talking_points.append("Belum ada match langsung dengan skor tinggi; tanyakan fleksibilitas harga dan tanggal kirim.")

    talking_points.append("Konfirmasi apakah nomor WhatsApp ini aktif untuk pengiriman draf rincian transaksi.")

    return {
        "found": True,
        "phone": norm_phone,
        "primary_listing": primary,
        "name": name,
        "role": role,
        "product": prod,
        "location": loc,
        "history_count": len(rows),
        "conversation": conv_dict,
        "is_opted_out": is_opted_out,
        "opt_out_detail": opt_out_detail,
        "talking_points": talking_points,
    }

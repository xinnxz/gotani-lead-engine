"""Modul Bantuan Telepon Masuk / Inbound Call Assistant (PRD §7.7 / F7).

Ketika ada telepon masuk dari petani atau pembeli, staf GoTani cukup memasukkan nomor HP.
Sistem otomatis menampilkan profil penelepon, komoditas, riwayat, rekomendasi match,
dan 5-7 poin panduan bicara untuk staf sales/CS.
"""
from __future__ import annotations

import sqlite3
from typing import Any

from .db import loads
from .normalize import normalize_phone


def lookup_caller(conn: sqlite3.Connection, raw_phone: str) -> dict[str, Any] | None:
    """Cari informasi penelepon berdasarkan nomor HP dan susun poin bicara (5-7 poin)."""
    norm_phone = normalize_phone(raw_phone)
    if not norm_phone:
        return None

    # Cari listing yang memiliki nomor kontak ini (bisa format mentah atau ternormalisasi)
    rows = conn.execute(
        """SELECT * FROM listings 
           WHERE (contact_phone LIKE ? OR contact_wa = ?) 
           ORDER BY created_at DESC""",
        (f"%{raw_phone.strip()[-8:]}%", norm_phone),
    ).fetchall()

    if not rows:
        return {
            "found": False,
            "phone": norm_phone,
            "message": f"Nomor {norm_phone} belum terdaftar di database GoTani. Perlakukan sebagai mitra baru.",
            "talking_points": [
                f"Sapa ramah dan tanyakan nama serta lokasi usaha beliau.",
                "Tanyakan apakah beliau bermaksud menjual hasil panen (Petani) atau mencari pasokan (Pembeli).",
                "Tanyakan komoditas yang ingin ditransaksikan, estimasi volume (kg/ton), dan harga yang diharapkan.",
                "Catat jadwal panen atau kebutuhan pengiriman (tanggal ketersediaan).",
                "Input data beliau ke sistem melalui Form Order Pembeli atau jalankan kampanye pencarian baru.",
            ],
        }

    # Ambil listing terbaru sebagai profil utama
    primary = dict(rows[0])
    role = "Petani / Penjual (Supply)" if primary.get("intent") == "supply" else "Pembeli / Pengepul (Demand)"
    name = primary.get("entity_name") or "Mitra GoTani"
    prod = (primary.get("product") or "-").title()
    vol = f"{primary['volume_kg']:g} kg" if primary.get("volume_kg") else "Volume belum tercatat"
    price = f"Rp {primary['price_per_kg']:,.0f}/kg" if primary.get("price_per_kg") else "Harga belum tercatat"
    loc = primary.get("kabupaten") or primary.get("location_text") or "Lokasi belum spesifik"
    date_info = primary.get("available_date") or primary.get("available_text") or "Jadwal belum pasti"

    # Cek apakah ada rekomendasi match terkait
    listing_id = primary["id"]
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

    match_points = []
    for mr in match_rows:
        m_dict = dict(mr)
        if primary.get("intent") == "supply":
            match_points.append(f"Ada pembeli cocok: {m_dict.get('buyer_name')} ({m_dict.get('buyer_loc')}) dengan skor kecocokan {m_dict['score']} (Budget: Rp {m_dict.get('buyer_budget', 0):,.0f})")
        else:
            match_points.append(f"Ada petani cocok: {m_dict.get('farmer_name')} ({m_dict.get('farmer_loc')}) dengan skor kecocokan {m_dict['score']}")

    # Susun 5-7 poin bicara ringkas untuk Sales / CS
    talking_points = [
        f"**Identitas:** {name} · Peran: {role}.",
        f"**Komoditas & Volume:** {prod} ({vol}) · Catatan Harga: {price}.",
        f"**Lokasi Usaha:** {loc} · Jadwal Ketersediaan: {date_info}.",
        f"**Status Verifikasi Database:** `{primary.get('review_status', 'pending')}` (Skor Relevansi: {primary.get('relevance')}%, Confidence: {primary.get('confidence')}%).",
    ]

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
        "talking_points": talking_points,
    }

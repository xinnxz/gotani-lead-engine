"""Modul deduplikasi listing (PRD F3.5).

Mendeteksi apakah sebuah listing baru merupakan duplikat dari listing yang sudah ada.
Kriteria duplikat:
1. Nomor telepon sama persis (setelah normalisasi +62).
2. URL sumber sama persis.
3. Nama entitas sangat mirip (fuzzy similarity >= 90) dengan kabupaten & produk yang sama.
"""
from __future__ import annotations

import re
import sqlite3
from typing import Optional

from rapidfuzz import fuzz

from .normalize import normalize_phone


def find_duplicate(
    conn: sqlite3.Connection,
    product: str | None,
    kabupaten: str | None,
    contact_phone: str | None,
    source_url: str | None,
    entity_name: str | None,
    exclude_listing_id: int | None = None,
) -> tuple[int | None, str | None]:
    """Cari apakah listing ini menduplikasi listing lain yang sudah ada di database.

    Mengembalikan (duplicate_of_id, alasan_duplikasi).
    Jika tidak ada duplikat, mengembalikan (None, None).
    """
    if not product:
        return None, None

    norm_phone = normalize_phone(contact_phone)

    # 1. Cek duplikasi berdasarkan nomor telepon (sinyal terkuat)
    if norm_phone:
        query = "SELECT id, contact_phone, product, entity_name FROM listings WHERE duplicate_of IS NULL"
        params: list = []
        if exclude_listing_id:
            query += " AND id != ?"
            params.append(exclude_listing_id)

        rows = conn.execute(query, params).fetchall()
        for r in rows:
            r_phone = normalize_phone(r["contact_phone"])
            if r_phone and r_phone == norm_phone:
                # Jika komoditas sama atau mirip, pasti orang yang sama
                if product.lower() in (r["product"] or "").lower() or (r["product"] or "").lower() in product.lower():
                    return r["id"], f"Nomor telepon sama ({norm_phone})"

    # 2. Cek duplikasi berdasarkan URL sumber (jika URL postingan sama)
    if source_url and len(source_url) > 10 and "/groups/" in source_url:
        query = """
            SELECT l.id, r.url FROM listings l
            JOIN raw_items r ON l.raw_item_id = r.id
            WHERE l.duplicate_of IS NULL AND r.url = ?
        """
        params = [source_url]
        if exclude_listing_id:
            query += " AND l.id != ?"
            params.append(exclude_listing_id)
        row = conn.execute(query, params).fetchone()
        if row:
            return row["id"], f"URL sumber postingan sama ({source_url})"

    # 3. Cek kemiripan fuzzy nama pemosting dalam kabupaten yang sama (rapidfuzz >= 90)
    if entity_name and len(entity_name.strip()) >= 3 and kabupaten:
        query = """
            SELECT id, entity_name, kabupaten, product FROM listings
            WHERE duplicate_of IS NULL AND kabupaten = ?
        """
        params = [kabupaten]
        if exclude_listing_id:
            query += " AND id != ?"
            params.append(exclude_listing_id)

        rows = conn.execute(query, params).fetchall()
        for r in rows:
            target_name = r["entity_name"]
            if target_name and len(target_name.strip()) >= 3:
                sim = fuzz.token_sort_ratio(entity_name.lower(), target_name.lower())
                if sim >= 90:
                    r_prod = (r["product"] or "").lower()
                    if product.lower() in r_prod or r_prod in product.lower():
                        return r["id"], f"Nama entitas mirip ({sim}%: {entity_name} ~ {target_name}) di {kabupaten}"

    return None, None

"""Seed script untuk mengisi data demo hackathon (Fase 1 & Fase 2).

Menghasilkan skenario demo lengkap:
1. Data pasokan petani (supply) dengan kontak, lokasi, tanggal panen, dan varietas.
2. Order pembeli nyata (demand) yang memicu Match 1-ke-1 (Outreach) dan Smart Pooling (Multi-petani).
3. Langsung menjalankan engine matchmaking sehingga hasil match & pool langsung siap dipresentasikan.
"""
import os
import sys
import json
from datetime import datetime, timedelta

# Tambahkan root directory ke sys.path supaya module agent bisa diimport
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from agent.db import connect, save_raw_item, now_iso
from agent.normalize import normalize_phone
from agent.match_runner import run_all_matches

CAMPAIGN_ID = "demo_melon_jatim"

# 12 Postingan Penawaran Petani (Supply)
FARMER_POSTS = [
    # Match 1-ke-1 candidate (Pak Budi Jombang, 600kg, 7.500/kg)
    {
        "text": "Panen melon Madesta lusa, ada sekitar 600 kg. Harga Rp 7.500/kg. Area Jombang, siap angkut. Hub WA 081234567890",
        "entity": "Pak Budi Santoso",
        "product": "melon",
        "variety": "madesta",
        "vol": 600.0,
        "price": 7500.0,
        "kab": "Jombang",
        "phone": "081234567890",
        "days_ahead": 2,
    },
    # Pooling candidate 1 (Kediri - Jangkar, 400kg, 7.000/kg)
    {
        "text": "Bismillah, jual melon Golden 4 kuintal. Siap petik besok. Lokasi Pare Kediri. Minat hubungi 085712345678",
        "entity": "Pak Joko Widodo (Kelompok Tani Pare)",
        "product": "melon",
        "variety": "golden",
        "vol": 400.0,
        "price": 7000.0,
        "kab": "Kediri",
        "phone": "085712345678",
        "days_ahead": 1,
    },
    # Pooling candidate 2 (Blitar, 350kg, 7.200/kg)
    {
        "text": "Ready melon Golden kualitas super, sisa panen 350 kg. Ambil langsung di kebun Blitar. WA 087888123456",
        "entity": "Bu Siti Aminah",
        "product": "melon",
        "variety": "golden",
        "vol": 350.0,
        "price": 7200.0,
        "kab": "Blitar",
        "phone": "087888123456",
        "days_ahead": 3,
    },
    # Pooling candidate 3 (Tulungagung, 250kg, 7.100/kg)
    {
        "text": "Dijual melon Golden 2.5 kuintal, buah manis mulus. Tulungagung. Kontak 082199887766",
        "entity": "Pak Ahmad Subagyo",
        "product": "melon",
        "variety": "golden",
        "vol": 250.0,
        "price": 7100.0,
        "kab": "Tulungagung",
        "phone": "082199887766",
        "days_ahead": 2,
    },
    # Petani lain (Nganjuk, Inthanon)
    {
        "text": "Panen melon Inthanon super greenhouse 1 ton. Nganjuk kota. Harga 8rb/kg nego. WA 089911223344",
        "entity": "Greenhouse Nganjuk Makmur",
        "product": "melon",
        "variety": "inthanon",
        "vol": 1000.0,
        "price": 8000.0,
        "kab": "Nganjuk",
        "phone": "089911223344",
        "days_ahead": 5,
    },
    # Petani lain (Mojokerto, Sky Rocket)
    {
        "text": "Sky rocket sisa panen 300 kg di gudang Mojokerto. 5rb/kg borongan. 085566778899",
        "entity": "Cak Lontong Tani",
        "product": "melon",
        "variety": "sky rocket",
        "vol": 300.0,
        "price": 5000.0,
        "kab": "Mojokerto",
        "phone": "085566778899",
        "days_ahead": 0,
    },
    # Petani Pisang (Pasuruan)
    {
        "text": "Panen pisang cavendish 1.5 ton minggu depan. Pasuruan. WA 081122334455",
        "entity": "Kebun Pisang Pandaan",
        "product": "pisang",
        "variety": "cavendish",
        "vol": 1500.0,
        "price": 6500.0,
        "kab": "Pasuruan",
        "phone": "081122334455",
        "days_ahead": 7,
    },
]

# 3 Kebutuhan Pembeli (Demand)
BUYER_ORDERS = [
    # 1. Memicu MATCH 1-KE-1 SEMPURNA dengan Pak Budi (Jombang -> Surabaya ~65 km)
    {
        "name": "PT Segar Buah Nusantara (Surabaya)",
        "product": "melon",
        "variety": "madesta",
        "vol": 500.0,
        "max_price": 9000.0,
        "kab": "Surabaya",
        "phone": "081987654321",
        "days_ahead": 5,
    },
    # 2. Memicu SMART POOLING (Agregasi 3 Petani: Kediri 400 + Blitar 350 + Tulungagung 250 = 1.000 kg)
    {
        "name": "Grosir Buah Indah Pare",
        "product": "melon",
        "variety": "golden",
        "vol": 1000.0,
        "max_price": 8500.0,
        "kab": "Kediri",
        "phone": "081299998888",
        "days_ahead": 4,
    },
    # 3. Kebutuhan Pisang (Demand Pasuruan/Malang)
    {
        "name": "Distributor Buah Malang Raya",
        "product": "pisang",
        "variety": "cavendish",
        "vol": 800.0,
        "max_price": 8000.0,
        "kab": "Malang",
        "phone": "081377776666",
        "days_ahead": 10,
    },
]


def run():
    print("[INFO] Memulai seed_demo.py (Fase 1 & Fase 2)...")
    conn = connect()
    now_dt = datetime.now()

    # Bersihkan data lama agar idempoten
    conn.execute("DELETE FROM matches")
    conn.execute("DELETE FROM match_items")
    conn.execute("DELETE FROM listings WHERE campaign_id IN (?, 'manual_demand')", (CAMPAIGN_ID,))
    conn.execute("DELETE FROM raw_items WHERE campaign_id IN (?, 'manual_demand')", (CAMPAIGN_ID,))
    conn.commit()

    # 1. Masukkan Penawaran Petani (Supply)
    for p in FARMER_POSTS:
        ts = now_iso()
        avail_date = (now_dt + timedelta(days=p["days_ahead"])).date().isoformat()
        norm_phone = normalize_phone(p["phone"])

        cur_raw = conn.execute(
            """INSERT INTO raw_items (campaign_id, platform, raw_text, content_hash, fetched_at, author_name, processed)
               VALUES (?, 'demo_fb', ?, ?, ?, ?, 1)""",
            (CAMPAIGN_ID, p["text"], f"hash_{p['phone']}", ts, p["entity"]),
        )
        raw_id = cur_raw.lastrowid

        attr = {"variety": [p["variety"]]}
        reasons = {
            "relevance": [f"+40 produk cocok ({p['product']})", "+30 niat sesuai (supply)", f"+20 lokasi di target ({p['kab']})"],
            "confidence": ["+30 post baru", "+25 ada kontak langsung (WA)", "+25 akun aktif", "+10 angka wajar"],
        }

        conn.execute(
            """INSERT INTO listings (
                campaign_id, raw_item_id, intent, entity_name, product,
                volume_kg, price_per_kg, location_text, kabupaten, provinsi,
                available_text, available_date, contact_phone, contact_wa,
                attributes_json, relevance, confidence, score_reasons_json,
                review_status, extractor, created_at
            ) VALUES (?, ?, 'supply', ?, ?, ?, ?, ?, ?, 'Jawa Timur', ?, ?, ?, ?, ?, 90, 85, ?, 'approved', 'demo', ?)""",
            (
                CAMPAIGN_ID, raw_id, p["entity"], p["product"],
                p["vol"], p["price"], f"Kab. {p['kab']}", p["kab"],
                f"Siap tgl {avail_date}", avail_date, p["phone"], norm_phone,
                json.dumps(attr), json.dumps(reasons), ts
            ),
        )

    # 2. Masukkan Kebutuhan Pembeli (Demand)
    for b in BUYER_ORDERS:
        ts = now_iso()
        needed_date = (now_dt + timedelta(days=b["days_ahead"])).date().isoformat()
        norm_phone = normalize_phone(b["phone"])

        cur_raw = conn.execute(
            """INSERT INTO raw_items (campaign_id, platform, raw_text, content_hash, fetched_at, author_name, processed)
               VALUES ('manual_demand', 'manual_order', ?, ?, ?, ?, 1)""",
            (f"Order: {b['name']} butuh {b['product']} {b['vol']}kg", f"hash_buyer_{b['phone']}", ts, b["name"]),
        )
        raw_id = cur_raw.lastrowid

        attr = {"variety": [b["variety"]]}
        conn.execute(
            """INSERT INTO listings (
                campaign_id, raw_item_id, intent, entity_name, product,
                volume_kg, price_per_kg, location_text, kabupaten, provinsi,
                available_text, available_date, contact_phone, contact_wa,
                attributes_json, relevance, confidence, review_status,
                extractor, created_at
            ) VALUES ('manual_demand', ?, 'demand', ?, ?, ?, ?, ?, ?, 'Jawa Timur', ?, ?, ?, ?, ?, 100, 100, 'approved', 'manual', ?)""",
            (
                raw_id, b["name"], b["product"],
                b["vol"], b["max_price"], f"Kab. {b['kab']}", b["kab"],
                f"Butuh tgl {needed_date}", needed_date, b["phone"], norm_phone,
                json.dumps(attr), ts
            ),
        )

    conn.commit()
    print("[OK] Berhasil menyimpan penawaran petani dan order pembeli demo.")

    # 3. Jalankan Matchmaking & Pooling Engine
    print("[RUN] Menjalankan Matchmaking & Smart Pooling Engine...")
    stats = run_all_matches(conn, include_pending_high_score=True)
    print(f"[SELESAI] Hasil: {stats['matches_created']} match 1-ke-1 dan {stats['pools_created']} smart pool berhasil dihitung.")



if __name__ == "__main__":
    run()

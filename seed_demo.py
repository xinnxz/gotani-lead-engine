"""Seed script untuk mengisi data demo hackathon komprehensif (Fase 1 & Fase 2).

Menghasilkan skenario demo lengkap dan kaya data:
1. 25+ Data pasokan petani riil (supply) dengan kontak, lokasi kabupaten Jawa Timur,
   tanggal panen kalender, harga/kg, varietas (Madesta, Golden, Inthanon, Action 434, Sky Rocket, Cavendish).
2. Data postingan mentah bervariasi (bahasa daerah, slang petani, penawaran riil, dan postingan non-relevan).
3. Order pembeli riil (demand) dari Surabaya, Malang, Sidoarjo, Kediri, Gresik.
4. Memicu skenario Match 1-ke-1 Sempurna (Outreach Tier), Smart Pooling multi-petani, Review Tier, dan Ignored Tier.
5. Menjalankan engine matchmaking secara otomatis dan idempoten.
"""
import os
import sys
import json
from datetime import datetime, timedelta

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from agent.db import connect, now_iso
from agent.normalize import normalize_phone
from agent.match_runner import run_all_matches

CAMPAIGN_ID = "demo_melon_jatim"

# 20 Data Petani (Supply) dengan variasi lokasi Jawa Timur
FARMER_POSTS = [
    # 1. Match 1-ke-1 Ideal (Pak Budi Jombang - Madesta, 600kg, 7.500/kg)
    {
        "text": "Panen melon Madesta lusa, ada sekitar 600 kg. Buah mulus jaring rapat. Harga Rp 7.500/kg nego tipis. Area Jombang siap angkut di kebun. Hub WA 081234567890",
        "entity": "Pak Budi Santoso (Tani Makmur Jombang)",
        "product": "melon",
        "variety": "madesta",
        "vol": 600.0,
        "price": 7500.0,
        "kab": "Jombang",
        "phone": "081234567890",
        "days_ahead": 2,
    },
    # 2. Smart Pooling Candidate 1 (Pare Kediri - Golden, 400kg, 7.000/kg)
    {
        "text": "Bismillah, jual melon Golden 4 kuintal. Siap petik besok pagi. Lokasi Pare Kediri. Manis legit grade super. Minat hubungi 085712345678",
        "entity": "Pak Joko Widodo (Kelompok Tani Pare)",
        "product": "melon",
        "variety": "golden",
        "vol": 400.0,
        "price": 7000.0,
        "kab": "Kediri",
        "phone": "085712345678",
        "days_ahead": 1,
    },
    # 3. Smart Pooling Candidate 2 (Blitar - Golden, 350kg, 7.200/kg)
    {
        "text": "Ready melon Golden kualitas super, sisa panen 350 kg. Ambil langsung di kebun Minggirsari Blitar. WA 087888123456",
        "entity": "Bu Siti Aminah",
        "product": "melon",
        "variety": "golden",
        "vol": 350.0,
        "price": 7200.0,
        "kab": "Blitar",
        "phone": "087888123456",
        "days_ahead": 3,
    },
    # 4. Smart Pooling Candidate 3 (Tulungagung - Golden, 250kg, 7.100/kg)
    {
        "text": "Dijual melon Golden 2.5 kuintal, buah manis mulus tanpa cacat. Lokasi Tulungagung barat. Kontak WA 082199887766",
        "entity": "Pak Ahmad Subagyo",
        "product": "melon",
        "variety": "golden",
        "vol": 250.0,
        "price": 7100.0,
        "kab": "Tulungagung",
        "phone": "082199887766",
        "days_ahead": 2,
    },
    # 5. Greenhouse Premium (Nganjuk - Inthanon, 1.000kg, 8.000/kg)
    {
        "text": "Panen melon Inthanon super greenhouse 1 ton. Daging hijau renyah brix 14. Nganjuk kota. Harga 8rb/kg nego borongan. WA 089911223344",
        "entity": "Greenhouse Nganjuk Makmur",
        "product": "melon",
        "variety": "inthanon",
        "vol": 1000.0,
        "price": 8000.0,
        "kab": "Nganjuk",
        "phone": "089911223344",
        "days_ahead": 5,
    },
    # 6. Pasokan Mojokerto (Sky Rocket, 300kg, 5.000/kg)
    {
        "text": "Sky rocket sisa panen 300 kg di gudang Mojokerto. 5rb/kg borongan ambil semua lusa. Kontak 085566778899",
        "entity": "Cak Lontong Tani",
        "product": "melon",
        "variety": "sky rocket",
        "vol": 300.0,
        "price": 5000.0,
        "kab": "Mojokerto",
        "phone": "085566778899",
        "days_ahead": 1,
    },
    # 7. Pasokan Lamongan (Action 434, 800kg, 6.800/kg)
    {
        "text": "Panen raya melon Action 434 sekitar 800 kg. Kulit mulus jaring tebal. Babat Lamongan siap kirim. WA 081344556677",
        "entity": "Haji Mansur Lamongan",
        "product": "melon",
        "variety": "action 434",
        "vol": 800.0,
        "price": 6800.0,
        "kab": "Lamongan",
        "phone": "081344556677",
        "days_ahead": 4,
    },
    # 8. Pasokan Gresik (Madesta, 450kg, 7.800/kg)
    {
        "text": "Tebas melon madesta siap petik 450 kg. Lokasi Driyorejo Gresik dekat Surabaya. Harga 7800 per kilo. 081255667788",
        "entity": "Pak Slamet Driyorejo",
        "product": "melon",
        "variety": "madesta",
        "vol": 450.0,
        "price": 7800.0,
        "kab": "Gresik",
        "phone": "081255667788",
        "days_ahead": 3,
    },
    # 9. Pasokan Tuban (Madesta, 1.200kg, 7.000/kg)
    {
        "text": "Panen melon madesta 1.2 ton kebun Tuban pesisir. Manis segar grade AB campur. WA 087711224455",
        "entity": "Kelompok Tani Bumi Tuban",
        "product": "melon",
        "variety": "madesta",
        "vol": 1200.0,
        "price": 7000.0,
        "kab": "Tuban",
        "phone": "087711224455",
        "days_ahead": 6,
    },
    # 10. Pasokan Madiun (Golden, 500kg, 7.300/kg)
    {
        "text": "Melon golden aroma wangi 500 kg siap angkut akhir pekan. Madiun kota. Harga 7.300/kg net. Hubungi 085233445566",
        "entity": "Madiun Horti Farm",
        "product": "melon",
        "variety": "golden",
        "vol": 500.0,
        "price": 7300.0,
        "kab": "Madiun",
        "phone": "085233445566",
        "days_ahead": 4,
    },
    # 11. Pasokan Bojonegoro (Madesta, 700kg, 7.200/kg)
    {
        "text": "Siap panen melon madesta 7 kuintal Bojonegoro timur. Kualitas ekspor jaring rata. WA 081988776655",
        "entity": "Mas Wahyu Bojonegoro",
        "product": "melon",
        "variety": "madesta",
        "vol": 700.0,
        "price": 7200.0,
        "kab": "Bojonegoro",
        "phone": "081988776655",
        "days_ahead": 5,
    },
    # 12. Pasokan Pasuruan (Pisang Cavendish, 1.500kg, 6.500/kg)
    {
        "text": "Panen pisang cavendish 1.5 ton minggu depan. Pasuruan Pandaan. Sisir rapat mulus. WA 081122334455",
        "entity": "Kebun Pisang Pandaan",
        "product": "pisang",
        "variety": "cavendish",
        "vol": 1500.0,
        "price": 6500.0,
        "kab": "Pasuruan",
        "phone": "081122334455",
        "days_ahead": 7,
    },
    # 13. Pasokan Lumajang (Pisang Cavendish, 1.000kg, 6.200/kg)
    {
        "text": "Jual pisang cavendish siap tebang 1 ton dari kebun Lumajang lereng Semeru. 6.200/kg. Hub 082233445566",
        "entity": "CV Semeru Agro",
        "product": "pisang",
        "variety": "cavendish",
        "vol": 1000.0,
        "price": 6200.0,
        "kab": "Lumajang",
        "phone": "082233445566",
        "days_ahead": 5,
    },
    # 14. Pasokan Sidoarjo (Melon Madesta, 200kg, 8.200/kg)
    {
        "text": "Sisa panen melon madesta 200 kg Krian Sidoarjo. Buah segar baru petik tadi pagi. WA 083811223344",
        "entity": "Cak Huda Krian",
        "product": "melon",
        "variety": "madesta",
        "vol": 200.0,
        "price": 8200.0,
        "kab": "Sidoarjo",
        "phone": "083811223344",
        "days_ahead": 0,
    },
    # 15. Pasokan Kediri (Melon Action 434, 600kg, 6.900/kg)
    {
        "text": "Ready melon action 600 kg siap ambil di kebun Gurah Kediri. Harga 6.900 per kilo. Kontak 085611223344",
        "entity": "Tani Makmur Gurah",
        "product": "melon",
        "variety": "action 434",
        "vol": 600.0,
        "price": 6900.0,
        "kab": "Kediri",
        "phone": "085611223344",
        "days_ahead": 3,
    },
    # 16. Pasokan Jember (Semangka Merah, 2.000kg, 4.500/kg)
    {
        "text": "Panen semangka merah non biji 2 ton Ambulu Jember. Manis berair bobot 4-7 kg. WA 081266778899",
        "entity": "Pak Hendro Jember",
        "product": "semangka",
        "variety": "non biji",
        "vol": 2000.0,
        "price": 4500.0,
        "kab": "Jember",
        "phone": "081266778899",
        "days_ahead": 4,
    },
    # 17. Pasokan Banyuwangi (Semangka Kuning, 1.500kg, 5.000/kg)
    {
        "text": "Panen semangka kuning super 1.5 ton Rogojampi Banyuwangi. Siap kirim Jawa Bali. Hub 087799881122",
        "entity": "Banyuwangi Fresh Farm",
        "product": "semangka",
        "variety": "kuning",
        "vol": 1500.0,
        "price": 5000.0,
        "kab": "Banyuwangi",
        "phone": "087799881122",
        "days_ahead": 6,
    },
    # 18. Pasokan Malang (Cabai Rawit Merah, 300kg, 28.000/kg)
    {
        "text": "Petik cabai rawit merah ori 3 kuintal Pujon Malang. Pedas segar petik subuh. WA 089511223344",
        "entity": "Petani Pujon Sejahtera",
        "product": "cabai",
        "variety": "rawit merah",
        "vol": 300.0,
        "price": 28000.0,
        "kab": "Malang",
        "phone": "089511223344",
        "days_ahead": 1,
    },
    # 19. Pasokan Probolinggo (Bawang Merah, 1.000kg, 22.000/kg)
    {
        "text": "Bawang merah super Probolinggo Dringu 1 ton kering simpan. Kualitas ekspor. Kontak 081377889900",
        "entity": "Haji Hasan Dringu",
        "product": "bawang merah",
        "variety": "super",
        "vol": 1000.0,
        "price": 22000.0,
        "kab": "Probolinggo",
        "phone": "081377889900",
        "days_ahead": 5,
    },
    # 20. Pasokan Kediri (Melon Madesta, 350kg, 7.600/kg)
    {
        "text": "Panen melon madesta 350 kg Plosoklaten Kediri. Net mulus brix 12 up. Hubungi WA 085811223344",
        "entity": "Cak Yanto Plosoklaten",
        "product": "melon",
        "variety": "madesta",
        "vol": 350.0,
        "price": 7600.0,
        "kab": "Kediri",
        "phone": "085811223344",
        "days_ahead": 2,
    },
]

# Postingan Mentah Tambahan untuk Tab 3 (Raw Data Log) termasuk non-relevan / spam yang disaring sistem
ADDITIONAL_RAW_SCRAPED = [
    {
        "text": "Info jual bibit melon madesta F1 unggul polybag siap tanam murah meriah per pohon 2500 wa 081299881122",
        "author": "Toko Bibit Tani Makmur",
        "platform": "facebook",
    },
    {
        "text": "Dibutuhkan tenaga kerja petik buah melon harian di kebun Nganjuk makan siang gratis hub pak tono 085699887766",
        "author": "Loker Pertanian Jatim",
        "platform": "facebook",
    },
    {
        "text": "Pupuk organik cair booster pelebat buah melon dan semangka dijamin panen melimpah pesan sekarang wa 087766554433",
        "author": "Agro Kimia Nusantara",
        "platform": "facebook",
    },
    {
        "text": "Resep es kuwut melon segar untuk menu buka puasa bersama keluarga",
        "author": "Kumpulan Resep Bunda",
        "platform": "facebook",
    },
    {
        "text": "Sewa truk engkel dan pick up grand max carter muatan hasil panen sayur buah rute jatim jabar wa 081355443322",
        "author": "Ekspedisi Angkutan Hasil Bumi",
        "platform": "facebook",
    },
    {
        "text": "Melon golden aroma manis renyah panen segar di kebun pare kediri monggo merapat",
        "author": "Komunitas Petani Kediri",
        "platform": "facebook",
    },
    {
        "text": "Update harga buah melon pasar keputran surabaya pagi ini stabil permintaan tinggi",
        "author": "Info Pasar Induk Jatim",
        "platform": "facebook",
    },
]

# 5 Kebutuhan Pembeli Nyata (Demand)
BUYER_ORDERS = [
    # 1. Memicu MATCH 1-KE-1 SEMPURNA (Pak Budi Jombang -> Surabaya ~65 km)
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
    # 4. Kebutuhan Melon Premium Supermarket (Sidoarjo / Surabaya)
    {
        "name": "Supermarket Buah Citra Sidoarjo",
        "product": "melon",
        "variety": "inthanon",
        "vol": 600.0,
        "max_price": 10500.0,
        "kab": "Sidoarjo",
        "phone": "081288887777",
        "days_ahead": 7,
    },
    # 5. Kebutuhan Agregasi Gresik / Lamongan (Action 434, 1.200 kg)
    {
        "name": "Katering Berkah Bersama Gresik",
        "product": "melon",
        "variety": "action 434",
        "vol": 1200.0,
        "max_price": 8200.0,
        "kab": "Gresik",
        "phone": "081399991111",
        "days_ahead": 5,
    },
]


def run():
    print("[INFO] Memulai seed_demo.py (Fase 1 & Fase 2 Komprehensif)...")
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
               VALUES (?, 'facebook', ?, ?, ?, ?, 1)""",
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

    # 2. Masukkan Postingan Mentah Tambahan (Memperkaya Tab 3 Raw Log)
    for idx, raw_extra in enumerate(ADDITIONAL_RAW_SCRAPED):
        ts = now_iso()
        conn.execute(
            """INSERT INTO raw_items (campaign_id, platform, raw_text, content_hash, fetched_at, author_name, processed)
               VALUES (?, ?, ?, ?, ?, ?, 1)""",
            (CAMPAIGN_ID, raw_extra["platform"], raw_extra["text"], f"hash_extra_{idx}", ts, raw_extra["author"]),
        )

    # 3. Masukkan Kebutuhan Pembeli (Demand)
    for b in BUYER_ORDERS:
        ts = now_iso()
        needed_date = (now_dt + timedelta(days=b["days_ahead"])).date().isoformat()
        norm_phone = normalize_phone(b["phone"])

        cur_raw = conn.execute(
            """INSERT INTO raw_items (campaign_id, platform, raw_text, content_hash, fetched_at, author_name, processed)
               VALUES ('manual_demand', 'manual_order', ?, ?, ?, ?, 1)""",
            (f"Order: {b['name']} butuh {b['product']} {b['vol']}kg di {b['kab']}", f"hash_buyer_{b['phone']}", ts, b["name"]),
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
    print("[OK] Berhasil menyimpan data prospek petani, raw items tambahan, dan order pembeli demo.")

    # 4. Jalankan Matchmaking & Pooling Engine
    print("[RUN] Menjalankan Matchmaking & Smart Pooling Engine...")
    stats = run_all_matches(conn, include_pending_high_score=True)
    print(f"[SELESAI] Hasil: {stats['matches_created']} match 1-ke-1 dan {stats['pools_created']} smart pool berhasil dihitung.")


if __name__ == "__main__":
    run()

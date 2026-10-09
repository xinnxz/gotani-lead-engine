import os
import sys
import json
import re

# Tambahkan root directory ke sys.path supaya module agent bisa diimport
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from agent.db import connect, save_raw_item

CAMPAIGN_ID = "demo_melon_jatim"

# 25 Postingan Demo yang realistis
POSTS = [
    # 1. Supply, Golden, Kediri, kw, WA
    "Bismillah, jual melon Golden 2 kuintal. Panen hari Senin. Lokasi Kediri. Minat hubungi 081234567890",
    # 2. Supply, Hikapel, Blitar, ton, WA
    "Ready melon Hikapel grade super, stok 5 ton. Ambil langsung di kebun Blitar. WA 085712345678",
    # 3. Demand, Jombang - Mojokerto, ton, WA
    "Cari melon 10 ton untuk ekspor, butuh grade A. Area Jombang - Mojokerto. Hub 087888123456",
    # 4. Irrelevant
    "Jual pupuk NPK murah meriah free ongkir",
    # 5. Supply, Inthanon, Kediri, kw, no WA (japri)
    "Dijual melon inthanon 3 kw, harga 4rb/kg. Lokasi kec. Pare Kediri. Japri ya",
    # 6. Demand, Surabaya, no WA? (rutin) The example has WA
    "Butuh supplier melon untuk supermarket Surabaya, rutin mingguan. 082199887766",
    # 7. Supply, Madesta, Nganjuk, kw
    "Panen melon Madesta besok pagi, ada sekitar 5 kuintal. Harga borongan Rp 5.000/kg. Area Nganjuk, minat DM.",
    # 8. Supply, Sky Rocket, Pasuruan, ton
    "Jual melon Sky Rocket 2 ton, buah mulus net tebal. Lokasi Pandaan Pasuruan. WA 089911223344",
    # 9. Supply, Apollo, Malang, kg
    "Ready melon Apollo manis, ada 500 kg aja. Yg mau ecer atau borong merapat ke Malang kota. 6rb/kg.",
    # 10. Irrelevant
    "Sedia bibit cabe rawit unggul, siap tanam, lokasi Madiun.",
    # 11. Supply, Golden, Tuban, ton, no WA
    "Golden melon siap panen minggu depan, perkiraan 3 ton. Tuban. Inbox untuk nego harga.",
    # 12. Supply, Hikapel, Lamongan, kw
    "Hikapel 8 kw, harga 7rb per kg ambil di tempat. Lamongan. Hub 085566778899",
    # 13. Demand, Malang, kg, no WA
    "Info dong yang punya melon Inthanon area Malang, butuh 200 kg untuk acara nikahan. PM ya.",
    # 14. Supply, Inthanon, Kediri, ton
    "Inthanon super, 1 ton lebih sedikit. Harga 8rb nego tipis. Kediri kota. WA 081122334455",
    # 15. Supply, Sky Rocket, Jombang, kg
    "Jual cepat melon Sky rocket sisa panen 300 kg. 3rb/kg bawa semua. Jombang. 088899990000",
    # 16. Irrelevant
    "Jasa ekspedisi truk bak terbuka, rute Surabaya - Jakarta tiap hari. WA 081211112222",
    # 17. Supply, Madesta, Mojokerto, kw
    "Melon Madesta daging tebal manis, 15 kuintal. Lokasi Mojokerto. Harga 5500. Japri.",
    # 18. Supply, Apollo, Blitar, kw
    "Apollo ready 10 kuintal, buah ukuran sedang. Blitar, WA 085600001111",
    # 19. Supply, Golden, Nganjuk, ton
    "Golden ekslusif, 4 ton siap angkut. Nganjuk selatan. 7500/kg. 081333334444",
    # 20. Supply, Hikapel, Surabaya, kg
    "Hikapel sisa 100 kg di gudang Surabaya. 6000 per kg. Minat inbox.",
    # 21. Demand, Kediri, ton
    "Cari melon jenis apa saja buat pabrik, butuh 20 ton/minggu. Kirim penawaran ke 081255556666. Lokasi Kediri.",
    # 22. Irrelevant
    "Jual mulsa plastik ukuran 120cm, stok banyak. Murah aja.",
    # 23. Supply, Sky Rocket, Tuban, kw
    "Sky rocket 6 kw, 4000/kg borongan. Tuban kota. WA 087711223344",
    # 24. Supply, Madesta, Pasuruan, ton
    "Madesta panen raya, 5 ton siap kirim se-Jatim. Pasuruan. 089988887777",
    # 25. Supply, Inthanon, Malang, kw
    "Jual inthanon 2 kuintal, 7rb aja. Malang kab. Japri."
]

def extract_listing(raw_item):
    """
    Simulasi rule-based extraction sederhana untuk data demo.
    Skor dibuat bervariasi agar tampilan dashboard lebih realistis.
    """
    text = raw_item['raw_text'].lower()
    
    # 1. Tentukan intent
    if any(kw in text for kw in ["cari", "butuh", "info dong"]):
        intent = "demand"
    elif any(kw in text for kw in ["jual", "ready", "panen", "sedia", "sisa", "dijual"]):
        intent = "supply"
    else:
        intent = "unknown"
        
    # 2. Filter irrelevant
    if any(kw in text for kw in ["pupuk", "bibit", "ekspedisi", "mulsa"]):
        return None
        
    # 3. Ekstrak No Telepon (WA)
    phone_match = re.search(r'(08[0-9]{8,11})', text)
    contact_phone = phone_match.group(1) if phone_match else None
    
    # 4. Ekstrak Volume ke KG
    volume_kg = None
    if "ton" in text:
        v_match = re.search(r'([0-9\.]+)\s*ton', text)
        if v_match:
            volume_kg = float(v_match.group(1)) * 1000
    elif "kuintal" in text or "kw" in text:
        v_match = re.search(r'([0-9\.]+)\s*(kuintal|kw)', text)
        if v_match:
            volume_kg = float(v_match.group(1)) * 100
    elif "kg" in text:
        v_match = re.search(r'([0-9\.]+)\s*kg', text)
        if v_match:
            volume_kg = float(v_match.group(1))

    # 5. Ekstrak Lokasi Kabupaten
    kabupaten = None
    locations = [
        "kediri", "blitar", "jombang", "mojokerto", "nganjuk", 
        "pasuruan", "malang", "surabaya", "lamongan", "tuban"
    ]
    for loc in locations:
        if loc in text:
            kabupaten = loc.capitalize()
            break

    # 6. Ekstrak Harga per kg
    price_per_kg = None
    price_match = re.search(r'(\d+)\s*(?:rb|ribu)', text)
    if price_match:
        price_per_kg = int(price_match.group(1)) * 1000
    else:
        price_match = re.search(r'(?:rp\.?\s*)?(\d[\d\.]*)\s*/?\s*kg', text)
        if price_match:
            price_per_kg = float(price_match.group(1).replace('.', ''))

    # 7. Ekstrak Produk / Varietas
    product = "Melon"
    varieties = ["golden", "hikapel", "inthanon", "madesta", "sky rocket", "apollo"]
    for var in varieties:
        if var in text:
            product = f"Melon {var.title()}"
            break
    
    # 8. Hitung skor realistis (bervariasi)
    rel_score = 35  # produk cocok (melon)
    rel_why = ["+35 produk cocok (melon)"]
    
    if intent == "supply":
        rel_score += 25
        rel_why.append("+25 niat sesuai (supply)")
    elif intent == "demand":
        rel_score += 25
        rel_why.append("+25 niat sesuai (demand)")

    if kabupaten:
        rel_score += 20
        rel_why.append(f"+20 lokasi di target ({kabupaten})")
    else:
        rel_score += 8
        rel_why.append("+8 lokasi tidak disebut")
    
    if volume_kg and volume_kg >= 500:
        rel_score += 10
        rel_why.append(f"+10 volume {volume_kg:g} kg ≥ minimal")
    elif volume_kg:
        rel_score += 5
        rel_why.append(f"+5 volume {volume_kg:g} kg (di bawah minimal)")
    else:
        rel_score += 5
        rel_why.append("+5 volume tidak disebut")

    rel_score += 10
    rel_why.append("+10 tidak ada syarat varietas")

    # Confidence
    conf_score = 30  # post baru (demo)
    conf_why = ["+30 post baru (demo data)"]

    if contact_phone:
        conf_score += 25
        conf_why.append("+25 ada kontak langsung (WA/telepon)")
    else:
        conf_score += 0
        conf_why.append("+0 tidak ada jalur kontak langsung")

    conf_score += 25
    conf_why.append("+25 akun aktif (demo)")
    
    conf_score += 10
    conf_why.append("+10 angka wajar, tidak ada pola spam")
    
    location_text = f"Kab. {kabupaten}" if kabupaten else None

    listing = {
        "campaign_id": raw_item["campaign_id"],
        "raw_item_id": raw_item["id"],
        "intent": intent,
        "product": product,
        "volume_kg": volume_kg,
        "price_per_kg": price_per_kg,
        "location_text": location_text,
        "kabupaten": kabupaten,
        "provinsi": "Jawa Timur",
        "contact_phone": contact_phone,
        "extractor": "rules",
        "relevance": min(rel_score, 100),
        "confidence": min(conf_score, 100),
        "score_reasons_json": json.dumps({"relevance": rel_why, "confidence": conf_why}, ensure_ascii=False),
        "review_status": "pending"
    }
    
    return listing

def run():
    print("Memulai seed_demo.py ...")
    conn = connect()
    
    # 1. Simpan raw_items ke database
    saved_count = 0
    for post in POSTS:
        # Menggunakan modul DB save_raw_item
        saved = save_raw_item(
            conn=conn,
            campaign_id=CAMPAIGN_ID,
            platform="demo",
            raw_text=post,
            author_name="Demo User"
        )
        if saved:
            saved_count += 1
            
    print(f"Berhasil menyimpan {saved_count} raw_items baru (Total post di script: {len(POSTS)}).")
    
    # 2. Ambil raw items yang belum diproses untuk campaign demo_melon_jatim
    cur = conn.execute(
        "SELECT * FROM raw_items WHERE campaign_id = ? AND processed = 0",
        (CAMPAIGN_ID,)
    )
    raw_items = [dict(row) for row in cur.fetchall()]
    
    # 3. Lakukan proses ekstraksi (pipeline offline rules-based)
    listings_count = 0
    for raw in raw_items:
        listing = extract_listing(raw)
        
        # update status processed raw_item agar tidak diproses berulang
        conn.execute("UPDATE raw_items SET processed = 1 WHERE id = ?", (raw["id"],))
        
        if listing and listing["intent"] in ["supply", "demand"]:
            # Insert ke tabel listings
            conn.execute(
                '''INSERT INTO listings (
                    campaign_id, raw_item_id, intent, product, volume_kg, 
                    price_per_kg, location_text, kabupaten, provinsi,
                    contact_phone, extractor, relevance, confidence, 
                    score_reasons_json, review_status, created_at
                ) VALUES (
                    :campaign_id, :raw_item_id, :intent, :product, :volume_kg,
                    :price_per_kg, :location_text, :kabupaten, :provinsi,
                    :contact_phone, :extractor, :relevance, :confidence, 
                    :score_reasons_json, :review_status, datetime('now')
                )''',
                listing
            )
            listings_count += 1
            
    conn.commit()
    print(f"Berhasil mengekstrak dan menyimpan {listings_count} listings ke database.")
    print("Selesai.")

if __name__ == "__main__":
    run()

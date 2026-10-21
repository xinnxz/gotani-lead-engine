import asyncio
import logging
from datetime import datetime

from . import db
from .config import settings
from .campaign import CampaignSpec
from .planner import build_group_queries
from .executors.fb import FacebookExecutor
from .executors.gmaps import GoogleMapsExecutor
from .masking import mask_text
from .rules import extract as rules_extract
from .extraction import llm_extract
from .llm_gateway import LLMGateway
from .normalize import to_kg, normalize_phone, parse_available
from .scoring import relevance, confidence, region_from
from .dedup import find_duplicate, deduplicate_database

logger = logging.getLogger(__name__)

def _split_merged_snippets(text: str) -> list[str]:
    """Deteksi & pecah teks yang berisi >1 postingan Facebook gabungan dari Google.

    Google Search kadang menggabungkan 2-3 snippet Facebook berbeda dalam
    satu hasil pencarian. Tanda-tanda gabungan:
    - Ada pola "... NamaAuthor · Tanggal" di tengah teks (awal post baru)
    - Ada pemisah "..." yang menunjukkan potongan snippet berbeda

    Jika terdeteksi gabungan, kita pecah menjadi beberapa post terpisah.
    Jika tidak, kembalikan list berisi 1 elemen (teks asli).
    """
    if not text or len(text) < 50:
        return [text]

    # Pola separator yang menunjukkan batas antar-snippet
    # Contoh: "...\nJual semangka kuning" atau "... Nandhini ..."
    separators = [
        r"\.\.\.[\s\n]+(?=[A-Z])",  # "..." diikuti kalimat baru
        r"(?<=\.)\s*(?:Jual|Ready|Bismillah|Assalamualaikum|Dijual|Open|Butuh|Cari)\b",  # Kata pembuka post baru
    ]

    # Cari posisi split
    split_positions = set()
    for sep in separators:
        for m in re.finditer(sep, text):
            pos = m.start()
            # Hanya split jika posisi cukup jauh dari awal (minimal 40 char)
            # dan masih cukup teks setelahnya (minimal 40 char)
            if pos > 40 and len(text) - pos > 40:
                split_positions.add(pos)

    if not split_positions:
        return [text]

    # Split teks di posisi-posisi yang ditemukan
    positions = sorted(split_positions)
    parts = []
    prev = 0
    for pos in positions:
        chunk = text[prev:pos].strip()
        if len(chunk) >= 30:  # Minimal 30 char agar bermakna
            parts.append(chunk)
        prev = pos
    # Tambah sisa teks
    last = text[prev:].strip()
    if len(last) >= 30:
        parts.append(last)

    return parts if parts else [text]




class Pipeline:
    def __init__(self, campaign: CampaignSpec, progress_callback = None):
        self.campaign = campaign
        self.conn = db.connect()
        self.fb_executor = FacebookExecutor()
        self.gmaps_executor = GoogleMapsExecutor()
        self.llm = LLMGateway(self.conn)
        self.progress_callback = progress_callback

    async def run(self):
        logger.info(f"Mulai pipeline untuk campaign: {self.campaign.campaign_id}")
        run_id = db.start_run(self.conn, self.campaign.campaign_id, "scrape_fb", platform="facebook")
        
        try:
            # 1. Rencanakan query pencarian
            query_objs = build_group_queries(self.campaign)
            queries = [q["query"] for q in query_objs]
            logger.info(f"Dihasilkan {len(queries)} query: {queries}")
            if self.progress_callback:
                self.progress_callback(
                    "Perencanaan Kata Kunci",
                    f"Menghasilkan {len(queries)} query pencarian multi-kanal (Google Maps, Facebook, Web B2B) untuk komoditas '{self.campaign.product.name}'."
                )
            
            raw_items_saved = 0
            
            # 2. Eksekusi scraping — route berdasarkan tujuan kampanye
            if self.campaign.target_intent == "demand":
                # DEMAND: Cari bisnis pembeli potensial di Google Maps (bukan Facebook)
                logger.info("Kampanye DEMAND: menggunakan Google Maps executor")
                if self.progress_callback:
                    self.progress_callback(
                        "Google Maps Scraper",
                        f"Mencari bisnis pembeli potensial (toko, distributor, grosir) untuk '{self.campaign.product.name}' di Google Maps..."
                    )
                posts = await self.gmaps_executor.scrape_demand(
                    product=self.campaign.product.name,
                    locations=self.campaign.location.include,
                    max_results=50,
                    progress_callback=self.progress_callback,
                )
            else:
                # SUPPLY: Cari petani/penjual di Facebook & web (default)
                queries_to_run = queries[:15]
                posts = await self.fb_executor.scrape_queries(
                    queries_to_run,
                    max_posts=50,
                    progress_callback=self.progress_callback,
                    target_intent=self.campaign.target_intent,
                )
            
            # 3. Simpan ke database raw_items
            if self.progress_callback:
                self.progress_callback(
                    "Penyimpanan Raw Data",
                    f"Menyimpan {len(posts)} postingan ke database lokal..."
                )
            for p in posts:
                saved = db.save_raw_item(
                    self.conn,
                    self.campaign.campaign_id,
                    platform=p.get("platform", "facebook"),
                    raw_text=p["raw_text"],
                    url=p["url"],
                    posted_at=p.get("posted_at"),
                    run_id=run_id
                )
                if saved:
                    raw_items_saved += 1
            
            db.finish_run(self.conn, run_id, status="success", items=raw_items_saved)
            logger.info(f"Berhasil scrape FB. Item baru tersimpan: {raw_items_saved}")
            if self.progress_callback:
                self.progress_callback(
                    "Sinkronisasi Raw Data",
                    f"Total {raw_items_saved} postingan unik berhasil ditambahkan ke database (duplikasi diabaikan)."
                )
            
            # 4. Ambil raw_items yang belum diproses (belum masuk listings)
            cur = self.conn.execute(
                "SELECT id, raw_text, platform, url, fetched_at, posted_at FROM raw_items WHERE campaign_id=? AND id NOT IN (SELECT raw_item_id FROM listings)",
                (self.campaign.campaign_id,)
            )
            unprocessed = cur.fetchall()
            
            if not unprocessed:
                logger.info("Tidak ada raw_items baru untuk diproses.")
                if self.progress_callback:
                    self.progress_callback("Ekstraksi AI", "Tidak ada postingan baru yang perlu diekstrak.")
                return

            total_unprocessed = len(unprocessed)
            batch_size = 5
            total_batches = (total_unprocessed + batch_size - 1) // batch_size
            logger.info(f"Memproses {total_unprocessed} item untuk diekstrak dalam {total_batches} batch...")
            
            new_leads_saved = 0
            
            # Batasi batch LLM agar hemat biaya
            for i in range(0, total_unprocessed, batch_size):
                batch = unprocessed[i:i+batch_size]
                batch_num = (i // batch_size) + 1
                
                if self.progress_callback:
                    self.progress_callback(
                        f"Ekstraksi AI (Batch {batch_num}/{total_batches})",
                        f"Memproses {len(batch)} data postingan: mengekstrak entitas, komoditas, volume (kg), harga, kontak telepon, dan lokasi..."
                    )
                
                raw_texts = [row["raw_text"] for row in batch]
                
                # 5. Masking PII
                masked_data = [mask_text(text) for text in raw_texts]
                masked_texts = [d[0] for d in masked_data]
                pii_mappings = [d[1] for d in masked_data]
                
                # 6. Ekstraksi dengan LLM
                if self.llm.available:
                    try:
                        extracted_results = llm_extract(self.llm, self.campaign, masked_texts)
                        for r in extracted_results:
                            if r: r["extractor"] = "llm"
                    except Exception as e:
                        logger.error(f"LLM gagal, fallback ke rules: {e}")
                        extracted_results = [rules_extract(t, self.campaign) for t in masked_texts]
                        for r in extracted_results:
                            if r: r["extractor"] = "rules"
                else:
                    logger.info("LLM tidak tersedia, menggunakan ekstraktor offline (rules).")
                    extracted_results = [rules_extract(t, self.campaign) for t in masked_texts]
                    for r in extracted_results:
                        if r: r["extractor"] = "rules"
                
                # 7. Normalisasi, Scoring & Simpan
                for j, result in enumerate(extracted_results):
                    if not result:
                        # PENTING: Jika LLM mengosongkan hasil (karena data sampah),
                        # kita TETAP harus menyimpannya ke database agar tidak diulang-ulang (hemat token).
                        result = {"intent": "other", "extractor": "llm_rejected"}
                    
                    # VALIDASI KERAS: Cek apakah komoditas target ADA di raw_text
                    # Jika tidak ada, PAKSA intent="irrelevant" agar tidak mencemari hasil
                    import re as _re_val
                    _raw_low = raw_texts[j].lower()
                    _product_terms = [t.lower() for t in self.campaign.product_terms()]
                    _product_found_in_text = any(
                        _re_val.search(rf"\b{_re_val.escape(t)}\b", _raw_low) for t in _product_terms
                    )
                    if not _product_found_in_text and result.get("intent") != "demand":
                        # Komoditas TIDAK ditemukan di teks -> data tidak relevan
                        result["intent"] = "irrelevant"
                        result["product"] = result.get("product") or "tidak_relevan"
                        result.setdefault("flags", [])
                        if isinstance(result.get("flags"), list):
                            result["flags"].append("komoditas_tidak_ditemukan_di_teks")

                    # VALIDASI NEGARA: Deteksi konten Malaysia (bukan Indonesia)
                    from .scoring import _is_malaysian_content
                    if _is_malaysian_content(_raw_low):
                        result["intent"] = "irrelevant"
                        result.setdefault("flags", [])
                        if isinstance(result.get("flags"), list):
                            result["flags"].append("konten_malaysia_bukan_indonesia")
                        
                    row = dict(batch[j])
                    mapping = pii_mappings[j]
                    raw_text = raw_texts[j]

                    # Injeksi data terstruktur dari Google Maps (jika ada)
                    gmaps_data = None
                    for p in posts:
                        if p.get("raw_text", "").strip() == raw_text.strip() and p.get("_gmaps_data"):
                            gmaps_data = p["_gmaps_data"]
                            break
                    if gmaps_data:
                        result.setdefault("entity_name", gmaps_data.get("business_name"))
                        result.setdefault("intent", "demand")
                        # Nomor telepon dari Google Maps akan diinjeksi
                        # SETELAH PII restore (lihat blok di bawah)
                        if not result.get("location_text") and gmaps_data.get("address"):
                            result["location_text"] = gmaps_data["address"]
                        result["_gmaps_meta"] = {
                            "rating": gmaps_data.get("rating"),
                            "reviews": gmaps_data.get("reviews_count"),
                            "category": gmaps_data.get("category"),
                            "website": gmaps_data.get("website"),
                        }
                    
                    # Normalisasi angka
                    price = result.get("price_value")
                    price_unit = result.get("price_unit")
                    unit_in_kg = to_kg(1.0, price_unit)
                    # Jika unit standar (kg, ton, kuintal), konversi ke /kg
                    # Jika unit non-standar (kresek, ikat, dll), price_per_kg = None (jujur)
                    price_kg = (float(price) / unit_in_kg) if price and unit_in_kg else None
                    
                    vol = result.get("volume_value")
                    vol_unit = result.get("volume_unit")
                    vol_kg = to_kg(float(vol), vol_unit) if vol else None
                    
                    result["price_per_kg"] = price_kg
                    result["volume_kg"] = vol_kg
                    
                    # Wilayah
                    loc_text = result.get("location_text")
                    region = region_from(loc_text)
                    if region:
                        result["kabupaten"] = region["nama"]
                        result["provinsi"] = region["provinsi"]
                        result["kode_wilayah"] = region["kode"]
                    
                    # Tanggal ketersediaan/panen kalender
                    avail_phrase, avail_date = parse_available(
                        result.get("available_text") or raw_text,
                        posted_at=row.get("posted_at") or row.get("fetched_at")
                    )
                    result["available_text"] = avail_phrase or result.get("available_text")
                    result["available_date"] = avail_date

                    # Restore PII untuk kontak
                    phones = [val for key, val in mapping.items() if "PHONE" in key]
                    
                    # Jika tidak ada phone dari PII, coba dari Google Maps data
                    if not phones and gmaps_data and gmaps_data.get("phone"):
                        phones = [gmaps_data["phone"]]
                    
                    contact_phone = None
                    contact_wa = None
                    if phones:
                        contact_phone = ", ".join(phones)
                        contact_wa = normalize_phone(phones[0])
                    result["contact_phone"] = contact_phone
                    result["contact_wa"] = contact_wa
                    
                    # Deteksi Duplikasi (PRD F3.5)
                    dup_of, dup_why = find_duplicate(
                        self.conn,
                        product=result.get("product"),
                        kabupaten=result.get("kabupaten"),
                        contact_phone=contact_phone,
                        source_url=row.get("url") if "url" in row.keys() else None,
                        entity_name=result.get("entity_name")
                    )
                    
                    # 8. Scoring
                    result["posted_at"] = row.get("posted_at")
                    rel_score, rel_why = relevance(result, self.campaign, raw_text)
                    conf_score, conf_why = confidence(result, self.campaign, row["platform"], 1)
                    if dup_of:
                        conf_score = 0
                        rel_score = 0
                        conf_why.append(f"Duplikat dari listing #{dup_of} ({dup_why})")
                    
                    # 9. Simpan ke database listings
                    safe_intent = result.get("intent")
                    if not safe_intent:
                        safe_intent = "other"
                        
                    self.conn.execute(
                        """INSERT INTO listings (
                            raw_item_id, campaign_id, intent, entity_name,
                            product, volume_kg, volume_unit, price_per_kg, price_unit, location_text,
                            kabupaten, provinsi, available_text, available_date,
                            contact_phone, contact_wa, duplicate_of,
                            attributes_json, evidence_json, flags_json, relevance, 
                            confidence, score_reasons_json, extractor, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            row["id"], self.campaign.campaign_id, safe_intent, result.get("entity_name"),
                            result.get("product"), vol_kg, result.get("volume_unit"), price_kg, result.get("price_unit"), loc_text,
                            result.get("kabupaten"), result.get("provinsi"), result.get("available_text"),
                            avail_date, contact_phone, contact_wa, dup_of,
                            db.dumps(result), db.dumps(result.get("evidence", {})),
                            db.dumps(result.get("flags", [])), rel_score, conf_score, 
                            db.dumps({"relevance": rel_why, "confidence": conf_why, "dup": dup_why}), 
                            result.get("extractor", "llm"), db.now_iso()
                        )
                    )
                    # Tandai raw item telah selesai diproses
                    self.conn.execute("UPDATE raw_items SET processed = 1 WHERE id = ?", (row["id"],))
                    if not dup_of:
                        new_leads_saved += 1
                self.conn.commit()
                logger.info(f"Batch {batch_num} selesai diproses.")

            # Jalankan deduplikasi database menyeluruh
            dedup_res = deduplicate_database(self.conn)
            if dedup_res.get("duplicates_marked", 0) > 0:
                logger.info(f"Deduplikasi otomatis: {dedup_res['duplicates_marked']} entri duplikat ditandai.")

            # Jalankan matchmaking otomatis agar pasangan langsung sinkron jika ada demand & supply
            try:
                from .match_runner import run_all_matches
                m_stats = run_all_matches(self.conn)
                extra_m = ""
                if m_stats["matches_created"] > 0 or m_stats["pools_created"] > 0:
                    extra_m = f" Terbentuk {m_stats['matches_created']} match tunggal dan {m_stats['pools_created']} smart pool."
            except Exception as me:
                logger.warning(f"Gagal sinkronisasi matchmaking otomatis: {me}")
                extra_m = ""

            if self.progress_callback:
                self.progress_callback(
                    "Pipeline Selesai",
                    f"Sukses! {raw_items_saved} raw items disimpan ke database, dan {new_leads_saved} prospek terverifikasi unik berhasil diproses AI.{extra_m}"
                )

            return {
                "raw_items_saved": raw_items_saved,
                "new_leads_saved": new_leads_saved,
            }

        except Exception as e:
            logger.exception("Error pada pipeline.")
            db.finish_run(self.conn, run_id, status="error", error=str(e))
            if self.progress_callback:
                self.progress_callback("Kesalahan Eksekusi", f"Terjadi kesalahan: {e}")
            raise

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # Test pipeline with dummy campaign
    c = CampaignSpec(campaign_id="test_malang", goal="find_supply")
    c.product.name = "gabah"
    c.location.include = ["Malang"]
    pipe = Pipeline(c)
    asyncio.run(pipe.run())

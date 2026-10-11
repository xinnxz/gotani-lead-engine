import asyncio
import logging
from datetime import datetime

from . import db
from .config import settings
from .campaign import CampaignSpec
from .planner import build_group_queries
from .executors.fb import FacebookExecutor
from .masking import mask_text
from .rules import extract as rules_extract
from .extraction import llm_extract
from .llm_gateway import LLMGateway
from .normalize import to_kg, normalize_phone, parse_available
from .scoring import relevance, confidence, region_from
from .dedup import find_duplicate

logger = logging.getLogger(__name__)

class Pipeline:
    def __init__(self, campaign: CampaignSpec):
        self.campaign = campaign
        self.conn = db.connect()
        self.fb_executor = FacebookExecutor()
        self.llm = LLMGateway(self.conn)

    async def run(self):
        logger.info(f"Mulai pipeline untuk campaign: {self.campaign.campaign_id}")
        run_id = db.start_run(self.conn, self.campaign.campaign_id, "scrape_fb", platform="facebook")
        
        try:
            # 1. Rencanakan query pencarian
            query_objs = build_group_queries(self.campaign)
            queries = [q["query"] for q in query_objs]
            logger.info(f"Dihasilkan {len(queries)} query: {queries}")
            
            raw_items_saved = 0
            
            # 2. Eksekusi scraping untuk setiap query sekaligus (Tingkatkan kapasitas data)
            queries_to_run = queries[:15]
            posts = await self.fb_executor.scrape_queries(queries_to_run, max_posts=50)
            
            # 3. Simpan ke database raw_items
            for p in posts:
                saved = db.save_raw_item(
                    self.conn,
                    self.campaign.campaign_id,
                    platform="facebook",
                    raw_text=p["raw_text"],
                    url=p["url"],
                    run_id=run_id
                )
                if saved:
                    raw_items_saved += 1
            
            db.finish_run(self.conn, run_id, status="success", items=raw_items_saved)
            logger.info(f"Berhasil scrape FB. Item baru tersimpan: {raw_items_saved}")
            
            # 4. Ambil raw_items yang belum diproses (belum masuk listings)
            cur = self.conn.execute(
                "SELECT id, raw_text, platform FROM raw_items WHERE campaign_id=? AND id NOT IN (SELECT raw_item_id FROM listings)",
                (self.campaign.campaign_id,)
            )
            unprocessed = cur.fetchall()
            
            if not unprocessed:
                logger.info("Tidak ada raw_items baru untuk diproses.")
                return

            logger.info(f"Memproses {len(unprocessed)} item untuk diekstrak...")
            
            # Batasi batch LLM agar hemat biaya
            batch_size = 5
            for i in range(0, len(unprocessed), batch_size):
                batch = unprocessed[i:i+batch_size]
                
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
                        
                    row = batch[j]
                    mapping = pii_mappings[j]
                    raw_text = raw_texts[j]
                    
                    # Normalisasi angka
                    price = result.get("price_value")
                    price_unit = result.get("price_unit")
                    # price adalah harga per satuan unit. 
                    # Untuk mencari price per kg: price_per_kg = price / (berat 1 unit dalam kg)
                    unit_in_kg = to_kg(1.0, price_unit)
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
                        posted_at=row.get("posted_at") if "posted_at" in row.keys() else None
                    )
                    result["available_text"] = avail_phrase or result.get("available_text")
                    result["available_date"] = avail_date

                    # Restore PII untuk kontak (contoh sederhana)
                    phones = [val for key, val in mapping.items() if "PHONE" in key]
                    contact_phone = None
                    contact_wa = None
                    if phones:
                        contact_phone = ", ".join(phones)
                        # Normalisasi nomor telepon pertama menjadi format WA (+62)
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
                    rel_score, rel_why = relevance(result, self.campaign, raw_text)
                    conf_score, conf_why = confidence(result, self.campaign, row["platform"], 1)
                    if dup_of:
                        conf_score = max(0, conf_score - 20)
                        conf_why.append(f"-20 duplikat dari listing #{dup_of} ({dup_why})")
                    
                    # 9. Simpan ke database listings
                    safe_intent = result.get("intent")
                    if not safe_intent:
                        safe_intent = "other"
                        
                    self.conn.execute(
                        """INSERT INTO listings (
                            raw_item_id, campaign_id, intent, entity_name,
                            product, volume_kg, price_per_kg, location_text,
                            kabupaten, provinsi, available_text, available_date,
                            contact_phone, contact_wa, duplicate_of,
                            attributes_json, evidence_json, flags_json, relevance, 
                            confidence, score_reasons_json, extractor, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            row["id"], self.campaign.campaign_id, safe_intent, result.get("entity_name"),
                            result.get("product"), vol_kg, price_kg, loc_text,
                            result.get("kabupaten"), result.get("provinsi"), result.get("available_text"),
                            avail_date, contact_phone, contact_wa, dup_of,
                            db.dumps(result), db.dumps(result.get("evidence", {})),
                            db.dumps(result.get("flags", [])), rel_score, conf_score, 
                            db.dumps({"relevance": rel_why, "confidence": conf_why, "dup": dup_why}), 
                            result.get("extractor", "llm"), db.now_iso()
                        )
                    )
                self.conn.commit()
                logger.info(f"Batch {i//batch_size + 1} selesai diproses.")


        except Exception as e:
            logger.exception("Error pada pipeline.")
            db.finish_run(self.conn, run_id, status="error", error=str(e))

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # Test pipeline with dummy campaign
    c = CampaignSpec(campaign_id="test_malang", goal="find_supply")
    c.product.name = "gabah"
    c.location.include = ["Malang"]
    pipe = Pipeline(c)
    asyncio.run(pipe.run())

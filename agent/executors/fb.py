import os
import time
import requests
import logging
from typing import List, Dict
import asyncio

logger = logging.getLogger(__name__)

class FacebookExecutor:
    """
    Eksekutor Apify untuk melakukan scraping Facebook secara profesional (Hackathon/Production).
    Tidak menggunakan Chromium lokal, sehingga 100% aman dari blokir IP/Akun pribadi.
    """
    def __init__(self, user_data_dir: str = None):
        key = os.getenv("APIFY_API_KEY")
        self.api_key = key.strip() if key else None

    async def scrape_queries(self, queries: List[str], max_posts: int = 10, progress_callback=None, target_intent: str = "supply") -> List[Dict]:
        """
        Mengekstrak postingan Facebook menggunakan Apify API.
        Karena kita butuh kepastian data masuk, kita akan memberikan beberapa URL
        Halaman Publik/Grup Pertanian Indonesia ke Apify.
        """
        if not self.api_key:
            logger.error("APIFY_API_KEY belum dipasang!")
            if progress_callback:
                progress_callback("Apify Error", "APIFY_API_KEY belum dipasang di konfigurasi environment.")
            return []
            
        print("\n" + "="*50)
        print("[APIFY] Menghubungi server Apify untuk pencarian dinamis...")
        print("="*50)
        
        # Kita menggunakan Google Search Scraper dari Apify untuk mencari spesifik di dalam Facebook
        # Ini memastikan hasil yang didapat SESUAI dengan kata kunci (misal: "melon")
        run_url = f"https://api.apify.com/v2/acts/apify~google-search-scraper/runs?token={self.api_key}"
        
        search_queries = []
        # Negative keywords untuk membuang spam (bibit, pupuk, lowongan kerja, resep)
        negatives = "-bibit -benih -pupuk -obat -loker -lowongan -resep -jus -olahan -jasa -2018 -2019 -2020 -2021 -2022 -2023 -2024"
        
        for q in queries:
            if not q.strip():
                continue
            clean_q = q.strip()
            lower_q = clean_q.lower()

            # 1. Target Google Maps & Bisnis Lokal (Toko Buah, Pasar Induk, Distributor)
            if any(k in lower_q for k in ["toko buah", "toko sayur", "distributor buah", "pasar induk", "grosir buah"]):
                search_queries.append(f'"{clean_q}" {negatives}')
                search_queries.append(f'site:maps.google.com "{clean_q}"')
            # 2. Target Web B2B / Supplier / Direktori Agribisnis
            elif any(k in lower_q for k in ["supplier", "kemitraan", "eksportir", "forwarder", "direktori"]):
                search_queries.append(f'"{clean_q}" -site:facebook.com {negatives}')
            # 3. Target Grup Facebook & Komunitas Agribisnis
            else:
                if target_intent == "demand":
                    # Cari posting PEMBELI di Facebook (orang/bisnis yang butuh pasokan)
                    # 1. Kueri dengan nomor kontak langsung
                    search_queries.append(f'site:facebook.com/groups "{clean_q}" (butuh OR cari OR beli OR terima OR tampung OR order) (wa OR "08" OR "628") {negatives}')
                    # 2. Kueri kebutuhan organik tanpa paksaan nomor kontak
                    search_queries.append(f'site:facebook.com/groups "{clean_q}" (butuh pasokan OR cari supplier OR siap tampung) {negatives}')
                    # 3. Kueri profil pembeli publik
                    search_queries.append(f'site:facebook.com "{clean_q}" (butuh OR dicari OR beli OR tampung) {negatives}')
                else:
                    # Cari posting PENJUAL/PETANI di Facebook (default, supply)
                    # 1. Kueri dengan kontak langsung (WA/HP)
                    search_queries.append(f'site:facebook.com/groups "{clean_q}" (ready OR panen OR jual OR petik OR diobral) (wa OR "08" OR "628") {negatives}')
                    # 2. Kueri panen organik alami di grup petani (menjaring post faktual tanpa paksaan no HP)
                    search_queries.append(f'site:facebook.com/groups "{clean_q}" (panen raya OR siap petik OR ready di kebun OR panen segar) {negatives}')
                    # 3. Kueri petani umum
                    search_queries.append(f'site:facebook.com/groups "petani {clean_q}" (panen OR jual OR stok) {negatives}')

                # Untuk kampanye demand, tambahkan pencarian bisnis lokal otomatis
                if target_intent == "demand":
                    # Tambahkan pencarian toko/distributor/pasar yang relevan
                    for biz_type in ["toko buah", "distributor", "grosir", "pasar induk"]:
                        biz_q = f'{biz_type} {clean_q}'
                        if biz_q not in search_queries:
                            search_queries.append(f'"{biz_q}" telepon alamat')

                
        if not search_queries:
            logger.warning("Tidak ada query pencarian yang valid. Membatalkan request Apify.")
            return []
            
        payload = {
            "queries": "\n".join(search_queries),
            "maxPagesPerQuery": 1,
            "resultsPerPage": max_posts,
            "countryCode": "id",
            "languageCode": "id",
            "tbs": "qdr:m",  # Past month Google parameter: singkirkan post basi 1-2 tahun lalu dari Google
        }
        
        if progress_callback:
            progress_callback("Apify Cloud", f"Mengirim {len(search_queries)} variasi query ke Apify Google Search Scraper...")
        
        try:
            resp = requests.post(run_url, json=payload, timeout=30)
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"Gagal menghubungi Apify: {e}")
            if progress_callback:
                progress_callback("Apify Error", f"Gagal menghubungi API Apify: {e}")
            return []
            
        run_data = resp.json().get("data", {})
        run_id = run_data.get("id")
        dataset_id = run_data.get("defaultDatasetId")
        
        print(f"[APIFY] Job dimulai di Cloud. (Run ID: {run_id})")
        print("[APIFY] Menunggu mesin Apify mengekstrak hasil pencarian...")
        if progress_callback:
            progress_callback("Apify Ekstraksi", f"Job berjalan di Apify Cloud (Run ID: {run_id}). Menunggu ekstraksi selesai...")
        
        # Polling status Apify setiap 5 detik
        poll_count = 0
        while True:
            await asyncio.sleep(5)
            poll_count += 1
            status_url = f"https://api.apify.com/v2/actor-runs/{run_id}?token={self.api_key}"
            try:
                s_resp = requests.get(status_url, timeout=10).json()
                status = s_resp.get("data", {}).get("status")
                print(f"[APIFY] Status job ({poll_count * 5}s): {status}...")
                if progress_callback:
                    progress_callback("Apify Ekstraksi", f"Memeriksa status aktor di Cloud: {status} (detik ke-{poll_count * 5})...")
                
                if status in ["SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"]:
                    break
            except Exception as e:
                logger.warning(f"Gagal mengecek status Apify: {e}")
                
        if status != "SUCCEEDED":
            print(f"[ERROR] Apify gagal atau dihentikan dengan status: {status}")
            if progress_callback:
                progress_callback("Apify Selesai", f"Job Apify berakhir dengan status: {status}")
            return []
            
        print("[DOWNLOAD] Mengunduh hasil pencarian spesifik dari Apify dataset...")
        if progress_callback:
            progress_callback("Unduh Dataset", f"Job berhasil selesai di Cloud. Mengunduh dataset {dataset_id}...")
        data_url = f"https://api.apify.com/v2/datasets/{dataset_id}/items?token={self.api_key}"
        try:
            d_resp = requests.get(data_url, timeout=30).json()
        except Exception as e:
            logger.error(f"Gagal mengunduh dataset Apify: {e}")
            if progress_callback:
                progress_callback("Unduh Gagal", f"Gagal mengunduh dataset Apify: {e}")
            return []
            
        all_posts_data = []
        maps_count = 0
        fb_count = 0
        web_count = 0

        for item in d_resp:
            # Pada Google Search Scraper, hasil ada di dalam array 'organicResults'
            organic_results = item.get("organicResults", [])
            sq_raw = item.get("searchQuery", "")
            if isinstance(sq_raw, dict):
                sq_term = str(sq_raw.get("term") or sq_raw.get("query") or "")
            else:
                sq_term = str(sq_raw or "")
            q_lower = sq_term.lower()

            for res in organic_results:
                title = str(res.get("title") or "")
                snippet = str(res.get("description") or "")
                url = str(res.get("url") or "")
                
                # Gabungkan judul dan deskripsi sebagai teks mentah
                text = f"{title}\n{snippet}"

                u_lower = url.lower()

                if "maps.google" in u_lower or "google.com/maps" in u_lower or any(k in q_lower for k in ["toko buah", "toko sayur", "pasar induk", "grosir buah"]):
                    platform_tag = "google_maps"
                    maps_count += 1
                elif "facebook.com" in u_lower:
                    platform_tag = "facebook"
                    fb_count += 1
                else:
                    platform_tag = "web_b2b"
                    web_count += 1
                
                if snippet and len(snippet.strip()) > 15:
                    from ..normalize import parse_posted_date
                    import re
                    from datetime import datetime
                    raw_date = res.get("date") or res.get("displayedDate") or res.get("publishedAt")
                    detected_date = parse_posted_date(text, raw_date=str(raw_date) if raw_date else None)

                    # Filter Kesegaran Ketat (Maksimal 1 Bulan / 35 Hari):
                    # 1. Jika terdeteksi tanggal postingan lebih dari 35 hari lalu (misal 2022, 2023, 2024), buang seketika!
                    if detected_date:
                        try:
                            p_dt = datetime.fromisoformat(detected_date)
                            diff_days = (datetime.now() - p_dt).total_seconds() / 86400
                            if diff_days > 35:
                                logger.info(f"Mengabaikan postingan kedaluwarsa ({diff_days:.0f} hari lalu / {detected_date}): {text[:60]}")
                                continue
                        except Exception:
                            pass

                    # 2. Jika isi snippet memuat tahun lampau (2010 - 2024), buang seketika!
                    if re.search(r"\b(201\d|202[0-4])\b", text.lower()):
                        logger.info(f"Mengabaikan postingan memuat tahun lampau: {text[:60]}")
                        continue

                    all_posts_data.append({
                        "platform": platform_tag,
                        "query": sq_term,
                        "raw_text": text.strip(),
                        "url": url,
                        "posted_at": detected_date,
                    })
                
        print(f"[SELESAI] Sukses! {len(all_posts_data)} postingan sumber berhasil diambil.")
        print("="*50 + "\n")
        if progress_callback:
            progress_callback("Scraping Selesai", f"Berhasil mengunduh {len(all_posts_data)} data sumber: Google Maps ({maps_count}), Facebook ({fb_count}), Direktori Web B2B ({web_count}).")
        return all_posts_data

# Standalone test
if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    logging.basicConfig(level=logging.INFO)
    executor = FacebookExecutor()
    results = asyncio.run(executor.scrape_queries(["petani melon"]))
    for r in results:
        print(f"\n--- URL: {r['url']} ---")
        print(r['raw_text'][:200] + "...")

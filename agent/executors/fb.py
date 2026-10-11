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

    async def scrape_queries(self, queries: List[str], max_posts: int = 10) -> List[Dict]:
        """
        Mengekstrak postingan Facebook menggunakan Apify API.
        Karena kita butuh kepastian data masuk, kita akan memberikan beberapa URL
        Halaman Publik/Grup Pertanian Indonesia ke Apify.
        """
        if not self.api_key:
            logger.error("APIFY_API_KEY belum dipasang!")
            return []
            
        print("\n" + "="*50)
        print("[APIFY] Menghubungi server Apify untuk pencarian dinamis...")
        print("="*50)
        
        # Kita menggunakan Google Search Scraper dari Apify untuk mencari spesifik di dalam Facebook
        # Ini memastikan hasil yang didapat SESUAI dengan kata kunci (misal: "melon")
        run_url = f"https://api.apify.com/v2/acts/apify~google-search-scraper/runs?token={self.api_key}"
        
        search_queries = []
        # Negative keywords untuk membuang spam (bibit, pupuk, lowongan kerja, resep)
        negatives = "-bibit -benih -pupuk -obat -loker -lowongan -resep -jus -olahan -jasa"
        
        for q in queries:
            if q.strip():
                clean_q = q.strip()
                # 1. Target spesifik ke postingan di dalam grup
                search_queries.append(f'site:facebook.com/groups/* (inurl:posts OR inurl:permalink) "{clean_q}" {negatives}')
                # 2. Target umum ke facebook
                search_queries.append(f'site:facebook.com "{clean_q}" {negatives}')
                
        if not search_queries:
            logger.warning("Tidak ada query pencarian yang valid. Membatalkan request Apify.")
            return []
            
        payload = {
            "queries": "\n".join(search_queries),
            "maxPagesPerQuery": 1,
            "resultsPerPage": max_posts
        }
        
        try:
            resp = requests.post(run_url, json=payload, timeout=30)
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"Gagal menghubungi Apify: {e}")
            return []
            
        run_data = resp.json().get("data", {})
        run_id = run_data.get("id")
        dataset_id = run_data.get("defaultDatasetId")
        
        print(f"✅ Apify mulai mencari kata kunci Anda di Cloud. (Run ID: {run_id})")
        print("⏳ Menunggu mesin Apify mengekstrak hasil pencarian (biasanya butuh 30-60 detik)...")
        
        # Polling status Apify setiap 5 detik
        while True:
            await asyncio.sleep(5)
            status_url = f"https://api.apify.com/v2/actor-runs/{run_id}?token={self.api_key}"
            try:
                s_resp = requests.get(status_url, timeout=10).json()
                status = s_resp.get("data", {}).get("status")
                print(f"Status Apify: {status}...")
                
                if status in ["SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"]:
                    break
            except Exception as e:
                logger.warning(f"Gagal mengecek status Apify: {e}")
                
        if status != "SUCCEEDED":
            print(f"❌ Apify gagal atau dihentikan dengan status: {status}")
            return []
            
        print("📥 Mengunduh hasil pencarian spesifik dari Apify...")
        data_url = f"https://api.apify.com/v2/datasets/{dataset_id}/items?token={self.api_key}"
        try:
            d_resp = requests.get(data_url, timeout=30).json()
        except Exception as e:
            logger.error(f"Gagal mengunduh dataset Apify: {e}")
            return []
            
        all_posts_data = []
        for item in d_resp:
            # Pada Google Search Scraper, hasil ada di dalam array 'organicResults'
            organic_results = item.get("organicResults", [])
            for res in organic_results:
                title = res.get("title", "")
                snippet = res.get("description", "")
                url = res.get("url", "")
                
                # Gabungkan judul dan deskripsi sebagai teks mentah
                text = f"{title}\n{snippet}"
                
                if snippet and len(snippet.strip()) > 15:
                    all_posts_data.append({
                        "platform": "facebook",
                        "query": item.get("searchQuery", ""),
                        "raw_text": text.strip(),
                        "url": url
                    })
                
        print(f"🎉 SUKSES! {len(all_posts_data)} Prospek Asli (Sesuai Kata Kunci) berhasil disedot.")
        print("="*50 + "\n")
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

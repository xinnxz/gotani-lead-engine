import os
import time
import requests
import logging
from typing import List, Dict
import asyncio

logger = logging.getLogger(__name__)

def _split_google_snippet(title: str, snippet: str, url: str) -> list[dict]:
    """Pecah Google Search snippet yang mengandung >1 postingan Facebook.

    Google sering menggabungkan 2-3 ringkasan post FB berbeda dalam satu snippet.
    Ini menyebabkan kontak/harga dari post orang lain tercampur ke post yang salah.
    Solusi: Deteksi batas antar-snippet, pecah, dan simpan terpisah.
    """
    import re

    full_text = f"{title}\n{snippet}".strip()

    if not snippet or len(snippet) < 60:
        return [{"text": full_text, "url": url}]

    # Pola pemisah antar-snippet Google
    # 1. "..." diikuti spasi/newline lalu huruf kapital = batas snippet
    # 2. Kata pembuka khas postingan baru setelah titik
    split_positions = []

    # Pattern 1: Tiga titik "..." diikuti teks baru
    for m in re.finditer(r"\.\.\.\s+(?=[A-Z])", snippet):
        if m.start() > 30 and len(snippet) - m.end() > 30:
            split_positions.append(m.end())

    # Pattern 2: Kata pembuka post FB setelah titik
    openers = r"(?:Jual|Ready|Bismillah|Assalamualaikum|Dijual|Open|Butuh|Cari|Dicari|Monggo|Hallo|Hai)"
    for m in re.finditer(r"(?<=\.\s)" + openers + r"\b", snippet, re.IGNORECASE):
        if m.start() > 30 and len(snippet) - m.start() > 30:
            split_positions.append(m.start())

    if not split_positions:
        return [{"text": full_text, "url": url}]

    # Pecah snippet di posisi yang ditemukan
    split_positions = sorted(set(split_positions))
    parts = []

    # Bagian pertama: title + awal snippet (milik post asli dari URL)
    first_snippet = snippet[:split_positions[0]].strip().rstrip(".")
    if len(first_snippet) >= 20:
        parts.append({"text": f"{title}\n{first_snippet}", "url": url})

    # Bagian selanjutnya: snippet terpisah (post orang lain, tanpa title)
    prev = split_positions[0]
    for pos in split_positions[1:]:
        chunk = snippet[prev:pos].strip()
        if len(chunk) >= 20:
            parts.append({"text": chunk, "url": url})
        prev = pos

    last_chunk = snippet[prev:].strip()
    if len(last_chunk) >= 20:
        parts.append({"text": last_chunk, "url": url})

    return parts if parts else [{"text": full_text, "url": url}]



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
        # Dynamic: blokir semua tahun sebelum tahun ini (misal 2026 → blokir 2018-2025)
        from datetime import datetime as _dt
        _cur_year = _dt.now().year
        _year_negs = " ".join(f"-{y}" for y in range(2018, _cur_year))
        negatives = f"-bibit -benih -pupuk -obat -loker -lowongan -resep -jus -olahan -jasa {_year_negs}"
        
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
                    is_short = len(clean_q.split()) == 1 and len(clean_q) <= 5
                    if is_short:
                        search_queries.append(f'site:facebook.com/groups "butuh {clean_q}" (wa OR "08" OR "628") {negatives}')
                        search_queries.append(f'site:facebook.com/groups "cari {clean_q}" (supplier OR pasokan OR ton) {negatives}')
                        search_queries.append(f'site:facebook.com "beli {clean_q}" (butuh OR tampung OR order) {negatives}')
                    else:
                        search_queries.append(f'site:facebook.com/groups "{clean_q}" (butuh OR cari OR beli OR terima OR tampung OR order) (wa OR "08" OR "628") {negatives}')
                        search_queries.append(f'site:facebook.com/groups "{clean_q}" (butuh pasokan OR cari supplier OR siap tampung) {negatives}')
                        search_queries.append(f'site:facebook.com "{clean_q}" (butuh OR dicari OR beli OR tampung) {negatives}')
                else:
                    # Cari posting PENJUAL/PETANI di Facebook (default, supply)
                    # Untuk komoditas pendek (misal "kol"), tambahkan konteks agar Google
                    # mengembalikan POSTINGAN individual, bukan halaman grup
                    is_short = len(clean_q.split()) == 1 and len(clean_q) <= 5
                    # Variasi query kontekstual (prioritas: post dengan kontak)
                    if is_short:
                        # Komoditas pendek: gunakan frasa lengkap agar lebih spesifik
                        search_queries.append(f'site:facebook.com/groups "jual {clean_q}" (ready OR panen OR segar) (wa OR "08" OR "628") {negatives}')
                        search_queries.append(f'site:facebook.com/groups "panen {clean_q}" (ton OR kwintal OR kg OR kuintal) {negatives}')
                        search_queries.append(f'site:facebook.com/groups "petani {clean_q}" (jual OR ready OR stok) {negatives}')
                    else:
                        search_queries.append(f'site:facebook.com/groups "{clean_q}" (ready OR panen OR jual OR petik) (wa OR "08" OR "628") {negatives}')
                        search_queries.append(f'site:facebook.com/groups "{clean_q}" (panen raya OR siap petik OR ready di kebun OR panen segar) {negatives}')
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
            if resp.status_code == 402:
                err_json = resp.json().get("error", {})
                msg = err_json.get("message", "Saldo tidak mencukupi untuk menjalankan scraper.")
                err_text = f"Saldo Apify Habis (402 Payment Required): {msg}. Silakan ganti API token di .env atau gunakan akun baru gratis di console.apify.com."
                logger.error(err_text)
                if progress_callback:
                    progress_callback("Apify Error", err_text)
                raise RuntimeError(err_text)
            resp.raise_for_status()
        except requests.exceptions.RequestException as e:
            err_text = f"Gagal menghubungi Apify: {e}"
            logger.error(err_text)
            if progress_callback:
                progress_callback("Apify Error", err_text)
            raise RuntimeError(err_text)
            
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
                
                # Teks gabungan dibuat oleh _split_google_snippet (anti-kontaminasi)

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
                
                # Skip halaman grup Facebook (bukan postingan individual)
                # Pattern: facebook.com/groups/XXXXX/ tanpa /posts/ atau /permalink/
                import re as _re_url
                if _re_url.match(r'https?://[^/]*facebook\.com/groups/[^/]+/?$', url):
                    logger.info(f"Mengabaikan halaman grup (bukan postingan): {url}")
                    continue

                if snippet and len(snippet.strip()) > 15:
                    from ..normalize import parse_posted_date
                    import re
                    from datetime import datetime
                    raw_date = res.get("date") or res.get("displayedDate") or res.get("publishedAt")

                    # ANTI-KONTAMINASI: Pecah snippet gabungan menjadi post terpisah
                    sub_posts = _split_google_snippet(title, snippet, url)

                    for sub in sub_posts:
                        sub_text = sub["text"]
                        detected_date = parse_posted_date(sub_text, raw_date=str(raw_date) if raw_date else None)

                        # Filter Kesegaran Ketat (Maksimal 1 Bulan / 35 Hari):
                        if detected_date:
                            try:
                                p_dt = datetime.fromisoformat(detected_date)
                                diff_days = (datetime.now() - p_dt).total_seconds() / 86400
                                if diff_days > 35:
                                    logger.info(f"Mengabaikan postingan kedaluwarsa ({diff_days:.0f} hari lalu / {detected_date}): {sub_text[:60]}")
                                    continue
                            except Exception:
                                pass

                        # Dynamic: buang snippet yang memuat tahun lampau (sebelum tahun ini)
                        _stale_max = _cur_year - 1
                        _stale_re = r"\b(201\d" + (f"|202[0-{_stale_max % 10}]" if _stale_max < 2030 else "|202\\d") + r")\b"
                        if re.search(_stale_re, sub_text.lower()):
                            logger.info(f"Mengabaikan postingan memuat tahun lampau: {sub_text[:60]}")
                            continue

                        # Smart fallback: jika Google tbs=qdr:m (past month) tapi tidak ada tanggal,
                        # assign tanggal hari ini (asumsi fresh karena Google filter 1 bulan terakhir)
                        final_date = detected_date
                        if not final_date:
                            final_date = _dt.now().strftime("%Y-%m-%d")

                        all_posts_data.append({
                            "platform": platform_tag,
                            "query": sq_term,
                            "raw_text": sub_text.strip(),
                            "url": sub["url"],
                            "posted_at": final_date,
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

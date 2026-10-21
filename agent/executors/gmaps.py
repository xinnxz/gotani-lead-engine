"""Google Maps Business Scraper — Executor khusus untuk data demand (pembeli).

Menggunakan Apify actor 'compass/crawler-google-places' untuk mengekstrak data
bisnis lengkap dari Google Maps: nama, telepon, alamat, rating, website, dll.

Dipakai saat kampanye bertujuan 'find_demand' karena pembeli B2B (toko buah,
distributor, grosir, pasar induk) TIDAK posting di Facebook — mereka ada di Google Maps.
"""
import os
import time
import requests
import logging
import asyncio
from typing import List, Dict
from datetime import datetime

logger = logging.getLogger(__name__)

# Pola query pencarian Google Maps berdasarkan komoditas
DEMAND_QUERY_TEMPLATES = [
    "toko buah {product}",
    "distributor {product}",
    "grosir {product}",
    "supplier {product}",
    "pasar buah {product}",
    "toko buah segar",
    "agen buah",
]

# Pola tambahan untuk komoditas non-buah
DEMAND_QUERY_TEMPLATES_SAYUR = [
    "toko sayur {product}",
    "distributor sayuran",
    "grosir {product}",
    "pasar sayur",
    "supplier {product}",
]

DEMAND_QUERY_TEMPLATES_REMPAH = [
    "toko rempah {product}",
    "distributor rempah",
    "grosir {product}",
    "supplier rempah {product}",
    "toko jamu",
]

# Kategori komoditas untuk memilih template yang tepat
KATEGORI_BUAH = {
    "melon", "semangka", "mangga", "pisang", "jeruk", "alpukat", "durian",
    "nanas", "salak", "manggis", "apel", "pepaya", "buah naga",
}
KATEGORI_SAYUR = {
    "cabai", "bawang merah", "bawang putih", "tomat", "kentang", "wortel",
    "kubis", "terong", "buncis", "timun",
}
KATEGORI_REMPAH = {
    "jahe", "cengkeh", "kunyit", "temulawak", "kencur", "lengkuas",
    "kapulaga", "pala", "lada", "vanili", "serai",
}


def _build_demand_queries(product: str, locations: List[str]) -> List[str]:
    """Bangun query pencarian Google Maps berdasarkan komoditas dan lokasi."""
    product_lower = product.lower().strip()

    # Pilih template berdasarkan kategori komoditas
    if product_lower in KATEGORI_SAYUR:
        templates = DEMAND_QUERY_TEMPLATES_SAYUR
    elif product_lower in KATEGORI_REMPAH:
        templates = DEMAND_QUERY_TEMPLATES_REMPAH
    else:
        templates = DEMAND_QUERY_TEMPLATES

    queries = []
    for tpl in templates:
        base_q = tpl.format(product=product)
        if locations:
            for loc in locations[:3]:  # Maksimal 3 lokasi agar hemat kuota
                queries.append(f"{base_q} di {loc}")
        else:
            queries.append(base_q)

    # Deduplikasi
    seen = set()
    unique = []
    for q in queries:
        if q not in seen:
            seen.add(q)
            unique.append(q)

    return unique[:15]  # Maksimal 15 query


class GoogleMapsExecutor:
    """Eksekutor Apify untuk scraping data bisnis dari Google Maps.

    Menggunakan actor 'compass/crawler-google-places' untuk mendapatkan:
    - Nama bisnis, kategori, rating, jumlah review
    - Nomor telepon, website
    - Alamat lengkap, kota, kode pos
    - URL Google Maps
    """

    # Actor Apify untuk Google Maps
    ACTOR_ID = "compass~crawler-google-places"  # Tilde format untuk Apify REST API

    def __init__(self):
        key = os.getenv("APIFY_API_KEY")
        self.api_key = key.strip() if key else None

    async def scrape_demand(
        self,
        product: str,
        locations: List[str],
        max_results: int = 30,
        progress_callback=None,
    ) -> List[Dict]:
        """Cari bisnis potensial pembeli di Google Maps.

        Args:
            product: Nama komoditas (misal "melon", "apel")
            locations: Daftar wilayah target (misal ["Jawa Timur", "Malang"])
            max_results: Maksimal hasil per query
            progress_callback: Callback untuk update progress UI

        Returns:
            List of dict berisi data bisnis terstruktur
        """
        if not self.api_key:
            logger.error("APIFY_API_KEY belum dipasang!")
            if progress_callback:
                progress_callback("Error", "APIFY_API_KEY belum diatur.")
            return []

        queries = _build_demand_queries(product, locations)

        print(f"\n{'='*50}")
        print(f"[GMAPS] Mencari {len(queries)} query bisnis di Google Maps...")
        print(f"[GMAPS] Komoditas: {product}")
        print(f"[GMAPS] Lokasi: {', '.join(locations) if locations else 'Seluruh Indonesia'}")
        print(f"{'='*50}")

        if progress_callback:
            progress_callback(
                "Google Maps",
                f"Mengirim {len(queries)} pencarian bisnis ke Google Maps via Apify..."
            )

        # Bangun lokasi pencarian
        location_query = ""
        if locations:
            location_query = f"{locations[0]}, Indonesia"
        else:
            location_query = "Indonesia"

        run_url = f"https://api.apify.com/v2/acts/{self.ACTOR_ID}/runs?token={self.api_key}"

        payload = {
            "searchStringsArray": queries,
            "locationQuery": location_query,
            "maxCrawledPlacesPerSearch": max(5, max_results // len(queries)),
            "language": "id",
            "includeWebResults": False,
            "maxImages": 0,
            "maxReviews": 0,
            "onlyDataFromSearchPage": False,
        }

        try:
            resp = requests.post(run_url, json=payload, timeout=30)
            if resp.status_code == 402:
                err_json = resp.json().get("error", {})
                msg = err_json.get("message", "Saldo tidak mencukupi.")
                err_text = f"Saldo Apify Habis (402): {msg}"
                logger.error(err_text)
                if progress_callback:
                    progress_callback("Apify Error", err_text)
                raise RuntimeError(err_text)
            resp.raise_for_status()
        except requests.exceptions.RequestException as e:
            err_text = f"Gagal menghubungi Apify: {e}"
            logger.error(err_text)
            if progress_callback:
                progress_callback("Error", err_text)
            raise RuntimeError(err_text)

        run_data = resp.json().get("data", {})
        run_id = run_data.get("id")
        dataset_id = run_data.get("defaultDatasetId")

        print(f"[GMAPS] Job dimulai (Run ID: {run_id})")
        if progress_callback:
            progress_callback("Google Maps", f"Job berjalan di Apify Cloud (Run ID: {run_id})...")

        # Polling status
        poll_count = 0
        status = "RUNNING"
        while True:
            await asyncio.sleep(5)
            poll_count += 1
            status_url = f"https://api.apify.com/v2/actor-runs/{run_id}?token={self.api_key}"
            try:
                s_resp = requests.get(status_url, timeout=10).json()
                status = s_resp.get("data", {}).get("status")
                print(f"[GMAPS] Status ({poll_count * 5}s): {status}...")
                if progress_callback:
                    progress_callback("Google Maps", f"Status: {status} (detik ke-{poll_count * 5})...")
                if status in ["SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"]:
                    break
            except Exception as e:
                logger.warning(f"Gagal cek status: {e}")

        if status != "SUCCEEDED":
            print(f"[ERROR] Google Maps job gagal: {status}")
            if progress_callback:
                progress_callback("Error", f"Job Google Maps berakhir: {status}")
            return []

        # Unduh hasil
        print("[GMAPS] Mengunduh data bisnis...")
        if progress_callback:
            progress_callback("Unduh Data", f"Mengunduh dataset {dataset_id}...")

        data_url = f"https://api.apify.com/v2/datasets/{dataset_id}/items?token={self.api_key}"
        try:
            d_resp = requests.get(data_url, timeout=30).json()
        except Exception as e:
            logger.error(f"Gagal unduh dataset: {e}")
            return []

        # Parse hasil Google Maps ke format listing GoTani
        results = []
        seen_phones = set()

        for item in d_resp:
            if not isinstance(item, dict):
                continue

            title = str(item.get("title") or "").strip()
            phone = str(item.get("phone") or item.get("phoneUnformatted") or "").strip()
            address = str(item.get("address") or "").strip()
            city = str(item.get("city") or "").strip()
            website = str(item.get("website") or "").strip()
            rating = item.get("totalScore") or item.get("rating")
            reviews = item.get("reviewsCount") or item.get("reviews") or 0
            category = str(item.get("categoryName") or item.get("category") or "").strip()
            maps_url = str(item.get("url") or "").strip()
            postal = str(item.get("postalCode") or "").strip()
            state = str(item.get("state") or "").strip()
            street = str(item.get("street") or "").strip()
            neighborhood = str(item.get("neighborhood") or "").strip()

            # Skip jika tidak ada nama bisnis
            if not title or len(title) < 3:
                continue

            # Deduplikasi berdasarkan nomor telepon
            phone_clean = phone.replace("+", "").replace("-", "").replace(" ", "")
            if phone_clean and phone_clean in seen_phones:
                continue
            if phone_clean:
                seen_phones.add(phone_clean)

            # Format alamat lengkap
            full_address = address
            if city and city not in address:
                full_address = f"{address}, {city}"

            # Bangun teks mentah untuk pipeline (supaya bisa diproses extraction)
            raw_parts = [title]
            if category:
                raw_parts.append(f"Kategori: {category}")
            if full_address:
                raw_parts.append(f"Alamat: {full_address}")
            if phone:
                raw_parts.append(f"Telepon: {phone}")
            if website and "google.com" not in website:
                raw_parts.append(f"Website: {website}")
            if rating:
                raw_parts.append(f"Rating: {rating}/5 ({reviews} ulasan)")

            raw_text = "\n".join(raw_parts)

            results.append({
                "platform": "google_maps",
                "query": f"demand_{product}",
                "raw_text": raw_text,
                "url": maps_url or website or "",
                "posted_at": datetime.now().strftime("%Y-%m-%d"),
                # Data terstruktur tambahan (akan dipakai langsung di pipeline)
                "_gmaps_data": {
                    "business_name": title,
                    "phone": phone,
                    "address": full_address,
                    "city": city,
                    "state": state,
                    "postal_code": postal,
                    "street": street,
                    "neighborhood": neighborhood,
                    "website": website,
                    "rating": float(rating) if rating else None,
                    "reviews_count": int(reviews) if reviews else 0,
                    "category": category,
                },
            })

        print(f"[GMAPS] Selesai! {len(results)} bisnis ditemukan.")
        if progress_callback:
            progress_callback(
                "Scraping Selesai",
                f"Berhasil menemukan {len(results)} bisnis potensial dari Google Maps."
            )

        return results

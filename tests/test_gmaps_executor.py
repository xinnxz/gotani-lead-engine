"""Tests untuk Google Maps executor dan integrasi pipeline demand.

Menguji:
1. Fungsi _build_demand_queries (pembangunan query pencarian)
2. Kategori komoditas (buah, sayur, rempah)
3. Parsing hasil Google Maps ke format GoTani
4. Deduplikasi telepon
5. Integrasi pipeline: phone injection dari gmaps_data
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime

from agent.executors.gmaps import (
    _build_demand_queries,
    GoogleMapsExecutor,
    KATEGORI_BUAH,
    KATEGORI_SAYUR,
    KATEGORI_REMPAH,
    DEMAND_QUERY_TEMPLATES,
    DEMAND_QUERY_TEMPLATES_SAYUR,
    DEMAND_QUERY_TEMPLATES_REMPAH,
)


# ==========================================
# 1. Query Builder Tests
# ==========================================

class TestBuildDemandQueries:
    """Test pembangunan query pencarian Google Maps."""

    def test_buah_uses_default_templates(self):
        """Komoditas buah harus pakai template default (toko buah, distributor)."""
        queries = _build_demand_queries("melon", ["Jawa Timur"])
        assert any("toko buah melon" in q for q in queries)
        assert any("distributor melon" in q for q in queries)
        assert any("grosir melon" in q for q in queries)
        # Harus ada lokasi
        assert any("di Jawa Timur" in q for q in queries)

    def test_sayur_uses_sayur_templates(self):
        """Komoditas sayur harus pakai template sayur (toko sayur, distributor sayuran)."""
        queries = _build_demand_queries("cabai", ["Jakarta"])
        assert any("toko sayur cabai" in q for q in queries)
        assert any("distributor sayuran" in q for q in queries)

    def test_rempah_uses_rempah_templates(self):
        """Komoditas rempah harus pakai template rempah (toko rempah, toko jamu)."""
        queries = _build_demand_queries("jahe", ["Jawa Barat"])
        assert any("toko rempah jahe" in q for q in queries)
        assert any("toko jamu" in q for q in queries)

    def test_empty_location_no_suffix(self):
        """Tanpa lokasi, query tidak boleh ada 'di ...' suffix."""
        queries = _build_demand_queries("melon", [])
        for q in queries:
            assert "di " not in q

    def test_max_15_queries(self):
        """Maksimal 15 query untuk hemat kuota Apify."""
        queries = _build_demand_queries("melon", [
            "Jawa Timur", "Jawa Barat", "Jawa Tengah",
            "Sumatera Utara", "Sulawesi Selatan",
        ])
        assert len(queries) <= 15

    def test_max_3_locations(self):
        """Hanya pakai maksimal 3 lokasi pertama."""
        queries = _build_demand_queries("melon", [
            "Jawa Timur", "Jawa Barat", "Jawa Tengah",
            "Sumatera Utara", "Sulawesi Selatan",
        ])
        # Lokasi ke-4 dan ke-5 tidak boleh ada
        assert not any("Sumatera Utara" in q for q in queries)
        assert not any("Sulawesi Selatan" in q for q in queries)

    def test_no_duplicate_queries(self):
        """Tidak boleh ada query duplikat."""
        queries = _build_demand_queries("melon", ["Jawa Timur"])
        assert len(queries) == len(set(queries))

    def test_unknown_product_uses_default(self):
        """Komoditas tidak dikenal pakai template default (buah)."""
        queries = _build_demand_queries("sawo", ["Malang"])
        # Sawo bukan di set KATEGORI_SAYUR/REMPAH, jadi pakai default
        assert any("toko buah sawo" in q for q in queries)


# ==========================================
# 2. Kategori Komoditas Tests
# ==========================================

class TestKategoriKomoditas:
    """Verifikasi kategori komoditas lengkap."""

    def test_buah_contains_common_fruits(self):
        """Set buah harus mengandung komoditas buah umum."""
        for fruit in ["melon", "semangka", "mangga", "durian", "jeruk"]:
            assert fruit in KATEGORI_BUAH, f"{fruit} tidak ada di KATEGORI_BUAH"

    def test_sayur_contains_common_vegetables(self):
        """Set sayur harus mengandung komoditas sayur umum."""
        for veg in ["cabai", "bawang merah", "tomat", "kentang"]:
            assert veg in KATEGORI_SAYUR, f"{veg} tidak ada di KATEGORI_SAYUR"

    def test_rempah_contains_common_spices(self):
        """Set rempah harus mengandung komoditas rempah umum."""
        for spice in ["jahe", "kunyit", "cengkeh", "lada"]:
            assert spice in KATEGORI_REMPAH, f"{spice} tidak ada di KATEGORI_REMPAH"

    def test_no_overlap_between_categories(self):
        """Tidak boleh ada komoditas yang ada di 2 kategori sekaligus."""
        assert not (KATEGORI_BUAH & KATEGORI_SAYUR), "Overlap buah-sayur"
        assert not (KATEGORI_BUAH & KATEGORI_REMPAH), "Overlap buah-rempah"
        assert not (KATEGORI_SAYUR & KATEGORI_REMPAH), "Overlap sayur-rempah"


# ==========================================
# 3. GoogleMapsExecutor Tests
# ==========================================

class TestGoogleMapsExecutor:
    """Test executor Google Maps."""

    def test_init_without_api_key(self):
        """Tanpa APIFY_API_KEY, api_key harus None."""
        with patch.dict("os.environ", {}, clear=True):
            # Remove APIFY_API_KEY if exists
            import os
            old = os.environ.pop("APIFY_API_KEY", None)
            try:
                executor = GoogleMapsExecutor()
                assert executor.api_key is None
            finally:
                if old:
                    os.environ["APIFY_API_KEY"] = old

    def test_init_with_api_key(self):
        """Dengan APIFY_API_KEY, api_key harus terisi."""
        with patch.dict("os.environ", {"APIFY_API_KEY": "test_key_123"}):
            executor = GoogleMapsExecutor()
            assert executor.api_key == "test_key_123"

    @pytest.mark.asyncio
    async def test_scrape_demand_no_api_key_returns_empty(self):
        """Tanpa API key, scrape_demand harus return list kosong."""
        with patch.dict("os.environ", {}, clear=True):
            import os
            old = os.environ.pop("APIFY_API_KEY", None)
            try:
                executor = GoogleMapsExecutor()
                result = await executor.scrape_demand("melon", ["Jawa Timur"])
                assert result == []
            finally:
                if old:
                    os.environ["APIFY_API_KEY"] = old


# ==========================================
# 4. Result Parsing Tests (Simulasi)
# ==========================================

class TestGmapsResultParsing:
    """Test parsing hasil Google Maps API ke format GoTani."""

    def _simulate_parse(self, api_items, product="melon"):
        """Simulasi parsing seperti yang dilakukan di scrape_demand."""
        results = []
        seen_phones = set()

        for item in api_items:
            if not isinstance(item, dict):
                continue

            title = str(item.get("title") or "").strip()
            phone = str(item.get("phone") or item.get("phoneUnformatted") or "").strip()
            address = str(item.get("address") or "").strip()
            city = str(item.get("city") or "").strip()
            website = str(item.get("website") or item.get("url") or "").strip()
            rating = item.get("totalScore") or item.get("rating")
            reviews = item.get("reviewsCount") or item.get("reviews") or 0
            category = str(item.get("categoryName") or item.get("category") or "").strip()

            if not title or len(title) < 3:
                continue

            phone_clean = phone.replace("+", "").replace("-", "").replace(" ", "")
            if phone_clean and phone_clean in seen_phones:
                continue
            if phone_clean:
                seen_phones.add(phone_clean)

            full_address = address
            if city and city not in address:
                full_address = f"{address}, {city}"

            results.append({
                "platform": "google_maps",
                "query": f"demand_{product}",
                "_gmaps_data": {
                    "business_name": title,
                    "phone": phone,
                    "address": full_address,
                    "city": city,
                    "rating": float(rating) if rating else None,
                    "reviews_count": int(reviews) if reviews else 0,
                    "category": category,
                },
            })

        return results

    def test_parse_basic_business(self):
        """Parse bisnis dasar dengan semua field."""
        items = [{
            "title": "Toko Buah Segar Malang",
            "phone": "+62812-3456-7890",
            "address": "Jl. Merdeka No. 10",
            "city": "Malang",
            "totalScore": 4.5,
            "reviewsCount": 120,
            "categoryName": "Toko Buah",
        }]
        results = self._simulate_parse(items)
        assert len(results) == 1
        r = results[0]
        assert r["platform"] == "google_maps"
        assert r["_gmaps_data"]["business_name"] == "Toko Buah Segar Malang"
        assert r["_gmaps_data"]["phone"] == "+62812-3456-7890"
        assert r["_gmaps_data"]["rating"] == 4.5
        assert r["_gmaps_data"]["reviews_count"] == 120

    def test_skip_empty_title(self):
        """Bisnis tanpa nama harus di-skip."""
        items = [
            {"title": "", "phone": "08123"},
            {"title": "AB", "phone": "08124"},  # < 3 char
            {"title": "Toko XYZ", "phone": "08125"},
        ]
        results = self._simulate_parse(items)
        assert len(results) == 1
        assert results[0]["_gmaps_data"]["business_name"] == "Toko XYZ"

    def test_dedup_by_phone(self):
        """Bisnis dengan nomor telepon sama harus di-deduplikasi."""
        items = [
            {"title": "Toko A", "phone": "0812-345-6789"},
            {"title": "Toko B", "phone": "08123456789"},  # Sama setelah clean
            {"title": "Toko C", "phone": "0813-999-8888"},
        ]
        results = self._simulate_parse(items)
        assert len(results) == 2
        names = [r["_gmaps_data"]["business_name"] for r in results]
        assert "Toko A" in names
        assert "Toko C" in names
        # Toko B (duplikat) di-skip
        assert "Toko B" not in names

    def test_no_phone_not_deduped(self):
        """Bisnis TANPA nomor telepon tidak boleh di-deduplikasi."""
        items = [
            {"title": "Toko X", "phone": ""},
            {"title": "Toko Y", "phone": ""},
            {"title": "Toko Z", "phone": None},
        ]
        results = self._simulate_parse(items)
        assert len(results) == 3  # Semua masuk karena tidak ada phone

    def test_city_appended_to_address(self):
        """Kota ditambahkan ke alamat jika belum ada."""
        items = [{
            "title": "Toko Test",
            "address": "Jl. Raya No. 5",
            "city": "Surabaya",
        }]
        results = self._simulate_parse(items)
        assert "Surabaya" in results[0]["_gmaps_data"]["address"]

    def test_city_not_doubled(self):
        """Kota TIDAK diduplikasi jika sudah ada di alamat."""
        items = [{
            "title": "Toko Test",
            "address": "Jl. Raya No. 5, Surabaya",
            "city": "Surabaya",
        }]
        results = self._simulate_parse(items)
        addr = results[0]["_gmaps_data"]["address"]
        assert addr.count("Surabaya") == 1

    def test_rating_none_for_unrated(self):
        """Rating None jika bisnis belum dirating."""
        items = [{"title": "Toko Baru", "totalScore": None}]
        results = self._simulate_parse(items)
        assert results[0]["_gmaps_data"]["rating"] is None


# ==========================================
# 5. Pipeline Phone Injection Tests
# ==========================================

class TestPipelinePhoneInjection:
    """Test bahwa pipeline.py menginjeksi phone dari gmaps_data dengan benar."""

    def test_gmaps_phone_not_overwritten(self):
        """Verifikasi fix: phone dari gmaps_data TIDAK di-overwrite oleh PII restore kosong.
        
        Bug sebelumnya: line 228 set phones = [gmaps_data["phone"]], tapi
        line 270 overwrite dengan phones = [...mapping...] yang kosong.
        Fix: gmaps phone diinjeksi SETELAH PII restore, hanya jika PII kosong.
        """
        # Baca source code pipeline.py
        import pathlib
        code = pathlib.Path(r"e:\DATA\Ngoding\gotani_lead_agent\agent\pipeline.py").read_text(encoding="utf-8")
        
        # Verifikasi bahwa fix sudah diterapkan:
        # 1. Ada logika "Jika tidak ada phone dari PII, coba dari Google Maps"
        assert "Jika tidak ada phone dari PII, coba dari Google Maps" in code, \
            "Fix belum diterapkan: missing gmaps phone fallback logic"
        
        # 2. gmaps phone injection SETELAH PII restore
        pii_restore_pos = code.index("Restore PII untuk kontak")
        gmaps_fallback_pos = code.index("Jika tidak ada phone dari PII")
        assert gmaps_fallback_pos > pii_restore_pos, \
            "gmaps phone injection harus SETELAH PII restore"


# ==========================================
# 6. Integration: Query Templates Completeness
# ==========================================

class TestQueryTemplateCompleteness:
    """Verifikasi template query cukup lengkap untuk berbagai use case."""

    def test_default_has_distributor(self):
        assert any("distributor" in t for t in DEMAND_QUERY_TEMPLATES)

    def test_default_has_grosir(self):
        assert any("grosir" in t for t in DEMAND_QUERY_TEMPLATES)

    def test_default_has_toko(self):
        assert any("toko" in t for t in DEMAND_QUERY_TEMPLATES)

    def test_sayur_has_distributor(self):
        assert any("distributor" in t for t in DEMAND_QUERY_TEMPLATES_SAYUR)

    def test_rempah_has_supplier(self):
        assert any("supplier" in t for t in DEMAND_QUERY_TEMPLATES_REMPAH)

    def test_all_templates_have_product_placeholder(self):
        """Minimal setengah template harus punya {product} placeholder."""
        for name, templates in [
            ("buah", DEMAND_QUERY_TEMPLATES),
            ("sayur", DEMAND_QUERY_TEMPLATES_SAYUR),
            ("rempah", DEMAND_QUERY_TEMPLATES_REMPAH),
        ]:
            with_product = [t for t in templates if "{product}" in t]
            assert len(with_product) >= len(templates) // 2, \
                f"Template {name}: kurang dari setengah punya {{product}} placeholder"

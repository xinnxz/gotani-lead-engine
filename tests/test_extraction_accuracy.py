"""Test case untuk peningkatan akurasi ekstraksi data GoTani.

Menguji:
1. Ekstraksi nama pemosting dari pola Facebook snippet
2. Ekstraksi lokasi dari nama grup Facebook
3. Harga dengan unit non-standar (kresek, ikat, karung)
4. Volume dengan unit non-standar
5. Klasifikasi intent tetap benar
"""
import pytest
from agent.campaign import CampaignSpec
from agent.rules import (
    extract, classify_intent, _extract_fb_author,
    _extract_location_from_group, _parse_non_kg_price, _parse_non_kg_volume,
)


def _melon_spec():
    c = CampaignSpec(campaign_id="test_melon", goal="find_supply")
    c.product.name = "melon"
    c.product.synonyms = ["melon", "semangka", "watermelon"]
    return c


class TestFbAuthorExtraction:
    """Test ekstraksi nama pemosting dari pola snippet Google Search Facebook."""

    def test_standard_fb_pattern(self):
        """Pola: 'NamaGrup · NamaAuthor · Tanggal · 🌐'"""
        text = "KUNIR GANDEKAN KARANGGAYAM (serba-serbi) · Al Farisy · 19 Oktober · 🌐\nReady melon amanda suluhan manis nyus 1 kresek 15k saja"
        assert _extract_fb_author(text) == "Al Farisy"

    def test_fb_pattern_with_dash(self):
        """Pola: 'NamaGrup - NamaAuthor - Tanggal'"""
        text = "Petani Melon Nganjuk - Budi Santoso - 2 hari lalu\nReady melon madesta 500kg"
        assert _extract_fb_author(text) == "Budi Santoso"

    def test_fb_pattern_posted_in(self):
        """Pola: 'NamaAuthor posted in NamaGrup'"""
        text = "Ahmad Rizal posted in Petani Cabai Jawa Timur\nJual cabai rawit 100kg"
        assert _extract_fb_author(text) == "Ahmad Rizal"

    def test_no_author_found(self):
        """Tidak ada pola author → return None."""
        text = "Ready melon madesta 500kg harga 7rb/kg WA 08123456789"
        assert _extract_fb_author(text) is None

    def test_reject_group_name_as_author(self):
        """Nama grup mengandung 'Petani'/'Komunitas' → bukan author."""
        text = "Grup Petani · Komunitas Petani Jatim · 2 hari lalu\nJual melon"
        result = _extract_fb_author(text)
        # Should not return "Komunitas Petani Jatim" as author
        assert result is None or "komunitas" not in (result or "").lower()


class TestLocationFromGroup:
    """Test ekstraksi lokasi dari nama grup Facebook."""

    def test_known_region_in_group(self):
        """Nama grup mengandung kab/kota yang dikenal."""
        text = "Petani Melon Nganjuk\nReady melon madesta 500kg"
        loc = _extract_location_from_group(text)
        assert loc is not None and "nganjuk" in loc.lower()

    def test_province_alias_in_group(self):
        """Nama grup mengandung alias provinsi."""
        text = "Jual Beli Buah Jatim\nReady melon golden"
        loc = _extract_location_from_group(text)
        assert loc is not None and "Jawa Timur" in loc


class TestNonKgPrice:
    """Test harga dengan unit non-standar."""

    def test_price_per_kresek(self):
        """'15k/kresek' → price 15000, unit 'kresek'."""
        price, unit, _ = _parse_non_kg_price("harga 15k/kresek")
        assert price == 15000
        assert unit == "kresek"

    def test_price_per_ikat(self):
        """'5rb/ikat' → price 5000, unit 'ikat'."""
        price, unit, _ = _parse_non_kg_price("harga 5rb/ikat")
        assert price == 5000
        assert unit == "ikat"

    def test_price_per_karung(self):
        """'200rb/karung' → price 200000, unit 'karung'."""
        price, unit, _ = _parse_non_kg_price("harga 200rb/karung")
        assert price == 200000
        assert unit == "karung"

    def test_price_per_dos(self):
        """'150.000/dos' → price 150000, unit 'dos'."""
        price, unit, _ = _parse_non_kg_price("rp 150.000/dos")
        assert price == 150000
        assert unit == "dos"

    def test_no_non_kg_price(self):
        """'7rb/kg' bukan non-kg → return None."""
        price, unit, _ = _parse_non_kg_price("harga 7rb/kg")
        assert price is None


class TestNonKgVolume:
    """Test volume dengan unit non-standar."""

    def test_volume_kresek(self):
        """'1 kresek' → volume 1, unit 'kresek'."""
        vol, unit, _ = _parse_non_kg_volume("ready 1 kresek melon")
        assert vol == 1
        assert unit == "kresek"

    def test_volume_karung(self):
        """'10 karung' → volume 10, unit 'karung'."""
        vol, unit, _ = _parse_non_kg_volume("stok 10 karung bawang")
        assert vol == 10
        assert unit == "karung"

    def test_volume_ikat(self):
        """'5 ikat' → volume 5, unit 'ikat'."""
        vol, unit, _ = _parse_non_kg_volume("ready 5 ikat kangkung")
        assert vol == 5
        assert unit == "ikat"


class TestFullExtractAccuracy:
    """Test ekstraksi lengkap dengan data realistis."""

    def test_melon_kresek_post(self):
        """Post Al Farisy: melon amanda 15k/kresek."""
        text = (
            "KUNIR GANDEKAN KARANGGAYAM (serba-serbi) · Al Farisy · 19 Oktober · 🌐\n"
            "Ready melon amanda suluhan manis nyus 1 kresek 15k saja pcc lempung wa [PHONE_1]"
        )
        spec = _melon_spec()
        result = extract(text, spec)

        assert result["intent"] == "supply"
        assert result["entity_name"] == "Al Farisy"
        assert result["product"] == "melon"
        assert result.get("variety") is not None  # Amanda atau Suluhan
        # Harga harus per kresek, BUKAN per kg
        if result.get("price_unit"):
            assert result["price_unit"] == "kresek"
        # Volume harus per kresek, BUKAN 20 kg
        if result.get("volume_unit"):
            assert result["volume_unit"] == "kresek"

    def test_melon_kg_post(self):
        """Post standar dengan harga per kg."""
        text = "Petani Melon Nganjuk · Pak Budi · 2 hari lalu\nReady melon madesta super 500kg harga 7rb/kg COD Nganjuk"
        spec = _melon_spec()
        result = extract(text, spec)

        assert result["intent"] == "supply"
        assert result["entity_name"] == "Pak Budi"
        assert result["product"] == "melon"
        assert result["price_unit"] == "kg"
        assert result["price_value"] == 7000
        assert result["volume_unit"] == "kg"
        assert result["volume_value"] == 500

    def test_intent_still_works(self):
        """Intent classification tidak rusak setelah perubahan."""
        spec = _melon_spec()
        assert classify_intent("Ready melon 500kg jual cepat wa 08123", spec) == "supply"
        assert classify_intent("Butuh melon 2 ton untuk hotel", spec) == "demand"
        assert classify_intent("Tips menanam melon agar berbuah banyak", spec) == "irrelevant"
        assert classify_intent("Jual bibit melon unggul", spec) == "other"

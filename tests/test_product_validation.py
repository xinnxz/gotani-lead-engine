"""Tests for strict product validation and non-agri penalty."""
import pytest
from agent.scoring import relevance
from agent.campaign import CampaignSpec


class TestNonAgriPenalty:
    """Test bahwa konten non-pertanian mendapat penalti keras."""

    def _make_spec(self, product="melon"):
        spec = CampaignSpec(campaign_id="test", goal="find_supply")
        spec.product.name = product
        return spec

    def test_pipa_gets_massive_penalty(self):
        """Post tentang pipa harus mendapat penalti -80."""
        spec = self._make_spec("melon")
        listing = {"product": "melon", "intent": "supply"}
        raw = "Jual pipa scaffolding meyediakan berbagai ukuran WA 0812345"
        score, why = relevance(listing, spec, raw)
        assert score == 0, f"Post tentang pipa harusnya skor 0, dapat {score}"
        assert any("-80" in w for w in why), "Harus ada penalti -80 non-pertanian"

    def test_besi_gets_penalty(self):
        """Post tentang besi baja harus ditolak."""
        spec = self._make_spec("cabai")
        listing = {"product": "cabai", "intent": "supply"}
        raw = "Jual besi baja murah harga terjangkau Surabaya hub 08123"
        score, why = relevance(listing, spec, raw)
        assert score == 0

    def test_real_melon_post_no_penalty(self):
        """Post melon asli TIDAK boleh kena penalti non-agri."""
        spec = self._make_spec("melon")
        listing = {"product": "melon", "intent": "supply", "posted_at": None}
        raw = "Ready melon inthanon grade A 25rb/kg lokasi Kediri wa 0812345"
        score, why = relevance(listing, spec, raw)
        assert score >= 40, f"Post melon asli harusnya skor tinggi, dapat {score}"
        assert not any("non-pertanian" in w for w in why)

    def test_elektronik_gets_penalty(self):
        """Post tentang elektronik harus ditolak."""
        spec = self._make_spec("melon")
        listing = {"product": "melon", "intent": "supply"}
        raw = "Jual laptop gaming second murah Surabaya ready stok"
        score, why = relevance(listing, spec, raw)
        assert score == 0


class TestProductValidation:
    """Test validasi keras: komoditas harus ada di raw_text."""

    def test_product_not_in_text_classified_irrelevant(self):
        """Jika 'melon' tidak ada di raw_text, extract harus return irrelevant."""
        from agent.rules import extract, classify_intent
        spec = CampaignSpec(campaign_id="test", goal="find_supply")
        spec.product.name = "melon"
        # Teks tentang pipa - tidak ada kata "melon"
        text = "Jual pipa scaffolding berbagai ukuran WA 08123"
        result = extract(text, spec)
        # product harus None (tidak ditemukan) dan intent bukan supply
        assert result["product"] is None or result["intent"] in ("irrelevant", "other")

    def test_product_in_text_classified_correctly(self):
        """Jika 'melon' ada di raw_text, extract harus benar."""
        from agent.rules import extract
        spec = CampaignSpec(campaign_id="test", goal="find_supply")
        spec.product.name = "melon"
        text = "Ready melon inthanon 2 ton grade A WA 08123"
        result = extract(text, spec)
        assert result["product"] == "melon"
        assert result["intent"] == "supply"

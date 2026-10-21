"""Tests for Malaysia content filter and expanded non-agri keywords."""
import pytest
from agent.scoring import relevance, _is_malaysian_content
from agent.campaign import CampaignSpec


class TestMalaysiaFilter:
    """Test konten Malaysia otomatis ditolak (skor 0)."""

    def _make_spec(self, product="durian"):
        spec = CampaignSpec(campaign_id="test", goal="find_supply")
        spec.product.name = product
        return spec

    def test_rm_currency_detected(self):
        """Teks dengan harga RM = Malaysia."""
        assert _is_malaysian_content("Durian musang king RM50/kg stok banyak") is True

    def test_malaysian_state_detected(self):
        """Teks dari negeri Malaysia terdeteksi."""
        assert _is_malaysian_content("Dijual durian di Pahang, harga RM80") is True

    def test_kuala_krai_detected(self):
        """Kuala Krai = wilayah Malaysia."""
        assert _is_malaysian_content("Kuala Krai Group durian musang king ready RM45") is True

    def test_hartanah_detected(self):
        """Hartanah = properti dalam bahasa Melayu Malaysia."""
        assert _is_malaysian_content("2 LOT TANAH BANGLO GUNTUNG LIMBAT UNTUK DIJUAL") is True

    def test_indonesian_content_not_flagged(self):
        """Konten Indonesia asli TIDAK boleh kena filter Malaysia."""
        assert _is_malaysian_content("Jual durian montong 500 kg Rp 35.000/kg Jombang wa 081234") is False

    def test_indonesian_with_rupiah(self):
        """Post Indonesia pakai Rp = aman."""
        assert _is_malaysian_content("Ready durian monthong grade A Rp 50rb lokasi Kediri") is False

    def test_scoring_rejects_malaysian_durian(self):
        """Post durian Malaysia harus skor 0."""
        spec = self._make_spec("durian")
        listing = {"product": "durian", "intent": "supply"}
        raw = "Durian black thorn ready RM60/kg Pahang boleh bincang wa +60123456789"
        score, why = relevance(listing, spec, raw)
        assert score == 0, f"Post Malaysia harusnya skor 0, dapat {score}"
        assert any("malaysia" in w.lower() for w in why)

    def test_scoring_accepts_indonesian_durian(self):
        """Post durian Indonesia harus skor tinggi."""
        spec = self._make_spec("durian")
        listing = {"product": "durian", "intent": "supply"}
        raw = "Ready durian montong super 500 kg harga Rp 40rb/kg lokasi Medan wa 081234567890"
        score, why = relevance(listing, spec, raw)
        assert score >= 40, f"Post Indonesia harusnya skor tinggi, dapat {score}"


class TestExpandedNonAgri:
    """Test keyword non-agri yang diperluas."""

    def _make_spec(self, product="durian"):
        spec = CampaignSpec(campaign_id="test", goal="find_supply")
        spec.product.name = product
        return spec

    def test_banglo_gets_penalty(self):
        """Post tentang banglo (properti) harus ditolak."""
        spec = self._make_spec("durian")
        listing = {"product": "durian", "intent": "supply"}
        raw = "Dijual lot tanah banglo 2 ekar lokasi strategis hubungi 0812345"
        score, why = relevance(listing, spec, raw)
        assert score == 0

    def test_kavling_gets_penalty(self):
        """Post tentang kavling tanah harus ditolak."""
        spec = self._make_spec("durian")
        listing = {"product": "durian", "intent": "supply"}
        raw = "Kavling tanah murah dekat jalan raya cocok untuk investasi 0812345"
        score, why = relevance(listing, spec, raw)
        assert score == 0

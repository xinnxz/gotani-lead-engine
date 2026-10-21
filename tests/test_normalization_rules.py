"""Unit Test Profesional: Normalisasi Data & Skoring Relevansi (PRD F3.3 & §7.4).

Memastikan aturan parsing kuantitas (tonase ke kg), mata uang, nomor telepon,
serta skoring relevansi dan confidence bekerja secara konsisten tanpa anomali.
"""
import pytest
from datetime import datetime
from agent.normalize import (
    normalize_phone,
    to_kg,
    parse_number,
    parse_price,
    parse_quantity,
)
from agent.scoring import relevance, confidence
from agent.campaign import CampaignSpec, Product, Location


class TestDataNormalization:
    """Uji konversi data mentah teks ke nilai terstruktur."""

    def test_normalize_phone_formats(self):
        # Format 08
        assert normalize_phone("081234567890") == "+6281234567890"
        # Format dengan spasi dan tanda minus
        assert normalize_phone("0812-3456-7890") == "+6281234567890"
        assert normalize_phone("0812 3456 7890") == "+6281234567890"
        # Format internasional tanpa plus
        assert normalize_phone("6281234567890") == "+6281234567890"
        # Format internasional dengan plus
        assert normalize_phone("+62 812-3456-7890") == "+6281234567890"
        # Format tidak valid (terlalu pendek atau bukan nomor Indonesia)
        assert normalize_phone("12345") is None
        assert normalize_phone("abcde") is None

    def test_weight_unit_conversion_to_kg(self):
        assert to_kg(2.0, "ton") == 2000.0
        assert to_kg(1.5, "t") == 1500.0
        assert to_kg(5.0, "kuintal") == 500.0
        assert to_kg(3.0, "kw") == 300.0
        assert to_kg(250.0, "kg") == 250.0
        assert to_kg(500.0, "gram") == 0.5
        assert to_kg(None, "ton") is None

    def test_parse_indonesian_number_styles(self):
        assert parse_number("1.500") == 1500.0
        assert parse_number("2,5") == 2.5
        assert parse_number("10.000,50") == 10000.5
        assert parse_number("invalid") is None

    def test_parse_price_variations(self):
        # Format standar rupiah per kg
        p1, raw1, _ = parse_price("Harga Rp 8.000/kg nego di lokasi")
        assert p1 == 8000

        # Format ribuan 'rb/kilo'
        p2, raw2, _ = parse_price("Dijual 7.5rb/kilo petik sendiri")
        assert p2 == 7500

        # Format 'k' per kilo
        p3, raw3, _ = parse_price("Net 9k/kg kualitas super grade A")
        assert p3 == 9000

    def test_parse_quantity_variations(self):
        # Format tonase
        qty1, raw1 = parse_quantity("Estimasi hasil panen 3 ton siap angkut")
        assert qty1 == 3000.0
        assert "3 ton" in raw1

        # Format kuintal
        qty2, raw2 = parse_quantity("Ada sisa sekitar 8 kuintal di gudang")
        assert qty2 == 800.0


class TestScoringRules:
    """Uji perhitungan skor relevansi dan confidence berdasarkan CampaignSpec."""

    @pytest.fixture
    def melon_spec(self):
        return CampaignSpec(
            campaign_id="cmp-melon-test",
            goal="find_supply",
            product=Product(name="melon", attributes={"variety": ["madesta", "golden"]}),
            location=Location(include=["Jawa Timur", "Ngawi", "Nganjuk"], exclude=["Bali"]),
        )

    def test_high_relevance_matching_lead(self, melon_spec):
        listing = {
            "product": "melon",
            "intent": "supply",
            "kabupaten": "Ngawi",
            "provinsi": "Jawa Timur",
            "volume_kg": 2000.0,
            "price_per_kg": 8000.0,
            "contact_phone": "+6281234567890",
        }
        raw_text = "Panen raya melon madesta Ngawi 2 ton harga 8rb per kilo hubungi 081234567890"
        score, why = relevance(listing, melon_spec, raw_text)
        assert score >= 70
        assert any("produk cocok" in w for w in why)
        assert any("niat sesuai" in w for w in why)

    def test_low_relevance_mismatching_product(self, melon_spec):
        listing = {
            "product": "cabai rawit",
            "intent": "supply",
            "kabupaten": "Ngawi",
            "provinsi": "Jawa Timur",
        }
        raw_text = "Jual cabai rawit merah petik segar Ngawi"
        score, why = relevance(listing, melon_spec, raw_text)
        assert score < 50
        assert any("PENALTI" in w for w in why)

    def test_confidence_scoring_data_completeness(self, melon_spec):
        complete_listing = {
            "product": "melon",
            "intent": "supply",
            "kabupaten": "Nganjuk",
            "volume_kg": 1500.0,
            "price_per_kg": 8500.0,
            "contact_phone": "+6281234567890",
            "posted_at": datetime.now().isoformat(),
        }
        conf_score, conf_why = confidence(complete_listing, melon_spec, platform="fb", confirmations=1)
        assert conf_score >= 60

        incomplete_listing = {
            "product": "melon",
            "intent": "supply",
        }
        low_conf, _ = confidence(incomplete_listing, melon_spec, platform="fb", confirmations=0)
        assert low_conf < 40

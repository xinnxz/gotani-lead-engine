"""Unit Test Khusus: Kualitas, Akurasi Tinggi, dan Penyaringan Postingan Usang (Freshness).

Memastikan:
1. Postingan kadaluwarsa (misal 2 tahun lalu) terdeteksi dan dipenalti keras.
2. Judul grup tidak mengecoh komoditas postingan (post kelapa di grup cabai otomatis ditolak).
3. Postingan sampah tanpa kontak/volume/harga dibatasi confidence skornya.
"""
import pytest
from datetime import datetime, timedelta
from agent.normalize import parse_posted_date
from agent.rules import extract
from agent.scoring import relevance, confidence
from agent.campaign import CampaignSpec, Product, Location


class TestAccuracyAndFreshness:
    """Uji ketahanan sistem terhadap false-positive dan data basi."""

    @pytest.fixture
    def cabai_spec(self):
        return CampaignSpec(
            campaign_id="cmp-cabai-jatim",
            goal="find_supply",
            product=Product(name="cabai", attributes={"variety": ["rawit", "keriting"]}),
            location=Location(include=["Jawa Timur", "Kediri", "Blitar"]),
        )

    def test_parse_posted_date_relative_indonesian(self):
        # 2 tahun lalu
        d1 = parse_posted_date("Jual cabai rawit merah petik segar. 2 tahun lalu — diposting oleh Budi")
        assert d1 is not None
        dt1 = datetime.fromisoformat(d1)
        assert (datetime.now() - dt1).days >= 700

        # 3 bulan lalu
        d2 = parse_posted_date("Ready cabai 5 kuintal. 3 bulan lalu — stok di gudang")
        assert d2 is not None
        dt2 = datetime.fromisoformat(d2)
        assert 80 <= (datetime.now() - dt2).days <= 100

        # Kemarin
        d3 = parse_posted_date("Panen raya cabai rawit kemarin sore harga 25rb")
        assert d3 is not None
        dt3 = datetime.fromisoformat(d3)
        assert (datetime.now() - dt3).days == 1

    def test_reject_competing_crop_in_group_name(self, cabai_spec):
        """Kasus nyata Arsen: Postingan kelapa di grup yang memuat kata cabai."""
        fake_post = (
            "JUAL BELI CABAI DAN KELAPA TUA JAWA TIMUR | Facebook\n"
            "Ready kelapa tua super 5 ton borongan dari kebun, hubungi WA 081297070101"
        )
        res = extract(fake_post, cabai_spec)
        # Sistem HARUS mengidentifikasi bahwa ini bukan cabai, melainkan kelapa
        assert res["intent"] == "irrelevant"
        assert res["product"] == "kelapa"
        assert "komoditas_berbeda" in res["flags"]

    def test_scoring_penalizes_old_posts(self, cabai_spec):
        """Postingan dari 2 tahun lalu harus mendapatkan penalti berat."""
        two_years_ago = (datetime.now() - timedelta(days=730)).date().isoformat()
        listing = {
            "product": "cabai",
            "intent": "supply",
            "kabupaten": "Kediri",
            "volume_kg": 1000.0,
            "price_per_kg": 25000.0,
            "contact_phone": "+6281234567890",
            "posted_at": two_years_ago,
        }
        raw_text = "Panen cabai rawit 1 ton kediri harga 25rb hub 081234567890"

        rel_score, rel_why = relevance(listing, cabai_spec, raw_text)
        conf_score, conf_why = confidence(listing, cabai_spec, platform="facebook", confirmations=1)

        # Relevansi harus jatuh karena penalti kedaluwarsa
        assert any("KADALUWARSA" in w for w in rel_why)
        assert rel_score < 50
        # Confidence harus dibatasi maksimal 20%
        assert conf_score <= 20
        assert any("kadaluwarsa" in w.lower() for w in conf_why)

    def test_scoring_penalizes_incomplete_commercial_data(self, cabai_spec):
        """Postingan tanpa kontak, tanpa volume, dan tanpa harga harus rendah confidence-nya."""
        empty_listing = {
            "product": "cabai",
            "intent": "supply",
            "kabupaten": "Kediri",
            # Tidak ada volume, tidak ada harga, tidak ada kontak
        }
        raw_text = "Siapa yang butuh cabai rawit bisa merapat"
        conf_score, conf_why = confidence(empty_listing, cabai_spec, platform="facebook", confirmations=1)
        assert conf_score <= 30
        assert any("minim data komersial" in w.lower() for w in conf_why)

    def test_reject_cengkeh_post_in_jahe_preset_and_parse_facebook_english_date(self):
        """Kasus nyata Arsen: Postingan cengkeh 30 ton 12 Desember 2024 di preset jahe."""
        jahe_spec = CampaignSpec(
            campaign_id="cmp-jahe-nasional",
            goal="find_supply",
            product=Product(name="jahe", attributes={"variety": ["gajah", "emprit", "merah"]}),
            location=Location(include=["Indonesia"]),
        )
        fake_post = (
            "Komunitas Eksportir Indonesia (Indonesian Exporter Community) · Aqella Al Agniyah Sutisna · December 12, 2024 · 🌐\n"
            "cengkeh Ready 30 ton harga 110rb minat wa 08569009485"
        )
        # 1. Tanggal bahasa Inggris 'December 12, 2024' harus terbaca dengan benar
        detected_date = parse_posted_date(fake_post)
        assert detected_date == "2024-12-12"

        # 2. Rule extractor HARUS menolak postingan cengkeh saat mencari jahe
        res = extract(fake_post, jahe_spec, posted_at=detected_date)
        assert res["intent"] == "irrelevant"
        assert res["product"] == "cengkeh"
        assert "komoditas_berbeda" in res["flags"]

        # 3. Relevansi harus dihukum ganda: produk tidak cocok (-50) dan kadaluwarsa (-60)
        rel_score, rel_why = relevance(res, jahe_spec, fake_post)
        assert rel_score == 0  # Clamped to 0
        assert any("KADALUWARSA" in w for w in rel_why)
        assert any("bukan jahe" in w.lower() for w in rel_why)

    def test_match_card_null_formatting_safe(self):
        """Memastikan ketiadaan volume/anggaran pada listing demand tidak memicu TypeError di UI f-string."""
        m = {
            "match_id": "m-test-1",
            "kind": "single",
            "tier": "review",
            "buyer_name": "Pak Hendra",
            "buyer_location": "Surabaya",
            "product": "jahe",
            "buyer_vol": None,          # Null volume
            "buyer_max_price": None,    # Null price
            "score": 75,
            "coverage_pct": None,       # Null coverage
        }
        # Evaluasi f-string yang sama persis dengan app.py line 1147-1155
        vol_str = f"{m['buyer_vol']:g} kg" if m.get('buyer_vol') is not None else "Tidak ditentukan"
        price_str = f"Rp {float(m['buyer_max_price']):,.0f}/kg" if m.get('buyer_max_price') is not None else 'Belum ditentukan'
        cov_str = f"{m['coverage_pct']:g}%" if m.get('coverage_pct') is not None else "-"

        assert vol_str == "Tidak ditentukan"
        assert price_str == "Belum ditentukan"
        assert cov_str == "-"

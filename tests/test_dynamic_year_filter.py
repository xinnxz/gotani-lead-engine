"""Test suite untuk dynamic year filter & advanced date parsing."""
import re
from datetime import datetime, timedelta
import pytest

from agent.normalize import parse_posted_date


class TestDynamicYearFilter:
    """Verifikasi bahwa tahun lampau terdeteksi secara dinamis, bukan hardcoded."""

    def test_year_2025_detected_as_stale(self):
        """2025 harus terdeteksi sebagai tahun lampau di tahun 2026."""
        result = parse_posted_date("Posting dari 2025 tentang melon")
        assert result is not None
        assert result.startswith("2025")

    def test_year_2024_detected_as_stale(self):
        """2024 harus terdeteksi sebagai tahun lampau."""
        result = parse_posted_date("Jual cabai Desember 2024")
        # Should match pattern "Desember 2024" → 2024-12-01
        assert result is not None
        assert "2024" in result

    def test_current_year_not_blocked(self):
        """Tahun ini (2026) TIDAK boleh diblokir oleh filter stale year."""
        cur_year = datetime.now().year
        result = parse_posted_date(f"Panen melon {cur_year}")
        # Current year should NOT be caught by stale filter
        # It might match "Month Year" pattern or not, but should NOT be forced to YYYY-01-01
        if result:
            # If detected, should not be forced to jan-01 via stale catch-all
            assert not result.endswith("-01-01") or str(cur_year) not in result

    def test_explicit_date_with_month_year_2025(self):
        """'Mei 2025' harus menghasilkan 2025-05-01."""
        result = parse_posted_date("Panen besar mei 2025 di Kediri")
        assert result == "2025-05-01"

    def test_old_year_2019(self):
        """2019 harus terdeteksi sebagai tahun lampau."""
        result = parse_posted_date("Posting lama dari 2019")
        assert result is not None
        assert "2019" in result


class TestAdvancedDatePatterns:
    """Test pola tanggal lanjutan yang baru ditambahkan."""

    def test_baru_saja(self):
        """'baru saja' harus menghasilkan hari ini."""
        result = parse_posted_date("baru saja diposting oleh petani")
        assert result == datetime.now().date().isoformat()

    def test_just_now(self):
        """'just now' harus menghasilkan hari ini."""
        result = parse_posted_date("posted just now by admin")
        assert result == datetime.now().date().isoformat()

    def test_jam_lalu(self):
        """'3 jam lalu' harus menghasilkan hari ini (atau kemarin jika tengah malam)."""
        result = parse_posted_date("diposting 3 jam lalu")
        assert result is not None
        # Should be today or yesterday
        today = datetime.now().date().isoformat()
        yesterday = (datetime.now() - timedelta(days=1)).date().isoformat()
        assert result in (today, yesterday)

    def test_menit_lalu(self):
        """'15 menit lalu' harus menghasilkan hari ini."""
        result = parse_posted_date("15 menit lalu")
        assert result == datetime.now().date().isoformat()

    def test_days_ago_english(self):
        """'3 days ago' harus menghasilkan 3 hari lalu."""
        result = parse_posted_date("posted 3 days ago in group")
        expected = (datetime.now() - timedelta(days=3)).date().isoformat()
        assert result == expected

    def test_weeks_ago_english(self):
        """'2 weeks ago' harus menghasilkan 14 hari lalu."""
        result = parse_posted_date("shared 2 weeks ago")
        expected = (datetime.now() - timedelta(days=14)).date().isoformat()
        assert result == expected

    def test_kemarin(self):
        """'kemarin' harus menghasilkan 1 hari lalu."""
        result = parse_posted_date("posting kemarin sore")
        expected = (datetime.now() - timedelta(days=1)).date().isoformat()
        assert result == expected

    def test_bulan_lalu(self):
        """'1 bulan lalu' harus menghasilkan ~30 hari lalu."""
        result = parse_posted_date("diposting 1 bulan lalu")
        expected = (datetime.now() - timedelta(days=30)).date().isoformat()
        assert result == expected


class TestScoringDynamicYear:
    """Verifikasi bahwa scoring.py juga memblokir tahun lampau secara dinamis."""

    def test_scoring_blocks_2025(self):
        """Teks dengan tahun 2025 harus mendapat penalti kadaluwarsa di scoring."""
        from agent.scoring import relevance
        from agent.campaign import CampaignSpec

        spec = CampaignSpec(campaign_id="test", goal="find_supply")
        spec.product.name = "melon"
        spec.product.synonyms = ["melon"]

        listing = {"product": "melon", "intent": "supply", "posted_at": None}
        raw_text = "Jual melon madesta 2025 di Kediri"

        score, reasons = relevance(listing, spec, raw_text)
        # Harus mendapat penalti kadaluwarsa
        assert score == 0
        assert any("KADALUWARSA" in r for r in reasons)

# ============================================
# Tests untuk parse_posted_date: Day Month tanpa tahun
# ============================================

class TestParseDateWithoutYear:
    """Test deteksi tanggal Facebook format '29 March' tanpa tahun."""

    def test_day_month_english_march(self):
        """'29 March' harus terdeteksi sebagai 29 Maret tahun ini."""
        from agent.normalize import parse_posted_date
        result = parse_posted_date("Ravindra . 29 March")
        assert result is not None
        assert result.endswith("-03-29")

    def test_day_month_english_october(self):
        """'5 October' harus terdeteksi sebagai 5 Oktober."""
        from agent.normalize import parse_posted_date
        result = parse_posted_date("5 October")
        assert result is not None
        assert "-10-05" in result

    def test_month_day_english(self):
        """'March 29' (English format) harus terdeteksi."""
        from agent.normalize import parse_posted_date
        result = parse_posted_date("March 29")
        assert result is not None
        assert "-03-29" in result

    def test_day_month_indonesian(self):
        """'12 mei' harus terdeteksi sebagai 12 Mei."""
        from agent.normalize import parse_posted_date
        result = parse_posted_date("12 mei")
        assert result is not None
        assert "-05-12" in result

    def test_old_date_detected_as_stale(self):
        """Post dari 29 March (7 bulan lalu) harus terdeteksi > 35 hari."""
        from agent.normalize import parse_posted_date
        from datetime import datetime
        result = parse_posted_date("29 March")
        assert result is not None
        dt = datetime.fromisoformat(result)
        age = (datetime.now() - dt).days
        # Maret ke Oktober = minimal 200 hari
        assert age > 35, f"Post 29 March seharusnya stale (age={age} hari)"

    def test_recent_date_not_stale(self):
        """Post dari bulan ini harus fresh (< 35 hari)."""
        from agent.normalize import parse_posted_date
        from datetime import datetime
        # Gunakan tanggal awal bulan ini
        now = datetime.now()
        month_name = ["january","february","march","april","may","june",
                      "july","august","september","october","november","december"][now.month - 1]
        result = parse_posted_date(f"1 {month_name}")
        assert result is not None
        dt = datetime.fromisoformat(result)
        age = (datetime.now() - dt).days
        assert age <= 35, f"Post awal bulan ini seharusnya fresh (age={age} hari)"

    def test_no_dangerous_today_fallback(self):
        """Teks tanpa tanggal harus return None, BUKAN hari ini."""
        from agent.normalize import parse_posted_date
        result = parse_posted_date("Ready melon premium grade A")
        assert result is None, "Teks tanpa tanggal harus return None"

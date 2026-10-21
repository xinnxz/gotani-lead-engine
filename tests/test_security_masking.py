"""Unit Test Profesional: Masking Data Pribadi & Kepatuhan Guardrails (PRD F3.6 & G9).

Memastikan nomor telepon seluler, telepon rumah, dan alamat email di-masking
secara sempurna sebelum dikirimkan ke model LLM untuk mencegah kebocoran data pribadi (PII).
"""
import pytest
from agent.masking import mask_text, find_pii


class TestSecurityMasking:
    """Test suite untuk validasi pengaburan data pribadi (PII Masking)."""

    def test_mask_single_mobile_phone(self):
        raw = "Petani melon Ngawi siap panen, silakan hubungi WA 081234567890."
        masked, mapping = mask_text(raw)
        assert "[PHONE_1]" in masked
        assert "081234567890" not in masked
        assert mapping["[PHONE_1]"] == "081234567890"

    def test_mask_international_format_phone(self):
        raw = "Kontak admin distributor: +6281987654321 untuk penawaran."
        masked, mapping = mask_text(raw)
        assert "[PHONE_1]" in masked
        assert "6281987654321" not in masked
        assert mapping["[PHONE_1]"] == "6281987654321"

    def test_mask_multiple_phones_and_consistency(self):
        raw = "Hubungi Pak Budi di 0812-3456-7890 atau nomor cadangan 0857-1122-3344. Ulangi: 0812-3456-7890."
        masked, mapping = mask_text(raw)
        assert "[PHONE_1]" in masked
        assert "[PHONE_2]" in masked
        # Nomor yang sama harus mendapatkan token yang sama
        assert masked.count("[PHONE_1]") == 2
        assert len(mapping) == 2

    def test_mask_email_addresses(self):
        raw = "Kirim proposal penawaran ke supply@gotani.id atau procurement.buah@ptagro.co.id."
        masked, mapping = mask_text(raw)
        assert "[EMAIL_1]" in masked
        assert "[EMAIL_2]" in masked
        assert "supply@gotani.id" not in masked
        assert "procurement.buah@ptagro.co.id" not in masked
        assert mapping["[EMAIL_1]"] == "supply@gotani.id"

    def test_find_pii_leak_detection(self):
        clean_text = "Panen melon madesta 2 ton siap angkut lokasi Nganjuk."
        assert find_pii(clean_text) == []

        leaky_text = "Ada stok melon di kebun, wa saya di 081234567890 atau email tes@gotani.com."
        leaks = find_pii(leaky_text)
        assert len(leaks) >= 2
        assert any("081234567890" in l for l in leaks)
        assert any("tes@gotani.com" in l for l in leaks)

    def test_mask_preserves_non_pii_numbers(self):
        raw = "Panen 2500 kg melon harga 8500 per kg tanggal 25 Oktober 2026."
        masked, mapping = mask_text(raw)
        # Angka volume, harga, dan tanggal tidak boleh di-masking
        assert "2500" in masked
        assert "8500" in masked
        assert "2026" in masked
        assert len(mapping) == 0

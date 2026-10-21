import re
import pytest
from agent.campaign import draft_spec_offline, KNOWN_COMMODITIES
from agent.masking import MOBILE_RE


def _extract_and_format_contact(listing_phone: str | None, raw_text: str | None) -> str:
    """Helper identik dengan logika Tab 4 Raw Data Log."""
    if listing_phone and str(listing_phone).strip() and str(listing_phone).strip() != "-":
        raw_c = str(listing_phone).strip()
    else:
        text = str(raw_text or "")
        matches = MOBILE_RE.findall(text)
        raw_c = matches[0].strip() if matches else None

    if not raw_c:
        return "-"

    digits = re.sub(r"\D", "", raw_c)
    if digits.startswith("628"):
        digits = "08" + digits[3:]
    elif digits.startswith("8"):
        digits = "08" + digits[1:]

    if len(digits) >= 10:
        if len(digits) == 10:
            return f"{digits[:4]}-{digits[4:7]}-{digits[7:]}"
        elif len(digits) == 11:
            return f"{digits[:4]}-{digits[4:7]}-{digits[7:]}"
        elif len(digits) == 12:
            return f"{digits[:4]}-{digits[4:8]}-{digits[8:]}"
        else:
            return f"{digits[:4]}-{digits[4:8]}-{digits[8:]}"
    return raw_c or "-"


def test_raw_contact_factual_honesty():
    # Kasus 1: Postingan dengan nomor HP di teks mentah
    txt1 = "Panen melon madesta 600 kg siap petik. Hub WA 081234567890 kebun Jombang."
    assert _extract_and_format_contact(None, txt1) == "0812-3456-7890"

    # Kasus 2: Postingan TANPA kontak sama sekali (harus '-' jujur, tidak boleh mengarang)
    txt2 = "Update harga melon di pasar induk hari ini lumayan stabil."
    assert _extract_and_format_contact(None, txt2) == "-"

    # Kasus 3: Postingan sudah diekstrak ke listing
    assert _extract_and_format_contact("+6285712345678", "teks tanpa kontak") == "0857-1234-5678"

    # Kasus 4: Nomor format internasional 628...
    txt4 = "Jual cabai rawit WA 6281770170496"
    assert _extract_and_format_contact(None, txt4) == "0817-7017-0496"


def test_draft_spec_offline_enhanced_commodities():
    # Uji rempah (Jahe)
    s1 = draft_spec_offline("Cari petani jahe merah di Pacitan minimal 500 kg", "cmp-jahe")
    assert s1.product.name == "Jahe"
    assert "jahe merah" in s1.product.synonyms
    assert s1.volume.min == 500.0
    assert "Kab. Pacitan" in s1.location.include

    # Uji rempah (Cengkeh)
    s2 = draft_spec_offline("Butuh pasokan cengkeh kering di Trenggalek 2 ton", "cmp-cengkeh")
    assert s2.product.name == "Cengkeh"
    assert s2.volume.min == 2000.0
    assert "Kab. Trenggalek" in s2.location.include

    # Uji komoditas baru via fallback regex (Porang)
    s3 = draft_spec_offline("Cari petani porang di Madiun 1 ton", "cmp-porang")
    assert s3.product.name == "Porang"
    assert s3.volume.min == 1000.0
    assert "Kab. Madiun" in s3.location.include

    # Uji pencarian pembeli (demand)
    s4 = draft_spec_offline("Cari pembeli melon di Surabaya minimal 1000 kg", "cmp-demand")
    assert s4.goal == "find_demand"
    assert s4.product.name == "Melon"

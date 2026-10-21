"""Ekstraksi berbasis aturan (tanpa LLM).

Dipakai saat API key belum ada, saat budget LLM habis, atau sebagai cadangan kalau LLM error.
Hasilnya lebih kasar daripada LLM, tapi gratis, cepat, dan bisa diuji.
Format keluaran SAMA dengan ekstraksi LLM (lihat `extraction.py`) supaya pipeline tidak peduli sumbernya.
"""
from __future__ import annotations

import re

from . import wilayah
from .campaign import CampaignSpec
from .normalize import parse_available, parse_price, parse_quantity

# Frasa yang mengandung kata "beli/butuh" tapi sebenarnya dari penjual
SELLER_PHRASES = r"\b(yang|yg|bagi yang|bagi yg|siapa yang|siapa yg|monggo yang|monggo yg)\s+(butuh|minat|berminat|mau|cari)\b"
NEUTRAL_PHRASES = r"\bjual\s*beli\b|\bterima\s*kasih\b|\bmakasih\b"

SUPPLY_PATTERNS = [
    r"\bjual\b", r"\bdijual\b", r"\bjualan\b", r"\bready\b", r"\bredi\b", r"\bstok\b", r"\bstock\b",
    r"\bpanen\b", r"\btersedia\b", r"\bsiap kirim\b", r"\bmenawarkan\b", r"\bada barang\b",
    r"\bopen (order|po)\b", r"\bsiap suplai\b", r"\bsupply\b",
]
DEMAND_PATTERNS = [
    r"\bcari\b", r"\bcarikan\b", r"\bmencari\b", r"\bdicari\b", r"\bbutuh\b", r"\bmembutuhkan\b",
    r"\bbeli\b", r"\bmembeli\b", r"\bterima\b", r"\bmenerima\b", r"\bnampung\b", r"\bmenampung\b",
    r"\bnyari\b", r"\bwtb\b", r"\bpenampung\b", r"\bdibeli\b",
]
OTHER_PATTERNS = [
    r"\bbibit\b", r"\bbenih\b", r"\bpupuk\b", r"\bpestisida\b", r"\bjasa\b", r"\bekspedisi\b",
    r"\bsewa\b", r"\bpinjaman\b", r"\bkredit\b", r"\blowongan\b", r"\bmulsa\b",
]
FRAUD_PATTERNS = [
    r"transfer dulu", r"dijamin untung", r"investasi", r"\bpinjol\b", r"\bslot\b", r"klik link",
    r"modal kecil untung besar", r"\bdp dulu\b",
]
RESELLER_PATTERNS = [r"\breseller\b", r"\bdropship", r"\bagen\b"]
GRADE_RE = re.compile(r"\bgrade\s*([abc]|super|premium|1|2|3)\b|\b(super|kw\s*1|kualitas\s*super)\b", re.IGNORECASE)


def _first_pos(patterns: list[str], text: str) -> tuple[int, int]:
    count, first = 0, 10**9
    for p in patterns:
        for m in re.finditer(p, text):
            count += 1
            first = min(first, m.start())
    return count, first


def classify_intent(text: str, spec: CampaignSpec) -> str:
    low = (text or "").lower()
    product_hit = any(re.search(rf"\b{re.escape(t)}\b", low) for t in spec.product_terms())

    cleaned = re.sub(NEUTRAL_PHRASES, " ", low)
    seller_hint = len(re.findall(SELLER_PHRASES, cleaned))
    cleaned = re.sub(SELLER_PHRASES, " ", cleaned)

    s_count, s_first = _first_pos(SUPPLY_PATTERNS, cleaned)
    d_count, d_first = _first_pos(DEMAND_PATTERNS, cleaned)
    s_count += seller_hint
    o_count, _ = _first_pos(OTHER_PATTERNS, cleaned)

    if not product_hit:
        return "other" if o_count else "irrelevant"
    if o_count and o_count >= max(s_count, d_count):
        return "other"
    if s_count == 0 and d_count == 0:
        return "irrelevant"
    if s_count != d_count:
        return "supply" if s_count > d_count else "demand"
    return "supply" if s_first <= d_first else "demand"


def extract(text: str, spec: CampaignSpec, posted_at: str | None = None) -> dict:
    """Ekstrak satu post (teks SUDAH di-masking)."""
    parts = (text or "").split("\n", 1)
    title = parts[0] if len(parts) > 0 else ""
    snippet = parts[1] if len(parts) > 1 else title
    low_snippet = snippet.lower()

    # Periksa komoditas lain yang bertentangan (misal post jual cengkeh saat cari jahe, atau kelapa saat cari cabai)
    OTHER_CROPS = [
        # Rempah & Herbal
        "cengkeh", "pala", "lada", "merica", "kayu manis", "vanili", "kapulaga", "kunyit", "temulawak", "kencur", "lengkuas", "sereh", "serai", "porang", "nilam", "jahe",
        # Perkebunan & Pangan
        "kelapa", "durian", "sawit", "karet", "kakao", "kopi", "singkong", "tebu", "tembakau", "jagung", "padi", "beras", "kedelai", "kacang tanah", "kacang hijau",
        # Sayuran & Hortikultura
        "cabai", "cabe", "bawang", "bawang merah", "bawang putih", "kentang", "tomat", "wortel", "kubis", "kol", "terong", "buncis", "timun",
        # Buah-buahan
        "melon", "semangka", "pisang", "pepaya", "mangga", "alpukat", "jeruk", "salak", "nanas", "apel", "jambu"
    ]
    target_terms = [t.lower() for t in spec.product_terms()]
    competing_crops = [c for c in OTHER_CROPS if not any(t == c or t in c or c in t for t in target_terms)]

    other_crop_hit = any(re.search(rf"\b{re.escape(c)}\b", low_snippet) for c in competing_crops)
    product_in_snippet = any(re.search(rf"\b{re.escape(t)}\b", low_snippet) for t in spec.product_terms())

    # Jika isi postingan menjual komoditas lain dan tidak menyebut komoditas target
    if other_crop_hit and not product_in_snippet:
        detected_other = next((c for c in competing_crops if re.search(rf"\b{re.escape(c)}\b", low_snippet)), "komoditas_lain")
        return {
            "intent": "irrelevant",
            "entity_name": None,
            "product": detected_other,
            "attributes": {},
            "flags": ["komoditas_berbeda"],
            "evidence": {"alasan": f"Isi postingan menjual {detected_other}, bukan {spec.product.name}"},
            "posted_at": posted_at,
        }

    low = (text or "").lower()
    intent = classify_intent(text, spec)
    evidence: dict[str, str] = {}

    product = None
    for term in spec.product_terms():
        m = re.search(rf"\b{re.escape(term)}\b", low)
        if m:
            product = spec.product.name
            evidence["product"] = text[m.start(): m.end()]
            break

    COMMON_VARIETIES = {
        "melon": ["inthanon", "madesta", "golden", "action", "alisha", "rock", "fujian", "kirani", "hamigua"],
        "cabai": ["rawit", "keriting", "merah besar", "ori 212"],
        "bawang": ["merah", "putih", "probolinggo", "brebes", "nganjuk"],
        "semangka": ["inul", "non biji", "kuning", "merah"],
        "pisang": ["cavendish", "ambon", "raja", "kepok"],
    }

    variety = None
    spec_vars = spec.product.attributes.get("variety") or []
    candidate_vars = spec_vars + COMMON_VARIETIES.get((product or "").lower(), [])
    for v in candidate_vars:
        if v and re.search(rf"\b{re.escape(v.lower())}\b", low):
            variety = v.capitalize()
            evidence["variety"] = v
            break

    grade = None
    gm = GRADE_RE.search(text or "")
    if gm:
        grade = gm.group(0)
        evidence["grade"] = grade

    price, price_ev, price_span = parse_price(text)
    if price_ev:
        evidence["price"] = price_ev
    qty, qty_ev = parse_quantity(text, skip=price_span)
    if qty_ev:
        evidence["volume"] = qty_ev

    regions = wilayah.find_regions_in_text(text)
    location_text = None
    if regions:
        location_text = wilayah.label(regions[0])
        evidence["location"] = regions[0]["nama"]
    else:
        prov = wilayah.mentions_province(text)
        if prov:
            location_text = prov
            evidence["location"] = prov

    available_text, _ = parse_available(text, posted_at)

    flags = []
    if any(re.search(p, low) for p in FRAUD_PATTERNS):
        flags.append("indikasi_penipuan")
    if any(re.search(p, low) for p in RESELLER_PATTERNS):
        flags.append("reseller")

    # Ekstraksi Nama Petani / Pemosting
    entity_name = None
    lines = [line.strip() for line in (text or "").split("\n") if line.strip()]
    forbidden_words = {
        "jual", "beli", "panen", "ready", "komunitas", "grup", "group",
        "order", "resep", "butuh", "wa", "hub", "wa:", "diobral", "harga"
    }
    if lines:
        for candidate in lines[:2]:
            words = candidate.split()
            c_low_words = [w.lower().strip(":,.-_") for w in words]
            if 1 <= len(words) <= 4 and not any(w in forbidden_words for w in c_low_words):
                if candidate[0].isupper() and not any(char in candidate for char in [":", "/", "\\", "@", "http"]):
                    entity_name = candidate
                    break

    return {
        "intent": intent,
        "entity_name": entity_name,
        "product": product,
        "variety": variety,
        "grade": grade,
        "volume_value": qty,
        "volume_unit": "kg" if qty else None,
        "price_value": price,
        "price_unit": "kg" if price else None,
        "location_text": location_text,
        "available_text": available_text,
        "flags": flags,
        "evidence": evidence,
        "posted_at": posted_at,
    }

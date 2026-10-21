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

# --- Unit non-standar yang TIDAK bisa dikonversi ke kg ---
# Jika harga/volume menggunakan unit ini, kita simpan apa adanya, bukan asumsikan /kg.
NON_KG_UNITS = {
    "kresek", "karung", "dos", "pak", "ikat", "polybag", "biji", "butir",
    "tandan", "sisir", "truk", "pickup", "box", "peti", "keranjang",
    "crate", "sak", "bal", "renteng", "lusin",
}

# --- Regex untuk unit non-standar dalam teks harga ---
_NON_KG_ALT = "|".join(re.escape(u) for u in sorted(NON_KG_UNITS, key=len, reverse=True))
NON_KG_PRICE_RE = re.compile(
    r"(?:rp\.?\s*|harga\s*:?\s*)?(\d+(?:[.,]\d+)*)\s*(rb|ribu|rban|k|jt|juta)?\s*(?:/|per\s*)\s*(" + _NON_KG_ALT + r")\b",
    re.IGNORECASE,
)
NON_KG_VOL_RE = re.compile(
    r"(\d+(?:[.,]\d+)*)\s*(" + _NON_KG_ALT + r")\b",
    re.IGNORECASE,
)

# --- Pola Facebook snippet untuk ekstrak nama author ---
# Pola: "NamaGrup · NamaAuthor · Tanggal · 🌐"
# atau: "NamaGrup · NamaAuthor · Tanggal"
# Separator bisa: " · ", " - ", " — ", " | "
FB_AUTHOR_SEP = r"\s*[·\-—|]\s*"
FB_AUTHOR_RE = re.compile(
    r"^.{5,80}?" + FB_AUTHOR_SEP +   # nama grup (5-80 char)
    r"([A-Z][a-zA-Z']+(?:\s+[A-Z][a-zA-Z']+){0,3})" +  # nama author (1-4 kata, tiap kata kapital)
    FB_AUTHOR_SEP +                    # separator
    r"(?:\d|yesterday|kemarin|hari|jam|menit|minggu|bulan|tahun|just now|hr|mggu|\d+\s*(?:h|d|w|m|y)\b)",  # timestamp
    re.MULTILINE,
)

# Pola alternatif: "NamaAuthor posted in NamaGrup"
FB_AUTHOR_ALT_RE = re.compile(
    r"^([A-Z][a-zA-Z']+(?:\s+[A-Z][a-zA-Z']+){0,3})\s+(?:posted|shared|commented)\s+(?:in|on|to)\b",
    re.MULTILINE,
)


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


def _extract_fb_author(text: str) -> str | None:
    """Ekstrak nama pemosting dari pola snippet Google Search Facebook.

    Pola yang dikenali:
      - "NamaGrup · NamaAuthor · 2 hari lalu · 🌐"
      - "NamaAuthor posted in NamaGrup"
      - "NamaGrup - NamaAuthor | 19 Oktober"
    """
    if not text:
        return None

    # Coba pola utama: Grup · Author · Timestamp
    m = FB_AUTHOR_RE.search(text)
    if m:
        name = m.group(1).strip()
        # Filter: bukan nama grup atau kata umum
        low_name = name.lower()
        skip_words = {
            "grup", "group", "komunitas", "forum", "petani", "jual", "beli",
            "ready", "panen", "facebook", "public", "private", "member",
        }
        if not any(w in low_name for w in skip_words) and len(name) >= 3:
            return name

    # Coba pola alternatif: "Author posted in Group"
    m2 = FB_AUTHOR_ALT_RE.search(text)
    if m2:
        return m2.group(1).strip()

    return None


def _extract_location_from_group(text: str) -> str | None:
    """Ekstrak nama lokasi dari nama grup Facebook di baris pertama teks.

    Contoh:
      - "KUNIR GANDEKAN KARANGGAYAM (serba-serbi)" → "Karanggayam"
      - "Petani Melon NGANJUK" → "Nganjuk"
      - "Jual Beli Buah Malang Raya" → "Malang"

    Strategi: Ambil baris pertama, cari kata-kata yang merupakan nama wilayah.
    """
    if not text:
        return None

    # Ambil baris pertama (biasanya nama grup)
    first_line = text.split("\n")[0].strip()
    if not first_line:
        return None

    # Coba match wilayah resmi dulu di baris pertama
    regions = wilayah.find_regions_in_text(first_line)
    if regions:
        return wilayah.label(regions[0])

    # Coba match provinsi
    prov = wilayah.mentions_province(first_line)
    if prov:
        return prov

    return None


def _parse_non_kg_price(text: str) -> tuple[float | None, str | None, str | None]:
    """Cari harga dengan unit NON-standar (kresek, ikat, karung, dll).

    Return: (price_value_rupiah, price_unit, evidence_string)
    """
    if not text:
        return None, None, None

    from .normalize import parse_number, MULTIPLIER

    for m in NON_KG_PRICE_RE.finditer(text):
        val = parse_number(m.group(1))
        if val is None:
            continue
        mul = m.group(2)
        if mul:
            val *= MULTIPLIER.get(mul.lower(), 1)
        unit = m.group(3).lower().strip()
        if 100 <= val <= 10_000_000:
            return round(val), unit, m.group(0).strip()

    return None, None, None


def _parse_non_kg_volume(text: str, skip_spans: list[tuple[int, int]] | None = None) -> tuple[float | None, str | None, str | None]:
    """Cari volume dengan unit non-standar (kresek, ikat, karung, dll).

    Return: (volume_value, volume_unit, evidence_string)
    """
    if not text:
        return None, None, None

    from .normalize import parse_number

    for m in NON_KG_VOL_RE.finditer(text):
        if skip_spans:
            if any(m.start() < s[1] and m.end() > s[0] for s in skip_spans):
                continue
        val = parse_number(m.group(1))
        if val is not None and val > 0:
            unit = m.group(2).lower().strip()
            return val, unit, m.group(0).strip()

    return None, None, None


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
            "entity_name": _extract_fb_author(text),
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
        "melon": ["inthanon", "madesta", "golden", "action", "alisha", "rock", "fujian", "kirani", "hamigua", "amanda", "suluhan"],
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

    # --- Harga: Cek unit non-standar DULU, baru fallback ke parse_price (per-kg) ---
    price_value = None
    price_unit = None
    price_span = None

    nk_price, nk_unit, nk_ev = _parse_non_kg_price(text)
    if nk_price is not None:
        price_value = nk_price
        price_unit = nk_unit
        evidence["price"] = nk_ev or ""
    else:
        price, price_ev, price_span = parse_price(text)
        if price is not None:
            price_value = price
            price_unit = "kg"
            if price_ev:
                evidence["price"] = price_ev

    # --- Volume: Cek unit non-standar DULU, baru fallback ke parse_quantity (kg) ---
    volume_value = None
    volume_unit = None

    skip_spans = []
    if price_span:
        skip_spans.append(price_span)

    nk_vol, nk_vol_unit, nk_vol_ev = _parse_non_kg_volume(text, skip_spans)
    if nk_vol is not None:
        volume_value = nk_vol
        volume_unit = nk_vol_unit
        if nk_vol_ev:
            evidence["volume"] = nk_vol_ev
    else:
        qty, qty_ev = parse_quantity(text, skip=price_span)
        if qty is not None:
            volume_value = qty
            volume_unit = "kg"
            if qty_ev:
                evidence["volume"] = qty_ev

    # --- Konteks Cerdas: Jika volume=non-standar & harga tanpa unit, asumsikan per unit volume ---
    # Contoh: "1 kresek 15k saja" → harga 15000 per KRESEK (bukan per kg)
    if volume_unit and volume_unit in NON_KG_UNITS and price_unit == "kg" and price_value:
        # Cek apakah harga dan volume berdekatan di teks (dalam 30 karakter)
        vol_ev = evidence.get("volume", "")
        price_ev = evidence.get("price", "")
        if vol_ev and price_ev:
            vol_pos = (text or "").lower().find(vol_ev.lower())
            price_pos = (text or "").lower().find(price_ev.lower())
            if vol_pos >= 0 and price_pos >= 0 and abs(vol_pos - price_pos) < 40:
                # Harga berdekatan dengan volume non-standar → ubah unit harga
                price_unit = volume_unit

    # --- Lokasi: Cek wilayah resmi + fallback nama grup ---
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
        else:
            # Fallback: coba ekstrak dari nama grup di baris pertama
            group_loc = _extract_location_from_group(text)
            if group_loc:
                location_text = group_loc
                evidence["location"] = f"dari nama grup: {group_loc}"

    available_text, _ = parse_available(text, posted_at)

    flags = []
    if any(re.search(p, low) for p in FRAUD_PATTERNS):
        flags.append("indikasi_penipuan")
    if any(re.search(p, low) for p in RESELLER_PATTERNS):
        flags.append("reseller")

    # --- Ekstraksi Nama Petani / Pemosting (diperbaiki) ---
    entity_name = None

    # Metode 1: Pola Facebook snippet (paling akurat)
    entity_name = _extract_fb_author(text)

    # Metode 2: Fallback - cek baris awal teks (heuristik lama yang diperbaiki)
    if not entity_name:
        lines = [line.strip() for line in (text or "").split("\n") if line.strip()]
        forbidden_words = {
            "jual", "beli", "panen", "ready", "komunitas", "grup", "group",
            "order", "resep", "butuh", "wa", "hub", "wa:", "diobral", "harga",
            "petani", "facebook", "gabung", "join", "member", "admin",
        }
        if lines:
            for candidate in lines[:3]:  # Cek 3 baris pertama (bukan hanya 2)
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
        "volume_value": volume_value,
        "volume_unit": volume_unit,
        "price_value": price_value,
        "price_unit": price_unit,
        "location_text": location_text,
        "available_text": available_text,
        "flags": flags,
        "evidence": evidence,
        "posted_at": posted_at,
    }

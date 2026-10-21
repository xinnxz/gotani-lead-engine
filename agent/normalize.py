"""Normalisasi (PRD F3.3): nomor → +62, satuan → kg, harga → Rp/kg, tanggal relatif → absolut."""
from __future__ import annotations

import re
from datetime import datetime, timedelta

UNIT_TO_KG = {
    "ton": 1000.0, "t": 1000.0,
    "kuintal": 100.0, "kwintal": 100.0, "kw": 100.0, "kwt": 100.0, "q": 100.0,
    "kg": 1.0, "kilo": 1.0, "kilogram": 1.0, "kgs": 1.0,
    "gram": 0.001, "gr": 0.001, "g": 0.001,
}
_UNIT_ALT = "ton|kuintal|kwintal|kwt|kw|kilogram|kilo|kgs|kg|gram|gr"

MULTIPLIER = {"rb": 1_000, "ribu": 1_000, "k": 1_000, "rban": 1_000, "jt": 1_000_000, "juta": 1_000_000}


def normalize_phone(raw: str | None) -> str | None:
    """'0812-3456-7890' / '62812...' / '+62 812...' → '+6281234567890'."""
    if not raw:
        return None
    d = re.sub(r"\D", "", raw)
    if d.startswith("0"):
        d = "62" + d[1:]
    elif d.startswith("8"):
        d = "62" + d
    if not d.startswith("62") or not (10 <= len(d) <= 15):
        return None
    return "+" + d


def is_mobile(e164: str | None) -> bool:
    return bool(e164 and e164.startswith("+628"))


def parse_number(s: str) -> float | None:
    """Angka gaya Indonesia: '1.500' = 1500, '1,5' = 1.5, '2.5' = 2.5."""
    s = s.strip()
    if re.fullmatch(r"\d{1,3}(\.\d{3})+(,\d+)?", s):
        s = s.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(,\d{3})+", s):
        s = s.replace(",", "")
    else:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def to_kg(value: float | None, unit: str | None) -> float | None:
    if value is None:
        return None
    factor = UNIT_TO_KG.get((unit or "kg").lower().strip(". "))
    return None if factor is None else round(value * factor, 3)


PRICE_RE = re.compile(
    r"(?P<pre>rp\.?\s*|harga\s*:?\s*(?:rp\.?\s*)?|hrg\s*:?\s*)?"
    r"(?P<num>\d+(?:[.,]\d+)*)\s*(?P<mul>rb|ribu|rban|k|jt|juta)?\b"
    r"(?:\s*,-)?\s*(?P<per>(?:/|per\s*|perr\s*|se)\s*(?:" + _UNIT_ALT + r"))?",
    re.IGNORECASE,
)
QTY_RE = re.compile(r"(?P<num>\d+(?:[.,]\d+)*)\s*(?P<unit>" + _UNIT_ALT + r")\b", re.IGNORECASE)


def parse_price(text: str) -> tuple[float | None, str | None, tuple[int, int] | None]:
    """Cari harga per kg di teks. Return (harga_rp_per_kg, potongan_bukti, span)."""
    for m in PRICE_RE.finditer(text or ""):
        pre, mul, per = m.group("pre"), m.group("mul"), m.group("per")
        if not (pre or mul or per):
            continue  # angka tanpa tanda harga → bukan harga
        val = parse_number(m.group("num"))
        if val is None:
            continue
        if mul:
            val *= MULTIPLIER[mul.lower()]
        unit = "kg"
        if per:
            unit = re.sub(r"^(/|per|perr|se)\s*", "", per.lower()).strip()
        factor = UNIT_TO_KG.get(unit, 1.0)
        per_kg = val / factor
        if 100 <= per_kg <= 1_000_000:
            return round(per_kg), m.group(0).strip(), m.span()
    return None, None, None


def parse_quantity(text: str, skip: tuple[int, int] | None = None) -> tuple[float | None, str | None]:
    """Cari kuantitas (dikonversi ke kg). `skip` = span harga agar '4rb/kg' tidak terbaca sebagai volume."""
    for m in QTY_RE.finditer(text or ""):
        if skip and m.start() < skip[1] and m.end() > skip[0]:
            continue
        before = text[max(0, m.start() - 2): m.start()]
        if "/" in before:
            continue
        kg = to_kg(parse_number(m.group("num")), m.group("unit"))
        if kg:
            return kg, m.group(0).strip()
    return None, None


INDONESIAN_MONTHS = {
    # Bahasa Indonesia
    "januari": 1, "jan": 1,
    "februari": 2, "feb": 2,
    "maret": 3, "mar": 3,
    "april": 4, "apr": 4,
    "mei": 5,
    "juni": 6, "jun": 6,
    "juli": 7, "jul": 7,
    "agustus": 8, "agt": 8, "ags": 8,
    "september": 9, "sep": 9,
    "oktober": 10, "okt": 10,
    "november": 11, "nov": 11,
    "desember": 12, "des": 12,
    # English (Facebook web timestamp)
    "january": 1, "february": 2, "march": 3,
    "may": 5, "june": 6, "july": 7,
    "august": 8, "aug": 8,
    "october": 10, "oct": 10,
    "december": 12, "dec": 12,
}

RELATIVE_DATES = [
    (r"hari ini|sekarang|ready|siap kirim|stok ada", 0),
    (r"besok", 1),
    (r"lusa", 2),
    (r"3 hari lagi", 3),
    (r"minggu depan|pekan depan", 7),
    (r"2 minggu lagi|dua minggu lagi", 14),
    (r"akhir bulan", 20),
    (r"bulan depan", 30),
]

AVAILABLE_RE = re.compile(
    r"(panen|siap panen|ready|tersedia|kirim|butuh|petik)\s*(?:mulai\s*|tgl\s*|tanggal\s*)?"
    r"(hari ini|besok|lusa|minggu depan|pekan depan|bulan depan|\d+\s*hari\s*lagi|\d{1,2}\s+[a-z]+(?:\s+\d{4})?|\d{1,2}[/\-]\d{1,2}(?:[/\-]\d{2,4})?)",
    re.IGNORECASE,
)


def parse_available(text: str, posted_at: str | None = None) -> tuple[str | None, str | None]:
    """Ekstrak frase waktu dan konversi ke tanggal kalender ISO (YYYY-MM-DD).

    Contoh:
    - 'panen minggu depan' (post 2026-10-01) -> ('panen minggu depan', '2026-10-08')
    - 'ready tgl 25 oktober' (tahun 2026) -> ('ready tgl 25 oktober', '2026-10-25')
    """
    if not text:
        return None, None
    m = AVAILABLE_RE.search(text)
    if not m:
        # Coba tangkap jika teks pendek itu sendiri adalah frase waktu (misal dari LLM available_text)
        low = text.lower().strip()
        for pat, d in RELATIVE_DATES:
            if re.search(pat, low):
                base = _parse_dt(posted_at) or datetime.now()
                return text, (base + timedelta(days=d)).date().isoformat()
        return text if len(text) <= 50 else None, None

    phrase = m.group(0).strip()
    when = m.group(2).lower().strip()
    base = _parse_dt(posted_at) or datetime.now()
    year = base.year

    # Cek format "25 oktober" atau "25 okt 2026"
    m_month = re.match(r"^(\d{1,2})\s+([a-z]+)(?:\s+(\d{4}))?$", when)
    if m_month:
        day = int(m_month.group(1))
        mon_str = m_month.group(2)
        y = int(m_month.group(3)) if m_month.group(3) else year
        mon = INDONESIAN_MONTHS.get(mon_str)
        if mon and 1 <= day <= 31:
            try:
                return phrase, datetime(y, mon, day).date().isoformat()
            except ValueError:
                pass

    # Cek format "25/10" atau "25-10-2026"
    m_slash = re.match(r"^(\d{1,2})[/\-](\d{1,2})(?:[/\-](\d{2,4}))?$", when)
    if m_slash:
        day = int(m_slash.group(1))
        mon = int(m_slash.group(2))
        raw_y = m_slash.group(3)
        y = int(raw_y) if raw_y and len(raw_y) == 4 else (2000 + int(raw_y) if raw_y else year)
        if 1 <= mon <= 12 and 1 <= day <= 31:
            try:
                return phrase, datetime(y, mon, day).date().isoformat()
            except ValueError:
                pass

    # Cek format "X hari lagi"
    mm = re.match(r"(\d+)\s*hari\s*lagi", when)
    if mm:
        days = int(mm.group(1))
        return phrase, (base + timedelta(days=days)).date().isoformat()

    # Cek pola relatif
    for pat, d in RELATIVE_DATES:
        if re.search(pat, when):
            return phrase, (base + timedelta(days=d)).date().isoformat()

    return phrase, None


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s).replace(tzinfo=None)
    except ValueError:
        return None



def parse_posted_date(text: str | None, raw_date: str | None = None) -> str | None:
    """Ekstrak tanggal publikasi postingan dari field Apify atau snippet Google Search.
    
    Mendukung format:
    - ISO / standar: '2024-05-12T...' -> '2024-05-12'
    - Relatif Indonesia: '2 tahun lalu', '3 bulan lalu', '2 minggu lalu', '5 hari lalu'
    - Format tanggal Indonesia: '12 Mei 2024', '25 Okt 2023'
    """
    now = datetime.now()
    if raw_date and isinstance(raw_date, str):
        raw_clean = raw_date.strip()
        if re.match(r"^\d{4}-\d{2}-\d{2}", raw_clean):
            return raw_clean[:10]
        m_iso = re.search(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})", raw_clean)
        if m_iso:
            try:
                return f"{int(m_iso.group(1)):04d}-{int(m_iso.group(2)):02d}-{int(m_iso.group(3)):02d}"
            except Exception:
                pass

    if not text:
        return None

    low = text.lower()

    # 1. Cek tahun lalu: "2 tahun lalu", "2 thn lalu", "1 tahun yang lalu"
    m_yr = re.search(r"(\d+)\s*(?:tahun|thn)\s*(?:yang\s*)?lalu", low)
    if m_yr:
        years = int(m_yr.group(1))
        return (now - timedelta(days=years * 365)).date().isoformat()

    # 2. Cek bulan lalu: "3 bulan lalu", "3 bln lalu"
    m_mo = re.search(r"(\d+)\s*(?:bulan|bln)\s*(?:yang\s*)?lalu", low)
    if m_mo:
        months = int(m_mo.group(1))
        return (now - timedelta(days=months * 30)).date().isoformat()

    # 3. Cek minggu lalu: "2 minggu lalu", "2 mggu lalu"
    m_wk = re.search(r"(\d+)\s*(?:minggu|mggu|pekan)\s*(?:yang\s*)?lalu", low)
    if m_wk:
        weeks = int(m_wk.group(1))
        return (now - timedelta(days=weeks * 7)).date().isoformat()

    # 4. Cek hari lalu: "5 hari lalu", "5 hr lalu", "kemarin"
    m_day = re.search(r"(\d+)\s*(?:hari|hr)\s*(?:yang\s*)?lalu", low)
    if m_day:
        days = int(m_day.group(1))
        return (now - timedelta(days=days)).date().isoformat()
    if "kemarin" in low:
        return (now - timedelta(days=1)).date().isoformat()

    # 5. Cek pola relatif bahasa Inggris Facebook (misal: "1y", "2 yrs ago", "3 mos ago")
    m_eng_yr = re.search(r"\b(\d+)\s*(?:years?|yrs?|y)\s*(?:ago)?\b", low)
    if m_eng_yr:
        years = int(m_eng_yr.group(1))
        return (now - timedelta(days=years * 365)).date().isoformat()

    m_eng_mo = re.search(r"\b(\d+)\s*(?:months?|mos?)\s*(?:ago)?\b", low)
    if m_eng_mo:
        months = int(m_eng_mo.group(1))
        return (now - timedelta(days=months * 30)).date().isoformat()

    # 6. Cek tanggal eksplisit format Day Month Year (misal: "12 Mei 2024", "12 Des 2024")
    m_date = re.search(r"\b(\d{1,2})\s+([a-z]+)\s+(\d{4})\b", low)
    if m_date:
        d_val = int(m_date.group(1))
        m_name = m_date.group(2)
        y_val = int(m_date.group(3))
        mo_val = INDONESIAN_MONTHS.get(m_name)
        if mo_val and 1 <= d_val <= 31:
            try:
                return datetime(y_val, mo_val, d_val).date().isoformat()
            except ValueError:
                pass

    # 7. Cek tanggal eksplisit format Month Day Year (Facebook timestamp: "December 12, 2024", "Dec 12, 2024")
    m_mdy = re.search(r"\b([a-z]+)\s+(\d{1,2}),?\s+(\d{4})\b", low)
    if m_mdy:
        m_name = m_mdy.group(1)
        d_val = int(m_mdy.group(2))
        y_val = int(m_mdy.group(3))
        mo_val = INDONESIAN_MONTHS.get(m_name)
        if mo_val and 1 <= d_val <= 31:
            try:
                return datetime(y_val, mo_val, d_val).date().isoformat()
            except ValueError:
                pass

    # 8. Cek tanggal numerik DD/MM/YYYY atau DD-MM-YYYY (misal: "12/10/2022", "12-10-2022")
    m_num = re.search(r"\b(\d{1,2})[\/-](\d{1,2})[\/-](\d{4})\b", low)
    if m_num:
        d_val = int(m_num.group(1))
        mo_val = int(m_num.group(2))
        y_val = int(m_num.group(3))
        if 1 <= mo_val <= 12 and 1 <= d_val <= 31:
            try:
                return datetime(y_val, mo_val, d_val).date().isoformat()
            except ValueError:
                pass

    # 9. Cek format Month Year tanpa hari (misal: "Agustus 2022", "May 2022", "Okt 2023")
    m_my = re.search(r"\b([a-z]+)\s+(\d{4})\b", low)
    if m_my:
        m_name = m_my.group(1)
        y_val = int(m_my.group(2))
        mo_val = INDONESIAN_MONTHS.get(m_name)
        if mo_val:
            try:
                return datetime(y_val, mo_val, 1).date().isoformat()
            except ValueError:
                pass

    # 10. Cek tahun lampau eksplisit (2010 - 2024) agar postingan lama selalu terdeteksi tanggalnya
    m_old_yr = re.search(r"\b(201\d|202[0-4])\b", low)
    if m_old_yr:
        y_val = int(m_old_yr.group(1))
        return f"{y_val:04d}-01-01"

    return None

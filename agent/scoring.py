"""Skor relevansi & confidence (PRD §7.4). Setiap poin skor disertai alasannya."""
from __future__ import annotations

import re
from datetime import datetime

from . import wilayah
from .campaign import CampaignSpec


def _age_days(posted_at: str | None, now: datetime) -> float | None:
    if not posted_at:
        return None
    try:
        dt = datetime.fromisoformat(posted_at).replace(tzinfo=None)
    except ValueError:
        return None
    return max(0.0, (now - dt).total_seconds() / 86400)


def _in_target_location(listing: dict, spec: CampaignSpec) -> bool | None:
    """True = di wilayah target, False = di luar, None = tidak diketahui."""
    kab, prov = listing.get("kabupaten"), listing.get("provinsi")
    if not kab and not prov:
        return None
    for x in spec.location.exclude:
        if kab and kab.lower() in x.lower():
            return False
    targets = [t.lower() for t in spec.location.include]
    if prov and prov.lower() in targets:
        return True
    if kab and any(kab.lower() == t or kab.lower().split(" ", 1)[-1] in t for t in targets):
        return True
    return False


def relevance(listing: dict, spec: CampaignSpec, raw_text: str) -> tuple[int, list[str]]:
    score, why = 0.0, []
    low = (raw_text or "").lower()

    terms = [t.lower() for t in spec.product_terms()]
    prod = (listing.get("product") or "").lower()
    # Hanya anggap cocok jika produk hasil ekstraksi cocok dengan terms komoditas target
    product_matched = any(t in prod for t in terms) or (prod and any(prod in t for t in terms))
    
    if product_matched:
        score += 40
        why.append(f"+40 produk cocok ({spec.product.name})")
    else:
        # Penalti keras: jika produk tidak cocok sama sekali, skor dipangkas drastis
        score -= 50
        why.append(f"-50 PENALTI: produk listing ({listing.get('product') or 'tidak cocok'}) bukan {spec.product.name}")

    # Penalti Usia / Kedaluwarsa Keras (PRD F2.3: batas maksimal kesegaran panen 1 bulan / 35 hari)
    posted_date_str = listing.get("posted_at")
    if posted_date_str:
        age_days = _age_days(posted_date_str, datetime.now())
        if age_days is not None:
            if age_days > 35:
                why.append(f"0 PENALTI KADALUWARSA: postingan sudah {age_days:.0f} hari lalu (> 35 hari)")
                return 0, why
            elif age_days > 20:
                score -= 20
                why.append(f"-20 penalti usia postingan ({age_days:.0f} hari lalu)")

    # Dynamic: periksa teks mentah, jika memuat tahun lampau (sebelum tahun ini), diskualifikasi
    _cur_yr = datetime.now().year
    _stale_max_s = _cur_yr - 1
    _stale_re_s = r"\b(201\d" + (f"|202[0-{_stale_max_s % 10}]" if _stale_max_s < 2030 else "|202\\d") + r")\b"
    if re.search(_stale_re_s, low):
        why.append(f"0 PENALTI KADALUWARSA: teks postingan memuat tahun lampau (sebelum {_cur_yr})")
        return 0, why

    intent_val = listing.get("intent")
    if intent_val == spec.target_intent:
        score += 30
        why.append(f"+30 niat sesuai ({intent_val})")
    elif intent_val in ("other", "irrelevant"):
        score -= 30
        why.append(f"-30 PENALTI: niat tidak relevan ({intent_val})")
    else:
        why.append(f"+0 niat tidak sesuai ({intent_val})")

    loc = _in_target_location(listing, spec)
    if loc is True:
        score += 20
        why.append(f"+20 lokasi di target ({listing.get('kabupaten') or listing.get('provinsi')})")
    elif loc is None:
        score += 5
        why.append("+5 lokasi tidak spesifik")
    else:
        score -= 10
        why.append(f"-10 lokasi di luar target ({listing.get('kabupaten') or listing.get('provinsi')})")

    vmin, vol = spec.volume.min, listing.get("volume_kg")
    if not vmin:
        score += 10
        why.append("+10 tidak ada syarat volume")
    elif vol is None:
        score += 5
        why.append("+5 volume tidak disebut")
    elif vol >= vmin:
        score += 10
        why.append(f"+10 volume {vol:g} kg ≥ minimal {vmin:g} kg")
    else:
        pts = round(10 * vol / vmin)
        score += pts
        why.append(f"+{pts} volume {vol:g} kg ({vol / vmin:.0%} dari minimal; kandidat pooling)")

    wanted = [v.lower() for v in (spec.product.attributes.get("variety") or []) if v]
    attrs = listing.get("attributes") or {}
    variety = (attrs.get("variety") or "") if isinstance(attrs, dict) else ""
    if not wanted:
        score += 10
        why.append("+10 tidak ada syarat varietas")
    elif not variety:
        score += 5
        why.append("+5 varietas tidak disebut")
    elif any(w in variety.lower() for w in wanted):
        score += 10
        why.append(f"+10 varietas cocok ({variety})")
    else:
        why.append(f"+0 varietas berbeda ({variety})")

    final_score = max(0, min(100, round(score)))
    return final_score, why


def confidence(listing: dict, spec: CampaignSpec, platform: str, confirmations: int,
               now: datetime | None = None) -> tuple[int, list[str]]:
    now = now or datetime.now()
    score, why = 0.0, []
    age = _age_days(listing.get("posted_at"), now)
    fd = max(spec.freshness_days, 8)

    if age is None:
        score += 10
        why.append("+10 tanggal post tidak diketahui")
    elif age <= 7:
        score += 30
        why.append(f"+30 post baru ({age:.0f} hari)")
    elif age < fd:
        pts = round(30 * (fd - age) / (fd - 7))
        score += pts
        why.append(f"+{pts} post {age:.0f} hari lalu")
    else:
        why.append(f"+0 post terlalu lama ({age:.0f} hari > {spec.freshness_days})")
        if age is not None and age > 90:
            score = min(score, 15.0)
            why.append(f"Confidence dibatasi maksimal 15% karena postingan sudah kadaluwarsa ({age:.0f} hari lalu)")

    if listing.get("contact_wa") or listing.get("contact_phone") or listing.get("contact_email"):
        score += 25
        why.append("+25 ada kontak langsung (WA/telepon/email)")
    elif listing.get("contact_profile"):
        score += 12
        why.append("+12 hanya link profil")
    else:
        why.append("+0 tidak ada jalur kontak")

    # Sinyal "akun/sumber aktif". MVP memakai tanggal post sebagai pengganti (PRD §7.4 catatan).
    if platform == "web":
        score += 15
        why.append("+15 situs bisa diakses (tanda aktivitas belum dicek)")
    elif age is not None and age <= 30:
        score += 25
        why.append("+25 akun aktif ≤30 hari (berdasarkan tanggal post)")
    elif age is None:
        score += 10
        why.append("+10 keaktifan akun belum diketahui")
    else:
        why.append("+0 akun tidak terlihat aktif 30 hari terakhir")

    if confirmations >= 2:
        score += 10
        why.append(f"+10 terkonfirmasi di {confirmations} sumber")
    else:
        why.append("+0 baru ditemukan di 1 sumber")

    flags = listing.get("flags") or []
    price, vol = listing.get("price_per_kg"), listing.get("volume_kg")
    weird = (price is not None and not (300 <= price <= 500_000)) or (vol is not None and vol > 2_000_000)
    if "indikasi_penipuan" in flags or "harga_tidak_wajar" in flags or weird:
        why.append("+0 ada tanda tidak wajar/penipuan: " + ", ".join(flags or ["angka tidak wajar"]))
    else:
        score += 10
        why.append("+10 angka wajar, tidak ada pola spam")

    # Bonus: nama pemosting terdeteksi = sumber lebih kredibel
    if listing.get("entity_name"):
        score += 5
        why.append("+5 nama pemosting terdeteksi")

    # Bonus: lokasi terdeteksi = data terverifikasi lebih tinggi
    if listing.get("kabupaten") or listing.get("provinsi"):
        score += 5
        why.append("+5 lokasi terdeteksi")

    # Penalti kelengkapan data komersial (jika tidak ada kontak, volume, dan harga)
    has_contact = bool(listing.get("contact_wa") or listing.get("contact_phone") or listing.get("contact_email"))
    has_vol = bool(listing.get("volume_kg") or listing.get("volume_value"))
    has_price = bool(listing.get("price_per_kg") or listing.get("price_value"))
    if not has_contact and not has_vol and not has_price:
        score = min(score, 30.0)
        why.append("Confidence dibatasi maksimal 30% karena minim data komersial (tanpa kontak, volume, dan harga)")

    # Batasi confidence secara absolut jika postingan sudah kadaluwarsa (> 90 hari)
    if age is not None and age > 90:
        score = min(score, 20.0)
        why.append(f"Confidence dibatasi maksimal 20% karena postingan sudah kadaluwarsa ({age:.0f} hari lalu)")

    return round(min(score, 100)), why


def region_from(text: str) -> dict | None:
    regs = wilayah.find_regions_in_text(text or "")
    return regs[0] if regs else None

"""Mesin perhitungan skor kecocokan (Matchmaking) supply ↔ demand (PRD §7.6 / F6.1–F6.3).

Fungsi murni (pure function): tidak menyentuh database, deterministik, tanpa biaya LLM.
Menghasilkan skor kecocokan 0–100, rincian 4 faktor, kekurangan (gaps), tier aksi, dan estimasi margin.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from .config import settings
from .geo import calculate_distance_km

RULE_VERSION = "v1"


def _parse_attr(attr_data: Any) -> dict:
    if isinstance(attr_data, dict):
        return attr_data
    if isinstance(attr_data, str) and attr_data.strip():
        try:
            return json.loads(attr_data)
        except Exception:
            return {}
    return {}


def _parse_date(d_str: str | None) -> datetime | None:
    if not d_str:
        return None
    try:
        return datetime.fromisoformat(d_str.split("T")[0])
    except Exception:
        return None


def score_match(
    demand: dict | Any,
    supply: dict | Any,
    margin_pct: float | None = None,
) -> dict:
    """Hitung skor kecocokan antara satu kebutuhan pembeli (demand) dan satu penawaran petani (supply).

    Mengembalikan dictionary lengkap:
    - score: skor akhir 0–100 (berlabel 'skor kecocokan', BUKAN probabilitas)
    - tier: 'outreach' | 'review' | 'ignored'
    - breakdown: rincian poin per faktor
    - gaps: daftar kekurangan data yang perlu dikonfirmasi manusia
    - distance_km: jarak logistik terhitung
    - est_margin: estimasi nilai margin GoTani
    """
    margin = margin_pct if margin_pct is not None else settings.match_margin_default_pct
    gaps: list[str] = []
    breakdown: dict[str, Any] = {}

    # Konversi input jika bertipe sqlite3.Row
    d_dict = dict(demand) if not isinstance(demand, dict) else demand
    s_dict = dict(supply) if not isinstance(supply, dict) else supply

    # -------------------------------------------------------------
    # FAKTOR 1: PRODUK & VARIETAS (Bobot 30)
    # -------------------------------------------------------------
    p_score = 0.0
    d_prod = (d_dict.get("product") or "").lower().strip()
    s_prod = (s_dict.get("product") or "").lower().strip()

    if not d_prod or not s_prod or (d_prod not in s_prod and s_prod not in d_prod):
        # Produk tidak sama -> match tidak valid sama sekali
        return {
            "score": 0,
            "raw_score": 0,
            "tier": "ignored",
            "breakdown": {"produk": 0, "volume_waktu": 0, "jarak": 0, "harga": 0},
            "gaps": ["Komoditas tidak cocok"],
            "distance_km": None,
            "est_margin": None,
            "rule_version": RULE_VERSION,
        }

    p_score += 20.0  # Produk sama persis
    p_desc = f"+20 produk cocok ({d_prod})"

    d_attr = _parse_attr(d_dict.get("attributes_json") or d_dict.get("attributes"))
    s_attr = _parse_attr(s_dict.get("attributes_json") or s_dict.get("attributes"))

    d_var = [v.lower().strip() for v in d_attr.get("variety", []) if v]
    s_var = [v.lower().strip() for v in s_attr.get("variety", []) if v]

    if not d_var:
        p_score += 10.0
        p_desc += " | +10 pembeli tidak mensyaratkan varietas khusus"
    elif any(v in s_var for v in d_var):
        p_score += 10.0
        p_desc += f" | +10 varietas cocok ({', '.join(s_var)})"
    elif not s_var:
        p_score += 4.0
        p_desc += " | +4 varietas petani belum disebut"
        gaps.append(f"Varietas petani belum diketahui (pembeli butuh: {', '.join(d_var)})")
    else:
        p_desc += f" | +0 varietas berbeda (petani: {', '.join(s_var)}, pembeli: {', '.join(d_var)})"
        gaps.append(f"Varietas berbeda: {', '.join(s_var)} vs {', '.join(d_var)}")

    breakdown["produk"] = {"poin": round(p_score, 1), "keterangan": p_desc}

    # -------------------------------------------------------------
    # FAKTOR 2: VOLUME & WAKTU (Bobot 30)
    # -------------------------------------------------------------
    vw_score = 0.0
    vw_desc = []

    # Volume (maks 15)
    d_vol = d_dict.get("volume_kg")
    s_vol = s_dict.get("volume_kg")

    if not d_vol:
        vw_score += 15.0
        vw_desc.append("+15 pembeli tidak membatasi volume")
    elif s_vol is None:
        vw_score += 5.0
        vw_desc.append("+5 volume petani belum dicantumkan")
        gaps.append(f"Volume penawaran petani belum diketahui (kebutuhan: {d_vol:g} kg)")
    elif s_vol >= d_vol:
        vw_score += 15.0
        vw_desc.append(f"+15 volume mencukupi ({s_vol:g} kg >= {d_vol:g} kg)")
    else:
        ratio = s_vol / d_vol
        pts_vol = round(15.0 * ratio, 1)
        vw_score += pts_vol
        vw_desc.append(f"+{pts_vol} volume mencakup {ratio:.0%} ({s_vol:g} dari {d_vol:g} kg; kandidat pooling)")
        gaps.append(f"Volume kurang: baru terpenuhi {s_vol:g} dari {d_vol:g} kg (butuh tambahan)")

    # Waktu panen / ketersediaan (maks 15)
    d_date_str = d_dict.get("available_date")
    s_date_str = s_dict.get("available_date")
    d_dt = _parse_date(d_date_str)
    s_dt = _parse_date(s_date_str)

    if not d_dt or not s_dt:
        vw_score += 7.0
        vw_desc.append("+7 salah satu tanggal tidak spesifik")
        if not s_dt:
            gaps.append("Jadwal panen petani belum pasti")
        if not d_dt:
            gaps.append("Tenggat waktu pembeli belum pasti")
    else:
        # Selisih hari (kapan petani panen relatif terhadap kapan pembeli butuh)
        # Ideal: petani panen sebelum atau tepat saat pembeli butuh (maks H-14 s.d H+0)
        diff_days = (s_dt - d_dt).days
        if diff_days <= 0 and abs(diff_days) <= 14:
            vw_score += 15.0
            vw_desc.append(f"+15 waktu tepat (panen {s_date_str}, butuh {d_date_str})")
        elif diff_days <= 3:
            # Toleransi telat 1-3 hari
            vw_score += 10.0
            vw_desc.append(f"+10 panen beda {diff_days} hari dari kebutuhan")
            gaps.append(f"Selisih jadwal panen {diff_days} hari")
        else:
            vw_score += 0.0
            vw_desc.append(f"+0 jadwal panen tidak pas (selisih {diff_days} hari)")
            gaps.append(f"Jadwal panen tidak pas (selisih {diff_days} hari)")

    breakdown["volume_waktu"] = {"poin": round(vw_score, 1), "keterangan": " | ".join(vw_desc)}

    # -------------------------------------------------------------
    # FAKTOR 3: JARAK & LOGISTIK (Bobot 20)
    # -------------------------------------------------------------
    dist_km, dist_why = calculate_distance_km(
        s_dict.get("kabupaten") or s_dict.get("location_text"),
        d_dict.get("kabupaten") or d_dict.get("location_text"),
        s_dict.get("provinsi"),
        d_dict.get("provinsi"),
    )

    if dist_km is None:
        j_score = 6.0
        j_desc = f"+6 {dist_why}"
        gaps.append("Lokasi belum cukup detail untuk rute logistik")
    elif dist_km <= 25.0:
        j_score = 20.0
        j_desc = f"+20 jarak sangat dekat ({dist_km} km <= 25 km)"
    elif dist_km <= 250.0:
        # Linear dari 25 km (20 poin) sampai 250 km (0 poin)
        j_score = round(20.0 * (250.0 - dist_km) / (250.0 - 25.0), 1)
        j_desc = f"+{j_score} jarak {dist_km} km (formula logistik)"
    else:
        j_score = 0.0
        j_desc = f"+0 jarak terlalu jauh ({dist_km} km > 250 km)"
        gaps.append(f"Jarak pengiriman sangat jauh ({dist_km} km)")

    breakdown["jarak"] = {"poin": j_score, "jarak_km": dist_km, "keterangan": j_desc}

    # -------------------------------------------------------------
    # FAKTOR 4: HARGA & MARGIN GOTANI (Bobot 20)
    # -------------------------------------------------------------
    h_score = 0.0
    s_price = s_dict.get("price_per_kg")
    d_max_price = d_dict.get("price_per_kg")
    margin_info = None

    if not s_price or not d_max_price:
        h_score = 8.0
        h_desc = "+8 salah satu pihak belum mencantumkan harga"
        if not s_price:
            gaps.append("Harga penawaran petani belum diketahui")
        if not d_max_price:
            gaps.append("Batas anggaran harga pembeli belum ditentukan")
    else:
        # Harga modal petani + margin GoTani
        delivered_price = s_price * (1.0 + margin)
        if delivered_price <= d_max_price:
            h_score = 20.0
            selisih_bruto = d_max_price - s_price
            h_desc = f"+20 harga masuk budget pembeli (petani Rp{s_price:,.0f} + margin {margin:.0%} = Rp{delivered_price:,.0f} <= Rp{d_max_price:,.0f})"
            vol_calc = min(s_vol or 1000, d_vol or 1000)
            est_gross_revenue = selisih_bruto * vol_calc
            margin_info = {
                "farmer_price": s_price,
                "buyer_budget": d_max_price,
                "margin_pct": margin,
                "suggested_price": round(delivered_price),
                "est_gross_margin_rp": round(est_gross_revenue),
                "feasible": True,
            }
        else:
            # Over budget
            over_pct = (delivered_price - d_max_price) / d_max_price
            h_score = max(0.0, round(20.0 - (over_pct * 40.0), 1))
            h_desc = f"+{h_score} harga di atas budget pembeli (terkirim Rp{delivered_price:,.0f} > Rp{d_max_price:,.0f})"
            gaps.append(f"Harga petani Rp{s_price:,.0f} melebihi batas budget pembeli Rp{d_max_price:,.0f}")
            margin_info = {
                "farmer_price": s_price,
                "buyer_budget": d_max_price,
                "margin_pct": margin,
                "suggested_price": round(delivered_price),
                "est_gross_margin_rp": 0,
                "feasible": False,
            }

    breakdown["harga"] = {"poin": h_score, "keterangan": h_desc}

    # -------------------------------------------------------------
    # PENGALI CONFIDENCE & HASIL AKHIR
    # -------------------------------------------------------------
    raw_score = p_score + vw_score + j_score + h_score

    # Rata-rata confidence kedua record
    c_demand = d_dict.get("confidence") or 80
    c_supply = s_dict.get("confidence") or 70
    avg_conf = (c_demand + c_supply) / 2.0

    # Pengali: 0.5 + 0.5 * (avg_conf / 100)
    conf_multiplier = 0.5 + (0.5 * (avg_conf / 100.0))
    final_score = int(round(raw_score * conf_multiplier))
    final_score = max(0, min(100, final_score))

    # Tentukan Tier Aksi (F6.5)
    if final_score >= settings.match_tier_outreach_min:
        tier = "outreach"
    elif final_score >= settings.match_tier_review_min:
        tier = "review"
    else:
        tier = "ignored"

    return {
        "score": final_score,
        "raw_score": round(raw_score, 1),
        "conf_multiplier": round(conf_multiplier, 3),
        "tier": tier,
        "breakdown": breakdown,
        "gaps": gaps,
        "distance_km": dist_km,
        "est_margin": margin_info,
        "rule_version": RULE_VERSION,
    }

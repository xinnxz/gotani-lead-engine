"""Modul Smart Pooling / Agregasi Petani Kecil (PRD §7.6 / F6.4).

Menggabungkan beberapa petani kecil terdekat untuk memenuhi kebutuhan pembeli bervolume besar,
lengkap dengan perhitungan porsi (alokasi kg), jarak multi-stop, skor pool, dan disclaimer transparan.
"""
from __future__ import annotations

from typing import Any

from .config import settings
from .geo import calculate_distance_km
from .matching import score_match


def build_smart_pool(
    demand: dict | Any,
    candidate_supplies: list[dict | Any],
    max_farmers: int | None = None,
    max_radius_km: float | None = None,
    margin_pct: float | None = None,
) -> dict | None:
    """Susun saran kombinasi beberapa petani untuk memenuhi kuota volume pembeli.

    Mengembalikan dict hasil pool atau None jika tidak ada kandidat yang memenuhi syarat.
    """
    limit_farmers = max_farmers or settings.match_max_pool_farmers
    limit_radius = max_radius_km or settings.match_max_pool_radius_km
    margin = margin_pct if margin_pct is not None else settings.match_margin_default_pct

    d_dict = dict(demand) if not isinstance(demand, dict) else demand
    target_vol = d_dict.get("volume_kg") or 0.0

    if target_vol <= 0 or not candidate_supplies:
        return None

    # 1. Hitung skor individual dan filter kandidat
    scored_candidates = []
    for s in candidate_supplies:
        s_dict = dict(s) if not isinstance(s, dict) else s
        # Jangan sertakan duplikat
        if s_dict.get("duplicate_of"):
            continue
        # Hanya komoditas yang cocok
        if (s_dict.get("product") or "").lower().strip() != (d_dict.get("product") or "").lower().strip():
            continue

        res = score_match(d_dict, s_dict, margin_pct=margin)
        if res["score"] >= 30:  # Ambang minimal untuk dipertimbangkan
            scored_candidates.append({
                "supply": s_dict,
                "score_res": res,
                "score": res["score"],
                "vol": s_dict.get("volume_kg") or 0.0,
                "kab": s_dict.get("kabupaten") or s_dict.get("location_text"),
                "prov": s_dict.get("provinsi"),
            })

    if not scored_candidates:
        return None

    # 2. Urutkan untuk mencari Petani Jangkar (Anchor Farmer)
    # Petani jangkar adalah yang berskor tertinggi dan punya volume nyata
    scored_candidates.sort(key=lambda x: (x["score"], x["vol"]), reverse=True)
    anchor = scored_candidates[0]

    pool_members = [anchor]
    collected_vol = anchor["vol"]
    anchor_kab = anchor["kab"]
    anchor_prov = anchor["prov"]

    # 3. Kumpulkan petani tambahan dalam radius dari Petani Jangkar
    remaining = scored_candidates[1:]

    # Hitung jarak tiap kandidat ke Petani Jangkar
    for item in remaining:
        dist_to_anchor, _ = calculate_distance_km(item["kab"], anchor_kab, item["prov"], anchor_prov)
        item["dist_to_anchor"] = dist_to_anchor if dist_to_anchor is not None else 999.0

    # Urutkan berdasarkan jarak terdekat ke jangkar, lalu skor
    remaining.sort(key=lambda x: (x["dist_to_anchor"], -x["score"]))

    for item in remaining:
        if len(pool_members) >= limit_farmers:
            break
        if collected_vol >= target_vol:
            break

        # Cek apakah masih dalam radius yang masuk akal
        if item["dist_to_anchor"] <= limit_radius:
            pool_members.append(item)
            collected_vol += item["vol"]

    # Jika hanya ada 1 petani, ini bukan pooling (melainkan match single)
    if len(pool_members) <= 1:
        return None

    # 4. Alokasikan volume per petani
    allocated_items = []
    needed_left = target_vol
    total_allocated = 0.0

    for m in pool_members:
        take = min(m["vol"], needed_left) if m["vol"] > 0 else (needed_left / len(pool_members))
        take = round(take, 1)
        needed_left = max(0.0, needed_left - take)
        total_allocated += take
        allocated_items.append({
            "supply_id": m["supply"].get("id"),
            "farmer_name": m["supply"].get("entity_name") or f"Petani #{m['supply'].get('id')}",
            "location": m["kab"],
            "offered_vol_kg": m["vol"],
            "allocated_kg": take,
            "price_per_kg": m["supply"].get("price_per_kg"),
            "dist_to_anchor_km": m.get("dist_to_anchor", 0.0),
            "individual_score": m["score"],
            "contact_phone": m["supply"].get("contact_phone"),
            "contact_wa": m["supply"].get("contact_wa"),
        })

    coverage_pct = round(min(100.0, (total_allocated / target_vol) * 100.0), 1)

    # 5. Hitung Skor Pool Tertimbang
    # Rata-rata skor berbobot volume, dikurangi penalti 3 poin per titik jemput tambahan
    weighted_score_sum = sum(item["individual_score"] * item["allocated_kg"] for item in allocated_items)
    base_pool_score = weighted_score_sum / max(1.0, total_allocated)
    pickup_penalty = (len(pool_members) - 1) * 3.0  # Penalti kerumitan rute multi-stop
    final_pool_score = int(round(max(0.0, min(100.0, base_pool_score - pickup_penalty))))

    # Tier untuk pool
    if final_pool_score >= settings.match_tier_outreach_min and coverage_pct >= 90.0:
        tier = "outreach"
    elif final_pool_score >= settings.match_tier_review_min:
        tier = "review"
    else:
        tier = "ignored"

    # 6. Susun Disclaimer & Catatan Kekurangan Otomatis (F6.4)
    names_summary = " + ".join(f"{it['farmer_name']} ({it['allocated_kg']:g} kg)" for it in allocated_items)
    disclaimer_lines = [
        f"Kebutuhan: {target_vol:g} kg. Terpenuhi: {total_allocated:g} kg ({coverage_pct}%).",
        f"Saran gabungan {len(allocated_items)} petani: {names_summary}.",
        f"Perhatian: Ada {len(allocated_items)} titik jemput terpisah di sekitar {anchor_kab} (radius maksimal {limit_radius:g} km).",
    ]
    if coverage_pct < 100.0:
        disclaimer_lines.append(f"Volume masih kurang {round(target_vol - total_allocated, 1):g} kg ({100.0 - coverage_pct:.1f}%).")

    # Cek apakah ada grade/varietas yang belum lengkap
    missing_attrs = [it["farmer_name"] for it in allocated_items if not it.get("price_per_kg")]
    if missing_attrs:
        disclaimer_lines.append(f"Harga belum tertera untuk: {', '.join(missing_attrs)}.")

    return {
        "kind": "pool",
        "score": final_pool_score,
        "tier": tier,
        "total_volume_kg": total_allocated,
        "target_volume_kg": target_vol,
        "coverage_pct": coverage_pct,
        "anchor_location": anchor_kab,
        "num_farmers": len(allocated_items),
        "items": allocated_items,
        "disclaimer": " ".join(disclaimer_lines),
        "disclaimer_lines": disclaimer_lines,
    }

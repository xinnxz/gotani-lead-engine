"""GoTani Lead Engine - Outreach Message Generator & Pre-Sales Copilot (PRD §7.8).

Menyusun draf pesan WhatsApp cold-outreach yang personal, profesional, dan patuh
terhadap etika komunikasi serta UU Pelindungan Data Pribadi (UU PDP).

Prinsip:
1. Transparansi: Menyebutkan identitas pengirim (GoTani) dan asal informasi secara jujur.
2. Konteks relevan: Menyertakan komoditas, estimasi volume, dan lokasi tanpa asumsi berlebihan.
3. Hak tolak (opt-out): Memberikan klausul sopan jika penerima tidak berkenan dihubungi.
4. Tanpa simbol/emoji yang berlebihan, gaya komunikasi formal-santun agribisnis Indonesia.
"""

from __future__ import annotations
import urllib.parse
import re
from typing import Any


def _clean_str(val: Any) -> str | None:
    """Bersihkan nilai string secara aman dari float nan, None, atau string kosong."""
    if val is None or not isinstance(val, str):
        return None
    s = val.strip()
    return s if s and s.lower() not in {"nan", "none", "null"} else None


def normalize_phone_number(raw_phone: Any) -> str | None:
    """Bersihkan nomor telepon ke format internasional MSISDN tanpa '+' (contoh: 6281234567890)."""
    clean_p = _clean_str(raw_phone)
    if not clean_p:
        return None
    # Ambil nomor pertama jika ada separator koma atau garis miring
    first_part = clean_p.split(",")[0].split("/")[0].strip()
    digits = re.sub(r"[^\d]", "", first_part)
    
    if not digits:
        return None
    if digits.startswith("0"):
        return "62" + digits[1:]
    elif digits.startswith("62"):
        return digits
    elif digits.startswith("8"):
        return "62" + digits
    return digits


def format_wa_url(raw_phone: Any, text_message: str) -> str | None:
    """Buat link WhatsApp https://wa.me/{phone}?text={encoded_message}."""
    clean_phone = normalize_phone_number(raw_phone)
    if not clean_phone:
        return None
    encoded = urllib.parse.quote(text_message)
    return f"https://wa.me/{clean_phone}?text={encoded}"


def draft_farmer_outreach_for_match(
    farmer_name: Any,
    commodity: str,
    farmer_location: Any,
    buyer_name: Any,
    buyer_location: Any,
    needed_vol_kg: float | None = None,
    farmer_price: float | None = None,
) -> str:
    """Draf pesan outreach ke petani berdasarkan kecocokan (match) dengan permintaan pembeli."""
    f_name = _clean_str(farmer_name)
    name_salutation = f"Pak/Bu {f_name}" if f_name and f_name.lower() not in {"petani", "penjual", "unknown", "-"} else "Bapak/Ibu"
    loc_f = _clean_str(farmer_location)
    loc_farmer_str = f" di {loc_f}" if loc_f and loc_f != "-" else ""
    loc_b = _clean_str(buyer_location)
    loc_buyer_str = f" di {loc_b}" if loc_b and loc_b != "-" else ""
    
    vol_str = f" sekitar {needed_vol_kg:g} kg" if needed_vol_kg and needed_vol_kg > 0 else ""
    
    lines = [
        f"Halo {name_salutation}, salam kenal dari tim kemitraan GoTani.",
        "",
        f"Kami melihat informasi ketersediaan pasokan {commodity.title()}{loc_farmer_str}. "
        f"Saat ini mitra pembeli kami{loc_buyer_str} sedang membutuhkan pasokan {commodity.lower()}{vol_str} dalam waktu dekat.",
        "",
        "Apakah stok tersebut saat ini masih tersedia untuk panen atau pengiriman mendatang? "
        "Jika berkenan, kami ingin mendiskusikan spesifikasi mutu komoditas dan penawaran harga terbaik yang saling menguntungkan.",
        "",
        "Terima kasih atas waktunya. (Apabila pesan ini kurang berkenan atau persediaan sudah habis, mohon diabaikan).",
    ]
    return "\n".join(lines)


def draft_farmer_outreach_for_lead(
    farmer_name: Any,
    commodity: str,
    farmer_location: Any,
    volume_kg: float | None = None,
    price_per_kg: float | None = None,
) -> str:
    """Draf pesan outreach pertama (eksplorasi prospek scraping) ke petani untuk Tab 1."""
    f_name = _clean_str(farmer_name)
    name_salutation = f"Pak/Bu {f_name}" if f_name and f_name.lower() not in {"petani", "penjual", "unknown", "-"} else "Bapak/Ibu"
    loc_f = _clean_str(farmer_location)
    loc_str = f" wilayah {loc_f}" if loc_f and loc_f != "-" else ""
    
    details = []
    if volume_kg and volume_kg > 0:
        details.append(f"volume sekitar {volume_kg:g} kg")
    if price_per_kg and price_per_kg > 0:
        details.append(f"penawaran kisaran Rp {price_per_kg:,.0f}/kg")
    
    detail_str = f" ({', '.join(details)})" if details else ""
    
    lines = [
        f"Halo {name_salutation}, salam kenal dari tim GoTani.",
        "",
        f"Kami membaca informasi penawaran pasokan {commodity.title()}{detail_str}{loc_str} di komunitas agribisnis. "
        "GoTani adalah platform penghubung hasil panen petani langsung ke jaringan distributor dan pasar induk.",
        "",
        f"Apakah pasokan {commodity.lower()} Bapak/Ibu saat ini masih tersedia? "
        "Kami ingin mendata kapasitas rutin Anda untuk kami sambungkan dengan permintaan pembeli terverifikasi di jaringan kami.",
        "",
        "Terima kasih atas perhatiannya. (Mohon abaikan pesan ini jika pasokan sudah tidak tersedia atau Anda tidak berkenan dihubungi).",
    ]
    return "\n".join(lines)


def draft_buyer_outreach_for_match(
    buyer_name: Any,
    commodity: str,
    buyer_location: Any,
    needed_vol_kg: float | None = None,
    suggested_price: float | None = None,
    is_pool: bool = False,
    num_farmers: int = 1,
    farmer_locations: list[str] | None = None,
) -> str:
    """Draf pesan outreach penawaran pasokan ke pembeli (demand lead) untuk Tab 2."""
    b_name = _clean_str(buyer_name) or "Bapak/Ibu"
    loc_b = _clean_str(buyer_location)
    loc_buyer = f" untuk area {loc_b}" if loc_b and loc_b != "-" else ""
    
    price_note = ""
    if suggested_price and suggested_price > 0:
        price_note = f"\nEstimasi penawaran harga sampai ke lokasi penerimaan adalah Rp {suggested_price:,.0f}/kg (sudah termasuk koordinasi logistik dan kurasi mutu)."
    
    has_vol = (needed_vol_kg is not None and float(needed_vol_kg) > 0)
    vol_target_desc = f"target {float(needed_vol_kg):g} kg" if has_vol else "kebutuhan volume Anda"
    vol_prep_desc = f"dengan kesiapan volume {float(needed_vol_kg):g} kg " if has_vol else "dengan kapasitas volume yang siap kirim "
    vol_req_desc = f" sebanyak {float(needed_vol_kg):g} kg" if has_vol else ""

    if is_pool and num_farmers > 1:
        locs_list = [_clean_str(l) for l in (farmer_locations or []) if _clean_str(l) and _clean_str(l) != "-"]
        locs_desc = f" ({', '.join(dict.fromkeys(locs_list))})" if locs_list else ""
        supply_desc = (
            f"tim GoTani telah menyiapkan program smart pooling dengan mengagregasi pasokan dari {num_farmers} petani mitra binaan terdekat{locs_desc} "
            f"untuk memenuhi {vol_target_desc} secara terkonsolidasi."
        )
    else:
        supply_desc = (
            f"tim GoTani telah mengidentifikasi pasokan petani terverifikasi {vol_prep_desc}"
            "dan jadwal panen yang sesuai dengan kebutuhan Anda."
        )

    lines = [
        f"Halo tim {b_name}, salam hangat dari GoTani.",
        "",
        f"Menindaklanjuti permintaan pasokan komoditas {commodity.title()}{vol_req_desc}{loc_buyer}, {supply_desc}",
        f"{price_note}",
        "",
        "Apakah kami dapat mengirimkan rincian spesifikasi mutu dan mendiskusikan jadwal rencana penerimaan barang lebih lanjut?",
        "",
        "Terima kasih atas kerja samanya.",
    ]
    # Filter empty lines if price_note was empty
    cleaned_lines = []
    for l in lines:
        if l == "" and cleaned_lines and cleaned_lines[-1] == "":
            continue
        cleaned_lines.append(l)
    return "\n".join(cleaned_lines)


def build_matches_export_dataframe(matches_list: list[dict]):
    """Format data hasil matchmaking dan pooling ke DataFrame terstruktur untuk ekspor CSV/Excel (PRD §7.5)."""
    import pandas as pd

    records = []
    for m in matches_list:
        is_pool = (m.get("kind") == "pool")
        items = m.get("items", [])
        margin_info = m.get("margin", {}) or {}
        
        # Ringkasan petani
        farmer_summaries = []
        farmer_phones = []
        for it in items:
            f_name = it.get("farmer_name") or "Petani"
            f_loc = it.get("farmer_location") or "-"
            f_vol_val = it.get("allocated_kg")
            f_vol_str = f"{float(f_vol_val):g} kg" if (f_vol_val is not None) else "volume tidak ditentukan"
            f_pr = it.get("farmer_price")
            pr_str = f"Rp {float(f_pr):,.0f}/kg" if (f_pr is not None) else "harga belum tertera"
            farmer_summaries.append(f"{f_name} ({f_loc}, {f_vol_str}, {pr_str})")
            if it.get("farmer_phone"):
                farmer_phones.append(str(it.get("farmer_phone")))
        
        records.append({
            "Match_ID": m.get("match_id"),
            "Tipe_Match": "Smart Pooling" if is_pool else "Match Tunggal",
            "Tier": m.get("tier"),
            "Skor_Kecocokan": m.get("score"),
            "Status_Alur": m.get("status"),
            "Hasil_Transaksi": m.get("outcome") or "pending",
            "Keterangan_Hasil": m.get("outcome_reason") or "",
            "Nama_Pembeli": m.get("buyer_name"),
            "Komoditas": m.get("product"),
            "Kebutuhan_Pembeli_Kg": m.get("buyer_vol"),
            "Lokasi_Pembeli": m.get("buyer_location"),
            "Anggaran_Maks_Rp": m.get("buyer_max_price") or "",
            "Tenggat_Kebutuhan": m.get("buyer_needed_date") or "",
            "Total_Volume_Terpenuhi_Kg": m.get("total_volume_kg"),
            "Cakupan_Persen": m.get("coverage_pct"),
            "Estimasi_Margin_GoTani_Rp": margin_info.get("est_gross_margin_rp", 0),
            "Harga_Rekomendasi_Rp": margin_info.get("suggested_price", 0),
            "Jumlah_Petani": len(items),
            "Rincian_Petani": " | ".join(farmer_summaries),
            "Kontak_Pembeli": m.get("buyer_phone") or "",
            "Kontak_Petani": ", ".join(dict.fromkeys(farmer_phones)),
            "Catatan_Gap": "; ".join(m.get("gaps", [])),
            "Waktu_Dibuat": m.get("matched_at") or "",
        })
    
    return pd.DataFrame(records)


"""Modul Handover Engine & Eskalasi Otomatis ke Tim Manusia (PRD §7.8 / F8.7).

Mengevaluasi balasan masuk dari lead untuk mendeteksi kapan sistem harus mengalihkan
kendali percakapan dari AI ke staf sales/CS manusia GoTani.

Pemicu Handover (F8.7):
1. Lead menyatakan tertarik (sesuai closing definition kampanye).
2. Ada negosiasi harga atau syarat pembayaran.
3. Pertanyaan apakah ini AI/bot (wajib dijawab jujur dan ditawarkan sambungan staf).
4. Komplain, nada negatif, atau kecurigaan penipuan.
5. Pertanyaan di luar cakupan pengetahuan AI atau AI ragu.
"""
from __future__ import annotations

import re
from typing import Any
from .compliance import detect_opt_out_intent


# 1. Pola Pertanyaan Bot / Identitas AI (F8.3 / G4)
BOT_INQUIRY_PATTERNS = [
    r"\b(kamu\s*(bot|ai|robot|mesin|otomatis)?)\b",
    r"\b(ini\s*(bot|ai|robot|orang\s*beneran|manusia|admin|cs|staf)?)\b",
    r"\b(apakah\s*(ini|anda|kamu)\s*(bot|ai|robot|sistem))\b",
    r"\b(bicara\s*sama\s*(orang|manusia|asli|admin|sales))\b",
    r"\b(chat\s*otomatis|auto\s*reply|autotext)\b",
]

# 2. Pola Ketertarikan Transaksi / Sinyal Deal (Closing Signals F8.8)
INTEREST_PATTERNS = [
    r"\b(tertarik|minat|boleh|bisa|siap|mau|setuju|deal)\b",
    r"\b(kirim\s*(sampel|sample|penawaran|proposal|pricelist|katalog|spek|spesifikasi))\b",
    r"\b(bisa\s*(kirim|tampung|pasok|angkut|ambil|ketemu|telepon|telfon|call|zoom|jadwalkan))\b",
    r"\b(lokasi\s*(kebun|gudang|lapak|kios)\s*dimana)\b",
    r"\b(stok\s*(ada|ready|tersedia|banyak|aman))\b",
    r"\b(jadwal\s*(panen|kirim|antar))\b",
]

# 3. Pola Negosiasi Harga & Syarat Pembayaran (F8.7)
NEGOTIATION_PATTERNS = [
    r"\b(kurang|turun|potong|diskon|tawar|nego|miring|kemahalan)\b",
    r"\b(harga\s*(pas|net|nett|grosir|terbaik|kawan|petani|modal))\b",
    r"\b(tempo|termin|dp|uang\s*muka|pembayaran|cash|transfer|titip|konsinyasi)\b",
    r"\b(ongkir|ongkos\s*kirim|tanggung\s*siapa|franco|loco)\b",
]

# 4. Pola Komplain / Nada Negatif
COMPLAINT_PATTERNS = [
    r"\b(penipu|bohong|abal|hoax|hati\s*hati|kecewa|rugi|ancam)\b",
    r"\b(jangan\s*sembarangan|ganggu|spam|lapor|polisi)\b",
]

COMPILED_BOT = [re.compile(p, re.IGNORECASE) for p in BOT_INQUIRY_PATTERNS]
COMPILED_INTEREST = [re.compile(p, re.IGNORECASE) for p in INTEREST_PATTERNS]
COMPILED_NEGO = [re.compile(p, re.IGNORECASE) for p in NEGOTIATION_PATTERNS]
COMPILED_COMPLAINT = [re.compile(p, re.IGNORECASE) for p in COMPLAINT_PATTERNS]


def evaluate_inbound_message(text: str | None, closing_def: str = "lead_interested") -> dict[str, Any]:
    """Evaluasi pesan masuk dari lead untuk menentukan apakah perlu eskalasi (handover) ke manusia.

    Kembalian:
    {
        "needs_handover": bool,
        "trigger_type": "opt_out" | "bot_inquiry" | "deal_interest" | "negotiation" | "complaint" | "routine",
        "confidence": float,
        "reason": str,
        "suggested_action": str,
    }
    """
    if not text or not isinstance(text, str) or not text.strip():
        return {
            "needs_handover": False,
            "trigger_type": "routine",
            "confidence": 0.0,
            "reason": "Teks kosong atau tidak terbaca",
            "suggested_action": "ignore",
        }

    raw = text.strip()

    # 1. Pengecekan Permintaan Berhenti (Opt-Out / UU PDP)
    is_opt_out, opt_reason = detect_opt_out_intent(raw)
    if is_opt_out:
        return {
            "needs_handover": False,
            "trigger_type": "opt_out",
            "confidence": 0.95,
            "reason": f"Permintaan berhenti/opt-out terdeteksi ({opt_reason})",
            "suggested_action": "register_opt_out_and_stop",
        }

    # 2. Pengecekan Komplain / Nada Negatif
    for p in COMPILED_COMPLAINT:
        if p.search(raw):
            return {
                "needs_handover": True,
                "trigger_type": "complaint",
                "confidence": 0.90,
                "reason": f"Terdeteksi komplain atau nada negatif: '{p.pattern}'",
                "suggested_action": "handover_to_human_complaint",
            }

    # 3. Pengecekan Pertanyaan Bot / Identitas AI (F8.3)
    for p in COMPILED_BOT:
        if p.search(raw):
            return {
                "needs_handover": True,
                "trigger_type": "bot_inquiry",
                "confidence": 0.85,
                "reason": "Lawan bicara menanyakan apakah ini AI/bot (wajib jawab jujur)",
                "suggested_action": "answer_honestly_and_offer_human",
            }

    # 4. Pengecekan Negosiasi Harga & Syarat Pembayaran
    for p in COMPILED_NEGO:
        if p.search(raw):
            return {
                "needs_handover": True,
                "trigger_type": "negotiation",
                "confidence": 0.85,
                "reason": f"Terdeteksi negosiasi harga atau syarat transaksi: '{p.pattern}'",
                "suggested_action": "handover_to_human_negotiation",
            }

    # 5. Pengecekan Ketertarikan / Sinyal Deal
    for p in COMPILED_INTEREST:
        if p.search(raw):
            return {
                "needs_handover": True,
                "trigger_type": "deal_interest",
                "confidence": 0.80,
                "reason": f"Sinyal ketertarikan lead terdeteksi (sesuai target {closing_def})",
                "suggested_action": "handover_to_human_closing",
            }

    # 6. Komunikasi Rutin / Pertanyaan Lanjutan Biasa
    return {
        "needs_handover": False,
        "trigger_type": "routine",
        "confidence": 0.70,
        "reason": "Percakapan rutin / pertanyaan informasi umum yang dapat ditanggapi AI",
        "suggested_action": "ai_generate_contextual_reply",
    }

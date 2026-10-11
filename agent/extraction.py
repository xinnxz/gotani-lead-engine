"""Ekstraksi dengan LLM, per batch (PRD §9.2: batch beberapa post dalam satu panggilan)."""
from __future__ import annotations

from .campaign import CampaignSpec
from .llm_gateway import LLMGateway

EXTRACT_SYSTEM = """Kamu adalah analis intelijen agribisnis Indonesia tingkat senior yang sangat teliti.
Tugasmu adalah memverifikasi dan mengekstrak data prospek (leads) dari postingan media sosial / grup Facebook.
Bahasa postingan bisa berupa bahasa Indonesia santai, slang petani, bahasa daerah (Jawa, Sunda), singkatan, atau salah ketik.

ATURAN KLASIFIKASI & VALIDASI KETAT:
1. INTENT:
   - "supply": Menawarkan/menjual panen atau stok hasil tani riil (misal: "panen melon", "ready semangka di lahan", "ecer/borongan").
     Kalimat seperti "yang butuh silakan japri" atau "minat WA" pada postingan penjual tetap "supply".
   - "demand": Mencari/membeli hasil tani (misal: "butuh melon 2 ton", "cari supplier semangka", "tampung hasil panen").
   - "other": Iklan bibit, benih, pupuk, pestisida, alat/mesin tani, pinjaman modal, tanah kebun, atau jasa transportasi.
   - "irrelevant": Diskusi umum, tanya jawab tips berkebun, resep masakan, postingan hoax, atau komoditas yang TIDAK SESUAI dengan target kampanye.

2. PENANGANAN KOMODITAS (PRODUCT):
   - Jika postingan membahas komoditas yang berbeda dari yang dicari kampanye, set intent = "irrelevant".
   - Ekstrak "variety" (misal: "madesta", "aromanis", "golden", "inthanon") dan "grade" (misal: "grade A", "super", "BS", "afkir") jika ada.

3. ANGKA & SATUAN (Wajib akurat):
   - Field yang tidak tertulis di teks WAJIB diisi null. DILARANG MENGARANG ATAU MENEBAK.
   - volume_value: angka nominal (misal: "2 ton" → 2, "5 kuintal" → 5, "500 kg" → 500).
   - volume_unit: satuan aslinya ("kg", "kuintal", "kw", "ton", "petak").
   - price_value: ubah bahasa gaul harga ke Rupiah penuh (contoh: "5rb" → 5000, "7,5k" → 7500, "10.000" → 10000).
   - price_unit: satuan harga (biasanya "kg", "ikat", "butir", "borongan").

4. LOKASI & WAKTU:
   - location_text: nama desa, kecamatan, kabupaten, atau pasar yang disebut di postingan (misal: "Minggirsari Blitar", "Kec. Pare").
   - available_text: waktu panen/ketersediaan (misal: "panen besok lusa", "ready tiap hari", "petik minggu depan").

5. KONTAK & PRIVASI:
   - Token seperti [PHONE_1] atau [EMAIL_1] adalah nomor kontak asli yang telah disensor demi privasi.
   - SALIN token tersebut apa adanya, jangan dimodifikasi atau ditebak.

6. FLAGS (Tanda Peringatan):
   - Beri flag jika terdeteksi: ["calo", "reseller", "indikasi_penipuan", "harga_tidak_wajar", "stok_tidak_pasti"].
"""

FORMAT_HINT = (
    '[{"idx":0,"intent":"supply","entity_name":"Pak Budi","product":"melon","variety":"madesta","grade":"super",'
    '"volume_value":500,"volume_unit":"kg","price_value":7000,"price_unit":"kg","location_text":"Nganjuk",'
    '"available_text":"panen lusa","flags":[],"evidence":{"product":"melon madesta","volume":"500 kg","price":"7rb/kg"}}]'
)


def llm_extract(gateway: LLMGateway, spec: CampaignSpec, masked_texts: list[str]) -> list[dict | None]:
    """Return list sepanjang input. Elemen None berarti LLM tidak mengembalikan hasil untuk post itu."""
    synonyms = ", ".join(spec.product.synonyms) or "-"
    varieties = ", ".join(spec.product.attributes.get("variety") or []) or "-"
    posts = "\n\n".join(f"### idx={i}\n{t[:1500]}" for i, t in enumerate(masked_texts))
    prompt = (
        f"Kampanye: mencari {spec.target_intent} untuk komoditas '{spec.product.name}' "
        f"(sinonim: {synonyms}; varietas dicari: {varieties}).\n\n"
        f"POSTS:\n{posts}\n\nContoh format jawaban:\n{FORMAT_HINT}"
    )
    data = gateway.generate_json(prompt, purpose="extract")
    if isinstance(data, dict):
        data = data.get("items") or data.get("results") or [data]
    out: list[dict | None] = [None] * len(masked_texts)
    for item in data if isinstance(data, list) else []:
        if not isinstance(item, dict):
            continue
        idx = item.get("idx")
        if isinstance(idx, int) and 0 <= idx < len(out):
            item.setdefault("flags", [])
            item.setdefault("evidence", {})
            out[idx] = item
    return out

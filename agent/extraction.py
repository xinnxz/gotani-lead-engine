"""Ekstraksi dengan LLM, per batch (PRD §9.2: batch beberapa post dalam satu panggilan)."""
from __future__ import annotations

from .campaign import CampaignSpec
from .llm_gateway import LLMGateway

EXTRACT_SYSTEM = """Kamu mengekstrak data lead agribisnis dari postingan media sosial / halaman web berbahasa Indonesia
(boleh campur bahasa daerah, singkatan, dan salah ketik). Balas HANYA JSON array, satu objek per post.

Aturan:
- intent: "supply" (menawarkan/menjual hasil tani), "demand" (mencari/membeli hasil tani),
  "other" (iklan jasa, bibit, pupuk, alat, pinjaman, dll), atau "irrelevant".
  Kalimat seperti "yang butuh silakan japri" pada post penjual tetap "supply".
- Field yang tidak disebut WAJIB null. Jangan mengarang atau menebak.
- entity_name: nama orang/usaha/kelompok tani bila disebut di teks.
- volume_value + volume_unit: apa adanya dari teks (kg, kuintal, kw, ton).
- price_value: rupiah penuh (4rb → 4000, 3,5k → 3500); price_unit: satuan harganya (kg, kw, ton).
- location_text: lokasi yang disebut (desa/kecamatan/kabupaten/provinsi).
- available_text: frasa waktu panen/ketersediaan/kebutuhan (misal "panen minggu depan").
- Token seperti [PHONE_1] atau [EMAIL_1] adalah kontak yang sudah disensor. Jangan diubah atau ditebak.
- flags: pilih dari ["calo", "reseller", "indikasi_penipuan", "harga_tidak_wajar"] bila ada tandanya.
- evidence: potongan teks asli (maks 60 karakter) untuk setiap field yang terisi; kuncinya nama field."""

FORMAT_HINT = (
    '[{"idx":0,"intent":"supply","entity_name":null,"product":"melon","variety":null,"grade":null,'
    '"volume_value":2,"volume_unit":"kuintal","price_value":4000,"price_unit":"kg","location_text":"Kediri",'
    '"available_text":null,"flags":[],"evidence":{"volume":"2 kuintal","price":"4rb/kg"}}]'
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

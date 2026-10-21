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

2. PENANGANAN KOMODITAS (PRODUCT) - SANGAT KETAT:
   - Judul postingan (baris pertama) seringkali adalah nama grup Facebook (misal: "Grup Petani Cabai & Kelapa").
   - KAMU WAJIB memverifikasi apa yang BENAR-BENAR DITAWARKAN / DIBUTUHKAN pada ISI POSTINGAN (snippet).
   - Jika isi postingan menjual kelapa, durian, atau komoditas lain padahal target kampanye adalah cabai, MAKA:
     * product: isi dengan komoditas asli yang dijual (misal "kelapa")
     * intent: WAJIB diisi "irrelevant"
   - Dilarang keras melabeli komoditas sebagai target kampanye jika isi postingan menjual komoditas berbeda!
   - Ekstrak "variety" (misal: "madesta", "golden", "ori 212") dan "grade" (misal: "grade A", "super", "BS") jika ada.

3. NAMA PEMOSTING (entity_name) - SANGAT PENTING:
   - Snippet Google dari Facebook biasanya mengandung pola:
     "NamaGrup · NamaAuthor · TanggalPosting · 🌐"  atau
     "NamaGrup · NamaAuthor · Tanggal"  atau
     "NamaAuthor - NamaGrup · Tanggal"
   - NamaAuthor biasanya 2-4 kata, diawali huruf kapital, misal: "Al Farisy", "Pak Budi Santoso", "Ahmad Rizal".
   - Kadang author ada di akhir snippet: "... minat WA · by NamaAuthor"
   - WAJIB ekstrak entity_name = NamaAuthor (bukan nama grup!).
   - Jika tidak ditemukan, isi null. DILARANG MENGARANG NAMA.

4. LOKASI (location_text) - CERDAS:
   - Ekstrak lokasi dari SEMUA sumber yang ada:
     a) Teks postingan: "kirim dari Nganjuk", "alamat Lempung", "pcc lempung"
     b) Nama Grup Facebook: "KUNIR GANDEKAN KARANGGAYAM (serba-serbi)" → lokasi: Karanggayam atau Kunir
     c) Nama pasar/kecamatan informal: "ps induk kramat jati", "pasar mangga dua"
   - "pcc" = singkatan tempat/pieces, perhatikan konteks.
   - Isi lokasi asli sebagaimana tertulis. Jangan tebak jika tidak ada.

5. ANGKA & SATUAN (Wajib akurat):
   - Field yang tidak tertulis di teks WAJIB diisi null. DILARANG MENGARANG ATAU MENEBAK.
   - volume_value: angka nominal (misal: "2 ton" → 2, "5 kuintal" → 5, "500 kg" → 500).
   - volume_unit: satuan aslinya (bisa: "kg", "kuintal", "kw", "ton", "petak", "kresek", "karung", "ikat", "biji", "butir", "dos", "pak", "polybag", "tandan", "sisir", "truk", "pickup").
     * PENTING: Jika teks tulis "1 kresek", volume_unit = "kresek", BUKAN "kg".
     * Jika satuan non-standar (kresek, ikat, dll), JANGAN konversi ke kg. Tulis apa adanya.
   - price_value: ubah bahasa gaul harga ke Rupiah penuh (contoh: "5rb" → 5000, "7,5k" → 7500, "10.000" → 10000, "15k" → 15000).
   - price_unit: satuan harga ASLI. Bisa: "kg", "ikat", "butir", "borongan", "kresek", "karung", "dos", "pak", "biji", "tandan", "sisir", "ton", "kuintal".
     * PENTING: "15k saja" per kresek → price_unit = "kresek", BUKAN "kg"!
     * Jika tidak jelas per apa, cek konteks kalimat.

6. SLANG & BAHASA GAUL PETANI:
   - "15k" / "15rb" = Rp 15.000
   - "nyus" / "nyuss" = enak/manis (deskripsi rasa, abaikan)
   - "pcc" = bisa berarti "pieces" atau nama tempat (lihat konteks)
   - "suluhan" = varietas/jenis lokal (bukan lokasi)
   - "ready" / "redi" = tersedia
   - "borongan" = beli semua sekaligus
   - "eceran" / "ecer" = beli satuan
   - "japri" = jalur pribadi (chat privat)
   - "COD" = cash on delivery
   - "bs" / "BS" = grade bawah (below standard)
   - "super" = grade atas

7. KONTAK & PRIVASI:
   - Token seperti [PHONE_1] atau [EMAIL_1] adalah nomor kontak asli yang telah disensor demi privasi.
   - SALIN token tersebut apa adanya, jangan dimodifikasi atau ditebak.

8. FLAGS (Tanda Peringatan):
   - Beri flag jika terdeteksi: ["calo", "reseller", "indikasi_penipuan", "harga_tidak_wajar", "stok_tidak_pasti"].
"""

FORMAT_HINT = (
    '[{"idx":0,"intent":"supply","entity_name":"Al Farisy","product":"melon","variety":"amanda","grade":null,'
    '"volume_value":1,"volume_unit":"kresek","price_value":15000,"price_unit":"kresek","location_text":"Lempung, Karanggayam",'
    '"available_text":"ready","flags":[],"evidence":{"product":"melon amanda","volume":"1 kresek","price":"15k/kresek","author":"Al Farisy","location_source":"nama grup"}}]'
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

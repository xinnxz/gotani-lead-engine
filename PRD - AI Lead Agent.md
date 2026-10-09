# PRD — AI Lead Agent (nama kerja)

**Agen AI untuk riset lead dinamis → database → matchmaking → sales**

| | |
|---|---|
| Versi | 0.4 — + rencana kerja 1 developer; milestone scrape pertama 16 Okt |
| Tanggal | 6 Oktober 2026 |
| Status | Draf, menunggu review tim GoTani |
| Pengguna pertama | Tim GoTani (agribisnis) |
| Target MVP (Fase 1) | ± 6 November 2026 |

> **Konvensi:** angka atau ambang bertanda **(usulan)** adalah titik awal yang dikalibrasi saat pilot, bukan keputusan final. Kode requirement (F2.4, G1, Q3, dst.) dipakai untuk rujukan silang.

---

## 0. Ringkasan

Bisnis cukup menjelaskan kebutuhannya lewat chat, misalnya *"saya tengkulak sawit, cari petani sawit varietas A di Kalimantan"*. AI bertanya balik sampai filternya lengkap. Setelah itu sebuah agent yang berjalan di laptop membuka browser dan menelusuri grup Facebook, Instagram, website buyer, direktori B2B, Google, serta marketplace. Data yang relevan diambil, diverifikasi, dan disimpan sebagai database yang setiap record-nya punya **skor relevansi** dan **skor confidence**.

Dua modul dibangun di atas database itu:

- **Matchmaking supply–demand** (Fase 2): mencocokkan penjual dan pembeli, termasuk saran menggabungkan beberapa penjual.
- **AI sales agent** (Fase 3): menghubungi lead, menindaklanjuti, dan menyerahkan ke manusia begitu lead tertarik.

Produk ditujukan untuk **bisnis secara umum**. **Agribisnis**, dimulai dari operasional GoTani sendiri, adalah pasar pertamanya.

---

## 1. Latar belakang & masalah

Cara kerja saat ini (manual):

- Data penjual (petani) dan pembeli dicari manual di grup-grup Facebook petani dan website buyer, lalu dicatat sendiri di Excel.
- Prosesnya lambat, sulit diskalakan, bergantung pada satu orang, dan sering menghasilkan duplikat.
- Tidak ada cara mengukur apakah data masih valid, misalnya post lama atau nomor yang sudah tidak aktif.
- Pencocokan petani dengan pembeli dilakukan dari ingatan atau spreadsheet. Outreach dan follow-up juga manual.

**Masalah inti:** mendapatkan lead yang **nyata dan relevan**, dengan cepat dan dalam jumlah cukup, bukan sekadar hasil scraping acak.

---

## 2. Visi & positioning

**Visi:** agen AI yang bisa diperintah dengan bahasa sehari-hari untuk menemukan, memverifikasi, mencocokkan, dan menghubungi calon mitra bisnis dari mana saja di internet.

- **Horizontal secara desain, vertikal secara go-to-market.** Engine-nya generik: ada kampanye, entitas, dan atribut dinamis. Template pertamanya adalah agribisnis.
- **GoTani adalah pengguna pertama dan design partner** (operator internal). Data dan feedback GoTani dipakai memvalidasi produk sebelum dibuka ke bisnis lain.

Tiga jenis tujuan kampanye (generik):

| Tujuan | Contoh agri (GoTani) | Contoh bisnis umum |
|---|---|---|
| `find_supply` | Cari petani melon dengan stok ≥500 kg di Jombang | Cari supplier kemasan di Jawa Timur |
| `find_demand` | Cari pedagang/eksportir yang butuh melon | Cari distributor yang butuh produk X |
| `find_customers` | — | Cari kafe di Surabaya untuk jasa foto menu |

Matchmaking dua sisi berlaku untuk pasangan supply ↔ demand. Pada kampanye `find_customers`, "match" berarti skor kecocokan lead terhadap profil pelanggan ideal (ICP).

---

## 3. Tujuan, non-goals & metrik

### 3.1 Tujuan Fase 1

1. Dari satu percakapan, AI menghasilkan spesifikasi kampanye yang lengkap.
2. Agent mengumpulkan lead dari beberapa jenis sumber secara otomatis selama laptop menyala.
3. Setiap lead punya bukti sumber, skor relevansi, dan skor confidence, tanpa duplikat.
4. Hasilnya langsung bisa dipakai tim di Google Sheets/Excel.

### 3.2 Non-goals Fase 1

- Mengirim pesan otomatis ke lead (masuk Fase 3).
- Matchmaking (Fase 2), dashboard web lengkap, voice AI, multi-tenant/SaaS, pembayaran.
- Agent membuat akun sendiri.
- Fitur apa pun untuk menghindari deteksi bot (lihat §10, G1).

### 3.3 Metrik sukses

Kriteria utama dari owner: **jumlah lead valid dan keyakinan bahwa datanya nyata serta relevan.**

**Definisi lead valid:** skor relevansi ≥70 (usulan), skor confidence ≥60 (usulan), punya ≥1 jalur kontak, dan sudah di-approve reviewer.

| Metrik | Target Fase 1 |
|---|---|
| Lead valid per minggu — kampanye **supply** (1 komoditas × 1 provinsi) | Minggu pertama ≥75 (termasuk backlog 30 hari); minggu berikutnya **≥25**, stretch 40 (usulan, §3.4) |
| Lead valid per minggu — kampanye **demand** (1 komoditas × 1 provinsi) | Minggu pertama ≥50; minggu berikutnya **≥15**, stretch 25 (usulan, §3.4) |
| Presisi review (% lead yang di-approve reviewer) | ≥70% (usulan) |
| Duplikat yang lolos ke Sheets | <5% (usulan) |
| % lead valid dengan nomor WA/telepon | ≥50% (usulan) |
| Biaya LLM + API per bulan | < Rp500.000 |
| Biaya per lead valid | Dipantau |
| Waktu review tim | ≤1 jam per kampanye per minggu (usulan) |

### 3.4 Dasar perhitungan target lead

Belum ada baseline manual, jadi target di atas diturunkan dari funnel berikut. **Semua angka adalah asumsi**, bukan data, dan akan diganti angka nyata setelah minggu pilot (lihat bagian Kalibrasi di bawah).

Contoh: kampanye supply "melon, Jawa Timur", satu akun FB + sumber web/IG.

| Tahap funnel (per minggu, kondisi stabil) | Asumsi | Hasil |
|---|---|---|
| Grup relevan yang dipantau | ±15 grup hasil penemuan dinamis (F2.1a–f) | — |
| Post baru yang dipindai | ±15 post baru per grup per hari | ±1.500 |
| Intent cocok (menawarkan melon) | 5–10% | 75–150 |
| Lokasi di Jawa Timur | 50–70% (sebagian grup tingkat nasional) | 50–90 |
| Setelah dedup (repost lintas grup/hari) | −30–40% | 35–60 |
| Lolos ambang relevansi & confidence | ±70% | 25–40 |
| Tambahan dari web/IG | — | +5–15 |
| Di-approve reviewer | Presisi 70% | **±20–40** |

Catatan:

- **Kecepatan agent bukan pembatasnya.** Dengan 5 jam/hari × 6 hari × ±100 post/jam/akun, kapasitas baca ±3.000 post/minggu, di atas volume post baru. Yang membatasi hasil adalah jumlah post relevan di grup-grup tersebut.
- **Minggu pertama lebih tinggi** (±3× kondisi stabil), karena agent juga membaca backlog 30 hari terakhir.
- **Demand lebih rendah.** Post "cari/butuh" jauh lebih jarang (±1–3% dari post). Sumber utama pembeli adalah Google Places (distributor buah, toko buah, pasar induk, supermarket) dan direktori B2B. Hasilnya banyak di run pertama, lalu hanya bertambah sedikit setiap minggu.
- **Kalibrasi.** Agent mencatat jumlah di setiap tahap funnel per sumber (F2.8). Setelah minggu pilot, asumsi di atas diganti angka nyata dan target diperbarui.
- **Faktor yang menggeser angka:** musim panen komoditas, jumlah grup aktif di wilayah itu, dan akun yang terkena limit.

---

## 4. Pengguna

| Peran | Mulai fase | Kebutuhan |
|---|---|---|
| Operator GoTani | 1 | Ngobrol dengan AI, menjalankan kampanye, ekspor data |
| Reviewer GoTani (boleh orang yang sama) | 1 | Approve/reject lead dengan cepat; feedback-nya memperbaiki AI |
| Sales/CS GoTani | 2 | Ringkasan konteks saat ditelepon; menerima handover lead yang tertarik |
| Petani (supply) & pembeli (demand) | 3 | Dihubungi secara relevan dan sopan, bisa minta berhenti kapan saja |
| Bisnis umum (self-serve) | Roadmap | Sama seperti operator, untuk bisnisnya sendiri |

Di fase awal, petani dan pembeli **tidak login**. Mereka hanya menjadi objek riset dan, mulai Fase 3, dihubungi.

---

## 5. Ruang lingkup & fase

| Fase | Waktu | Isi |
|---|---|---|
| **1 — Riset & database** | 7 Okt – ±6 Nov 2026 | Kuesioner chat → Campaign Spec; browser agent lokal; ekstraksi, normalisasi, dedup; skor relevansi & confidence; SQLite + sinkron Google Sheets + ekspor Excel; antrean review; handoff ke manusia. Sumber: grup FB, web/B2B, Google Places. **Scrape pertama: Jumat 16 Okt** (§12). |
| **2 — Matchmaking** | Nov – Des 2026 | Matching supply–demand + saran pooling + tier aksi; bantuan telepon masuk; monitoring sumber terjadwal; dashboard web ringan; executor Instagram, marketplace & TikTok (digeser dari Fase 1 karena hanya ada 1 developer) |
| **3 — AI sales agent** | Des 2026 – Jan 2027 | Percakapan WA/DM/email: draf → semi-otomatis → otomatis lewat jalur resmi; memori percakapan; follow-up; handover; definisi closing per kampanye |
| **Roadmap** | 2027 | Voice AI; skor match terkalibrasi dari hasil deal; pindah dari laptop ke server; multi-tenant SaaS & monetisasi |

---

## 6. Alur end-to-end (contoh)

```
Operator : "Saya tengkulak sawit, cari petani sawit varietas A di Kalimantan."
AI       : tanya balik → provinsi mana? volume minimal? petani swadaya/plasma?
           harga beli? mulai kapan?
         → ringkasan → operator konfirmasi → Campaign Spec (JSON)

Planner  : kata kunci + sinonim (TBS, buah sawit, sawit swadaya, ...),
           grup FB & hashtag IG, query web, daftar lokasi
Executor : jalan per sumber (rate-limited) → item mentah + bukti
Pipeline : klasifikasi intent → ekstraksi LLM → normalisasi → dedup → skoring
Output   : Google Sheets tab "Review" → reviewer approve/reject → tab "Database"

(Fase 2) : match petani ↔ pembeli → tier aksi
(Fase 3) : AI sales: sapa → kualifikasi → follow-up → lead tertarik → handover ke manusia
```

---

## 7. Requirement fungsional

### 7.1 Kuesioner onboarding (chat) — Fase 1

- **F1.1** Chat bebas berbahasa Indonesia yang toleran terhadap bahasa campuran, bahasa daerah, dan singkatan.
- **F1.2** AI mengisi *slot* yang wajib untuk tujuan kampanyenya, dan hanya bertanya balik untuk slot yang kosong atau ambigu (maksimal 1–2 pertanyaan per giliran). Slot generiknya:
  - tujuan;
  - konteks bisnis;
  - entitas target;
  - produk/jasa beserta atributnya (varietas, grade, spesifikasi);
  - lokasi (include/exclude);
  - volume & satuan;
  - waktu;
  - harga;
  - sumber yang dipakai;
  - field wajib;
  - batas kesegaran data (hari);
  - definisi closing (dipakai di Fase 3).
- **F1.3** AI mengusulkan sinonim dan istilah lokal, misalnya "kw/kuintal", "TBS", "japri", atau nama varietas lokal. Operator bisa mengeditnya.
- **F1.4** Sebelum agent jalan, AI menampilkan ringkasan kampanye, lalu operator mengonfirmasi.
- **F1.5** Output-nya berupa **Campaign Spec JSON** yang tersimpan dan bisa di-clone atau diedit.
- **F1.6** Agri menjadi template vertikal pertama, dengan atribut komoditas, varietas, grade, volume, waktu panen, lokasi, harga, dan sertifikasi. Untuk bisnis non-agri, slot atribut disusun dinamis oleh AI dari percakapan.

Contoh Campaign Spec:

```json
{
  "campaign_id": "cmp-2026-001",
  "goal": "find_supply",
  "business_context": "Tengkulak sawit, membeli TBS dari petani swadaya",
  "target_entity": "petani / kelompok tani sawit",
  "product": {
    "name": "Tandan Buah Segar (TBS) sawit",
    "attributes": { "variety": ["Varietas A"], "grade": null },
    "synonyms": ["TBS", "buah sawit", "kelapa sawit", "sawit swadaya"]
  },
  "location": { "include": ["Kalimantan Barat", "Kalimantan Tengah", "Kalimantan Timur"], "exclude": [] },
  "volume": { "min": 5, "unit": "ton", "per": "bulan" },
  "timeframe": { "from": "2026-11-01", "to": "2026-12-31" },
  "price": { "max": null, "currency": "IDR", "unit": "kg" },
  "sources": ["facebook_groups", "instagram", "web_b2b", "google_places"],
  "required_fields": ["product", "location", "contact_any"],
  "freshness_days": 30,
  "closing_definition": "lead_interested"
}
```

### 7.2 Agent riset & scraping — Fase 1

**Prinsip: text-first, LLM hemat.**

- Navigasi ke sumber yang strukturnya sudah dikenal (FB, IG) memakai skrip Playwright deterministik.
- LLM dipakai untuk memahami teks (klasifikasi & ekstraksi) dan untuk menjelajah website yang belum dikenal.
- Navigasi berbasis screenshot hanya menjadi fallback, karena paling boros token.

**F2.1 Planner.** Mengubah Campaign Spec menjadi rencana pencarian: sumber, query/kata kunci, grup/hashtag, urutan prioritas, dan kuota per sumber. Planner bekerja **tanpa seed list**.

**Penemuan sumber dinamis.** Operator cukup menyebut komoditas dan wilayah, misalnya "melon, Jawa Timur". Agent sendiri yang mencari grup, akun, dan website.

- **F2.1a Ekspansi wilayah.** Provinsi di spec dipecah menjadi kabupaten/kota berdasarkan dataset kode wilayah Kemendagri (Jawa Timur: 38 kabupaten/kota). Urutan prioritasnya:
  1. sentra produksi komoditas tersebut, yang dicari agent sendiri lewat web search dari data BPS/dinas pertanian;
  2. kabupaten yang ternyata sering muncul di hasil, dipelajari otomatis selama run;
  3. kabupaten lainnya.

  Operator bisa mengubah urutan atau mengecualikan wilayah.
- **F2.1b Generator query.** Query dibentuk dari kombinasi komoditas × sinonim/varietas × wilayah (provinsi, kabupaten, kadang kecamatan sentra) × pola niat:
  - supply: "jual", "panen", "ready", "stok";
  - demand: "cari", "butuh", "terima", "beli";
  - nama grup generik: "jual beli hasil tani {kabupaten}", "petani {kabupaten}", "komunitas {komoditas} {provinsi}".

  Contoh untuk melon Jawa Timur: `petani melon kediri`, `melon blitar`, `jual beli hasil bumi jombang`, `komunitas petani melon jawa timur`, `#melonkediri`, `supplier melon surabaya`.
- **F2.1c Penemuan grup Facebook.** Query di atas dijalankan di pencarian grup FB. Setiap kandidat grup diberi **skor grup** dari empat hal:
  - kecocokan nama/deskripsi dengan komoditas dan wilayah;
  - aktivitas (jumlah post per minggu, tanggal post terakhir);
  - jumlah anggota;
  - yield sampel: % post relevan dari 20–30 post terbaru yang bisa dibaca.

  Grup publik langsung dibaca. Grup privat dengan skor tinggi masuk antrean "minta join" untuk manusia (F2.3).
- **F2.1d Sumber lain dengan pola yang sama:**
  - hashtag dan akun IG (`#petanimelon`, `#melonkediri`);
  - website dan direktori lewat search API;
  - untuk kampanye demand, Google Places per kota dengan kategori calon pembeli (distributor buah, toko buah, pasar induk, supermarket).
- **F2.1e Registry sumber yang belajar.** Semua grup, akun, dan website yang ditemukan disimpan di `source_registry` bersama skor dan yield historisnya (lead valid per 100 post). Kampanye berikutnya memakai ulang dan memperbarui registry ini:
  - sumber dengan yield tinggi dipindai lebih sering;
  - sumber dengan yield rendah diturunkan prioritasnya;
  - ±20% kuota tetap dipakai untuk menjelajah sumber baru.

  Dengan begitu seed list terbentuk sendiri dari pemakaian. Operator boleh menambahkan sumber secara manual, tapi tidak wajib.
- **F2.1f Perluasan otomatis.** Kalau setelah run awal hasilnya masih di bawah target, planner melebarkan pencarian secara bertahap: kabupaten tetangga, lalu sinonim tambahan, lalu grup tingkat nasional (lokasinya difilter saat ekstraksi). Setiap perluasan dilaporkan ke operator.

**F2.2 Executor per sumber:**

| Sumber | Prioritas | Cara | Catatan |
|---|---|---|---|
| Grup Facebook | **P0** | Browser login dengan akun dummy (satu profil Chromium per akun). Cari grup dari kata kunci, baca feed, dan gunakan pencarian di grup yang sudah diikuti. | Join grup baru diserahkan ke manusia, karena biasanya ada pertanyaan dari admin. |
| Website buyer & direktori B2B | **P0** | Search API → buka halaman → ekstraksi kontak dan kebutuhan | Hormati `robots.txt` |
| Instagram | P1 → **Fase 2** | Browser login; telusuri hashtag/kata kunci, bio, dan caption | Kuota ketat |
| Google Maps / bisnis lokal | P1 | Places API resmi, bukan scraping halaman Maps | Lihat §10 |
| Marketplace (Tokopedia, Shopee, dll.) | P2 → **Fase 2** | Browser; kalau perlu login, minta manusia membuatkan atau me-login-kan akun | |
| TikTok | P2 → **Fase 2** | Browser; caption dan bio | |

P0 adalah dua sumber yang selama ini dipakai manual. Karena hanya ada 1 developer, Fase 1 dibatasi ke grup FB, web/B2B, dan Google Places. Instagram, marketplace, dan TikTok digeser ke Fase 2.

- **F2.3 Handoff ke manusia.** Kalau agent menemui login, checkpoint/verifikasi, CAPTCHA, pertanyaan join grup, atau kebutuhan membuat akun:
  - tugas itu dijeda dan operator diberi notifikasi di UI/desktop;
  - agent mengerjakan tugas lain sementara menunggu;
  - setelah manusia selesai, tugas dilanjutkan.
- **F2.4 Rate limit.** Batasnya konservatif dan bisa diatur per akun per sumber (jumlah halaman per jam, jeda antar-aksi). Kalau platform memberi peringatan atau limit, akun itu berhenti otomatis untuk sisa hari tersebut dan operator diberi tahu.
- **F2.5 Berjalan selama laptop menyala.** Status disimpan berkala (checkpoint), sehingga run bisa dilanjutkan setelah laptop sleep atau restart tanpa mengulang dari awal.
- **F2.6 Bukti sumber.** Setiap item mentah menyimpan URL sumber, waktu ambil, waktu posting, teks mentah, akun pemosting, dan (opsional) screenshot.
- **F2.7 Klasifikasi intent per post.** Kategorinya: menawarkan (jual/supply), mencari (beli/demand), iklan jasa lain, atau tidak relevan. Pola calo, reseller, dan penipuan ditandai, tidak dibuang.
- **F2.8 Panel status.** Menampilkan kampanye yang berjalan, jumlah item per sumber, error, antrean handoff, dan biaya LLM hari ini. Panel ini juga menampilkan **hitungan per tahap funnel per sumber** (dipindai → intent cocok → lokasi cocok → setelah dedup → lolos ambang → approved), yang dipakai untuk kalibrasi target (§3.4) dan yield di `source_registry`.

### 7.3 Ekstraksi, normalisasi & dedup — Fase 1

- **F3.1** LLM mengekstrak data ke skema kampanye. Field **boleh kosong** dan tidak boleh dikarang. Setiap field menyimpan potongan teks sumbernya.
- **F3.2** Urutan jalur kontak: **WhatsApp → telepon → email → profil sosmed (FB/IG) → form kontak website**. Kalau sebuah post hanya mencantumkan lokasi, kontaknya diisi link profil pemosting.
- **F3.3** Normalisasi:
  - nomor telepon → format `+62`;
  - satuan → kg (kuintal/kw = 100 kg, ton = 1.000 kg);
  - lokasi → desa/kecamatan/kabupaten/provinsi + kode wilayah Kemendagri;
  - harga → Rp/kg;
  - tanggal relatif ("panen minggu depan") → tanggal absolut, dihitung dari waktu posting.
- **F3.4** Geocoding di tingkat kecamatan/kabupaten (centroid) untuk menghitung jarak. Hasilnya di-cache dan batas pemakaian layanan dipatuhi (Nominatim: 1 permintaan/detik).
- **F3.5** Dedup / entity resolution berdasarkan nomor yang sama, URL profil yang sama, atau kemiripan nama + lokasi (fuzzy). Record hasil merge menyimpan semua sumbernya, dan ini dipakai untuk skor konfirmasi lintas sumber.
- **F3.6** **Masking data pribadi sebelum dikirim ke LLM.** Nomor HP dan email diekstrak dengan regex secara lokal, lalu diganti token (`[PHONE_1]`) sebelum teks dikirim ke API LLM.

### 7.4 Skor relevansi & confidence — Fase 1

Ada dua skor yang terpisah. Keduanya ditampilkan bersama alasannya ("kenapa skornya segini").

**Relevansi (0–100)** mengukur seberapa cocok record dengan kampanye: produk/sinonim, atribut (varietas/grade), intent yang benar (jual vs beli), lokasi, volume, dan waktu.

**Confidence (0–100)** mengukur seberapa nyata dan aktif sumbernya. Bobotnya (usulan):

| Sinyal | Bobot |
|---|---|
| Kesegaran post/penawaran: ≤7 hari dapat nilai penuh, lalu menurun sampai batas `freshness_days` | 30 |
| Jalur kontak langsung: WA/telepon/email valid dapat nilai penuh; hanya link profil dapat setengah | 25 |
| Akun/sumber aktif: akun posting dalam ≤30 hari terakhir; untuk website: situs hidup dan ada tanda aktivitas terbaru (tanggal update, medsos aktif, ulasan Maps terbaru) | 25 |
| Terkonfirmasi di ≥2 sumber | 10 |
| Konsistensi: angka masuk akal, bukan pola spam/penipuan | 10 |

Catatan:

- Data trafik website yang sebenarnya hanya tersedia lewat tool berbayar. Karena itu MVP memakai sinyal pengganti di atas.
- Status "nomor WA aktif" **tidak** diverifikasi otomatis di Fase 1, karena butuh API resmi atau berisiko blokir. Verifikasinya terjadi saat kontak pertama di Fase 3, dan hasilnya memperbarui skor.
- **F4.1** Hasil review manusia (approve/reject + alasan) disimpan sebagai data untuk memperbaiki prompt dan bobot skor.

### 7.5 Database & output — Fase 1

- **F5.1** Source of truth: **SQLite lokal**.
- **F5.2** Sinkron ke Google Sheets per kampanye dengan tiga tab:
  - **Review:** lead baru + skor + alasan + link bukti + kolom keputusan;
  - **Database:** lead yang sudah di-approve;
  - **Log.**

  Kolom keputusan reviewer dibaca balik ke SQLite.
- **F5.3** Ekspor Excel/CSV bisa dilakukan kapan saja.
- **F5.4** Dashboard web lengkap ada di Fase 2. Fase 1 cukup memakai UI lokal (chat + status + tabel).

### 7.6 Matchmaking — Fase 2

- **F6.1** Kandidat match adalah listing supply vs demand dengan produk yang sama (atau substitusi yang diizinkan di kampanye) dan jendela waktu yang beririsan.
- **F6.2** Skor match 0–100 dihitung dari empat faktor (bobot usulan, bisa diatur):

  | Faktor | Bobot |
  |---|---|
  | Volume & waktu panen/kebutuhan | 30 |
  | Produk, varietas & grade | 30 |
  | Jarak & logistik | 20 |
  | Harga: rentang beririsan setelah margin GoTani 8–12% | 20 |

  Skor confidence kedua record ikut menjadi pengali.
- **F6.3** Setiap match selalu menampilkan alasan dan kekurangannya, misalnya "grade tidak disebut" atau "jarak 140 km".
- **F6.4** **Pooling/agregasi.** Kalau satu penjual tidak cukup, AI menyusun kombinasi beberapa penjual (yang terdekat dan berskor tertinggi lebih dulu) sebagai **saran**, lengkap dengan disclaimer:
  > Pembeli X butuh 500 kg melon. Petani A hanya punya 100 kg (20%). Saran: tambah Petani B (200 kg, 12 km dari A) + Petani C (200 kg) = 500 kg. Perhatian: ada 3 titik jemput, dan grade Petani C belum diketahui.
- **F6.5** **Tier aksi** (ambang usulan):

  | Skor | Aksi |
  |---|---|
  | ≥80 | Masuk antrean outreach AI. Selama Fase 2 tetap dikonfirmasi manusia sampai Fase 3 aktif. |
  | 50–79 | Review manusia |
  | <50 | Diabaikan, tetapi tetap tersimpan |
- **F6.6** Hasil setiap match (deal/tidak + alasan) dicatat. Karena **belum ada data transaksi historis**, skor awal berbasis aturan + penilaian LLM dan **belum merupakan probabilitas terkalibrasi**. Label "probabilitas" baru dipakai setelah data hasil cukup untuk kalibrasi (usulan: ≥100 match dengan hasil tercatat).
- **F6.7** Untuk kampanye `find_customers` (bisnis umum), engine yang sama menghitung skor kecocokan lead terhadap ICP.

### 7.7 Bantuan telepon masuk — Fase 2

Voice AI belum dibangun. Kalau ada telepon masuk, tim GoTani yang menjawab. Operator memasukkan nomor penelepon, lalu sistem menampilkan 5–7 poin ringkas:

- siapa penelepon (nama/usaha, peran);
- apa yang ditawarkan atau dibutuhkan;
- lokasi;
- status dan riwayat percakapan;
- match yang relevan;
- saran poin bicara dan pertanyaan.

### 7.8 AI sales agent — Fase 3

- **F8.1 Kanal:** WhatsApp, DM Facebook/Instagram, email. Voice AI masuk roadmap.
- **F8.2 Mode bertahap:**

  | Mode | Cara kirim | Kapan |
  |---|---|---|
  | Draf | AI menyusun pesan; manusia menyalin teks atau mengklik link `wa.me` berisi teks, lalu menekan kirim | Awal Fase 3; **selalu** dipakai untuk DM FB/IG |
  | Semi-otomatis | AI mengirim pesan rutin lewat jalur resmi; kasus sensitif diserahkan ke manusia | Setelah kualitas draf terbukti |
  | Otomatis | WA hanya lewat WhatsApp Business Platform resmi (pesan pertama wajib template yang disetujui Meta, berbayar per pesan; cek tarif terbaru). Email dikirim dari domain GoTani dengan SPF/DKIM. | Setelah budget tersedia (Q9) |

  FB/IG tidak punya API resmi untuk DM dingin, jadi kanal ini selalu memakai mode draf.
- **F8.3 Persona.** Agent memakai nama dan gaya bicara natural seperti anggota tim GoTani. **Kalau lawan bicara bertanya apakah ini bot/AI, agent menjawab jujur** dan menawarkan untuk menyambungkan ke tim. AI hanya melanjutkan percakapan kalau lawan bicara tidak keberatan. Manusia yang mengambil alih juga tidak menyangkal bahwa pesan sebelumnya dibantu AI.
- **F8.4 Konteks & memori.** Sebelum membalas, AI membaca:
  - profil lead dari database (sumber, post, komoditas, volume, lokasi, match);
  - seluruh riwayat percakapan;
  - ringkasan percakapan yang diperbarui setiap interaksi.

  Pesan pertama menyebut konteks yang relevan **beserta asal informasinya**, misalnya "kami lihat penawaran melon Bapak di grup X". Ini juga memenuhi asas transparansi.
- **F8.5 Follow-up.** Kalau tidak dibalas, AI mengirim maksimal 2 follow-up (usulan: hari ke-3 dan ke-7), lalu berhenti. AI langsung berhenti kalau lead menolak.
- **F8.6 Waktu kirim.** Jeda balasan wajar, jam kirim yang sopan (usulan: 07.00–20.00 waktu setempat), dan kuota pesan harian per nomor/akun.
- **F8.7 Handover ke manusia** terjadi saat:
  - lead tertarik (sesuai definisi closing);
  - ada negosiasi harga atau syarat;
  - ada komplain atau nada negatif;
  - lawan bicara bertanya apakah ini bot (setelah dijawab jujur);
  - ada pertanyaan di luar pengetahuan AI;
  - AI sendiri ragu.

  Setelah manusia selesai, percakapan bisa dikembalikan ke AI.
- **F8.8 Definisi closing** dipilih per kampanye: lead menyatakan tertarik (**default**), meeting/telepon terjadwal, deal disepakati (volume/harga/tanggal), atau DP/pembayaran masuk.
- **F8.9 Opt-out.** Kalau lawan bicara minta berhenti atau minta datanya dihapus:
  - AI berhenti;
  - kontak ditandai *do-not-contact* di semua kampanye;
  - datanya dihapus atau dianonimkan sesuai permintaan.
- **F8.10 Metrik:** reply rate, % tertarik, % handover, % opt-out, dan jumlah laporan spam/blokir (target 0).

---

## 8. Model data (ringkas)

| Tabel | Isi kunci |
|---|---|
| `campaigns` | id, tujuan, spec JSON, status, definisi closing |
| `runs` | campaign_id, sumber, akun, waktu mulai/selesai, jumlah item, error, biaya |
| `source_registry` | platform, url/id, nama, tipe (grup/akun/website/kategori Places), wilayah, komoditas, skor sumber, status akses (publik/privat/menunggu join/ditolak), yield historis, terakhir dipindai |
| `raw_items` | run_id, source_id, url, waktu ambil, waktu post, teks mentah, pemosting, screenshot_path |
| `entities` | orang/usaha: nama, peran (supply/demand/customer), lokasi + kode wilayah, koordinat |
| `contact_points` | entity_id, jenis (wa/telp/email/fb/ig/web), nilai, sumber, status verifikasi, do_not_contact |
| `listings` | entity_id, campaign_id, intent (supply/demand), produk, **atribut JSON**, volume_kg, waktu tersedia/dibutuhkan, harga/kg, raw_item_ids |
| `scores` | listing_id, relevance, confidence, alasan JSON, versi aturan |
| `reviews` | listing_id, reviewer, keputusan, alasan, waktu |
| `matches` (F2) | demand_listing_id, supply_listing_ids[], skor, alasan, tier, hasil |
| `conversations`, `messages` (F3) | entity_id, kanal, isi pesan, pengirim (AI/manusia), ringkasan, status |
| `opt_outs` | contact_point, waktu, jenis permintaan (stop/hapus) |

Kolom `atribut JSON` membuat skema tetap dinamis, sehingga vertikal non-agri tidak perlu mengubah struktur tabel.

---

## 9. Arsitektur & stack

Keputusan owner (6 Okt):

- **MVP:** Streamlit + LLM API, semuanya dalam **Python**. Satu bahasa dan satu proses lokal sudah cukup untuk Fase 1.
- **Produksi:** frontend **React/Next.js**, backend **Go / Node / Python** (§9.2).

### 9.1 Stack MVP (Fase 1)

```
[UI lokal (Streamlit): chat kuesioner · status run · tabel lead · antrean handoff]
        │
[Orchestrator / Planner] ── [LLM Gateway: Gemini ↔ OpenAI, bisa diganti; budget cap; log biaya]
        │
  ┌─────┴──────────┬──────────────┬──────────────────┬────────────────────┐
[FB executor]  [IG executor]  [Web/B2B executor]  [Places API]  [Marketplace]
  (Playwright, satu profil browser per akun, rate limiter, deteksi checkpoint → handoff)
        │
[Klasifikasi intent] → [Ekstraksi LLM] → [Normalisasi] → [Dedup] → [Skoring]
        │
[SQLite] ⇄ [Google Sheets] → ekspor Excel
```

| Komponen | Pilihan |
|---|---|
| Bahasa | Python 3.11+ |
| Browser automation | Playwright (persistent context per akun); `browser-use` hanya untuk menjelajah website yang belum dikenal |
| LLM | Gemini API (free tier untuk development) atau OpenAI (model kelas mini), di balik satu lapisan abstraksi supaya bisa ditukar |
| Search | Search API dengan tier gratis (kandidat: Tavily, Brave Search, SerpAPI, grounding Google Search di Gemini). Pilih setelah cek kuota & harga terbaru (Q6). |
| Lokasi | Dataset kode wilayah Kemendagri + geocoding Nominatim (dengan cache) |
| Utilitas | `phonenumbers`, `rapidfuzz`, `pydantic` (validasi skema), `gspread`, APScheduler (Fase 2) |
| Penyimpanan | SQLite; Google Sheets via service account |
| UI | Streamlit (lokal) |

### 9.2 Stack produksi (Fase 2+, saat pindah dari laptop ke server / dashboard web)

| Lapisan | Pilihan | Catatan |
|---|---|---|
| Frontend / dashboard | React + Next.js | Pengganti UI Streamlit: dashboard lead, match, inbox sales |
| API backend | Node (Next.js route handlers / NestJS) **atau** Go | Pilih satu saja, sesuai bahasa yang paling dikuasai tim |
| Agent worker & pipeline | **Tetap Python** | Kode MVP (Playwright, ekstraksi, skoring) dipakai ulang, tidak ditulis ulang |
| Database | SQLite → PostgreSQL | Skema §8 tetap; kolom `atribut JSON` → `jsonb` |
| Antrean job | Redis (atau tabel job di Postgres) | API mengirim job ke worker Python; worker menulis hasil ke DB |

**Rekomendasi:** batasi maksimal **dua bahasa backend**, yaitu Python untuk worker ditambah Node *atau* Go untuk API. Tiga bahasa backend sekaligus akan memberatkan tim kecil. Kalau tim paling nyaman di Python, API juga bisa memakai Python (FastAPI) sehingga backend cukup satu bahasa.

**Supaya tetap di bawah budget:**

- Model kecil/murah dipakai untuk klasifikasi dan ekstraksi, yang volumenya besar. Model yang lebih kuat hanya dipakai untuk planner dan percakapan sales.
- Gunakan teks DOM, bukan screenshot. Batch beberapa post dalam satu panggilan LLM, dan cache hasil ekstraksi per URL.
- Pasang budget cap harian di config. Kalau cap tercapai, agent berhenti memanggil LLM.
- Perkiraan owner untuk testing adalah ±$1–3 per minggu dengan OpenAI. Angka sebenarnya dipantau lewat log biaya per run.

**Catatan Gemini free tier:** menurut ketentuan layanan tak berbayar Gemini API, konten yang dikirim dapat dipakai Google untuk pengembangan produk. Karena itu masking data pribadi (F3.6) wajib, dan untuk produksi/komersial sebaiknya pakai tier berbayar.

---

## 10. Guardrails: etika, hukum & platform

Aturan berikut berlaku di semua fase dan **tidak bisa diubah per kampanye.**

| Kode | Aturan |
|---|---|
| **G1** | **Tanpa fitur anti-deteksi.** Produk tidak membangun spoofing fingerprint, pemecah CAPTCHA, simulasi gerakan kursor/ketikan untuk mengelabui deteksi bot, atau rotasi proxy/akun untuk menghindari blokir. Kalau platform memberi tantangan, agent berhenti dan menyerahkan ke manusia. |
| G2 | Rate limit dan kuota konservatif (F2.4, F8.6). |
| G3 | Akun dibuat dan di-login oleh manusia; agent tidak pernah mendaftar akun sendiri. |
| G4 | Kejujuran AI: persona boleh, menyangkal bahwa dirinya AI tidak boleh (F8.3). |
| G5 | Permintaan opt-out dan hapus data dihormati segera (F8.9). |
| G6 | Minimisasi data: hanya field yang ada di Campaign Spec. Tidak mengambil data sensitif (NIK, foto KTP, agama, kesehatan, data anak) maupun pesan privat. |
| G7 | Jejak sumber: setiap data punya URL dan waktu ambil. |
| G8 | Data lead tidak dijual atau dibagikan ke pihak ketiga. Di versi SaaS, data antar-bisnis terisolasi. |
| G9 | Data pribadi di-masking sebelum dikirim ke LLM (F3.6). |

**Alasan G1:**

- Perilaku itu persis yang dilarang platform dan menjadi dasar blokir permanen.
- Inti produk jadi bergantung pada kucing-kucingan yang rusak setiap kali platform update.
- Begitu produk dijual ke bisnis lain, akun atau nomor klien yang terblokir menjadi risiko reputasi produk.

**Catatan hukum** (perlu review ahli hukum sebelum versi komersial, lihat Q10):

- **UU PDP No. 27/2022** (berlaku penuh sejak Oktober 2024). Nomor HP dan nama termasuk data pribadi.
  - **Posisi produk:** hanya memakai data yang dipublikasikan sendiri oleh pemiliknya untuk tujuan jual/beli, dengan dasar kepentingan yang sah; opt-out dan penghapusan dilayani saat diminta.
  - **Keputusan owner:** pesan pertama tidak memuat pemberitahuan khusus soal data; opt-out hanya bila diminta.
  - **Risiko:** UU PDP mengatur kewajiban transparansi pengendali data, jadi keputusan ini perlu dicek dengan ahli hukum. Minimal, pesan pertama menyebut asal informasinya (F8.4).
- **Akun dummy FB/IG** (keputusan owner). Ketentuan Meta melarang akun palsu dan pengumpulan data otomatis tanpa izin. Konsekuensinya:
  - akun bisa di-checkpoint atau diblokir kapan saja, jadi perlakukan sebagai akun sekali pakai;
  - **jangan** memakai akun utama GoTani yang menyimpan relasi dengan petani dan pembeli;
  - database tidak boleh bergantung pada satu akun saja.
- **Google Maps.** Gunakan Places API resmi, karena scraping halaman Maps melanggar ketentuan Google.

---

## 11. Requirement non-fungsional

- **Biaya:** total operasional < Rp500 rb/bulan di Fase 1–2; biaya dicatat per run dan per lead valid.
- **Keandalan:** run bisa dilanjutkan setelah laptop sleep/restart; error di satu sumber tidak menghentikan sumber lain.
- **Kinerja:** satu kampanye menghasilkan batch pertama lead dalam ≤1 jam (usulan).
- **Keamanan:**
  - profil browser, cookie, dan kredensial hanya disimpan lokal dan tidak dibagikan;
  - API key disimpan di `.env` dan tidak di-commit;
  - Google Sheets hanya dibagikan ke tim.
- **Observabilitas:** setiap aksi agent dicatat (sumber, URL, hasil) dan bisa diaudit.
- **Bahasa:** UI dan percakapan dalam Bahasa Indonesia; ekstraksi toleran terhadap bahasa daerah dan singkatan.
- **Portabilitas:** konfigurasi per kampanye dan per sumber disimpan di file (YAML/JSON), bukan di-hardcode. Menambah vertikal baru cukup dengan menambah template.

---

## 12. Rencana kerja Fase 1 (1 developer, ±4 minggu)

Kapasitas tim: **1 developer**. Rencana ini mengasumsikan dia bekerja ±penuh waktu; kalau paruh waktu, M1 tetap dikejar dan milestone sesudahnya digeser.

**Strategi:** bangun irisan tipis end-to-end dulu, yaitu *grup FB → post → ekstraksi → tabel*, supaya scraping sudah jalan minggu depan. Setelah itu kualitas data (normalisasi, dedup, skor) dan sumber lain ditambahkan bertahap.

| Periode | Output | Milestone |
|---|---|---|
| 7–9 Okt (Rab–Jum) | Repo Python; Playwright + profil browser akun dummy (login manual sekali); skema SQLite minimal (`campaigns`, `source_registry`, `raw_items`, `listings`); LLM gateway (Gemini) + budget cap + masking nomor/email (F3.6); daftar kabupaten/kota per provinsi | Lingkungan siap |
| 12–16 Okt | Streamlit sederhana: operator menulis 1–2 kalimat, LLM menyusun Campaign Spec, operator mengedit JSON-nya; generator query per kabupaten (F2.1a–b, prioritas sentra menyusul); pencarian grup FB + simpan ke `source_registry` dengan skor sederhana (nama cocok + tanggal post terakhir); baca post grup publik / grup yang sudah diikuti, dengan rate limit; klasifikasi intent + ekstraksi LLM; simpan ke SQLite; ekspor CSV / Google Sheets | **M1 — Jumat 16 Okt: scrape pertama.** "Melon, Jawa Timur" → ≥10 grup ditemukan, ≥200 post terbaca, daftar lead muncul di Sheets |
| 19–23 Okt | Normalisasi (+62, satuan, kode wilayah, tanggal); dedup; skor relevansi & confidence + alasan; tab Review di Sheets yang dibaca balik; checkpoint/resume; handoff saat checkpoint/CAPTCHA | **M2:** lead berskor & bebas duplikat |
| 26–30 Okt | Executor web/B2B (search API) + Google Places untuk kampanye demand; prioritas sentra produksi (F2.1a); yield & funnel per sumber (F2.1e, F2.8); perluasan otomatis (F2.1f); chat tanya-balik penuh (F1.2–F1.4) | **M3:** kampanye demand jalan |
| 2–6 Nov | **Pilot 2 kampanye nyata GoTani** (1 `find_supply`, 1 `find_demand`); perbaikan; ukur metrik §3.3; keputusan go/no-go Fase 2 | **M4:** MVP Fase 1 |

**Prasyarat yang harus siap sebelum Senin 12 Okt** (oleh owner, bukan developer):

1. Akun dummy FB sudah dibuat manusia dan bisa login normal. Developer memakainya untuk login manual sekali di profil browser agent.
2. API key Gemini, serta service account Google untuk Sheets.
3. Laptop yang dipakai menjalankan agent: Python 3.11+, tidak masuk sleep selama run.
4. **Grup privat butuh persetujuan admin, yang bisa makan beberapa hari.** M1 cukup memakai grup publik. Grup privat hasil penemuan agent di-join oleh manusia seawal mungkin, supaya sudah disetujui saat pilot.

**Acceptance criteria Fase 1:**

1. Dari chat ≤10 giliran terbentuk Campaign Spec yang dikonfirmasi operator.
2. Agent berjalan ≥2 jam tanpa pengawasan dan bisa melanjutkan run setelah laptop restart.
3. Setiap lead punya URL sumber, waktu ambil, ≥1 jalur kontak (link profil juga dihitung), serta skor relevansi & confidence beserta alasannya.
4. Duplikat yang lolos <5% pada sampel 50 lead.
5. Presisi review ≥70% pada sampel 50 lead pilot (usulan).
6. Setiap checkpoint/CAPTCHA selalu berujung handoff ke manusia, tidak pernah dicoba dibobol.
7. Biaya LLM selama pilot tercatat dan masih dalam budget.
8. Nomor HP dan email tidak pernah terkirim mentah ke API LLM (dicek dari log).
9. Dari spec "melon, Jawa Timur" tanpa seed list, run pertama menemukan dan menilai ≥10 grup/akun/website yang relevan (usulan).
10. Hitungan funnel per sumber tercatat, sehingga target §3.3 bisa dikalibrasi.

---

## 13. Risiko & mitigasi

| Risiko | Dampak | Mitigasi |
|---|---|---|
| Akun dummy diblokir Meta | Sumber FB/IG berhenti | Rate limit; akun cadangan dibuat manusia; sumber lain (web/B2B/Places) tetap berjalan |
| Struktur halaman FB/IG berubah | Executor rusak | Ekstraksi berbasis teks + LLM; selektor seminimal mungkin; tes harian sederhana |
| Data tidak akurat atau kedaluwarsa | Lead tidak valid | Skor confidence, batas kesegaran, review manusia, feedback loop |
| Biaya LLM membengkak | Melewati budget | Text-first, model kecil, batching, cache, budget cap |
| Isu UU PDP atau komplain | Hukum & reputasi | Guardrails G5–G9; review hukum sebelum versi komersial |
| Nomor WA diblokir/dilaporkan spam (Fase 3) | Kanal hilang | Mulai dari mode draf; kuota; jalur resmi; pesan yang relevan dan jujur |
| Laptop mati atau sleep | Run terhenti | Checkpoint/resume; nonaktifkan sleep selama run; pindah ke server masuk roadmap |
| Hanya 1 developer | MVP molor; developer menjadi satu-satunya titik kegagalan | Scope Fase 1 dipangkas (IG, marketplace, TikTok → Fase 2); milestone mingguan M1–M4; kode & keputusan didokumentasikan di repo |
| Grup FB privat butuh persetujuan admin | M1/pilot kekurangan sumber | M1 memakai grup publik; permintaan join dikirim manusia sejak awal |
| Skor match dibaca sebagai probabilitas | Keputusan bisnis keliru | Pakai label "skor kecocokan" sampai terkalibrasi (F6.6) |

---

## 14. Keputusan terbuka

| # | Pertanyaan | Pemilik | Batas |
|---|---|---|---|
| Q1 | **Terjawab 6 Okt:** tidak ada baseline manual; dipakai target usulan berbasis funnel (§3.3–3.4) yang dikalibrasi dari data pilot. Masih terbuka (opsional): kolom Excel lama sebagai acuan skema. | Tim | Kalibrasi di akhir Fase 1 |
| Q2 | **Terjawab 6 Okt:** tanpa seed list; sumber ditemukan secara dinamis dari komoditas + wilayah (F2.1a–f). | — | — |
| Q3 | **Terjawab 6 Okt:** 1 developer; target scraping sudah jalan minggu depan (M1, 16 Okt). Stack MVP = Python + Streamlit + LLM API; produksi = Next.js + backend Go/Node/Python (§9). Asumsi: developer ±penuh waktu (§12). | — | — |
| Q4 | Siapa reviewer dan berapa jam per minggu tersedia untuk review. *Usulan:* 1 orang, ±1 jam per kampanye per minggu. | Owner | Minggu 2 |
| Q5 | Siapa yang mengkurasi sinonim, varietas, dan grade per komoditas. *Usulan:* AI membuatnya otomatis saat kuesioner (F1.3); operator cukup mengoreksi, dan koreksinya disimpan sebagai glosarium bersama untuk kampanye berikutnya. | Tim GoTani | Minggu 2 |
| Q6 | Search API dan model LLM final. *Usulan:* Gemini free tier selama development; putuskan di akhir minggu 1 berdasarkan log biaya dan kualitas ekstraksi. | Tim dev | Minggu 1 |
| Q7 | Berapa lama data disimpan. *Usulan:* teks mentah 90 hari; lead yang di-reject 30 hari; lead yang tidak merespons 12 bulan lalu dianonimkan; data opt-out langsung dihapus. | Owner | Fase 2 |
| Q8 | Ambang skor final. *Usulan:* pakai default PRD (relevansi 70, confidence 60, tier match 80/50), lalu kalibrasi dari hasil review pilot. | Tim | Akhir Fase 1 |
| Q9 | Kanal WA di Fase 3. *Usulan:* tetap mode draf sampai ada funding, lalu pindah ke WhatsApp Business Platform. | Owner | Fase 2 |
| Q10 | Review hukum UU PDP & ToS platform. *Usulan:* wajib sebelum dijual ke bisnis lain. Selama pilot internal, guardrails §10 dijalankan penuh dan risiko UU PDP tetap tercatat. | Owner | Sebelum komersial |
| Q11 | Model monetisasi versi bisnis umum (langganan / per lead / komisi). *Usulan:* putuskan setelah pilot GoTani, saat biaya per lead valid sudah diketahui. | Owner | Roadmap |
| Q12 | Nama produk. | Owner | Sebelum dibuka ke bisnis lain |

---

## Lampiran A — Keputusan hasil wawancara (6 Okt 2026)

| Topik | Keputusan owner |
|---|---|
| Positioning | AI untuk bisnis umum; pasar awal agribisnis lewat GoTani |
| Pengguna awal | Internal GoTani; kuesioner dibuat generik secara teknis |
| Modul | Keempat modul masuk scope; rilis riset + database dulu (bulan 1), matching & sales di bulan 2–3 |
| Sumber data | Grup FB, IG/TikTok, website buyer & direktori B2B, Google Search/Maps & marketplace |
| Ukuran sukses | Jumlah lead valid + keyakinan bahwa datanya nyata dan relevan |
| Bentuk kuesioner | Chat bebas dengan AI |
| Output | Google Sheets/Excel + dashboard web |
| Eksekusi | Agent lokal di laptop, berjalan selama laptop menyala, menjelajah seperti manusia (scroll FB/IG) |
| Akun | Akun dummy buatan owner; akun marketplace dimintakan ke manusia |
| Field | Identitas & kontak, lokasi, komoditas & panen, harga & syarat; boleh kosong; kontak diambil berurutan dari WA sampai link profil |
| Validasi | Kontak/akun aktif, post baru, website aktif |
| UU PDP | Hanya data publik; opt-out bila diminta, tanpa pemberitahuan khusus di pesan pertama |
| Faktor match | Volume & waktu, komoditas/varietas/grade, jarak & logistik, harga |
| Agregasi | Gabungkan beberapa petani sebagai saran + disclaimer kekurangan |
| Aksi setelah match | Bertingkat menurut skor |
| Data transaksi historis | Belum ada |
| Kanal sales | WA, DM FB/IG, email; voice AI di roadmap; telepon masuk dijawab manusia + ringkasan dari AI |
| Persona | Persona anggota tim (lihat Lampiran B) |
| Otonomi AI | Sampai lead tertarik, lalu handover |
| Closing | Bisa dipilih per kampanye |
| Monetisasi | Belum ditentukan |
| Pembangun | Tim GoTani: 1 developer |
| Timeline | MVP ≤1 bulan; scraping sudah jalan minggu depan (M1, 16 Okt) |
| Budget | < Rp500 rb/bulan; naik kalau sudah ada funding |
| Model AI | Gemini API (free tier) atau OpenAI |
| Stack | MVP: Python + Streamlit + LLM API. Produksi: React/Next.js + backend Go/Node/Python |
| Target lead (Q1) | Tidak ada baseline manual → target usulan berbasis funnel, dikalibrasi saat pilot |
| Seed list (Q2) | Tidak ada; AI menemukan grup dan sumber secara dinamis per komoditas & wilayah (provinsi → kabupaten, mis. Jawa Timur → Kediri, Blitar, dst.) |

## Lampiran B — Permintaan yang disesuaikan

| Permintaan awal | Disesuaikan menjadi | Alasan |
|---|---|---|
| Kalau ditanya "bot?", percakapan dioper ke manusia lalu dikembalikan ke AI | Dijawab jujur + ditawarkan bicara dengan manusia; AI melanjutkan hanya kalau lawan bicara tidak keberatan (F8.3) | Lawan bicara tidak boleh digiring percaya sedang bicara dengan manusia; sejalan dengan asas transparansi |
| Simulasi gerakan kursor & kecepatan ketik supaya tidak terdeteksi sebagai bot | Rate limit, jeda wajar, handoff saat ada tantangan, dan jalur resmi (F2.4, F8.2, F8.6) | G1 |
| Agent membuat akun marketplace sendiri dari email dummy | Manusia yang membuat akun; agent hanya meminta (F2.3) | G3: pendaftaran otomatis paling cepat memicu sistem anti-bot |

"""Modul geocoding & perhitungan jarak logistik (PRD F3.4 & F6.2).

Menyediakan:
1. Centroid (lat, lon) untuk 38 kabupaten/kota di Jawa Timur.
2. Rumus Haversine untuk menghitung jarak lurus (km) antar dua titik.
3. Fallback jarak antar-provinsi atau jika wilayah tidak diketahui.
"""
from __future__ import annotations

import math
from typing import Tuple

# Centroid perkiraan (lintang, bujur) untuk 38 kab/kota Jawa Timur (Kemendagri)
# Sumber: BPS & Peta Tematik Jawa Timur
JATIM_CENTROIDS: dict[str, tuple[float, float]] = {
    "Pacitan": (-8.1333, 111.1667),
    "Ponorogo": (-7.9333, 111.4667),
    "Trenggalek": (-8.1000, 111.6000),
    "Tulungagung": (-8.0667, 111.9000),
    "Blitar": (-8.1333, 112.1667),
    "Kediri": (-7.8333, 112.0167),
    "Malang": (-8.1667, 112.6333),
    "Lumajang": (-8.1333, 113.2167),
    "Jember": (-8.1721, 113.7007),
    "Banyuwangi": (-8.2192, 114.3692),
    "Bondowoso": (-7.9135, 113.8214),
    "Situbondo": (-7.7063, 114.0048),
    "Probolinggo": (-7.7543, 113.2159),
    "Pasuruan": (-7.6453, 112.9075),
    "Sidoarjo": (-7.4478, 112.7183),
    "Mojokerto": (-7.4726, 112.4381),
    "Jombang": (-7.5458, 112.2331),
    "Nganjuk": (-7.6046, 111.9038),
    "Madiun": (-7.6298, 111.5239),
    "Magetan": (-7.6527, 111.3283),
    "Ngawi": (-7.4039, 111.4462),
    "Bojonegoro": (-7.1502, 111.8817),
    "Tuban": (-6.8976, 112.0649),
    "Lamongan": (-7.1199, 112.4137),
    "Gresik": (-7.1566, 112.6555),
    "Bangkalan": (-7.0455, 112.7483),
    "Sampang": (-7.0504, 113.2394),
    "Pamekasan": (-7.1593, 113.4735),
    "Sumenep": (-7.0167, 113.8667),
    "Kota Kediri": (-7.8228, 112.0119),
    "Kota Blitar": (-8.0983, 112.1681),
    "Kota Malang": (-7.9797, 112.6304),
    "Kota Probolinggo": (-7.7543, 113.2159),
    "Kota Pasuruan": (-7.6453, 112.9075),
    "Kota Mojokerto": (-7.4726, 112.4381),
    "Kota Madiun": (-7.6298, 111.5239),
    "Kota Surabaya": (-7.2575, 112.7521),
    "Kota Batu": (-7.8712, 112.5271),
}

# Jarak estimasi jika hanya tahu provinsi yang sama tapi kab tidak cocok (km)
DEFAULT_SAME_PROVINCE_KM = 80.0
DEFAULT_DIFFERENT_PROVINCE_KM = 250.0


def haversine_km(coord1: tuple[float, float], coord2: tuple[float, float]) -> float:
    """Hitung jarak lingkaran besar (lingkaran bumi) dalam kilometer antara dua titik."""
    lat1, lon1 = coord1
    lat2, lon2 = coord2
    r = 6371.0  # radius bumi rata-rata (km)

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return round(r * c, 1)


def get_region_centroid(region_name: str | None) -> tuple[float, float] | None:
    """Ambil koordinat centroid berdasarkan nama kabupaten/kota.

    Bisa menerima 'Kediri', 'Kab. Kediri', 'Kota Surabaya', dsb.
    """
    if not region_name:
        return None
    cleaned = region_name.strip()
    # Hapus prefix Kab. / Kota jika ada untuk pencocokan awal
    cleaned_short = cleaned.replace("Kab.", "").replace("Kota", "").strip()

    # Cek kecocokan persis
    if cleaned in JATIM_CENTROIDS:
        return JATIM_CENTROIDS[cleaned]
    if cleaned_short in JATIM_CENTROIDS:
        return JATIM_CENTROIDS[cleaned_short]

    # Cek case-insensitive dan variasi Kota / Kab
    lower = cleaned.lower()
    for k, v in JATIM_CENTROIDS.items():
        k_lower = k.lower()
        if k_lower == lower or k_lower == cleaned_short.lower():
            return v
        if k_lower.replace("kota", "").replace("kab.", "").strip() == cleaned_short.lower():
            return v
    return None


def calculate_distance_km(
    loc1: str | None,
    loc2: str | None,
    prov1: str | None = None,
    prov2: str | None = None,
) -> tuple[float | None, str]:
    """Hitung jarak logistik antara dua lokasi.

    Mengembalikan (jarak_km, keterangan).
    Jika lokasi persis diketahui, dihitung via Haversine.
    Jika tidak, menggunakan estimasi fallback yang wajar.
    """
    c1 = get_region_centroid(loc1)
    c2 = get_region_centroid(loc2)

    if c1 and c2:
        d = haversine_km(c1, c2)
        return d, f"Jarak terhitung: {d} km ({loc1} ke {loc2})"

    # Fallback jika kedua lokasi di provinsi yang sama tapi koordinat kab belum ada
    if prov1 and prov2 and prov1.lower() == prov2.lower():
        return DEFAULT_SAME_PROVINCE_KM, f"Estimasi dalam satu provinsi ({prov1}): {DEFAULT_SAME_PROVINCE_KM} km"

    if (loc1 and loc2) and loc1.lower() == loc2.lower():
        return 15.0, f"Lokasi sama ({loc1}): estimasi 15 km"

    return None, "Lokasi tidak lengkap untuk menghitung jarak"

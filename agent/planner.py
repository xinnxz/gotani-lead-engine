"""Planner (PRD F2.1a-b): Campaign Spec -> daftar query pencarian teroptimasi."""
from __future__ import annotations

from . import wilayah
from .campaign import CampaignSpec

# Pola query pencarian Facebook (fokus postingan transaksional)
GROUP_PATTERNS_SUPPLY = [
    "jual {p} {r}",
    "panen {p} {r}",
    "ready {p} {r}",
    "petani {p} {r}",
]

GROUP_PATTERNS_DEMAND = [
    "cari {p} {r}",
    "butuh {p} {r}",
    "tampung {p} {r}",
    "beli {p} {r}",
]

# Pola Google Maps / Bisnis Lokal
PLACES_PATTERNS = [
    "toko buah {r}",
    "toko sayur {r}",
    "distributor buah {r}",
    "pasar induk {r}",
    "grosir buah {r}",
]

# Pola Web B2B
WEB_B2B_PATTERNS = [
    "supplier {p} {r}",
    "distributor {p} {r}",
    "kemitraan pasokan {p} {r}",
]

PROVINCE_PATTERNS = [
    "jual {p} {prov}",
    "panen {p} {prov}",
    "komunitas {p} {prov}",
]

INTENT_WORDS = {
    "supply": ["jual", "panen", "ready", "stok", "borongan"],
    "demand": ["cari", "butuh", "terima", "beli", "tampung"],
}

NEGATIVE_KEYWORDS = "-bibit -benih -pupuk -obat -loker -lowongan -resep -jus -olahan -jasa -mesin"


def expand_regions(spec: CampaignSpec) -> list[dict]:
    """Provinsi dipecah menjadi kabupaten/kota. Urutan: prioritas operator -> sisanya."""
    regions: list[dict] = []
    seen: set[str] = set()
    excluded = {r["kode"] for x in spec.location.exclude for r in wilayah.find_regions_in_text(x)}

    def add(r: dict) -> None:
        if r["kode"] not in seen and r["kode"] not in excluded:
            seen.add(r["kode"])
            regions.append(r)

    for name in spec.location.priority:
        r = wilayah.find_region_by_name(name)
        if r:
            add(r)
    for item in spec.location.include:
        prov = wilayah.resolve_province(item)
        if prov:
            for r in wilayah.regions_of(prov):
                add(r)
        else:
            for r in wilayah.find_regions_in_text(item):
                add(r)
    return regions


def build_group_queries(spec: CampaignSpec, max_queries: int | None = None) -> list[dict]:
    """Bangun query pencarian teroptimasi. Fewer queries, higher quality.
    
    Urutan prioritas:
    1. Query level PROVINSI (Google Search paling efektif dengan nama provinsi)
    2. Query SINONIM level provinsi (misal "kol" selain "kubis")
    3. Query level KABUPATEN (max 5 kabupaten teratas, hemat kuota)
    4. Fallback nasional jika lokasi kosong
    """
    p = (spec.product.name or "").lower()
    if not p:
        return []
    patterns = GROUP_PATTERNS_DEMAND if spec.target_intent == "demand" else GROUP_PATTERNS_SUPPLY
    queries: list[dict] = []
    seen: set[str] = set()

    def add(q: str, region: str, platform: str = "facebook", kind: str = "group_search") -> None:
        q = " ".join(q.lower().split())
        if q not in seen:
            seen.add(q)
            queries.append({"query": q, "region": region, "platform": platform, "kind": kind})

    provinces = spec.provinces()

    # === PRIORITAS 1: Query level provinsi (PALING EFEKTIF) ===
    for prov in provinces:
        # Pola provinsi standar
        for pat in PROVINCE_PATTERNS:
            add(pat.format(p=p, prov=prov), prov, "facebook", "group_search")
        # Pola supply/demand di level provinsi
        for pat in patterns:
            add(pat.format(p=p, r=prov), prov, "facebook", "group_search")

    # === PRIORITAS 2: Sinonim di level provinsi ===
    for syn in spec.product.synonyms:
        if syn.lower() != p:
            for prov in provinces:
                # Hanya 2 pola terpenting per sinonim
                add(f"jual {syn} {prov}", prov)
                add(f"panen {syn} {prov}", prov)
            if not provinces:
                add(f"jual {syn}", "Indonesia (Nasional)")

    # === PRIORITAS 3: Query kabupaten (DIBATASI max 5) ===
    regions = expand_regions(spec)
    top_regions = regions[:5]
    for r in top_regions:
        # Facebook: hanya 2 pola terpenting
        for pat in patterns[:2]:
            add(pat.format(p=p, r=r["nama"]), wilayah.label(r), "facebook", "group_search")
        # Google Maps & B2B: hanya untuk top 3
        if r in regions[:3]:
            for pat in PLACES_PATTERNS[:3]:
                add(pat.format(r=r["nama"]), wilayah.label(r), "google_maps", "places_search")
            for pat in WEB_B2B_PATTERNS[:2]:
                add(pat.format(p=p, r=r["nama"]), wilayah.label(r), "web_b2b", "web_search")

    # FALLBACK 1: Lokasi tidak ada di database wilayah
    if not regions and not provinces and spec.location.include:
        for loc in spec.location.include:
            for pat in patterns:
                add(pat.format(p=p, r=loc), loc, "facebook", "group_search")
            for pat in PLACES_PATTERNS[:3]:
                add(pat.format(r=loc), loc, "google_maps", "places_search")

    # FALLBACK 2: Tidak ada lokasi sama sekali
    if not queries:
        for w in INTENT_WORDS.get(spec.target_intent, ["jual", "panen"]):
            add(f"{w} {p}", "Indonesia (Nasional)")
        add(f"petani {p}", "Indonesia (Nasional)")
        add(f"komunitas {p}", "Indonesia (Nasional)")

    return queries[:max_queries] if max_queries else queries


def build_post_keywords(spec: CampaignSpec) -> list[str]:
    """Kata kunci untuk pencarian di dalam grup (misal 'jual melon')."""
    p = (spec.product.name or "").lower()
    return [f"{w} {p}" for w in INTENT_WORDS[spec.target_intent]] if p else []

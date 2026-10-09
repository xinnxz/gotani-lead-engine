"""Planner (PRD F2.1a–b): Campaign Spec → daftar wilayah & query pencarian, tanpa seed list."""
from __future__ import annotations

from . import wilayah
from .campaign import CampaignSpec

GROUP_PATTERNS_SUPPLY = ["{p} {r}", "petani {p} {r}", "jual beli hasil tani {r}"]
GROUP_PATTERNS_DEMAND = ["{p} {r}", "pedagang {p} {r}", "jual beli hasil bumi {r}"]
PROVINCE_PATTERNS = ["komunitas petani {p} {prov}", "{p} {prov}", "jual beli {p} {prov}"]
INTENT_WORDS = {
    "supply": ["jual", "panen", "ready", "stok"],
    "demand": ["cari", "butuh", "terima", "beli"],
}


def expand_regions(spec: CampaignSpec) -> list[dict]:
    """Provinsi dipecah menjadi kabupaten/kota. Urutan: prioritas operator → sisanya.

    Catatan: PRD F2.1a meminta prioritas sentra produksi dicari otomatis dari data BPS/dinas.
    Itu dijadwalkan di M3; sementara ini operator bisa mengisi `location.priority`.
    """
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
    """Query untuk pencarian grup FB. Nama kota & kabupaten yang sama (Kediri) cukup sekali."""
    p = (spec.product.name or "").lower()
    if not p:
        return []
    patterns = GROUP_PATTERNS_DEMAND if spec.target_intent == "demand" else GROUP_PATTERNS_SUPPLY
    queries: list[dict] = []
    seen: set[str] = set()

    def add(q: str, region: str) -> None:
        q = " ".join(q.lower().split())
        if q not in seen:
            seen.add(q)
            queries.append({"query": q, "region": region, "platform": "facebook", "kind": "group_search"})

    for prov in spec.provinces():
        for pat in PROVINCE_PATTERNS:
            add(pat.format(p=p, prov=prov), prov)
            
    regions = expand_regions(spec)
    for r in regions:
        for pat in patterns:
            add(pat.format(p=p, r=r["nama"]), wilayah.label(r))
            
    # FALLBACK: Jika lokasi tidak ada di database wilayah.json (misal luar Jawa Timur),
    # gunakan teks lokasi mentah yang diinputkan dari spec.location.include
    if not regions and not spec.provinces():
        for loc in spec.location.include:
            for pat in patterns:
                # loc adalah string mentah misal "Kab. Cianjur"
                add(pat.format(p=p, r=loc), loc)

    for syn in spec.product.synonyms:
        if syn.lower() != p:
            for prov in spec.provinces():
                add(f"{syn} {prov}", prov)
    return queries[:max_queries] if max_queries else queries


def build_post_keywords(spec: CampaignSpec) -> list[str]:
    """Kata kunci untuk pencarian di dalam grup (misal 'jual melon')."""
    p = (spec.product.name or "").lower()
    return [f"{w} {p}" for w in INTENT_WORDS[spec.target_intent]] if p else []

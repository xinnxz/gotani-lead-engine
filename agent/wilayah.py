"""Data wilayah (provinsi → kabupaten/kota) dan pencocokan lokasi di teks."""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "wilayah"

# Alias nama provinsi yang sering dipakai di postingan
PROVINCE_ALIASES = {
    "jawa timur": "Jawa Timur",
    "jatim": "Jawa Timur",
    "jawatimur": "Jawa Timur",
    "east java": "Jawa Timur",
}


@lru_cache(maxsize=None)
def _load_all() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for path in DATA_DIR.glob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        out[data["provinsi"]] = data
    return out


def available_provinces() -> list[str]:
    return sorted(_load_all())


def resolve_province(text: str) -> str | None:
    """'jatim' → 'Jawa Timur'. Return None kalau bukan nama provinsi yang dikenal."""
    t = (text or "").strip().lower()
    if t in PROVINCE_ALIASES:
        return PROVINCE_ALIASES[t]
    for name in _load_all():
        if name.lower() == t:
            return name
    return None


def regions_of(province: str) -> list[dict]:
    data = _load_all().get(province)
    if not data:
        return []
    return [{**r, "provinsi": province} for r in data["wilayah"]]


def label(region: dict) -> str:
    prefix = "Kab." if region["jenis"] == "kabupaten" else "Kota"
    return f"{prefix} {region['nama']}"


def find_region_by_name(name: str) -> dict | None:
    """Cari wilayah dari nama bebas, misalnya 'kediri', 'kota malang', 'kab. blitar'."""
    hits = find_regions_in_text(name)
    return hits[0] if hits else None


def find_regions_in_text(text: str) -> list[dict]:
    """Temukan semua kabupaten/kota yang disebut di teks, urut sesuai posisi kemunculan.

    Aturan: 'kota X' → kota; selain itu default ke kabupaten (lebih umum untuk petani).
    """
    if not text:
        return []
    low = text.lower()
    found: list[tuple[int, dict]] = []
    seen: set[str] = set()
    for province in _load_all():
        regs = regions_of(province)
        names = {r["nama"].lower() for r in regs}
        for nm in names:
            for m in re.finditer(rf"\b{re.escape(nm)}\b", low):
                before = low[max(0, m.start() - 12): m.start()]
                is_kota = bool(re.search(r"kota\s*$", before))
                candidates = [r for r in regs if r["nama"].lower() == nm]
                pick = None
                if is_kota:
                    pick = next((r for r in candidates if r["jenis"] == "kota"), None)
                if pick is None:
                    pick = next((r for r in candidates if r["jenis"] == "kabupaten"), None)
                if pick is None:
                    pick = candidates[0]
                    if pick.get("wajib_prefix") and not is_kota:
                        continue
                if pick["kode"] not in seen:
                    seen.add(pick["kode"])
                    found.append((m.start(), pick))
    found.sort(key=lambda x: x[0])
    return [r for _, r in found]


def mentions_province(text: str) -> str | None:
    low = (text or "").lower()
    for alias, name in PROVINCE_ALIASES.items():
        if re.search(rf"\b{re.escape(alias)}\b", low):
            return name
    return None

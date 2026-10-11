"""Campaign Spec (PRD §7.1): model data + penyusunan dari chat operator."""
from __future__ import annotations

import re
import sqlite3
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from . import wilayah
from .db import dumps, loads, now_iso
from .normalize import parse_quantity

# Sinonim awal per komoditas (F1.3). Operator bisa mengedit di Campaign Spec.
KNOWN_COMMODITIES: dict[str, list[str]] = {
    "melon": ["melon"],
    "semangka": ["semangka"],
    "mangga": ["mangga", "harumanis", "aromanis", "gedong gincu"],
    "pisang": ["pisang", "cavendish", "kepok"],
    "jeruk": ["jeruk", "jeruk nipis", "jeruk purut"],
    "cabai": ["cabai", "cabe", "lombok", "rawit"],
    "bawang merah": ["bawang merah", "brambang"],
    "bawang putih": ["bawang putih"],
    "tomat": ["tomat"],
    "jagung": ["jagung", "jagung pipil", "jagung pakan"],
    "padi": ["padi", "gabah", "GKP", "GKG"],
    "beras": ["beras"],
    "sawit": ["sawit", "kelapa sawit", "TBS", "tandan buah segar", "buah sawit"],
    "kopi": ["kopi", "green bean", "biji kopi"],
    "kakao": ["kakao", "cokelat", "coklat"],
    "singkong": ["singkong", "ubi kayu", "ketela pohon", "telo"],
    "kentang": ["kentang"],
    "wortel": ["wortel"],
    "kubis": ["kubis", "kol"],
    "pisang": ["pisang"],
    "mangga": ["mangga"],
    "jeruk": ["jeruk"],
    "alpukat": ["alpukat", "avokad"],
    "durian": ["durian"],
    "nanas": ["nanas", "nanas madu"],
    "tebu": ["tebu"],
    "kedelai": ["kedelai"],
}

DEMAND_HINTS = r"\b(cari pembeli|cari buyer|cari pedagang|cari eksportir|cari distributor|yang butuh|pembeli|buyer|offtaker|penampung)\b"


class Product(BaseModel):
    name: str | None = None
    attributes: dict = Field(default_factory=lambda: {"variety": [], "grade": None})
    synonyms: list[str] = Field(default_factory=list)


class Location(BaseModel):
    include: list[str] = Field(default_factory=list)
    exclude: list[str] = Field(default_factory=list)
    priority: list[str] = Field(default_factory=list)  # kabupaten yang dipindai lebih dulu


class Volume(BaseModel):
    min: float | None = None
    unit: str | None = "kg"
    per: str | None = None


class Timeframe(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    from_: str | None = Field(default=None, alias="from")
    to: str | None = None


class Price(BaseModel):
    min: float | None = None
    max: float | None = None
    currency: str | None = "IDR"
    unit: str | None = "kg"


class CampaignSpec(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    campaign_id: str
    goal: Literal["find_supply", "find_demand", "find_customers"] = "find_supply"
    business_context: str | None = None
    target_entity: str | None = None
    product: Product = Field(default_factory=Product)
    location: Location = Field(default_factory=Location)
    volume: Volume = Field(default_factory=Volume)
    timeframe: Timeframe = Field(default_factory=Timeframe)
    price: Price = Field(default_factory=Price)
    sources: list[str] = Field(default_factory=lambda: ["facebook_groups", "web_b2b"])
    required_fields: list[str] = Field(default_factory=lambda: ["product", "location", "contact_any"])
    freshness_days: int | None = 30
    closing_definition: str | None = "lead_interested"

    @property
    def target_intent(self) -> str:
        return "demand" if self.goal == "find_demand" else "supply"

    def product_terms(self) -> list[str]:
        terms = [self.product.name or ""] + list(self.product.synonyms)
        return sorted({t.strip().lower() for t in terms if t and t.strip()}, key=len, reverse=True)

    def provinces(self) -> list[str]:
        out = []
        for item in self.location.include:
            p = wilayah.resolve_province(item)
            if p and p not in out:
                out.append(p)
        return out

    def to_json(self) -> str:
        return self.model_dump_json(by_alias=True, indent=2)


def new_campaign_id(conn: sqlite3.Connection) -> str:
    year = date.today().year
    n = conn.execute("SELECT COUNT(*) FROM campaigns WHERE id LIKE ?", (f"cmp-{year}-%",)).fetchone()[0]
    return f"cmp-{year}-{n + 1:03d}"


# ---------------------------------------------------------------- penyusunan spec

def missing_slots(spec: CampaignSpec) -> list[str]:
    miss = []
    if not spec.product.name:
        miss.append("product")
    if not spec.location.include:
        miss.append("location")
    return miss


QUESTIONS = {
    "product": "Komoditas apa yang dicari? (misal: melon, cabai, sawit)",
    "location": "Di provinsi atau kabupaten mana? (misal: Jawa Timur, atau Kediri dan Blitar)",
    "volume": "Berapa volume minimalnya? (misal: 500 kg per minggu)",
    "variety": "Ada varietas atau grade khusus? Kalau tidak ada, jawab 'bebas'.",
}


def follow_up_questions(spec: CampaignSpec) -> list[str]:
    """Maksimal 2 pertanyaan per giliran (F1.2)."""
    qs = [QUESTIONS[s] for s in missing_slots(spec)]
    if len(qs) < 2 and spec.volume.min is None:
        qs.append(QUESTIONS["volume"])
    return qs[:2]


def draft_spec_offline(text: str, campaign_id: str) -> CampaignSpec:
    """Susun spec dari teks bebas tanpa LLM (aturan sederhana). Cocok untuk kalimat seperti
    'cari petani melon di Jawa Timur, minimal 500 kg'."""
    low = (text or "").lower()
    spec = CampaignSpec(campaign_id=campaign_id, business_context=(text or "").strip()[:300] or None)

    if re.search(DEMAND_HINTS, low):
        spec.goal = "find_demand"
        spec.target_entity = "pembeli / pedagang / distributor"
    else:
        spec.goal = "find_supply"
        spec.target_entity = "petani / kelompok tani / pengepul"

    for name in sorted(KNOWN_COMMODITIES, key=len, reverse=True):
        if any(re.search(rf"\b{re.escape(s.lower())}\b", low) for s in KNOWN_COMMODITIES[name]):
            spec.product.name = name
            spec.product.synonyms = KNOWN_COMMODITIES[name]
            break

    prov = wilayah.mentions_province(low)
    if prov:
        spec.location.include.append(prov)
    for reg in wilayah.find_regions_in_text(text):
        lbl = wilayah.label(reg)
        if lbl not in spec.location.include:
            spec.location.include.append(lbl)
            spec.location.priority.append(lbl)

    kg, _ = parse_quantity(text)
    if kg:
        spec.volume.min = kg
        spec.volume.unit = "kg"
        m = re.search(r"per\s*(hari|minggu|bulan|panen)", low)
        spec.volume.per = m.group(1) if m else None
    return spec


SPEC_SYSTEM = """Kamu membantu operator agribisnis Indonesia menyusun Campaign Spec untuk agen pencari lead.
Balas HANYA JSON dengan kunci: "spec" dan "questions".
- "spec" mengikuti skema: goal (find_supply|find_demand|find_customers), business_context, target_entity,
  product{name, attributes{variety[], grade}, synonyms[]}, location{include[], exclude[], priority[]},
  volume{min, unit, per}, timeframe{from, to}, price{min, max, currency, unit}, freshness_days.
- ATURAN LOKASI (CERDAS & PRESISI):
  * Nama provinsi tulis lengkap (misal "Jawa Barat", "Jawa Timur").
  * Jika operator menyebut daerah/kota (misal "Bandung"), masukkan kabupaten/kota terkait di `include` (misal: ["Kab. Bandung", "Kota Bandung", "Kab. Bandung Barat", "Jawa Barat"]).
  * Di `priority`, masukkan nama daerah atau kecamatan sentra pertanian yang relevan (misal untuk Bandung: ["Lembang", "Pangalengan", "Ciwidey", "Soreang"]).
  * Jangan mengarang provinsi jika tidak relevan, tapi ekspansi kota ke entitas kabupatennya.
- Usulkan sinonim & istilah lokal di product.synonyms (misal TBS untuk sawit, lombok untuk cabai, gedang untuk pisang).
- Jangan mengarang nilai volume/harga yang tidak disebut operator; isi null.
- "questions": maksimal 2 pertanyaan singkat untuk slot penting yang masih kosong/ambigu. Kosongkan jika sudah lengkap."""


def draft_spec_llm(gateway, conversation: str, campaign_id: str) -> tuple[CampaignSpec, list[str]]:
    data = gateway.generate_json(f"Percakapan operator:\n{conversation}", purpose="campaign_spec", system=SPEC_SYSTEM)
    raw = data.get("spec", {}) if isinstance(data, dict) else {}
    
    # Buang nilai None agar Pydantic bisa menggunakan default_factory-nya (list kosong, dict kosong)
    def remove_nulls(d):
        if not isinstance(d, dict):
            return d
        return {k: remove_nulls(v) for k, v in d.items() if v is not None}
        
    raw = remove_nulls(raw)
    raw["campaign_id"] = campaign_id
    
    spec = CampaignSpec.model_validate(raw)
    questions = [q for q in (data.get("questions") or []) if isinstance(q, str)][:2]
    return spec, questions


# ---------------------------------------------------------------- penyimpanan

def save_campaign(conn: sqlite3.Connection, spec: CampaignSpec, status: str = "active") -> None:
    ts = now_iso()
    conn.execute(
        """INSERT INTO campaigns (id, goal, spec_json, status, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(id) DO UPDATE SET goal=excluded.goal, spec_json=excluded.spec_json,
               status=excluded.status, updated_at=excluded.updated_at""",
        (spec.campaign_id, spec.goal, spec.to_json(), status, ts, ts),
    )
    conn.commit()


def load_campaign(conn: sqlite3.Connection, campaign_id: str) -> CampaignSpec:
    row = conn.execute("SELECT spec_json FROM campaigns WHERE id=?", (campaign_id,)).fetchone()
    if not row:
        raise KeyError(f"Kampanye {campaign_id} tidak ditemukan")
    return CampaignSpec.model_validate(loads(row["spec_json"], {}))


def list_campaigns(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT id, goal, status, created_at, spec_json FROM campaigns ORDER BY created_at DESC").fetchall()


__all__ = [
    "CampaignSpec", "draft_spec_offline", "draft_spec_llm", "follow_up_questions",
    "save_campaign", "load_campaign", "list_campaigns", "new_campaign_id", "dumps",
]

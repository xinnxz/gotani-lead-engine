"""Unit test untuk Smart Pooling / Agregasi Petani (PRD F6.4 / M2.2)."""
import pytest
from agent.pooling import build_smart_pool


def test_smart_pool_aggregates_multiple_farmers():
    """Pembeli butuh 1.000 kg melon.

    Petani A punya 400 kg di Kediri.
    Petani B punya 350 kg di Blitar (~37 km dari Kediri).
    Petani C punya 250 kg di Tulungagung (~35 km dari Kediri).
    Harus berhasil digabung menjadi 1 pool dengan coverage 100%.
    """
    demand = {
        "id": 1,
        "product": "melon",
        "volume_kg": 1000.0,
        "price_per_kg": 9000.0,
        "kabupaten": "Surabaya",
        "confidence": 85,
    }
    supplies = [
        {"id": 101, "entity_name": "Pak Budi", "product": "melon", "volume_kg": 400.0, "price_per_kg": 7500.0, "kabupaten": "Kediri", "confidence": 75},
        {"id": 102, "entity_name": "Pak Joko", "product": "melon", "volume_kg": 350.0, "price_per_kg": 7600.0, "kabupaten": "Blitar", "confidence": 70},
        {"id": 103, "entity_name": "Bu Siti", "product": "melon", "volume_kg": 250.0, "price_per_kg": 7700.0, "kabupaten": "Tulungagung", "confidence": 70},
    ]

    pool = build_smart_pool(demand, supplies, max_farmers=4, max_radius_km=50.0)

    assert pool is not None
    assert pool["kind"] == "pool"
    assert pool["num_farmers"] == 3
    assert pool["total_volume_kg"] == 1000.0
    assert pool["coverage_pct"] == 100.0
    assert "Saran gabungan 3 petani" in pool["disclaimer"]
    assert "titik jemput" in pool["disclaimer"]
    assert pool["score"] > 50


def test_smart_pool_excludes_farmers_outside_radius():
    """Petani yang berada di luar radius 50 km (misal Banyuwangi ke Kediri ~240 km) tidak boleh dimasukkan."""
    demand = {
        "id": 2,
        "product": "melon",
        "volume_kg": 1000.0,
        "kabupaten": "Surabaya",
    }
    supplies = [
        {"id": 201, "entity_name": "Petani Kediri", "product": "melon", "volume_kg": 300.0, "kabupaten": "Kediri"},
        {"id": 202, "entity_name": "Petani Jauh", "product": "melon", "volume_kg": 800.0, "kabupaten": "Banyuwangi"},
    ]

    # Hanya ada 1 petani dalam radius, sehingga pool tidak bisa terbentuk (butuh min 2 petani)
    pool = build_smart_pool(demand, supplies, max_radius_km=50.0)
    assert pool is None

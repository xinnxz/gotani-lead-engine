"""Unit test untuk mesin matching (PRD F6.2 / M2.1)."""
import pytest
from agent.matching import score_match


def test_example_from_implementation_plan():
    """Contoh di Implementation Plan §6:

    Pembeli: butuh melon 500 kg di Surabaya, maks Rp9.000/kg, butuh 20 Okt, varietas bebas. Conf 80.
    Petani: 600 kg di Jombang (jarak terhitung ~65.6 km), Rp7.500/kg, panen 18 Okt. Conf 70.
    Harus menghasilkan skor kecocokan ~83-84 dan tier outreach.
    """
    demand = {
        "product": "melon",
        "volume_kg": 500.0,
        "price_per_kg": 9000.0,
        "kabupaten": "Surabaya",
        "available_date": "2026-10-20",
        "attributes": {"variety": []},
        "confidence": 80,
    }
    supply = {
        "product": "melon",
        "volume_kg": 600.0,
        "price_per_kg": 7500.0,
        "kabupaten": "Jombang",
        "available_date": "2026-10-18",
        "attributes": {"variety": []},
        "confidence": 70,
    }

    res = score_match(demand, supply, margin_pct=0.10)

    # Verifikasi tier dan skor
    assert res["tier"] == "outreach"
    assert 80 <= res["score"] <= 90
    assert res["breakdown"]["produk"]["poin"] == 30.0  # 20 + 10
    assert res["breakdown"]["volume_waktu"]["poin"] == 30.0  # 15 + 15
    assert res["breakdown"]["harga"]["poin"] == 20.0  # 7500 * 1.10 = 8250 <= 9000
    assert res["est_margin"] is not None
    assert res["est_margin"]["feasible"] is True


def test_different_product_gives_zero():
    """Komoditas berbeda (melon vs semangka) harus langsung bernilai 0."""
    demand = {"product": "melon", "volume_kg": 500}
    supply = {"product": "semangka", "volume_kg": 500}
    res = score_match(demand, supply)
    assert res["score"] == 0
    assert res["tier"] == "ignored"


def test_incomplete_data_records_gaps():
    """Data yang kurang lengkap tidak dibuang tapi dicatat kekurangannya."""
    demand = {"product": "pisang", "volume_kg": 1000, "kabupaten": "Kediri"}
    supply = {"product": "pisang", "kabupaten": "Blitar"}  # tanpa volume & harga & tanggal
    res = score_match(demand, supply)
    assert res["score"] > 0
    assert len(res["gaps"]) >= 2
    assert any("Volume" in g for g in res["gaps"])

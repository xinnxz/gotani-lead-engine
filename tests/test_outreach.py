from agent.outreach import (
    normalize_phone_number,
    format_wa_url,
    draft_farmer_outreach_for_match,
    draft_farmer_outreach_for_lead,
    draft_buyer_outreach_for_match,
)


def test_normalize_phone_number():
    assert normalize_phone_number("0812-3456-7890") == "6281234567890"
    assert normalize_phone_number("+62 812 3456 7890") == "6281234567890"
    assert normalize_phone_number("6281234567890") == "6281234567890"
    assert normalize_phone_number("81234567890") == "6281234567890"
    assert normalize_phone_number("081234567890, 08567890123") == "6281234567890"
    assert normalize_phone_number("") is None
    assert normalize_phone_number(None) is None


def test_format_wa_url():
    url = format_wa_url("081234567890", "Halo Pak Tani")
    assert url is not None
    assert url.startswith("https://wa.me/6281234567890?text=")
    assert "Halo%20Pak%20Tani" in url


def test_draft_farmer_outreach_for_match():
    msg = draft_farmer_outreach_for_match(
        farmer_name="Pak Joko",
        commodity="melon",
        farmer_location="Kabupaten Jombang",
        buyer_name="PT Buah Segar",
        buyer_location="Kota Surabaya",
        needed_vol_kg=500.0,
    )
    assert "Pak Joko" in msg
    assert "Melon" in msg or "melon" in msg
    assert "Kota Surabaya" in msg
    assert "500 kg" in msg
    assert "GoTani" in msg
    assert "mohon diabaikan" in msg.lower()


def test_draft_farmer_outreach_for_lead():
    msg = draft_farmer_outreach_for_lead(
        farmer_name="Samsul",
        commodity="semangka",
        farmer_location="Kabupaten Kediri",
        volume_kg=2000.0,
        price_per_kg=6000.0,
    )
    assert "Samsul" in msg
    assert "Semangka" in msg or "semangka" in msg
    assert "Kediri" in msg
    assert "2000 kg" in msg
    assert "Rp 6,000/kg" in msg
    assert "GoTani" in msg


def test_draft_buyer_outreach_for_match_single():
    msg = draft_buyer_outreach_for_match(
        buyer_name="UD Berkah Buah",
        commodity="melon",
        buyer_location="Kota Surabaya",
        needed_vol_kg=300.0,
        suggested_price=10500.0,
        is_pool=False,
    )
    assert "UD Berkah Buah" in msg
    assert "300 kg" in msg
    assert "Rp 10,500/kg" in msg
    assert "GoTani" in msg
    assert "spesifikasi mutu" in msg


def test_draft_buyer_outreach_for_match_pool():
    msg = draft_buyer_outreach_for_match(
        buyer_name="PT Restu Ibu",
        commodity="melon",
        buyer_location="Kota Surabaya",
        needed_vol_kg=500.0,
        suggested_price=9500.0,
        is_pool=True,
        num_farmers=3,
        farmer_locations=["Kediri", "Blitar", "Tulungagung"],
    )
    assert "PT Restu Ibu" in msg
    assert "500 kg" in msg
    assert "smart pooling" in msg.lower()
    assert "3 petani mitra" in msg
    assert "Rp 9,500/kg" in msg


def test_build_matches_export_dataframe():
    from agent.outreach import build_matches_export_dataframe

    dummy_matches = [
        {
            "match_id": 1,
            "kind": "single",
            "tier": "outreach",
            "score": 92,
            "status": "open",
            "outcome": "deal",
            "outcome_reason": "Harga disetujui",
            "buyer_name": "PT Sumber Segar",
            "product": "melon",
            "buyer_vol": 500.0,
            "buyer_location": "Kota Surabaya",
            "buyer_max_price": 10000.0,
            "buyer_needed_date": "2026-10-20",
            "buyer_phone": "081234567890",
            "total_volume_kg": 500.0,
            "coverage_pct": 100.0,
            "margin": {"est_gross_margin_rp": 500000.0, "suggested_price": 9500.0},
            "items": [
                {
                    "farmer_name": "Pak Joko",
                    "farmer_location": "Kabupaten Jombang",
                    "allocated_kg": 500.0,
                    "farmer_price": 8500.0,
                    "farmer_phone": "085612345678",
                }
            ],
            "gaps": [],
            "matched_at": "2026-10-11T10:00:00",
        }
    ]

    df = build_matches_export_dataframe(dummy_matches)
    assert not df.empty
    assert len(df) == 1
    assert df.iloc[0]["Match_ID"] == 1
    assert df.iloc[0]["Tipe_Match"] == "Match Tunggal"
    assert df.iloc[0]["Skor_Kecocokan"] == 92
    assert df.iloc[0]["Hasil_Transaksi"] == "deal"
    assert df.iloc[0]["Nama_Pembeli"] == "PT Sumber Segar"
    assert df.iloc[0]["Estimasi_Margin_GoTani_Rp"] == 500000.0
    assert "Pak Joko" in df.iloc[0]["Rincian_Petani"]
    assert "085612345678" in df.iloc[0]["Kontak_Petani"]


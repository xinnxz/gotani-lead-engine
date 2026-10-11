from agent.campaign import CampaignSpec
from agent.planner import build_group_queries


def test_build_group_queries_multi_source():
    spec = CampaignSpec(campaign_id="test_camp", goal="find_demand")
    spec.product.name = "melon"
    spec.location.include = ["Kediri", "Surabaya"]

    queries = build_group_queries(spec)
    assert len(queries) > 0

    platforms = {q["platform"] for q in queries}
    # Harus mencakup facebook, google_maps, dan web_b2b
    assert "facebook" in platforms
    assert "google_maps" in platforms
    assert "web_b2b" in platforms

    # Memastikan query Toko Buah / Maps dan Pasar Induk terbentuk
    q_texts = [q["query"].lower() for q in queries]
    assert any("toko buah" in t for t in q_texts)
    assert any("pasar induk" in t for t in q_texts)
    assert any("distributor buah" in t for t in q_texts)

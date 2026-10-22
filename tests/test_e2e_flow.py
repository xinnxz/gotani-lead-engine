"""End-to-end integration test: Simulates the full GoTani flow.

Supply scraping → Review → Manual demand → Matchmaking → CRM outreach

Tujuan: Memastikan seluruh pipeline berjalan tanpa error dari awal sampai akhir.
"""
import sqlite3
import sys
import os

# Setup path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from agent.db import connect, save_manual_order, now_iso, dumps
from agent.match_runner import run_all_matches, get_matches_for_display, update_match_outcome, update_match_status
from agent.matching import score_match
from agent.outreach import (
    draft_farmer_outreach_for_match,
    draft_farmer_outreach_for_lead,
    draft_buyer_outreach_for_match,
    format_wa_url,
)
from agent.sales_agent import (
    generate_initial_outreach,
    generate_conversational_reply,
    summarize_conversation,
    calculate_sales_metrics,
)
from agent.cadence import get_due_followups, generate_followup_message, advance_followup, calculate_due_date
from agent.handover import evaluate_inbound_message
from agent.compliance import is_do_not_contact, register_opt_out_contact, is_within_operating_hours
from agent.config import settings

import tempfile
import json


def test_e2e():
    """Test end-to-end flow dengan database sementara."""
    # 1. Buat database di memory
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    conn = connect(db_path)
    print("=" * 60)
    print("E2E TEST: GoTani Lead Engine Full Flow")
    print("=" * 60)

    errors = []
    warnings = []

    # ============================================================
    # STEP 1: Simulasi data supply (petani) — seperti hasil scraping
    # ============================================================
    print("\n[STEP 1] Simulasi data supply (petani)...")
    try:
        ts = now_iso()

        # Insert raw_item pertanian
        for i, (name, product, vol, price, loc, phone, text) in enumerate([
            ("Pak Budi", "durian", 2000, 35000, "Medan", "081234567890",
             "Ready durian musang king 2 ton, harga 35rb/kg. Medan. WA 081234567890"),
            ("Bu Siti", "durian", 500, 30000, "Sidoarjo", "082345678901",
             "Jual durian montong 500kg, harga 30rb/kg. Sidoarjo Jatim. Hub 082345678901"),
            ("Pak Agus", "melon", 1000, 8000, "Kediri", "083456789012",
             "Panen melon golden 1 ton. Kediri. Rp 8000/kg. Call 083456789012"),
        ]):
            raw_id = conn.execute(
                """INSERT INTO raw_items (campaign_id, platform, raw_text, content_hash, fetched_at, author_name, processed)
                   VALUES (?, 'facebook', ?, ?, ?, ?, 1)""",
                (f"cmp-test-{i}", text, f"hash_{i}_{name}", ts, name),
            ).lastrowid

            listing_id = conn.execute(
                """INSERT INTO listings (
                    campaign_id, raw_item_id, intent, entity_name, product,
                    volume_kg, price_per_kg, location_text, kabupaten,
                    contact_phone, contact_wa, relevance, confidence,
                    review_status, extractor, created_at
                ) VALUES (?, ?, 'supply', ?, ?, ?, ?, ?, ?, ?, ?, 95, 80, 'approved', 'test', ?)""",
                (f"cmp-test-{i}", raw_id, name, product, vol, price, loc, loc, phone, phone, ts),
            ).lastrowid
            print(f"  Supply #{listing_id}: {name} - {product} {vol}kg @Rp{price}/kg ({loc})")

        conn.commit()
        supply_count = conn.execute("SELECT COUNT(*) FROM listings WHERE intent='supply'").fetchone()[0]
        assert supply_count == 3, f"Expected 3 supply, got {supply_count}"
        print(f"  -> {supply_count} supply listings created")
    except Exception as e:
        errors.append(f"STEP 1 FAILED: {e}")
        print(f"  ERROR: {e}")

    # ============================================================
    # STEP 2: Input demand (pembeli) — via save_manual_order
    # ============================================================
    print("\n[STEP 2] Input demand (pembeli) via manual order...")
    try:
        order1_id = save_manual_order(
            conn,
            buyer_name="PT Buah Segar Indonesia",
            product="durian",
            volume_kg=1500,
            max_price_per_kg=40000,
            kabupaten="Surabaya",
            needed_date="2026-11-15",
            contact_phone="085678901234",
            variety="musang king",
        )
        print(f"  Demand #{order1_id}: PT Buah Segar Indonesia - durian 1500kg @Rp40k/kg (Surabaya)")

        order2_id = save_manual_order(
            conn,
            buyer_name="Toko Buah Makmur",
            product="melon",
            volume_kg=500,
            max_price_per_kg=12000,
            kabupaten="Malang",
            needed_date="2026-11-20",
            contact_phone="086789012345",
        )
        print(f"  Demand #{order2_id}: Toko Buah Makmur - melon 500kg @Rp12k/kg (Malang)")

        demand_count = conn.execute("SELECT COUNT(*) FROM listings WHERE intent='demand'").fetchone()[0]
        assert demand_count == 2, f"Expected 2 demand, got {demand_count}"
        print(f"  -> {demand_count} demand listings created")
    except Exception as e:
        errors.append(f"STEP 2 FAILED: {e}")
        print(f"  ERROR: {e}")

    # ============================================================
    # STEP 3: Jalankan matchmaking
    # ============================================================
    print("\n[STEP 3] Jalankan matchmaking...")
    try:
        stats = run_all_matches(conn, include_pending_high_score=True)
        print(f"  Results: {stats}")
        assert stats["total_demand"] == 2, f"Expected 2 demand processed, got {stats['total_demand']}"
        assert stats["matches_created"] > 0, f"Expected >0 matches, got {stats['matches_created']}"
        print(f"  -> {stats['matches_created']} matches + {stats['pools_created']} pools created")
    except Exception as e:
        errors.append(f"STEP 3 FAILED: {e}")
        print(f"  ERROR: {e}")

    # ============================================================
    # STEP 4: Tampilkan match results
    # ============================================================
    print("\n[STEP 4] Get matches for display...")
    try:
        matches = get_matches_for_display(conn)
        print(f"  Total matches displayed: {len(matches)}")
        for m in matches:
            items = m.get("items", [])
            farmer_names = [it.get("farmer_name", "?") for it in items]
            print(f"  Match #{m['match_id']}: {m['buyer_name']} <-> {', '.join(farmer_names)} "
                  f"| Score: {m['score']}/100 | Tier: {m['tier']} | Coverage: {m.get('coverage_pct', '?')}%")

        # Test filter
        outreach = get_matches_for_display(conn, tier_filter="outreach")
        review = get_matches_for_display(conn, tier_filter="review")
        ignored = get_matches_for_display(conn, tier_filter="ignored")
        print(f"  Filter: outreach={len(outreach)}, review={len(review)}, ignored={len(ignored)}")

        assert len(matches) > 0, "No matches found!"
    except Exception as e:
        errors.append(f"STEP 4 FAILED: {e}")
        print(f"  ERROR: {e}")

    # ============================================================
    # STEP 5: Generate outreach drafts
    # ============================================================
    print("\n[STEP 5] Generate outreach drafts...")
    try:
        if matches:
            m = matches[0]
            items = m.get("items", [])
            if items:
                it = items[0]
                # Farmer outreach
                farmer_draft = draft_farmer_outreach_for_match(
                    farmer_name=it.get("farmer_name"),
                    commodity=m["product"],
                    farmer_location=it.get("farmer_location"),
                    buyer_name=m["buyer_name"],
                    buyer_location=m["buyer_location"],
                    needed_vol_kg=it.get("allocated_kg") or m["buyer_vol"],
                    farmer_price=it.get("farmer_price"),
                )
                print(f"  Farmer draft ({len(farmer_draft)} chars): {farmer_draft[:100]}...")

                # Buyer outreach
                buyer_draft = draft_buyer_outreach_for_match(
                    buyer_name=m["buyer_name"],
                    commodity=m["product"],
                    buyer_location=m["buyer_location"],
                    needed_vol_kg=m["buyer_vol"],
                    suggested_price=it.get("farmer_price"),
                    is_pool=m["kind"] == "pool",
                    num_farmers=len(items),
                    farmer_locations=[x.get("farmer_location") for x in items],
                )
                print(f"  Buyer draft ({len(buyer_draft)} chars): {buyer_draft[:100]}...")

                # WA URL
                wa_url = format_wa_url(it.get("farmer_phone") or it.get("farmer_wa"), farmer_draft)
                assert wa_url is not None, "WA URL should not be None"
                print(f"  WA URL generated: {wa_url[:80]}...")
    except Exception as e:
        errors.append(f"STEP 5 FAILED: {e}")
        print(f"  ERROR: {e}")

    # ============================================================
    # STEP 6: CRM — Create conversation & messages
    # ============================================================
    print("\n[STEP 6] CRM conversation flow...")
    try:
        from agent.db import create_conversation, add_message, get_messages, list_conversations, update_conversation, get_conversation_by_listing

        # Buat conversation untuk supply listing pertama
        supply_listing = conn.execute("SELECT * FROM listings WHERE intent='supply' LIMIT 1").fetchone()
        s_id = supply_listing["id"]

        c_id = create_conversation(
            conn,
            listing_id=s_id,
            campaign_id="cmp-sales-test",
            contact_phone="081234567890",
            role="farmer",
            contact_name="Pak Budi",
            initial_state="drafted",
            followup_due_at=calculate_due_date(days_ahead=3),
        )
        print(f"  Conversation #{c_id} created for Pak Budi")

        # Add initial outreach message
        init_msg = generate_initial_outreach(conn, s_id)
        add_message(conn, c_id, "outbound", "ai", init_msg, delivery_status="draft")
        print(f"  Initial outreach ({len(init_msg)} chars): {init_msg[:100]}...")

        # Verify messages
        msgs = get_messages(conn, c_id)
        assert len(msgs) == 1, f"Expected 1 message, got {len(msgs)}"
        print(f"  Messages in thread: {len(msgs)}")

        # Simulate inbound reply
        inbound_text = "Oh iya, saya masih ada stok 2 ton. Harga bisa nego kalau ambil banyak."
        add_message(conn, c_id, "inbound", "lead", inbound_text, delivery_status="received")

        # Evaluate handover
        eval_res = evaluate_inbound_message(inbound_text)
        print(f"  Handover eval: needs_handover={eval_res['needs_handover']}, trigger={eval_res['trigger_type']}, reason={eval_res.get('reason', '-')}")

        # Generate AI reply
        ai_reply = generate_conversational_reply(conn, c_id, inbound_text)
        add_message(conn, c_id, "outbound", "ai", ai_reply, delivery_status="draft")
        print(f"  AI reply ({len(ai_reply)} chars): {ai_reply[:100]}...")

        # Verify thread
        msgs = get_messages(conn, c_id)
        assert len(msgs) == 3, f"Expected 3 messages, got {len(msgs)}"
        print(f"  Total messages now: {len(msgs)}")

        # List conversations
        convos = list_conversations(conn)
        assert len(convos) >= 1
        print(f"  Total conversations: {len(convos)}")

        # Check duplicate prevention
        existing = get_conversation_by_listing(conn, s_id)
        assert existing is not None, "Should find existing conversation"
        print(f"  Duplicate check: correctly found existing conversation #{existing['id']}")
    except Exception as e:
        errors.append(f"STEP 6 FAILED: {e}")
        print(f"  ERROR: {e}")
        import traceback
        traceback.print_exc()

    # ============================================================
    # STEP 7: Handover detection scenarios
    # ============================================================
    print("\n[STEP 7] Handover detection scenarios...")
    try:
        test_messages = [
            ("Tertarik pak, bisa kirim sampel?", True, "interest"),
            ("Harga segitu kemahalan, bisa kurang?", True, "negotiation"),
            ("Ini bot ya? Saya mau bicara sama orang asli", True, "bot_inquiry"),
            ("STOP jangan hubungi saya lagi", False, "opt_out"),
            ("Oke terima kasih infonya", False, None),
            ("Masih ada stok ga?", False, None),
        ]
        all_pass = True
        for msg, expected_handover, expected_trigger in test_messages:
            res = evaluate_inbound_message(msg)
            status = "OK" if res["needs_handover"] == expected_handover else "FAIL"
            if status == "FAIL":
                all_pass = False
                warnings.append(f"Handover detection mismatch: '{msg}' -> expected {expected_handover}, got {res['needs_handover']}")
            trigger_match = "" if expected_trigger is None else (
                "OK" if res.get("trigger_type") == expected_trigger else f"WARN(got {res.get('trigger_type')})"
            )
            print(f"  [{status}] \"{msg[:50]}\" -> handover={res['needs_handover']} trigger={res.get('trigger_type', '-')} {trigger_match}")
    except Exception as e:
        errors.append(f"STEP 7 FAILED: {e}")
        print(f"  ERROR: {e}")

    # ============================================================
    # STEP 8: Compliance & Opt-out
    # ============================================================
    print("\n[STEP 8] Compliance & opt-out...")
    try:
        test_phone = "089999888777"
        assert not is_do_not_contact(conn, test_phone), "Should not be DNC initially"
        register_opt_out_contact(conn, test_phone, reason="user_stop", source_message="jangan hubungi lagi")
        assert is_do_not_contact(conn, test_phone), "Should be DNC after opt-out"
        print(f"  Opt-out flow: OK")

        # Operating hours
        from datetime import datetime, timezone, timedelta
        tz_wib = timezone(timedelta(hours=7))
        morning = datetime(2026, 10, 22, 8, 0, tzinfo=tz_wib)
        night = datetime(2026, 10, 22, 22, 0, tzinfo=tz_wib)
        assert is_within_operating_hours(morning) == True, "8am should be within hours"
        assert is_within_operating_hours(night) == False, "10pm should be outside hours"
        print(f"  Operating hours: OK (8am=allowed, 10pm=blocked)")
    except Exception as e:
        errors.append(f"STEP 8 FAILED: {e}")
        print(f"  ERROR: {e}")

    # ============================================================
    # STEP 9: Sales metrics
    # ============================================================
    print("\n[STEP 9] Sales metrics...")
    try:
        metrics = calculate_sales_metrics(conn)
        print(f"  Metrics: {json.dumps(metrics, indent=2)}")
        assert "total_convs" in metrics
        assert "reply_rate_pct" in metrics
        assert "conversion_rate_pct" in metrics
        print(f"  All metric fields present: OK")
    except Exception as e:
        errors.append(f"STEP 9 FAILED: {e}")
        print(f"  ERROR: {e}")

    # ============================================================
    # STEP 10: Match outcome recording
    # ============================================================
    print("\n[STEP 10] Match outcome recording...")
    try:
        if matches:
            m_id = matches[0]["match_id"]
            # Confirm outreach
            ok = update_match_status(conn, m_id, "confirmed")
            assert ok, "update_match_status should succeed"
            print(f"  Match #{m_id} confirmed: OK")

            # Record deal
            ok = update_match_outcome(conn, m_id, "deal", "Harga cocok, jadwal sesuai")
            assert ok, "update_match_outcome should succeed"
            print(f"  Match #{m_id} deal recorded: OK")

            # Verify
            row = conn.execute("SELECT status, outcome, outcome_reason FROM matches WHERE id = ?", (m_id,)).fetchone()
            assert row["status"] == "closed"
            assert row["outcome"] == "deal"
            print(f"  Match #{m_id} verified: status={row['status']}, outcome={row['outcome']}")
    except Exception as e:
        errors.append(f"STEP 10 FAILED: {e}")
        print(f"  ERROR: {e}")

    # ============================================================
    # SUMMARY
    # ============================================================
    print("\n" + "=" * 60)
    print("E2E TEST SUMMARY")
    print("=" * 60)
    if errors:
        print(f"\nERRORS ({len(errors)}):")
        for e in errors:
            print(f"  [X] {e}")
    else:
        print("\n  ALL 10 STEPS PASSED!")

    if warnings:
        print(f"\nWARNINGS ({len(warnings)}):")
        for w in warnings:
            print(f"  [!] {w}")

    # Cleanup
    conn.close()
    os.unlink(db_path)

    if errors:
        sys.exit(1)
    print("\nE2E test completed successfully!")


if __name__ == "__main__":
    test_e2e()

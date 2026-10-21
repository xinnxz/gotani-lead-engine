"""Unit test untuk modul compliance (UU PDP) dan handover detector (PRD §7.8)."""
import pytest
import sqlite3
from datetime import datetime
from agent import db
from agent.compliance import (
    detect_opt_out_intent,
    is_do_not_contact,
    register_opt_out_contact,
    is_within_operating_hours,
)
from agent.handover import evaluate_inbound_message


@pytest.fixture
def test_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(db.SCHEMA_PATH.read_text(encoding="utf-8"))
    return conn


def test_detect_opt_out_patterns():
    # Pola penolakan
    assert detect_opt_out_intent("Stop wa saya ya")[0] is True
    assert detect_opt_out_intent("Tolong jangan hubungi lagi")[0] is True
    assert detect_opt_out_intent("Hapus nomor saya dari data kalian")[0] is True
    assert detect_opt_out_intent("Salah sambung mas, bukan petani")[0] is True
    assert detect_opt_out_intent("stop")[0] is True
    
    # Bukan penolakan
    assert detect_opt_out_intent("Halo apa kabar mas")[0] is False
    assert detect_opt_out_intent("Melon ready 1 ton siap kirim")[0] is False


def test_compliance_dnc_registration(test_conn):
    phone = "085712345678"
    assert is_do_not_contact(test_conn, phone) is False
    
    ok = register_opt_out_contact(test_conn, phone, reason="user_stop", source_message="jangan wa lagi")
    assert ok is True
    assert is_do_not_contact(test_conn, phone) is True
    assert is_do_not_contact(test_conn, "6285712345678") is True


def test_operating_hours():
    # Jam kerja 07.00 - 20.00
    dt_morning = datetime(2026, 10, 21, 8, 30)   # 08:30 -> Boleh
    dt_noon = datetime(2026, 10, 21, 14, 0)      # 14:00 -> Boleh
    dt_night = datetime(2026, 10, 21, 21, 15)    # 21:15 -> Tidak boleh
    dt_dawn = datetime(2026, 10, 21, 4, 0)       # 04:00 -> Tidak boleh
    
    assert is_within_operating_hours(dt_morning) is True
    assert is_within_operating_hours(dt_noon) is True
    assert is_within_operating_hours(dt_night) is False
    assert is_within_operating_hours(dt_dawn) is False


def test_handover_deal_interest():
    res = evaluate_inbound_message("Saya tertarik mas, bisa minta penawaran resmi dan kirim sampel?")
    assert res["needs_handover"] is True
    assert res["trigger_type"] == "deal_interest"


def test_handover_negotiation():
    res = evaluate_inbound_message("Bisa kurang gak harganya kalau ambil 2 ton? Minta harga pas.")
    assert res["needs_handover"] is True
    assert res["trigger_type"] == "negotiation"


def test_handover_bot_inquiry():
    res = evaluate_inbound_message("Ini saya bicara sama orang beneran atau bot ya?")
    assert res["needs_handover"] is True
    assert res["trigger_type"] == "bot_inquiry"


def test_handover_complaint():
    res = evaluate_inbound_message("Jangan sembarangan chat nomor saya penipu kalian ya!")
    assert res["needs_handover"] is True
    assert res["trigger_type"] == "complaint"


def test_handover_opt_out():
    res = evaluate_inbound_message("Jangan hubungi nomor ini lagi.")
    assert res["needs_handover"] is False
    assert res["trigger_type"] == "opt_out"
    assert res["suggested_action"] == "register_opt_out_and_stop"


def test_routine_conversation():
    res = evaluate_inbound_message("Iya masih ada melon inthanon nya mas di kebun.")
    assert res["needs_handover"] is False
    assert res["trigger_type"] == "routine"

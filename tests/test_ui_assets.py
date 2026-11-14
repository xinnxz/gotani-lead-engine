"""Unit tests for agent.ui_assets module."""
import pytest
from agent.ui_assets import (
    load_svg,
    icon_svg,
    logo_wordmark_svg,
    logo_mark_svg,
    illustration_farm_svg,
    render_top_navbar,
    render_hero_banner,
    render_kpi_card,
)


def test_load_svg_icons():
    raw = load_svg("icons/search.svg")
    assert "<svg" in raw
    assert "viewBox" in raw


def test_icon_svg_customization():
    ic = icon_svg("rocket", size=24, color="#16A765", extra_class="my-icon")
    assert "width:24px" in ic
    assert "height:24px" in ic
    assert "color:#16A765" in ic
    assert "my-icon" in ic


def test_logo_and_illustration():
    wm = logo_wordmark_svg(36)
    assert "GoTani" in wm
    assert "height:36px" in wm

    lm = logo_mark_svg(28)
    assert "<svg" in lm

    farm = illustration_farm_svg()
    assert "<svg" in farm


def test_render_components():
    nav = render_top_navbar()
    assert "gt-topbar" in nav
    assert "gt-deploy-btn" in nav

    hero = render_hero_banner(
        total_raw=100,
        total_leads=40,
        total_matches=5,
        total_convs=2,
        cost_usd=0.012,
        last_run_time="2026-11-14 22:00",
    )
    assert "Selamat Datang di GoTani Lead Agent" in hero
    assert "Total Posts: <b>100</b>" in hero
    assert "Valid Leads: <b>40</b>" in hero

    kpi = render_kpi_card("Raw Posts", 100, "file", "mint")
    assert "gt-kpi-card" in kpi
    assert "Raw Posts" in kpi
    assert "100" in kpi

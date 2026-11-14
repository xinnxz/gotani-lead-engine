"""UI Assets & Theme Engine untuk GoTani Lead Agent.

Menyediakan fungsi terpusat untuk memuat ikon SVG vektor, logo, ilustrasi lanskap,
dan merender komponen visual bertema GoTani (Hero Banner, KPI Cards, Status Pills).
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

# Path ke direktori asset UI
UI_ASSET_DIR = Path(__file__).resolve().parent.parent / "assets" / "ui"

# Cache memori agar I/O disk hanya dilakukan 1x
_SVG_CACHE: dict[str, str] = {}


def load_svg(relative_path: str) -> str:
    """Muat file SVG dari folder assets/ui/ dengan caching in-memory."""
    if relative_path in _SVG_CACHE:
        return _SVG_CACHE[relative_path]

    file_path = UI_ASSET_DIR / relative_path
    if not file_path.exists():
        # Coba cari di root assets/ui jika tidak ada di subfolder
        fallback_path = UI_ASSET_DIR / file_path.name
        if fallback_path.exists():
            file_path = fallback_path
        else:
            return f"<!-- SVG '{relative_path}' not found -->"

    try:
        content = file_path.read_text(encoding="utf-8").strip()
        # Bersihkan XML declaration jika ada
        content = re.sub(r"<\?xml.*?\?>", "", content).strip()
        _SVG_CACHE[relative_path] = content
        return content
    except Exception as e:
        return f"<!-- Error loading SVG '{relative_path}': {e} -->"


def icon_svg(
    name: str,
    size: int = 16,
    color: str | None = None,
    extra_class: str = "",
    stroke_width: float | None = None,
) -> str:
    """Dapatkan ikon SVG dengan ukuran, warna, dan stroke yang dapat disesuaikan.
    
    Semua ikon menggunakan stroke='currentColor' secara default.
    """
    raw_svg = load_svg(f"icons/{name}.svg")
    if raw_svg.startswith("<!--"):
        return raw_svg

    # Tambahkan style inline untuk width, height, dan warna
    style_parts = [
        f"width:{size}px",
        f"height:{size}px",
        "display:inline-block",
        "vertical-align:middle",
        "flex-shrink:0",
    ]
    if color:
        style_parts.append(f"color:{color}")

    style_attr = f'style="{"; ".join(style_parts)}"'
    class_attr = f'class="gt-icon gt-icon-{name} {extra_class}".strip()'

    # Sisipkan atribut ke dalam tag <svg>
    svg_mod = raw_svg
    if stroke_width is not None:
        svg_mod = re.sub(r'stroke-width="[^"]*"', f'stroke-width="{stroke_width}"', svg_mod)

    # Ganti tag pembuka <svg ...>
    svg_mod = re.sub(
        r"<svg\b([^>]*)>",
        rf"<svg \1 {style_attr} {class_attr}>",
        svg_mod,
        count=1,
    )
    return svg_mod


def logo_wordmark_svg(height: int = 34) -> str:
    """Logo utama GoTani Wordmark (Ikon Daun + Teks GoTani)."""
    raw = load_svg("logo/gotani-wordmark.svg")
    # Skalakan height
    return re.sub(
        r"<svg\b([^>]*)>",
        rf'<svg \1 style="height:{height}px; width:auto; display:inline-block; vertical-align:middle;">',
        raw,
        count=1,
    )


def logo_mark_svg(size: int = 28) -> str:
    """Logo mark GoTani (Ikon Daun saja)."""
    raw = load_svg("logo/gotani-mark.svg")
    return re.sub(
        r"<svg\b([^>]*)>",
        rf'<svg \1 style="width:{size}px; height:{size}px; display:inline-block; vertical-align:middle;">',
        raw,
        count=1,
    )


def illustration_farm_svg() -> str:
    """Ilustrasi lanskap pertanian untuk Hero Banner."""
    return load_svg("illustrations/farm-landscape.svg")


def render_top_navbar() -> str:
    """Render top navbar floating dengan Logo GoTani di kiri dan tombol Deploy di kanan."""
    wordmark = logo_wordmark_svg(height=36)
    rocket_ic = icon_svg("rocket", size=14, color="#FFFFFF")
    
    return f"""
    <div class="gt-topbar">
        <div class="gt-topbar-left">
            {wordmark}
        </div>
        <div class="gt-topbar-right">
            <a href="https://streamlit.io/cloud" target="_blank" class="gt-deploy-btn">
                {rocket_ic}
                <span>Deploy</span>
            </a>
        </div>
    </div>
    """


def render_hero_banner(
    total_raw: int,
    total_leads: int,
    total_matches: int,
    total_convs: int,
    cost_usd: float,
    last_run_time: str,
) -> str:
    """Render Welcome Hero Banner dengan ilustrasi lanskap pertanian dan status bar terintegrasi."""
    check_ic = icon_svg("check-circle", size=13, color="#075B40")
    
    return f"""
    <div class="gt-hero-card">
        <div class="gt-hero-content">
            <div class="gt-hero-text">
                <h1 class="gt-hero-title">Selamat Datang di GoTani Lead Agent 👋</h1>
                <p class="gt-hero-subtitle">Kelola dan verifikasi prospek petani & pembeli dengan lebih cepat dan akurat.</p>
            </div>
            <div class="gt-hero-illustration">
                {illustration_farm_svg()}
            </div>
        </div>
        <div class="gt-hero-statusbar">
            <div class="gt-hero-status-left">
                <span class="gt-pill-succeeded">
                    {check_ic}
                    <span>Succeeded</span>
                </span>
                <span class="gt-status-badge-title">Dataset Siap</span>
                <span class="gt-status-meta">Total Posts: <b>{total_raw:,}</b></span>
                <span class="gt-status-meta">Valid Leads: <b>{total_leads:,}</b></span>
                <span class="gt-status-meta">Matches: <b>{total_matches:,}</b></span>
                <span class="gt-status-meta">CRM Convs: <b>{total_convs:,}</b></span>
                <span class="gt-status-meta">Biaya: <b>${cost_usd:.3f}</b></span>
                <span class="gt-status-meta">Waktu: <b>{last_run_time}</b></span>
            </div>
            <div class="gt-hero-status-right">
                <span class="gt-pulse-dot"></span>
                <span class="gt-status-operational">Status Operasional Normal</span>
            </div>
        </div>
    </div>
    """


def render_kpi_card(
    title: str,
    value: Any,
    icon_name: str,
    theme: str = "mint",  # 'mint', 'green', 'amber', 'purple', 'blue'
    help_text: str = "",
) -> str:
    """Render satu kartu metrik KPI dengan border & background bertema warna khusus."""
    theme_colors = {
        "mint": {"icon": "#0B8F61", "bg": "#F1FAF5", "border": "#D2EBDD"},
        "green": {"icon": "#16A765", "bg": "#F0FDF4", "border": "#BBF7D0"},
        "amber": {"icon": "#E6A008", "bg": "#FFFBEB", "border": "#FDE68A"},
        "purple": {"icon": "#7863D8", "bg": "#F5F3FF", "border": "#DDD6FE"},
        "blue": {"icon": "#2687C9", "bg": "#F0F9FF", "border": "#BAE6FD"},
    }
    cfg = theme_colors.get(theme, theme_colors["mint"])
    ic = icon_svg(icon_name, size=20, color=cfg["icon"])
    info_ic = icon_svg("info", size=13, color="#94A3B8")
    
    tooltip_attr = f'title="{help_text}"' if help_text else ""
    
    return f"""
    <div class="gt-kpi-card gt-kpi-{theme}" style="background-color:{cfg['bg']}; border-color:{cfg['border']};">
        <div class="gt-kpi-header">
            <div class="gt-kpi-icon-wrap" style="color:{cfg['icon']};">
                {ic}
            </div>
            <div class="gt-kpi-title" {tooltip_attr}>
                <span>{title}</span>
                <span class="gt-kpi-info-btn">{info_ic}</span>
            </div>
        </div>
        <div class="gt-kpi-value">{value}</div>
    </div>
    """

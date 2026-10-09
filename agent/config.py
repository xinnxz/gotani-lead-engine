"""Pengaturan aplikasi. Semua nilai bisa diubah lewat file .env (lihat .env.example)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return default


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


@dataclass
class Settings:
    # --- LLM (Gemini) ---
    gemini_api_key: str
    gemini_model: str
    llm_daily_budget_usd: float
    llm_max_requests_per_day: int
    llm_min_seconds_between_calls: float
    llm_price_input_per_m: float
    llm_price_output_per_m: float
    llm_batch_size: int

    # --- Ambang lead valid (PRD §3.3, usulan) ---
    relevance_min: int
    confidence_min: int

    # --- Facebook executor (F2.4: rate limit konservatif) ---
    fb_seconds_between_pages: float
    fb_max_pages_per_hour: int
    fb_max_pages_per_day: int
    fb_settle_ms: int
    fb_rescan_hours: int

    # --- Path ---
    db_path: Path
    profiles_dir: Path
    exports_dir: Path
    logs_dir: Path

    @classmethod
    def load(cls) -> "Settings":
        s = cls(
            gemini_api_key=os.getenv("GEMINI_API_KEY", "").strip(),
            gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip(),
            llm_daily_budget_usd=_float("LLM_DAILY_BUDGET_USD", 0.50),
            llm_max_requests_per_day=_int("LLM_MAX_REQUESTS_PER_DAY", 800),
            llm_min_seconds_between_calls=_float("LLM_MIN_SECONDS_BETWEEN_CALLS", 4.0),
            llm_price_input_per_m=_float("LLM_PRICE_INPUT_PER_M", 0.10),
            llm_price_output_per_m=_float("LLM_PRICE_OUTPUT_PER_M", 0.40),
            llm_batch_size=_int("LLM_BATCH_SIZE", 15),
            relevance_min=_int("RELEVANCE_MIN", 70),
            confidence_min=_int("CONFIDENCE_MIN", 60),
            fb_seconds_between_pages=_float("FB_SECONDS_BETWEEN_PAGES", 20),
            fb_max_pages_per_hour=_int("FB_MAX_PAGES_PER_HOUR", 60),
            fb_max_pages_per_day=_int("FB_MAX_PAGES_PER_DAY", 300),
            fb_settle_ms=_int("FB_SETTLE_MS", 4000),
            fb_rescan_hours=_int("FB_RESCAN_HOURS", 12),
            db_path=ROOT / os.getenv("DB_PATH", "data/gotani.db"),
            profiles_dir=ROOT / "profiles",
            exports_dir=ROOT / "exports",
            logs_dir=ROOT / "logs",
        )
        for d in (s.db_path.parent, s.profiles_dir, s.exports_dir, s.logs_dir):
            d.mkdir(parents=True, exist_ok=True)
        return s


settings = Settings.load()

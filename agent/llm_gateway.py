"""Gerbang tunggal ke LLM (PRD §9.1 "LLM Gateway").

Tanggung jawab:
1. Menolak prompt yang masih berisi nomor/email mentah (pengaman G9).
2. Budget cap harian: berhenti memanggil LLM kalau batas biaya/request tercapai.
3. Jeda minimum antar-panggilan supaya tidak kena limit free tier.
4. Mencatat token & perkiraan biaya setiap panggilan ke tabel llm_usage.

Provider saat ini: Google Gemini (library `google-genai`). Kalau nanti mau pindah ke OpenAI,
cukup tambah method baru di kelas ini; modul lain tidak perlu diubah.
"""
from __future__ import annotations

import json
import re
import sqlite3
import time
from datetime import date

from .config import settings
from .db import now_iso
from .masking import find_pii


class LLMUnavailable(Exception):
    """API key belum diisi."""


class BudgetExceeded(Exception):
    """Budget harian LLM habis."""


class UnmaskedDataError(Exception):
    """Prompt masih mengandung data pribadi mentah."""


class LLMGateway:
    _last_call: float = 0.0

    def __init__(self, conn: sqlite3.Connection, api_key: str | None = None, model: str | None = None):
        self.conn = conn
        self.api_key = (api_key or settings.gemini_api_key or "").strip()
        raw_model = model or settings.gemini_model or "gemini-2.5-flash"
        if "3.8" in raw_model or not raw_model.startswith("gemini-"):
            raw_model = "gemini-2.5-flash"
        self.model = raw_model
        self._client = None

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def usage_today(self) -> dict:
        today = date.today().isoformat()
        row = self.conn.execute(
            """SELECT COUNT(*) AS n, COALESCE(SUM(est_cost_usd), 0) AS cost,
                      COALESCE(SUM(input_tokens), 0) AS tin, COALESCE(SUM(output_tokens), 0) AS tout
               FROM llm_usage WHERE substr(ts, 1, 10) = ?""",
            (today,),
        ).fetchone()
        return {"requests": row["n"], "cost_usd": row["cost"], "input_tokens": row["tin"], "output_tokens": row["tout"]}

    def _client_get(self):
        if self._client is None:
            from google import genai
            from google.genai import types

            self._client = genai.Client(
                api_key=self.api_key,
                http_options=types.HttpOptions(timeout=15000),
            )
        return self._client

    def _log(self, purpose: str, tin: int, tout: int, ok: bool, error: str | None = None) -> None:
        cost = tin / 1e6 * settings.llm_price_input_per_m + tout / 1e6 * settings.llm_price_output_per_m
        self.conn.execute(
            """INSERT INTO llm_usage (ts, purpose, model, input_tokens, output_tokens, est_cost_usd, ok, error)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (now_iso(), purpose, self.model, tin, tout, cost, int(ok), error),
        )
        self.conn.commit()

    def generate_json(self, prompt: str, purpose: str, system: str | None = None):
        """Kirim prompt, minta jawaban JSON, kembalikan hasil yang sudah di-parse."""
        if not self.available:
            raise LLMUnavailable("GEMINI_API_KEY belum diisi")

        leaks = find_pii(prompt) + find_pii(system or "")
        if leaks:
            raise UnmaskedDataError(f"Prompt berisi {len(leaks)} data pribadi mentah; panggilan dibatalkan")

        usage = self.usage_today()
        if usage["requests"] >= settings.llm_max_requests_per_day:
            raise BudgetExceeded(f"Batas {settings.llm_max_requests_per_day} request/hari tercapai")
        if usage["cost_usd"] >= settings.llm_daily_budget_usd:
            raise BudgetExceeded(f"Budget harian ${settings.llm_daily_budget_usd:.2f} tercapai")

        wait = settings.llm_min_seconds_between_calls - (time.time() - LLMGateway._last_call)
        if wait > 0:
            time.sleep(wait)
        LLMGateway._last_call = time.time()

        from google.genai import types

        try:
            resp = self._client_get().models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system,
                    temperature=0.1,
                    response_mime_type="application/json",
                ),
            )
        except Exception as e:  # noqa: BLE001 - semua error API dicatat lalu dilempar ulang
            self._log(purpose, 0, 0, False, str(e)[:500])
            raise

        meta = getattr(resp, "usage_metadata", None)
        tin = int(getattr(meta, "prompt_token_count", 0) or 0)
        tout = int(getattr(meta, "candidates_token_count", 0) or 0)
        text = (resp.text or "").strip()
        text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            self._log(purpose, tin, tout, False, f"JSON tidak valid: {e}")
            raise
        self._log(purpose, tin, tout, True)
        return data

    def generate_text(self, prompt: str, purpose: str, system: str | None = None, temperature: float = 0.3) -> str:
        """Kirim prompt, minta jawaban teks bebas (cocok untuk percakapan sales), kembalikan teks bersih."""
        if not self.available:
            raise LLMUnavailable("GEMINI_API_KEY belum diisi")

        leaks = find_pii(prompt) + find_pii(system or "")
        if leaks:
            raise UnmaskedDataError(f"Prompt berisi {len(leaks)} data pribadi mentah; panggilan dibatalkan")

        usage = self.usage_today()
        if usage["requests"] >= settings.llm_max_requests_per_day:
            raise BudgetExceeded(f"Batas {settings.llm_max_requests_per_day} request/hari tercapai")
        if usage["cost_usd"] >= settings.llm_daily_budget_usd:
            raise BudgetExceeded(f"Budget harian ${settings.llm_daily_budget_usd:.2f} tercapai")

        wait = settings.llm_min_seconds_between_calls - (time.time() - LLMGateway._last_call)
        if wait > 0:
            time.sleep(wait)
        LLMGateway._last_call = time.time()

        from google.genai import types

        try:
            resp = self._client_get().models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system,
                    temperature=temperature,
                ),
            )
        except Exception as e:
            self._log(purpose, 0, 0, False, str(e)[:500])
            raise

        meta = getattr(resp, "usage_metadata", None)
        tin = int(getattr(meta, "prompt_token_count", 0) or 0)
        tout = int(getattr(meta, "candidates_token_count", 0) or 0)
        text = (resp.text or "").strip()
        self._log(purpose, tin, tout, True)
        return text

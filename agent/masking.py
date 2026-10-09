"""Masking data pribadi sebelum teks dikirim ke LLM (PRD F3.6 & G9).

Nomor HP dan email diambil LOKAL dengan regex, lalu diganti token seperti [PHONE_1].
LLM hanya melihat token. Nomor asli disimpan di `mapping` dan dipasang kembali secara lokal.
"""
from __future__ import annotations

import re

# Nomor HP Indonesia: 08xx / +62 8xx / 62 8xx, boleh dipisah spasi, titik, atau strip.
MOBILE_RE = re.compile(r"(?<![\d+])(?:\+?62|0)[\s.\-]?8\d{1,3}(?:[\s.\-]?\d{2,5}){2,3}(?!\d)")
# Telepon rumah/kantor: (0341) 123456, 031-1234567
LANDLINE_RE = re.compile(r"(?<!\d)\(?0[2-79]\d{1,2}\)?[\s.\-]?\d{5,8}(?!\d)")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
TOKEN_RE = re.compile(r"\[(PHONE|EMAIL)_\d+\]")


def _digits(s: str) -> str:
    return re.sub(r"\D", "", s)


def _valid_phone(raw: str) -> bool:
    n = len(_digits(raw))
    return 9 <= n <= 15


def mask_text(text: str, mapping: dict[str, str] | None = None) -> tuple[str, dict[str, str]]:
    """Ganti nomor telepon & email dengan token.

    `mapping` boleh diberikan supaya token konsisten di beberapa teks (misal satu batch).
    Nilai yang sama selalu mendapat token yang sama.
    """
    mapping = {} if mapping is None else mapping
    reverse = {v: k for k, v in mapping.items()}

    def token_for(kind: str, value: str) -> str:
        key = value if kind == "EMAIL" else _digits(value)
        if key in reverse:
            return reverse[key]
        n = sum(1 for t in mapping if t.startswith(f"[{kind}_")) + 1
        tok = f"[{kind}_{n}]"
        mapping[tok] = key
        reverse[key] = tok
        return tok

    out = EMAIL_RE.sub(lambda m: token_for("EMAIL", m.group(0).lower()), text or "")
    out = MOBILE_RE.sub(lambda m: token_for("PHONE", m.group(0)) if _valid_phone(m.group(0)) else m.group(0), out)
    out = LANDLINE_RE.sub(lambda m: token_for("PHONE", m.group(0)) if _valid_phone(m.group(0)) else m.group(0), out)
    return out, mapping


def find_pii(text: str) -> list[str]:
    """Cari sisa nomor/email yang belum ter-masking. Dipakai sebagai pengaman di LLM gateway."""
    leaks = [m.group(0) for m in EMAIL_RE.finditer(text or "")]
    leaks += [m.group(0) for m in MOBILE_RE.finditer(text or "") if _valid_phone(m.group(0))]
    leaks += [m.group(0) for m in LANDLINE_RE.finditer(text or "") if _valid_phone(m.group(0))]
    return leaks

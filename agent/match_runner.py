"""Orkestrator Matchmaking & Penyimpanan (PRD §7.6 / M2.3).

Menjalankan proses pencocokan semua listing demand terhadap supply yang tersedia,
menyimpan hasil match secara idempoten (tanpa duplikasi), dan menyediakan fungsi
kueri untuk dashboard serta pencatatan hasil deal (outcome).
"""
from __future__ import annotations

import hashlib
import sqlite3
from typing import Any

from .config import settings
from .db import dumps, loads, now_iso
from .matching import score_match
from .pooling import build_smart_pool


def _product_match(a: str, b: str) -> bool:
    """Cocokkan komoditas dengan substring dua arah (misal 'melon' cocok dengan 'melon madesta')."""
    if not a or not b:
        return False
    return a in b or b in a


def generate_match_signature(demand_id: int, supply_ids: list[int]) -> str:
    """Kunci unik idempoten berdasarkan ID demand dan daftar ID supply yang terurut."""
    sorted_ids = sorted(supply_ids)
    raw = f"{demand_id}:" + ",".join(str(i) for i in sorted_ids)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def run_all_matches(
    conn: sqlite3.Connection,
    include_pending_high_score: bool = True,
    margin_pct: float | None = None,
) -> dict[str, int]:
    """Jalankan proses matchmaking menyeluruh untuk semua listing demand.

    Mengembalikan statistik: {'total_demand': X, 'matches_created': Y, 'pools_created': Z}.
    """
    ts = now_iso()
    margin = margin_pct if margin_pct is not None else settings.match_margin_default_pct

    # 1. Ambil semua listing demand (kebutuhan pembeli)
    demand_rows = conn.execute(
        """SELECT * FROM listings 
           WHERE intent = 'demand' AND duplicate_of IS NULL 
           ORDER BY created_at DESC"""
    ).fetchall()

    # 2. Ambil semua listing supply (penawaran petani) yang memenuhi kriteria
    supply_query = "SELECT * FROM listings WHERE intent = 'supply' AND duplicate_of IS NULL"
    if include_pending_high_score:
        supply_query += f" AND (review_status = 'approved' OR (relevance >= {settings.relevance_min} AND confidence >= {settings.confidence_min}))"
    else:
        supply_query += " AND review_status = 'approved'"

    supply_rows = conn.execute(supply_query).fetchall()

    stats = {"total_demand": len(demand_rows), "matches_created": 0, "pools_created": 0}

    for d in demand_rows:
        d_dict = dict(d)
        d_id = d_dict["id"]
        d_prod = (d_dict.get("product") or "").lower().strip()
        d_vol = d_dict.get("volume_kg") or 0.0

        # Filter kandidat supply untuk komoditas yang sama
        candidate_supplies = [
            dict(s) for s in supply_rows 
            if _product_match((s["product"] or "").lower().strip(), d_prod)
        ]

        if not candidate_supplies:
            continue

        single_matched_ids = []
        has_full_coverage = False

        # 3. Match 1-ke-1
        for s_dict in candidate_supplies:
            s_id = s_dict["id"]
            res = score_match(d_dict, s_dict, margin_pct=margin)

            if res["score"] >= 1:  # Simpan semua match non-zero (termasuk tier ignored)
                single_matched_ids.append(s_id)
                sig = generate_match_signature(d_id, [s_id])
                s_vol = s_dict.get("volume_kg") or 0.0
                cov_pct = 100.0 if (d_vol <= 0 or s_vol >= d_vol) else round((s_vol / d_vol) * 100.0, 1)

                if cov_pct >= 100.0:
                    has_full_coverage = True

                # Simpan idempoten via signature
                cur = conn.execute(
                    """INSERT INTO matches (
                        demand_listing_id, kind, score, score_breakdown_json,
                        gaps_json, total_volume_kg, coverage_pct, est_margin_json,
                        tier, status, rule_version, signature, created_at, updated_at
                    ) VALUES (?, 'single', ?, ?, ?, ?, ?, ?, ?, 'open', ?, ?, ?, ?)
                    ON CONFLICT(signature) DO UPDATE SET
                        score = excluded.score,
                        score_breakdown_json = excluded.score_breakdown_json,
                        gaps_json = excluded.gaps_json,
                        tier = excluded.tier,
                        updated_at = excluded.updated_at
                    """,
                    (
                        d_id, res["score"], dumps(res["breakdown"]), dumps(res["gaps"]),
                        s_vol, cov_pct, dumps(res["est_margin"]), res["tier"],
                        res["rule_version"], sig, ts, ts
                    ),
                )
                match_id = cur.lastrowid
                if not match_id:
                    # Ambil id jika update
                    row_exist = conn.execute("SELECT id FROM matches WHERE signature = ?", (sig,)).fetchone()
                    match_id = row_exist["id"] if row_exist else None

                if match_id:
                    conn.execute(
                        """INSERT OR REPLACE INTO match_items (match_id, supply_listing_id, allocated_kg, distance_km)
                           VALUES (?, ?, ?, ?)""",
                        (match_id, s_id, min(s_vol, d_vol) if d_vol > 0 else s_vol, res.get("distance_km")),
                    )
                    stats["matches_created"] += 1

        # 4. Smart Pooling (jika ada kebutuhan volume dan belum ada supply tunggal yang cukup)
        if d_vol > 0 and len(candidate_supplies) >= 2:
            pool_res = build_smart_pool(d_dict, candidate_supplies, margin_pct=margin)
            if pool_res and pool_res["num_farmers"] >= 2:
                pool_supply_ids = [it["supply_id"] for it in pool_res["items"] if it.get("supply_id")]
                pool_sig = generate_match_signature(d_id, pool_supply_ids)

                cur_p = conn.execute(
                    """INSERT INTO matches (
                        demand_listing_id, kind, score, score_breakdown_json,
                        gaps_json, total_volume_kg, coverage_pct, est_margin_json,
                        tier, status, rule_version, signature, created_at, updated_at
                    ) VALUES (?, 'pool', ?, ?, ?, ?, ?, ?, ?, 'open', 'v1', ?, ?, ?)
                    ON CONFLICT(signature) DO UPDATE SET
                        score = excluded.score,
                        score_breakdown_json = excluded.score_breakdown_json,
                        gaps_json = excluded.gaps_json,
                        tier = excluded.tier,
                        updated_at = excluded.updated_at
                    """,
                    (
                        d_id, pool_res["score"], dumps({"disclaimer": pool_res["disclaimer"], "lines": pool_res["disclaimer_lines"]}),
                        dumps(pool_res["disclaimer_lines"]), pool_res["total_volume_kg"], pool_res["coverage_pct"],
                        dumps({"is_pool": True}), pool_res["tier"], pool_sig, ts, ts
                    ),
                )
                p_match_id = cur_p.lastrowid
                if not p_match_id:
                    row_p = conn.execute("SELECT id FROM matches WHERE signature = ?", (pool_sig,)).fetchone()
                    p_match_id = row_p["id"] if row_p else None

                if p_match_id:
                    for it in pool_res["items"]:
                        if it.get("supply_id"):
                            conn.execute(
                                """INSERT OR REPLACE INTO match_items (match_id, supply_listing_id, allocated_kg, distance_km)
                                   VALUES (?, ?, ?, ?)""",
                                (p_match_id, it["supply_id"], it["allocated_kg"], it.get("dist_to_anchor_km")),
                            )
                    stats["pools_created"] += 1

    conn.commit()
    return stats


def get_matches_for_display(conn: sqlite3.Connection, tier_filter: str | None = None) -> list[dict]:
    """Ambil data match lengkap beserta detail pembeli dan penjual untuk ditampilkan di UI."""
    query = """
        SELECT 
            m.id AS match_id,
            m.kind,
            m.score,
            m.tier,
            m.status,
            m.outcome,
            m.outcome_reason,
            m.total_volume_kg,
            m.coverage_pct,
            m.score_breakdown_json,
            m.gaps_json,
            m.est_margin_json,
            m.created_at AS matched_at,
            d.id AS demand_id,
            d.entity_name AS buyer_name,
            d.product,
            d.volume_kg AS buyer_vol,
            d.price_per_kg AS buyer_max_price,
            d.kabupaten AS buyer_location,
            d.available_date AS buyer_needed_date,
            d.contact_phone AS buyer_phone,
            d.contact_wa AS buyer_wa
        FROM matches m
        JOIN listings d ON m.demand_listing_id = d.id
    """
    params = []
    if tier_filter and tier_filter != "Semua":
        query += " WHERE m.tier = ?"
        params.append(tier_filter.lower())

    query += " ORDER BY m.score DESC, m.created_at DESC"

    rows = conn.execute(query, params).fetchall()
    results = []

    for r in rows:
        m_dict = dict(r)
        m_id = m_dict["match_id"]

        # Ambil daftar supply item untuk match ini
        items_rows = conn.execute(
            """SELECT 
                mi.allocated_kg,
                mi.distance_km,
                s.id AS supply_id,
                s.entity_name AS farmer_name,
                s.volume_kg AS farmer_vol,
                s.price_per_kg AS farmer_price,
                s.kabupaten AS farmer_location,
                s.available_date AS harvest_date,
                s.contact_phone AS farmer_phone,
                s.contact_wa AS farmer_wa
               FROM match_items mi
               JOIN listings s ON mi.supply_listing_id = s.id
               WHERE mi.match_id = ?
            """,
            (m_id,),
        ).fetchall()

        m_dict["items"] = [dict(it) for it in items_rows]
        m_dict["breakdown"] = loads(m_dict.get("score_breakdown_json"), {})
        m_dict["gaps"] = loads(m_dict.get("gaps_json"), [])
        m_dict["margin"] = loads(m_dict.get("est_margin_json"), {})
        results.append(m_dict)

    return results


def update_match_outcome(conn: sqlite3.Connection, match_id: int, outcome: str, reason: str | None = None) -> bool:
    """Catat hasil transaksi match (deal / no_deal) dan alasannya (PRD F6.6)."""
    cur = conn.execute(
        """UPDATE matches 
           SET outcome = ?, outcome_reason = ?, status = 'closed', updated_at = ?
           WHERE id = ?""",
        (outcome, reason, now_iso(), match_id),
    )
    conn.commit()
    return cur.rowcount > 0


def update_match_status(conn: sqlite3.Connection, match_id: int, status: str) -> bool:
    """Perbarui status match (open, confirmed, dismissed)."""
    cur = conn.execute(
        "UPDATE matches SET status = ?, updated_at = ? WHERE id = ?",
        (status, now_iso(), match_id),
    )
    conn.commit()
    return cur.rowcount > 0

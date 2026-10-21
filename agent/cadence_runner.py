"""CLI Runner & Scheduled Task untuk Cadence Follow-Up Sales (PRD §7.8 / F8.5–F8.6).

Skrip ini bertugas memeriksa percakapan yang jatuh tempo, menyusun pesan follow-up santun,
dan memperbarui status percakapan secara otomatis (H+3, H+7, hingga auto-closed_lost).
Dapat dijalankan secara terjadwal (misal setiap hari jam 09.00 WIB) via cron atau Task Scheduler.

Penggunaan:
    python -m agent.cadence_runner --dry-run
    python -m agent.cadence_runner
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import db
from .cadence import get_due_followups, generate_followup_message, advance_followup
from .compliance import is_within_operating_hours


def run_cadence_check(
    conn: sqlite3.Connection,
    now_dt: datetime | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Pindai percakapan jatuh tempo dan lakukan proses cadence follow-up."""
    now_check = now_dt or datetime.now(timezone.utc).astimezone()

    if not is_within_operating_hours(now_check):
        return {
            "status": "outside_operating_hours",
            "message": "Di luar jam kerja operasional yang sopan (07.00 - 20.00 WIB). Pengecekan dibatalkan.",
            "processed_count": 0,
            "dry_run": dry_run,
            "items": [],
        }

    due_list = get_due_followups(conn, now_dt=now_check)
    processed_items = []

    for row in due_list:
        r_dict = dict(row)
        c_id = r_dict["id"]
        c_name = r_dict.get("contact_name") or "Tanpa Nama"
        c_phone = r_dict["contact_phone"]
        fu_count = r_dict["followup_count"]

        # Susun pesan follow-up
        fu_message = generate_followup_message(conn, c_id)

        item_result = {
            "conversation_id": c_id,
            "contact_name": c_name,
            "contact_phone": c_phone,
            "previous_count": fu_count,
            "generated_message": fu_message,
        }

        if not dry_run:
            # 1. Simpan pesan follow-up ke message ledger
            db.add_message(
                conn,
                conversation_id=c_id,
                direction="outbound",
                sender_type="ai",
                content=fu_message,
                delivery_status="sent",
            )
            # 2. Majukan tahapan follow-up (ke followup_1, followup_2, atau closed_lost)
            action_taken = advance_followup(conn, c_id)
            item_result["action_taken"] = action_taken
            conn.commit()
        else:
            item_result["action_taken"] = "simulated_advance"

        processed_items.append(item_result)

    return {
        "status": "success",
        "processed_count": len(processed_items),
        "dry_run": dry_run,
        "items": processed_items,
    }


def main():
    parser = argparse.ArgumentParser(description="GoTani Cadence Follow-Up Runner")
    parser.add_argument(
        "--db",
        type=str,
        default="data/gotani.db",
        help="Jalur file SQLite database (default: data/gotani.db)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulasi pengecekan tanpa mengubah status di database",
    )
    args = parser.parse_args()

    db_file = Path(args.db)
    if not db_file.exists():
        print(f"[ERROR] Database file '{db_file}' tidak ditemukan.")
        sys.exit(1)

    conn = db.get_connection(db_file)
    print(f"[CADENCE] Memulai pengecekan follow-up... (dry_run={args.dry_run})")
    res = run_cadence_check(conn, dry_run=args.dry_run)

    print(json.dumps(res, indent=2, ensure_ascii=False))
    print(f"[CADENCE] Selesai: {res['processed_count']} percakapan diproses.")
    conn.close()


if __name__ == "__main__":
    main()

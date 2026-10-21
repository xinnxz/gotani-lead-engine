"""Modul Sales Agent, Konteks Memori & Generator Komunikasi Cerdas (PRD §7.8).

Tanggung Jawab:
1. Penyusunan pesan pembuka dipersonalisasi dengan bukti asal informasi (F8.4).
2. Penyusunan draf balasan percakapan kontekstual berdasarkan riwayat messages (F8.4).
3. Transparansi persona AI: jujur saat ditanya dan sopan agribisnis (F8.3).
4. Pembaruan ringkasan konteks percakapan untuk handover ke staf sales.
"""
from __future__ import annotations

import sqlite3
from typing import Any

from . import db
from .outreach import (
    draft_farmer_outreach_for_lead,
    draft_farmer_outreach_for_match,
    draft_buyer_outreach_for_match,
    _clean_str,
)


SALES_SYSTEM_PROMPT = """Kamu adalah tim kemitraan resmi dari GoTani, platform penghubung hasil panen petani langsung ke distributor dan pasar induk di Indonesia.
Gaya komunikasi kamu:
- Sopan, santun, profesional, dan akrab khas hubungan agribisnis Indonesia (gunakan sapaan Pak/Bu).
- Transparan: sebutkan asal usul informasi (misal dari postingan di grup komunitas).
- Tanpa simbol/emoji yang berlebihan. Hindari bahasa robot yang kaku.
- Jika ditanya apakah kamu bot/AI, JAWAB DENGAN JUJUR bahwa kamu adalah asisten digital GoTani, dan tawarkan apakah lawan bicara ingin disambungkan ke staf manusia GoTani.
- Jangan mengarang data kuantitas atau harga yang tidak ada di konteks. Jika tidak tahu, tanyakan dengan sopan.
- Balas HANYA dengan teks pesan WhatsApp yang siap dikirim."""


def generate_initial_outreach(
    conn: sqlite3.Connection,
    listing_id: int,
    match_id: int | None = None,
    gateway: Any | None = None,
) -> str:
    """Susun pesan pembuka pertama ke petani atau pembeli."""
    listing = conn.execute("SELECT * FROM listings WHERE id = ?", (listing_id,)).fetchone()
    if not listing:
        return "Halo, salam kenal dari tim kemitraan GoTani."

    l_dict = dict(listing)
    intent = l_dict.get("intent", "supply")
    product = l_dict.get("product") or "hasil panen"
    entity = _clean_str(l_dict.get("entity_name"))
    location = _clean_str(l_dict.get("location_text") or l_dict.get("kabupaten"))
    vol_kg = l_dict.get("volume_kg")
    price_kg = l_dict.get("price_per_kg")

    # Jika terkait dengan match (rekomendasi pasangan)
    if match_id:
        match_row = conn.execute(
            """SELECT m.*, d.entity_name AS buyer_name, d.kabupaten AS buyer_loc, d.volume_kg AS buyer_vol
               FROM matches m
               JOIN listings d ON m.demand_listing_id = d.id
               WHERE m.id = ?""",
            (match_id,),
        ).fetchone()

        if match_row:
            m_dict = dict(match_row)
            if intent == "supply":
                return draft_farmer_outreach_for_match(
                    farmer_name=entity,
                    commodity=product,
                    farmer_location=location,
                    buyer_name=m_dict.get("buyer_name"),
                    buyer_location=m_dict.get("buyer_loc"),
                    needed_vol_kg=m_dict.get("buyer_vol"),
                    farmer_price=price_kg,
                )
            else:
                return draft_buyer_outreach_for_match(
                    buyer_name=entity,
                    commodity=product,
                    buyer_location=location,
                    needed_vol_kg=vol_kg or 0.0,
                    suggested_price=price_kg,
                    is_pool=(m_dict.get("kind") == "pool"),
                )

    # Outreach umum berbasis listing
    return draft_farmer_outreach_for_lead(
        farmer_name=entity,
        commodity=product,
        farmer_location=location,
        volume_kg=vol_kg,
        price_per_kg=price_kg,
    )


def generate_conversational_reply(
    conn: sqlite3.Connection,
    conversation_id: int,
    inbound_text: str,
    gateway: Any | None = None,
) -> str:
    """Susun draf balasan percakapan berbasis riwayat pesan dan konteks lead."""
    conv = db.get_conversation(conn, conversation_id)
    if not conv:
        return "Halo, terima kasih telah membalas pesan dari GoTani. Ada yang bisa kami bantu?"

    messages = db.get_messages(conn, conversation_id)
    listing = conn.execute("SELECT * FROM listings WHERE id = ?", (conv["listing_id"],)).fetchone()
    l_dict = dict(listing) if listing else {}

    c_name = _clean_str(conv["contact_name"]) or "Bapak/Ibu"
    prod = l_dict.get("product", "komoditas")
    vol = l_dict.get("volume_kg")
    vol_str = f" sekitar {vol:g} kg" if vol else ""

    # 1. Jika terhubung dengan LLM Gateway (Gemini)
    if gateway and getattr(gateway, "available", False):
        try:
            # Susun thread riwayat obrolan
            history_lines = []
            for m in messages[-6:]:  # Ambil maksimal 6 pesan terakhir untuk efisiensi
                sender = "GoTani" if m["direction"] == "outbound" else c_name
                history_lines.append(f"{sender}: {m['content']}")

            prompt = f"""Konteks Lead:
- Nama: {c_name} ({conv['role']})
- Komoditas: {prod}{vol_str}
- Lokasi: {l_dict.get('location_text') or '-'}
- Ringkasan Sebelumnya: {conv.get('summary_text') or 'Belum ada'}

Riwayat Obrolan:
{chr(10).join(history_lines)}
{c_name}: {inbound_text}

Tugas: Buat draf balasan WhatsApp yang relevan, sopan, dan langsung menjawab pertanyaan di atas."""

            reply_json = gateway.generate_json(
                prompt=prompt,
                purpose="sales_reply",
                system=SALES_SYSTEM_PROMPT + '\nBalas dengan JSON: {"reply": "isi balasan"}',
            )
            if isinstance(reply_json, dict) and reply_json.get("reply"):
                return reply_json["reply"].strip()
        except Exception:
            pass  # Fallback ke template lokal

    # 2. Respon Template Heuristik Cerdas (Offline Fallback)
    inbound_low = inbound_text.lower()

    if any(q in inbound_low for q in ["bot", "robot", "ai", "mesin"]):
        return (
            f"Halo Pak/Bu {c_name}, perkenalkan saya asisten digital dari tim kemitraan GoTani. "
            "Pesan kami dibantu sistem otomatis untuk mendata ketersediaan pasokan secara cepat. "
            "Jika Bapak/Ibu berkenan berdiskusi langsung dengan tim operasional manusia kami, "
            "saya dapat segera menyambungkan nomor ini ke staf kemitraan kami. Terima kasih."
        )

    if any(q in inbound_low for q in ["dimana", "lokasi", "alamat", "kantor"]):
        return (
            f"Baik Pak/Bu {c_name}, tim GoTani beroperasi menghubungkan hasil panen daerah Jawa Timur "
            "langsung ke distributor sentra. Untuk titik pengiriman atau gudang penampungan akan kami sesuaikan "
            "dengan rute pengiriman mitra terdekat. Apakah stok {prod} saat ini posisinya siap angkut di kebun?"
        )

    return (
        f"Terima kasih atas informasinya Pak/Bu {c_name}. Kami telah mencatat ketersediaan pasokan {prod} tersebut. "
        "Tim kemitraan GoTani akan segera memeriksa kecocokan kuota dan rute pengiriman untuk tindak lanjut kerja sama ini."
    )


def summarize_conversation(
    conn: sqlite3.Connection,
    conversation_id: int,
    gateway: Any | None = None,
) -> str:
    """Buat ringkasan 1-2 kalimat status percakapan untuk catatan handover."""
    messages = db.get_messages(conn, conversation_id)
    if not messages:
        return "Belum ada interaksi pesan."

    last_msg = messages[-1]["content"]
    summary = f"Interaksi terakhir ({len(messages)} pesan): '{last_msg[:80]}...'"
    db.update_conversation(conn, conversation_id, summary_text=summary)
    return summary

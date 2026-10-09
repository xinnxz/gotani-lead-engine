-- Skema database GoTani Lead Agent (Fase 1 / M1)
-- Mengacu PRD §8. Kolom JSON disimpan sebagai TEXT supaya skema tetap fleksibel.

-- Kampanye: satu "surat tugas" pencarian lead (Campaign Spec)
CREATE TABLE IF NOT EXISTS campaigns (
    id          TEXT PRIMARY KEY,
    goal        TEXT NOT NULL,               -- find_supply | find_demand | find_customers
    spec_json   TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'draft',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

-- Setiap kali agent dijalankan (discover / read / fetch / import)
CREATE TABLE IF NOT EXISTS runs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id  TEXT,
    kind         TEXT NOT NULL,
    platform     TEXT,
    account      TEXT,
    started_at   TEXT NOT NULL,
    finished_at  TEXT,
    status       TEXT NOT NULL DEFAULT 'running',  -- running | done | handoff | error | limited
    items_found  INTEGER NOT NULL DEFAULT 0,
    error        TEXT
);

-- Registry sumber yang "belajar" (F2.1e): grup FB, website, dst.
CREATE TABLE IF NOT EXISTS source_registry (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    platform         TEXT NOT NULL,
    url              TEXT NOT NULL UNIQUE,
    name             TEXT,
    source_type      TEXT,                   -- group | website | page
    commodity        TEXT,
    region           TEXT,
    found_by_query   TEXT,
    score            REAL NOT NULL DEFAULT 0,
    score_reason     TEXT,
    access_status    TEXT NOT NULL DEFAULT 'unknown',  -- public | private | pending_join | denied | unknown
    members          INTEGER,
    activity_text    TEXT,
    posts_scanned    INTEGER NOT NULL DEFAULT 0,
    valid_leads      INTEGER NOT NULL DEFAULT 0,
    last_scanned_at  TEXT,
    discovered_at    TEXT NOT NULL
);

-- Item mentah + bukti sumber (F2.6)
CREATE TABLE IF NOT EXISTS raw_items (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id        INTEGER,
    campaign_id   TEXT NOT NULL,
    source_id     INTEGER,
    platform      TEXT NOT NULL,             -- facebook | web | manual | sample
    url           TEXT,
    fetched_at    TEXT NOT NULL,
    posted_at     TEXT,
    author_name   TEXT,
    author_url    TEXT,
    raw_text      TEXT NOT NULL,
    content_hash  TEXT NOT NULL,
    processed     INTEGER NOT NULL DEFAULT 0,
    intent        TEXT,                      -- hasil klasifikasi (F2.7)
    UNIQUE (campaign_id, content_hash)
);

-- Listing hasil ekstraksi (penawaran / permintaan)
CREATE TABLE IF NOT EXISTS listings (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id         TEXT NOT NULL,
    raw_item_id         INTEGER NOT NULL,
    intent              TEXT NOT NULL,       -- supply | demand
    entity_name         TEXT,
    product             TEXT,
    attributes_json     TEXT,
    volume_kg           REAL,
    price_per_kg        REAL,
    location_text       TEXT,
    kabupaten           TEXT,
    provinsi            TEXT,
    kode_wilayah        TEXT,
    available_text      TEXT,
    available_date      TEXT,
    contact_wa          TEXT,
    contact_phone       TEXT,
    contact_email       TEXT,
    contact_profile     TEXT,
    evidence_json       TEXT,
    flags_json          TEXT,
    relevance           INTEGER,
    confidence          INTEGER,
    score_reasons_json  TEXT,
    duplicate_of        INTEGER,
    source_urls_json    TEXT,
    review_status       TEXT NOT NULL DEFAULT 'pending',  -- pending | approved | rejected
    review_note         TEXT,
    reviewed_at         TEXT,
    extractor           TEXT,                -- llm | rules
    created_at          TEXT NOT NULL
);

-- Log pemakaian & biaya LLM (budget cap, §9.2)
CREATE TABLE IF NOT EXISTS llm_usage (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    ts             TEXT NOT NULL,
    purpose        TEXT,
    model          TEXT,
    input_tokens   INTEGER NOT NULL DEFAULT 0,
    output_tokens  INTEGER NOT NULL DEFAULT 0,
    est_cost_usd   REAL NOT NULL DEFAULT 0,
    ok             INTEGER NOT NULL DEFAULT 1,
    error          TEXT
);

-- Antrean handoff ke manusia (F2.3)
CREATE TABLE IF NOT EXISTS handoffs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ts           TEXT NOT NULL,
    campaign_id  TEXT,
    platform     TEXT,
    account      TEXT,
    kind         TEXT NOT NULL,              -- checkpoint | login | captcha | join_group | limited
    detail       TEXT,
    url          TEXT,
    status       TEXT NOT NULL DEFAULT 'open'
);

-- Status & kuota akun per hari (F2.4)
CREATE TABLE IF NOT EXISTS account_state (
    account       TEXT PRIMARY KEY,
    platform      TEXT NOT NULL,
    paused_until  TEXT,
    pause_reason  TEXT,
    usage_date    TEXT,
    pages_today   INTEGER NOT NULL DEFAULT 0
);

-- Audit log setiap aksi agent (observabilitas, §11)
CREATE TABLE IF NOT EXISTS events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ts           TEXT NOT NULL,
    level        TEXT NOT NULL,
    campaign_id  TEXT,
    message      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_raw_campaign ON raw_items (campaign_id, processed);
CREATE INDEX IF NOT EXISTS idx_listing_campaign ON listings (campaign_id);
CREATE INDEX IF NOT EXISTS idx_source_platform ON source_registry (platform, commodity);

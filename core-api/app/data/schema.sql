-- Catalog and business transactions (mock fixtures, seeded at startup)
CREATE TABLE IF NOT EXISTS clients (
    client_id     TEXT PRIMARY KEY,          -- 4-11 digits, already validated by the API
    full_name     TEXT NOT NULL,
    phone         TEXT NOT NULL,
    email         TEXT NOT NULL,
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS products (
    id TEXT PRIMARY KEY, category TEXT, name TEXT, brand TEXT,
    price INTEGER, specs TEXT, stock INTEGER,
    warranty_months INTEGER NOT NULL DEFAULT 12   -- coverage every sale of this product carries
);

CREATE TABLE IF NOT EXISTS orders (
    order_id TEXT PRIMARY KEY, client_id TEXT, status TEXT,                    -- fixed vocabulary, see app/schemas/orders.py
    estimated_delivery_date TEXT, delivery_address TEXT, products TEXT,        -- JSON
    FOREIGN KEY (client_id) REFERENCES clients (client_id)
);

CREATE TABLE IF NOT EXISTS warranties (
    warranty_id TEXT PRIMARY KEY, order_id TEXT, product_id TEXT,
    coverage_months INTEGER, purchase_date TEXT
);

CREATE TABLE IF NOT EXISTS warranty_claims (
    claim_id TEXT PRIMARY KEY, warranty_id TEXT, client_id TEXT,
    description TEXT, ticket_id TEXT, escalated INTEGER, created_at TEXT
);

CREATE TABLE IF NOT EXISTS escalations (        -- support tickets, see app/schemas/escalations.py
    ticket_id TEXT PRIMARY KEY, session_id TEXT, client_id TEXT,
    reason TEXT, priority TEXT, status TEXT, created_at TEXT,
    origin TEXT NOT NULL DEFAULT 'agent_request',  -- 'agent_request' | 'warranty_claim' | 'safety_risk'
    assignee TEXT, resolution_note TEXT, updated_at TEXT,
    related_ticket_id TEXT                         -- the ticket this one is a follow-up of
);

-- The one customer an authenticated end user of the chat frontend is allowed to act as
CREATE TABLE IF NOT EXISTS identity_bindings (
    subject_id TEXT PRIMARY KEY,               -- value of the X-End-User-Id header
    client_id  TEXT NOT NULL,
    bound_at   TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Memory: current session state plus cross-session history per client

CREATE TABLE IF NOT EXISTS sessions (
    session_id           TEXT PRIMARY KEY,   -- session_id derived in the n8n Webhook
    client_id            TEXT,               -- NULL until the client identifies in this session
    client_name          TEXT,
    mentioned_budgets    TEXT,               -- JSON array, chronological; the last one is current
    last_order_checked   TEXT,
    products_viewed      TEXT,               -- JSON array of ids, this session only
    preferences          TEXT,               -- JSON array of strings, this session only
    started_at           TEXT NOT NULL DEFAULT (datetime('now')),
    last_activity_at     TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (client_id) REFERENCES clients (client_id)
);

CREATE TABLE IF NOT EXISTS client_memory (
    client_id            TEXT PRIMARY KEY,  -- aggregate, lives as long as the client exists
    client_name          TEXT,
    mentioned_budgets    TEXT,              -- JSON array, ACCUMULATED cross-session; the last one is current
    last_order_checked   TEXT,
    products_viewed      TEXT,              -- JSON array, ACCUMULATED across sessions
    preferences          TEXT,              -- JSON array, ACCUMULATED across sessions
    last_session_id      TEXT,
    updated_at           TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (client_id) REFERENCES clients (client_id)
);

CREATE TABLE IF NOT EXISTS interactions (             -- append-only audit log of facts per session
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id   TEXT NOT NULL,
    client_id    TEXT,                          -- filled in once known
    type         TEXT NOT NULL,                 -- 'tool_call' | 'preference' | 'budget' | 'note'
    detail       TEXT NOT NULL,                 -- JSON of the fact, e.g. {"tool":"get_catalog","params":{...}}
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (session_id) REFERENCES sessions (session_id)
);

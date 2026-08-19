-- FMLV automated data flow: run store schema.
--
-- Applied idempotently (CREATE TABLE IF NOT EXISTS) on every connect — see db.py.
-- Table purposes are described in DESIGN.md §7. Only `run` has behaviour built on
-- top of it yet (runs.py, Phase 2); the rest are scaffolding for later phases and
-- may still change shape.

CREATE TABLE IF NOT EXISTS run (
    id INTEGER PRIMARY KEY,
    manufacturer_id INTEGER NOT NULL,
    fmlv_manufacturer TEXT NOT NULL,
    trigger TEXT NOT NULL CHECK (trigger IN ('manual', 'scheduled')),
    status TEXT NOT NULL CHECK (status IN ('running', 'succeeded', 'failed')) DEFAULT 'running',
    started_at TEXT NOT NULL,
    finished_at TEXT,
    error_message TEXT,
    range_label TEXT
);

CREATE INDEX IF NOT EXISTS idx_run_manufacturer ON run (manufacturer_id, started_at);

CREATE TABLE IF NOT EXISTS source_snapshot (
    id INTEGER PRIMARY KEY,
    run_id INTEGER NOT NULL REFERENCES run (id),
    url TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    file_path TEXT NOT NULL,
    content_type TEXT,
    status_code INTEGER
);

CREATE INDEX IF NOT EXISTS idx_source_snapshot_run ON source_snapshot (run_id);
CREATE INDEX IF NOT EXISTS idx_source_snapshot_url_hash ON source_snapshot (url, content_hash);

-- One row per product we know about, matched across runs by manufacturer + range +
-- model until the NCC has assigned a product_id. See DESIGN.md §4.1 (product_id is
-- NCC-assigned) and TODO.md Phase 5 (the matching logic itself).
CREATE TABLE IF NOT EXISTS product (
    id INTEGER PRIMARY KEY,
    manufacturer_id INTEGER NOT NULL,
    fmlv_product_id INTEGER,
    manufacturer_range TEXT,
    model TEXT,
    first_seen_run_id INTEGER REFERENCES run (id),
    last_seen_run_id INTEGER REFERENCES run (id),
    UNIQUE (manufacturer_id, manufacturer_range, model)
);

CREATE INDEX IF NOT EXISTS idx_product_fmlv_id ON product (fmlv_product_id);

CREATE TABLE IF NOT EXISTS proposed_change (
    id INTEGER PRIMARY KEY,
    run_id INTEGER NOT NULL REFERENCES run (id),
    product_id INTEGER NOT NULL REFERENCES product (id),
    field TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    source_url TEXT,
    source_snippet TEXT,
    confidence REAL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_proposed_change_run ON proposed_change (run_id);
CREATE INDEX IF NOT EXISTS idx_proposed_change_product ON proposed_change (product_id);

CREATE TABLE IF NOT EXISTS decision (
    id INTEGER PRIMARY KEY,
    proposed_change_id INTEGER NOT NULL REFERENCES proposed_change (id),
    action TEXT NOT NULL CHECK (action IN ('accept', 'reject', 'correct', 'undo')),
    corrected_value TEXT,
    decided_by TEXT,
    decided_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_decision_proposed_change ON decision (proposed_change_id);

-- "Checked, unchanged" confirmations — see DESIGN.md §6.5.
CREATE TABLE IF NOT EXISTS verification (
    id INTEGER PRIMARY KEY,
    run_id INTEGER NOT NULL REFERENCES run (id),
    product_id INTEGER NOT NULL REFERENCES product (id),
    field TEXT NOT NULL,
    verified_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_verification_product ON verification (product_id);

-- A baseline product not found on the manufacturer's site during a run
-- (`ChangeKind.DISAPPEARED`). Deliberately not a `proposed_change`: there is no CSV
-- field to change, so there's nothing to accept/reject — this is purely a note for a
-- reviewer to go and consider manually deactivating the product on the FMLV Nova site.
CREATE TABLE IF NOT EXISTS disappearance_notice (
    id INTEGER PRIMARY KEY,
    run_id INTEGER NOT NULL REFERENCES run (id),
    product_id INTEGER NOT NULL REFERENCES product (id),
    note TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_disappearance_notice_run ON disappearance_notice (run_id);
CREATE INDEX IF NOT EXISTS idx_disappearance_notice_product ON disappearance_notice (product_id);

-- HAT-ORBITAL Ledger Schema v2.0 (M9)
-- Reducido de 7 tablas a 3:
--   - hat_facts           : hechos confirmados (θ=0 en OVC)
--   - hat_hypotheses      : creencias no verificadas (θ=π/4 en OVC)
--   - hat_progress        : historial de despachos + intent_hash + ttl_expires_at
--                           (reemplaza hat_dispatch_registry)

-- ============================================================
-- hat_facts
-- ============================================================
CREATE TABLE IF NOT EXISTS hat_facts (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id             TEXT NOT NULL,
    session_id          TEXT NOT NULL,
    fact_key            TEXT NOT NULL,
    fact_value          TEXT NOT NULL,        -- JSON
    confidence          REAL DEFAULT 1.0,
    orbital_theta       REAL DEFAULT 0.0,
    orbital_amplitude   REAL DEFAULT 1.0,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, session_id, fact_key)
);
CREATE INDEX IF NOT EXISTS idx_facts_user_session ON hat_facts(user_id, session_id);

-- ============================================================
-- hat_hypotheses
-- ============================================================
CREATE TABLE IF NOT EXISTS hat_hypotheses (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id             TEXT NOT NULL,
    session_id          TEXT NOT NULL,
    hypothesis_key      TEXT NOT NULL,
    hypothesis_value    TEXT NOT NULL,
    confidence          REAL DEFAULT 0.5,
    orbital_theta       REAL DEFAULT 0.785,   -- π/4 = menor confianza que Fact
    orbital_amplitude   REAL DEFAULT 0.5,
    verified            BOOLEAN DEFAULT 0,
    verified_at         TIMESTAMP,
    promoted_to_fact    BOOLEAN DEFAULT 0,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, session_id, hypothesis_key)
);
CREATE INDEX IF NOT EXISTS idx_hyp_user_session ON hat_hypotheses(user_id, session_id);

-- ============================================================
-- hat_progress (ampliada — reemplaza hat_dispatch_registry)
-- ============================================================
CREATE TABLE IF NOT EXISTS hat_progress (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id             TEXT NOT NULL,
    session_id          TEXT NOT NULL,
    dispatch_id         TEXT NOT NULL UNIQUE,
    domain              TEXT NOT NULL,
    specialist          TEXT,
    worker              TEXT,
    status              TEXT NOT NULL,           -- dispatched|running|completed|failed
    result_summary      TEXT,                    -- JSON con output resumido
    orbital_resonance   REAL,
    intent_hash         TEXT,                    -- M9: sha256 del intent (reemplaza hat_dispatch_registry)
    ttl_expires_at      TIMESTAMP,               -- M9: para anti-dup TTL freshness
    subscriber_count    INTEGER DEFAULT 0,       -- M9: para anti-dup idempotency layer
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at        TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_progress_user_session ON hat_progress(user_id, session_id);
CREATE INDEX IF NOT EXISTS idx_progress_hash ON hat_progress(intent_hash);
CREATE INDEX IF NOT EXISTS idx_progress_status ON hat_progress(status);
CREATE INDEX IF NOT EXISTS idx_progress_ttl ON hat_progress(ttl_expires_at);

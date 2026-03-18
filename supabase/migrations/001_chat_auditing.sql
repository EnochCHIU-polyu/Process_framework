-- =============================================================================
-- PROCESS Chat Auditing — Supabase SQL Migration
-- Run this in your Supabase SQL editor (or via psql / Supabase CLI).
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. chat_sessions
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS chat_sessions (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     TEXT,
    room_id     TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_chat_sessions_user_id   ON chat_sessions (user_id);
CREATE INDEX IF NOT EXISTS idx_chat_sessions_room_id   ON chat_sessions (room_id);
CREATE INDEX IF NOT EXISTS idx_chat_sessions_created_at ON chat_sessions (created_at DESC);

-- ---------------------------------------------------------------------------
-- 2. chat_messages
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS chat_messages (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id  UUID NOT NULL REFERENCES chat_sessions (id) ON DELETE CASCADE,
    role        TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content     TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_session_id  ON chat_messages (session_id);
CREATE INDEX IF NOT EXISTS idx_chat_messages_created_at  ON chat_messages (created_at DESC);

-- ---------------------------------------------------------------------------
-- 3. ai_audits
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ai_audits (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    message_id  UUID NOT NULL REFERENCES chat_messages (id) ON DELETE CASCADE,
    session_id  UUID NOT NULL REFERENCES chat_sessions (id) ON DELETE CASCADE,
    status      TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'suspected_hallucination', 'reviewed')),
    verdict     TEXT CHECK (verdict IN ('ok', 'bad_case', NULL)),
    bad_case_id UUID,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ai_audits_message_id  ON ai_audits (message_id);
CREATE INDEX IF NOT EXISTS idx_ai_audits_session_id  ON ai_audits (session_id);
CREATE INDEX IF NOT EXISTS idx_ai_audits_status      ON ai_audits (status);
CREATE INDEX IF NOT EXISTS idx_ai_audits_created_at  ON ai_audits (created_at DESC);

-- ---------------------------------------------------------------------------
-- 4. bad_cases
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS bad_cases (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    message_id       UUID NOT NULL REFERENCES chat_messages (id) ON DELETE CASCADE,
    session_id       UUID NOT NULL REFERENCES chat_sessions (id) ON DELETE CASCADE,
    reason           TEXT NOT NULL,
    category         TEXT NOT NULL DEFAULT 'hallucination'
                         CHECK (category IN (
                             'hallucination', 'intent_understanding', 'user_experience',
                             'factual', 'logical', 'referential'
                         )),
    notes            TEXT,
    reviewer         TEXT,
    root_cause       TEXT,
    expected_output  TEXT,
    actual_output    TEXT,
    ignored_keywords JSONB NOT NULL DEFAULT '[]'::JSONB,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_bad_cases_message_id  ON bad_cases (message_id);
CREATE INDEX IF NOT EXISTS idx_bad_cases_session_id  ON bad_cases (session_id);
CREATE INDEX IF NOT EXISTS idx_bad_cases_category    ON bad_cases (category);
CREATE INDEX IF NOT EXISTS idx_bad_cases_created_at  ON bad_cases (created_at DESC);

-- Add FK from ai_audits.bad_case_id → bad_cases.id.
-- NOT VALID skips the scan of existing rows (tables are new, so this is safe)
-- and avoids a circular dependency at creation time.
-- Run `ALTER TABLE ai_audits VALIDATE CONSTRAINT fk_ai_audits_bad_case_id;`
-- after an initial data load if you want to enforce integrity on historical rows.
ALTER TABLE ai_audits
    ADD CONSTRAINT fk_ai_audits_bad_case_id
    FOREIGN KEY (bad_case_id) REFERENCES bad_cases (id) ON DELETE SET NULL
    NOT VALID;

-- ---------------------------------------------------------------------------
-- 5. process_reports
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS process_reports (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id  UUID NOT NULL REFERENCES chat_sessions (id) ON DELETE CASCADE,
    report      JSONB NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_process_reports_session_id ON process_reports (session_id);
CREATE INDEX IF NOT EXISTS idx_process_reports_created_at ON process_reports (created_at DESC);

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
    report_context JSONB NOT NULL DEFAULT '{}'::JSONB,
    analysis_label TEXT,
    analysis_summary TEXT,
    triaged_at TIMESTAMPTZ,
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
-- Conditionally add to handle re-runs of this migration
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints 
        WHERE constraint_name = 'fk_ai_audits_bad_case_id'
        AND table_name = 'ai_audits'
    ) THEN
        ALTER TABLE ai_audits
            ADD CONSTRAINT fk_ai_audits_bad_case_id
            FOREIGN KEY (bad_case_id) REFERENCES bad_cases (id) ON DELETE SET NULL;
    END IF;
END $$;

-- Ensure newer triage columns exist for already-deployed databases
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'ai_audits' AND column_name = 'report_context'
    ) THEN
        ALTER TABLE ai_audits
            ADD COLUMN report_context JSONB NOT NULL DEFAULT '{}'::JSONB;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'ai_audits' AND column_name = 'analysis_label'
    ) THEN
        ALTER TABLE ai_audits
            ADD COLUMN analysis_label TEXT;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'ai_audits' AND column_name = 'analysis_summary'
    ) THEN
        ALTER TABLE ai_audits
            ADD COLUMN analysis_summary TEXT;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'ai_audits' AND column_name = 'triaged_at'
    ) THEN
        ALTER TABLE ai_audits
            ADD COLUMN triaged_at TIMESTAMPTZ;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_ai_audits_analysis_label ON ai_audits (analysis_label);

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

-- ---------------------------------------------------------------------------
-- 6. learned_patterns — Clustered, deduplicated pattern knowledge base
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS learned_patterns (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    category            TEXT NOT NULL DEFAULT 'user_experience'
                        CHECK (category IN (
                            'hallucination', 'intent_understanding', 'user_experience',
                            'factual', 'logical', 'referential'
                        )),
    pattern_keywords    JSONB NOT NULL DEFAULT '[]'::JSONB,
    pattern_description TEXT NOT NULL,
    remediation_guidance TEXT NOT NULL,
    occurrence_count    INT NOT NULL DEFAULT 1,
    last_seen           TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_learned_patterns_category ON learned_patterns (category);
CREATE INDEX IF NOT EXISTS idx_learned_patterns_occurrence ON learned_patterns (occurrence_count DESC);
CREATE INDEX IF NOT EXISTS idx_learned_patterns_last_seen ON learned_patterns (last_seen DESC);

-- ---------------------------------------------------------------------------
-- 7. auto_audit_reports — 自動審計結果
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS auto_audit_reports (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id  TEXT,  -- 可能是 'all' 或特定 session_id
    report      JSONB NOT NULL,  -- 包含幻覺檢測、低品質案例、微調數據集等
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_auto_audit_reports_session_id ON auto_audit_reports (session_id);
CREATE INDEX IF NOT EXISTS idx_auto_audit_reports_created_at ON auto_audit_reports (created_at DESC);

-- =============================================================================
-- RLS Policies (Optional: Adjust based on your security requirements)
-- =============================================================================

-- Example: Allow read for authenticated users, write for service role
-- ALTER TABLE chat_sessions ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE chat_messages ENABLE ROW LEVEL SECURITY;
-- etc.

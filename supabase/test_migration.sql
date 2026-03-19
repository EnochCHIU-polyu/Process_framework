-- Test SQL to verify migration can be applied safely
-- Run this in Supabase SQL editor to test

-- Drop tables from previous failed attempts (optional cleanup)
-- Uncomment to reset:
-- DROP TABLE IF EXISTS auto_audit_reports CASCADE;
-- DROP TABLE IF EXISTS process_reports CASCADE;
-- DROP TABLE IF EXISTS ai_audits CASCADE;
-- DROP TABLE IF EXISTS learned_patterns CASCADE;
-- DROP TABLE IF EXISTS bad_cases CASCADE;
-- DROP TABLE IF EXISTS chat_messages CASCADE;
-- DROP TABLE IF EXISTS chat_sessions CASCADE;

-- Now run the actual migration
-- Apply 001_chat_auditing.sql here

-- After it runs, verify the tables:
SELECT 
    table_name 
FROM information_schema.tables 
WHERE table_schema = 'public' 
AND table_name IN ('chat_sessions', 'chat_messages', 'ai_audits', 'bad_cases', 'process_reports', 'learned_patterns', 'auto_audit_reports')
ORDER BY table_name;

-- Verify learned_patterns columns:
SELECT 
    column_name, 
    data_type 
FROM information_schema.columns 
WHERE table_name = 'learned_patterns' 
AND table_schema = 'public'
ORDER BY ordinal_position;

-- Check index on learned_patterns:
SELECT 
    indexname 
FROM pg_indexes 
WHERE tablename = 'learned_patterns';

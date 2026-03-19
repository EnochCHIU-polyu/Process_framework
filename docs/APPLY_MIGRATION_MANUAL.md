# Apply Migration Manually to Supabase

Your credentials are working! ✅ Now let's apply the SQL schema to your Supabase database.

## Step 1: Open SQL Editor

Go directly to your Supabase SQL editor:

```
https://app.supabase.com/project/sgdokyljluajsoajvujw/sql/new
```

## Step 2: Copy Migration SQL

The complete migration file is: `supabase/migrations/001_chat_auditing.sql`

Copy the entire contents (all 149 lines) and paste into the Supabase SQL editor.

## Step 3: Execute

Click the **"Run"** button (top right in Supabase editor).

Expected output:

```
Executed as: postgres
Query 1 (CREATE TABLE...): SUCCESS
Query 2 (CREATE INDEX...): SUCCESS
...
Query N (CREATE INDEX...): SUCCESS

No errors
```

## Step 4: Verify

Tables created:

- ✅ chat_sessions
- ✅ chat_messages
- ✅ ai_audits
- ✅ bad_cases
- ✅ process_reports
- ✅ **learned_patterns** ← This is the new one for clustering
- ✅ auto_audit_reports

### Check in Supabase Dashboard:

1. Go to **Table Editor** in left sidebar
2. Scroll down and verify **learned_patterns** appears
3. Click it to see columns:
   - `id` (UUID)
   - `category` (text)
   - `pattern_keywords` (jsonb) ← Stores keyword clusters
   - `pattern_description` (text)
   - `remediation_guidance` (text)
   - `occurrence_count` (integer)
   - `last_seen` (timestamp)
   - `created_at` (timestamp)

## Step 5: Test Connection

After migration succeeds, test with your API:

```bash
# From Process_framework directory
export SUPABASE_URL="https://sgdokyljluajsoajvujw.supabase.co"
export SUPABASE_SERVICE_ROLE_KEY="sb_publishable_fPuVFrI5qdevI2u2ooVm_Q_P5okhS22"

# Start server
uvicorn process_framework.api.main:app --reload
```

The API will now:

- ✅ Fetch learned patterns from database on startup
- ✅ Store new clustered patterns after each audit
- ✅ Use learned patterns to improve prompt guidance

## Troubleshooting

### If you see "relation already exists"

This is normal if you've migrated before. The `CREATE TABLE IF NOT EXISTS` protects against re-creation.

### If you see permission errors

Your key might be a **publishable** key instead of **service_role** key.

- Correct format: `sb_...` (service role)
- Wrong format: `pk_...` (publishable)

Go to Supabase Settings → API to get the correct **service_role** key.

### If tables don't appear in Table Editor

Refresh the browser page. Sometimes the UI needs a reload to show new tables.

---

Once verified, your clustering system is **fully deployed and ready to use**! 🎉

Next: Start flagging similar bad cases in the chat UI to see clustering in action.

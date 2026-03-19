# Quick Start: Fix & Deploy (5 Minutes)

## Your Issue

You tried to run the migration with placeholder credentials:

```bash
export SUPABASE_URL="https://your-project.supabase.co"
export SUPABASE_SERVICE_ROLE_KEY="your-key"
bash supabase/apply_migrations.sh
```

Result: `❌ Could not extract project ID` ✗

**Reason:** The script correctly rejected placeholders. You need REAL Supabase credentials.

## Solution: Get Real Credentials (2 minutes)

### Step 1: Open Supabase

```
https://app.supabase.com/projects
→ Sign in
→ Click your project (or create new one)
→ Go to Settings → API (left sidebar)
```

### Step 2: Copy Your Real Credentials

You'll see:

- **Project URL** (looks like: `https://abc123def456.supabase.co`) ← **This is SUPABASE_URL**
- **Service Role Secret** (starts with `eyJ...`) ← **This is SUPABASE_SERVICE_ROLE_KEY**

### Step 3: Set Environment Variables

```bash
export SUPABASE_URL="https://abc123def456.supabase.co"
export SUPABASE_SERVICE_ROLE_KEY="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
```

(Replace with your ACTUAL values, not placeholders)

### Step 4: Verify They're Set

```bash
echo $SUPABASE_URL
echo $SUPABASE_SERVICE_ROLE_KEY
```

You should see your actual values, not placeholders.

## Deploy: Run Migration (1 minute)

```bash
bash supabase/setup_and_migrate.sh
```

This script will:

1. ✅ Validate your credentials
2. ✅ Extract project ID
3. ✅ Apply the migration (or guide you through manual steps)
4. ✅ Confirm success

### If it still fails:

Alternative method in Supabase Dashboard:

1. Go to: https://app.supabase.com/project/YOUR-PROJECT-ID/sql/new
2. Create new query
3. Copy entire content from: `supabase/migrations/001_chat_auditing.sql`
4. Paste into editor
5. Click "Run"

## Test: Verify It Works (2 minutes)

```bash
# Start API server
uvicorn process_framework.api.main:app --reload

# In another terminal, open chat
open chat_ui.html
```

**Test clustering:**

1. Send a message to AI
2. Flag as bad: "response too long"
3. Send another message
4. Flag as bad: "verbose output"
5. Send a third message
6. **Check guard** → Should say "Brevity (2×)" instead of two separate issues ✅

**Verify in Supabase:**

- Go to Table Editor
- Find table: `learned_patterns`
- Should see pattern with `occurrence_count=2` ✅

## Common Issues

### "Could not extract project ID"

**You're still using placeholders**

- ❌ `https://your-project.supabase.co`
- ❌ `your-service-role-key`

Use REAL values from Supabase dashboard instead:

- ✅ `https://abc123def456.supabase.co`
- ✅ `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...`

### "Permission denied"

Make sure you copied **Service Role Secret** (not Anon Public key)

### "Table doesn't exist"

Migration didn't run. Try:

1. Manual SQL method (see above)
2. Check Table Editor → look for `learned_patterns` table

## What Just Deployed

✅ **Clustering System** — Deduplicates similar bad cases  
✅ **Pattern Storage** — Saves patterns in database  
✅ **Cross-Session Learning** — New users inherit patterns  
✅ **Persistent Knowledge** — Patterns accumulate over time

## Next Actions

1. ✅ Get REAL credentials from Supabase (5 min)
2. ✅ Run migration (1 min)
3. ✅ Test in chat (5 min)

**Total: ~10 minutes to full deployment**

---

See `SUPABASE_SETUP.md` for detailed credential guide.  
See `FINAL_STATUS.md` for complete system overview.

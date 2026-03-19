# Finding Your Supabase Credentials

## Quick Reference

Your system is ready—you just need to set up Supabase with real credentials instead of placeholders.

## Step-by-Step: Get Your Credentials

### Step 1: Open Supabase Dashboard

```
Go to: https://app.supabase.com/projects
Sign in with your account
```

### Step 2: Select or Create Project

- Find your project in the list, OR
- Click "New project" to create one
- Click on the project name

### Step 3: Navigate to API Settings

```
Left sidebar → Settings → API
```

### Step 4: Copy Your Credentials

**You'll find these two values:**

```
┌─ Settings / API ──────────────────────────────────────┐
│                                                        │
│  Project URL                                          │
│  ┌──────────────────────────────────────────────────┐ │
│  │ https://your-actual-project-id.supabase.co      │ │ ← Copy this
│  └──────────────────────────────────────────────────┘ │
│                                                        │
│  Service Role Secret                                  │
│  ┌──────────────────────────────────────────────────┐ │
│  │ eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...         │ │ ← Copy this
│  └──────────────────────────────────────────────────┘ │
│                                                        │
│  ⚠️  Keep secret! Never commit to git                │
│                                                        │
└────────────────────────────────────────────────────────┘
```

### Step 5: Set Environment Variables

**Option A: One-time (current terminal session)**

```bash
export SUPABASE_URL="https://your-actual-project-id.supabase.co"
export SUPABASE_SERVICE_ROLE_KEY="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
```

Then run migration:

```bash
bash supabase/setup_and_migrate.sh
```

**Option B: Permanent (add to ~/.zshrc or ~/.bash_profile)**

```bash
# Open your shell config file
nano ~/.zshrc

# Add these lines at the end:
export SUPABASE_URL="https://your-actual-project-id.supabase.co"
export SUPABASE_SERVICE_ROLE_KEY="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."

# Save and close, then reload:
source ~/.zshrc
```

### Step 6: Verify Setup

```bash
# Check URL is set
echo $SUPABASE_URL
# Should show: https://your-project-id.supabase.co

# Check key is set (first 20 chars)
echo ${SUPABASE_SERVICE_ROLE_KEY:0:20}
# Should show: eyJhbGciOiJIUzI1NiIsI...

# Run migration
bash supabase/setup_and_migrate.sh
```

### Step 7: Verify Migration Succeeded

**In Supabase Dashboard:**

1. Go to: Table Editor (left sidebar)
2. Look for: New table `learned_patterns`
3. Check columns: id, category, pattern_keywords, pattern_description, remediation_guidance, occurrence_count, last_seen, created_at
4. Verify indexes exist on: category, occurrence_count, last_seen

**If you don't see it:**

- Go to SQL Editor (left sidebar)
- Click "New query"
- Run: `SELECT COUNT(*) FROM learned_patterns;`
- Should return: 0 rows (empty table, but table exists)

## Troubleshooting

### "Could not extract project ID"

**Problem:** Your URL doesn't match expected format  
**Fix:** Make sure URL is exactly like: `https://abc123def456.supabase.co`  
(Not `https://your-project.supabase.co`)

### "Could not connect to database"

**Problem:** Bad credentials or wrong project  
**Fix:**

1. Double-check credentials in Supabase dashboard
2. Verify copy/paste (no extra spaces)
3. Try new query in SQL Editor instead (see Step 7)

### "Permission denied"

**Problem:** Service key doesn't have write permissions  
**Fix:**

1. Go back to Settings → API
2. Make sure you copied "Service Role Secret" (not "Anon Public" key)
3. Service Role should start with `eyJ...`

### Manual Alternative: SQL Editor Method

If scripts don't work:

1. Go to: https://app.supabase.com/project/YOUR-PROJECT-ID/sql/new
2. Create new query
3. Copy entire content from: `supabase/migrations/001_chat_auditing.sql`
4. Paste into SQL editor
5. Click "Run"
6. Verify: Table Editor → `learned_patterns` appears

## Real Example

```bash
# DON'T use placeholders like this:
export SUPABASE_URL="https://your-project.supabase.co"        ❌
export SUPABASE_SERVICE_ROLE_KEY="your-service-role-key"      ❌

# USE real values like this:
export SUPABASE_URL="https://asjdh1234kjs56.supabase.co"       ✅
export SUPABASE_SERVICE_ROLE_KEY="eyJhbGciOiJIUzI1Ni..."      ✅
```

## Security Note

- Service role key gives full database access
- **Never** commit to Git
- **Never** put in public repos
- **Never** share in Slack/email
- Always keep in `.env` or environment variables only

---

**Need help?** Once credentials are set correctly, run:

```bash
bash supabase/setup_and_migrate.sh
```

This script will validate your credentials and guide you through the rest.

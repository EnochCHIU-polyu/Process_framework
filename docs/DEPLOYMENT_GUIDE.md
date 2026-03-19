# Pattern Clustering Deployment Guide

## Quick Start (3 steps)

### Step 1: Apply Supabase Migration

The new `learned_patterns` table needs to be created in your Supabase project.

**Option A: Using migration runner script (macOS/Linux)**

```bash
cd /Users/yeechiu/Documents/GitHub/mobile-app-assignment-1/AI-Assignment-1/AI-assignment-2/Process_framework

# Set environment variables
export SUPABASE_URL="https://your-project-id.supabase.co"
export SUPABASE_SERVICE_ROLE_KEY="your-service-role-key-here"

# Run migration
bash supabase/apply_migrations.sh
```

**Option B: Manual SQL in Supabase Dashboard**

1. Go to [Supabase Dashboard](https://app.supabase.com) → Your Project → SQL Editor
2. Create new query
3. Copy entire content from `supabase/migrations/001_chat_auditing.sql`
4. Run it (you'll see the new `learned_patterns` table + indexes)

**Find your credentials:**

- SUPABASE_URL: Go to Settings → API → URL (starts with `https://`)
- SUPABASE_SERVICE_ROLE_KEY: Go to Settings → API → Service Role Key (starts with `eyJ...`)

### Step 2: Verify Migration

In Supabase Dashboard, go to **Table Editor** and check:

- New table `learned_patterns` exists
- Columns: `id`, `category`, `pattern_keywords`, `pattern_description`, `remediation_guidance`, `occurrence_count`, `last_seen`, `created_at`
- Indexes on `category`, `occurrence_count`, `last_seen`

### Step 3: Test Clustering System

No code changes needed! The system activates automatically.

**In your chat interface:**

1. Send a message to the AI
2. Flag bad case: "response too long"
3. Send another message
4. Flag bad case: "verbose output"
5. Send a third message
   - **Notice:** Guard now says `"BREVITY ISSUE (seen=2×)"` instead of separate entries
   - Check Supabase → `learned_patterns` table → Should see one pattern with `occurrence_count=2`

## System Architecture

```
Bad Case Flagged
    ↓
Store in bad_cases table
    ↓
build_session_guard() orchestrator:
    ├─ Fetch session's bad cases → cluster_bad_cases()
    ├─ Cluster similar meanings
    ├─ Store clusters → learned_patterns table
    ├─ Fetch top patterns from DB
    └─ Build guard from fresh + accumulated
    ↓
Guard injected into LLM system prompt
    ↓
LLM generates better response
```

## Key Features

| Feature              | How It Works                                            |
| -------------------- | ------------------------------------------------------- |
| **Deduplication**    | "too long" + "verbose" + "too many words" → one pattern |
| **Persistence**      | Patterns stored in DB, reused across sessions           |
| **Accumulation**     | `occurrence_count` grows as patterns repeat             |
| **Global Learning**  | Top patterns retrieved from DB help all sessions        |
| **Safe Degradation** | If DB unavailable, falls back to fresh clustering       |

## Monitoring

### View Learned Patterns

**In Supabase Dashboard:**

1. Table Editor → `learned_patterns`
2. Sort by `occurrence_count DESC`
3. Top patterns are most frequently flagged issues

**Example:**

```
Pattern                          Category            Occurrences  Last Seen
────────────────────────────────────────────────────────────────────────
"Output too long"                user_experience            5      2024-03-19 15:30
"Unsupported facts"              hallucination              3      2024-03-19 14:52
"Missing constraint"             intent_understanding      2      2024-03-19 12:40
```

### Query Recent Patterns

```sql
SELECT
  category,
  pattern_description,
  occurrence_count,
  last_seen
FROM learned_patterns
ORDER BY occurrence_count DESC
LIMIT 10;
```

### Clear/Reset Patterns

```sql
-- Delete all patterns (fresh start)
DELETE FROM learned_patterns;

-- Delete patterns older than 7 days
DELETE FROM learned_patterns
WHERE created_at < now() - interval '7 days';

-- Reset occurrence count for a category
UPDATE learned_patterns
SET occurrence_count = 1
WHERE category = 'user_experience';
```

## Tuning

### Adjust Clustering Threshold

Lower = more aggressive clustering (fewer patterns stored)
Higher = conservative clustering (more patterns stored)

**In `process_framework/api/feedback.py`, function `_cluster_bad_cases()`:**

```python
# Look for this line:
if matched_cluster_idx >= 0 and best_similarity > 0.6:  # ← Change 0.6

# Recommended values:
# 0.4 = Very aggressive merging (more deduplication)
# 0.6 = Moderate (current)
# 0.8 = Conservative (rarely merges)
```

**Test different thresholds by:**

1. Edit the value
2. Run `python3 verify_clustering.py` to see clustering results
3. Flag bad cases in chat and observe
4. Check `occurrence_count` in learned_patterns table

### Adjust Pattern Fetch Limit

**In `feedback.py`, function `fetch_learned_patterns()`:**

```python
query_parts = ["order=occurrence_count.desc", "limit=50"]  # ← Change 50

# The guard uses top patterns → more patterns = longer guard
# Recommended: 20-50 depending on your needs
```

## Troubleshooting

**Q: Why aren't my patterns clustering?**
A: Similarity score is below threshold (currently 60%). Check:

```bash
# Run verification to see similarity scores
python3 verify_clustering.py
```

Then adjust threshold in `_cluster_bad_cases()` if needed.

**Q: Where is my pattern stored?**
A: In Supabase → Table Editor → `learned_patterns`
Check filters: might be offset by sorting.

**Q: Can I delete old patterns?**
A: Yes, use SQL in Supabase SQL Editor:

```sql
DELETE FROM learned_patterns
WHERE last_seen < now() - interval '30 days'
AND occurrence_count < 2;
```

**Q: How do I force re-clustering?**
A: Clear patterns and let them re-accumulate:

```sql
DELETE FROM learned_patterns;
```

## Performance

- **DB writes:** Async, doesn't block chat response
- **Pattern fetch:** Top 50 patterns, cached at start of session
- **Clustering:** O(n²) for n bad cases, typically n<10 per session (fast)
- **Query time:** <100ms for most queries (Supabase is fast)

## What's Next?

**Possible enhancements:**

- [ ] Semantic clustering using embeddings for richer deduplication
- [ ] Automatic pattern merging when occurrence_count exceeds threshold
- [ ] Pattern weighting by recency (recent patterns prioritized)
- [ ] Per-category pattern limits
- [ ] Export patterns for analysis/visualization

## Files Modified/Created

**Modified:**

- `process_framework/api/feedback.py` — Added clustering logic, pattern storage/fetch
- `supabase/migrations/001_chat_auditing.sql` — Added `learned_patterns` table

**Created:**

- `supabase/apply_migrations.sh` — Migration runner
- `verify_clustering.py` — Clustering verification script
- `md/CLUSTERING_AND_LEARNING.md` — Detailed documentation

**No changes needed:**

- `chat.py` — Works with new guard format automatically
- Chat UI — No frontend changes needed

---

**Status:** ✅ Ready to deploy  
**Last Updated:** 2024-03-19

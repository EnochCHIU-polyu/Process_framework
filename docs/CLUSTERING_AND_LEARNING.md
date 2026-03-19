# Pattern Clustering & Persistent Learning Guide

## Overview

Your PROCESS framework now features **semantic pattern clustering** and **persistent learning** across sessions. Instead of recomputing policy from raw bad cases each turn, the system:

1. **Clusters** semantically similar bad cases (deduplicates repetition)
2. **Stores** clusters in a database as learned patterns
3. **Accumulates** knowledge across multiple sessions
4. **Reuses** top patterns to guide LLM behavior persistently

## Architecture

### 1. Clustering Strategy

Bad cases are automatically grouped by:

- **Category** (primary): `hallucination`, `user_experience`, `intent_understanding`, etc.
- **Keyword overlap** (secondary): Cases with overlapping `ignored_keywords` are grouped
- **Reason similarity** (tertiary): Cases with similar reason text (>60% string match) are clustered

**Deduplication Example:**

```
Bad case 1: reason: "response too long", keywords: ["brevity", "concise"]
Bad case 2: reason: "verbose output", keywords: ["concise", "short"]
Bad case 3: reason: "too many words", keywords: ["brevity"]

→ All three cluster into ONE pattern: "OUTPUT BREVITY ISSUE"
  - Combined keywords: ["brevity", "concise", "short"]
  - Occurrence count: 3
```

### 2. Database Storage

New table: `learned_patterns`

**Schema:**

```sql
CREATE TABLE learned_patterns (
    id UUID PRIMARY KEY,
    category TEXT,                    -- e.g., 'user_experience'
    pattern_keywords JSONB,           -- dedup'd keywords: ["brevity", "concise"]
    pattern_description TEXT,         -- normalized summary
    remediation_guidance TEXT,        -- what to do about it
    occurrence_count INT,             -- total times seen
    last_seen TIMESTAMPTZ,           -- when last encountered
    created_at TIMESTAMPTZ           -- when pattern first recorded
);
```

**Example row:**

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "category": "user_experience",
  "pattern_keywords": ["brevity", "concise", "short"],
  "pattern_description": "Output too long, verbose, needs compression",
  "remediation_guidance": "Keep answer concise and direct; avoid repetition.",
  "occurrence_count": 7,
  "last_seen": "2024-03-19T14:32:00Z",
  "created_at": "2024-03-15T09:00:00Z"
}
```

### 3. Learning Flow

**Session 1:**

```
User flags: "response too long"
  → Creates bad_case in DB
  → Clustering: new "BREVITY" pattern
  → Stores in learned_patterns (occurrence_count=1)
  → Guard includes: "Avoid verbosity"

User flags another: "too verbose"
  → Clusters with previous (keyword overlap + reason similarity)
  → Updates learned_patterns (occurrence_count=2, last_seen updated)

Next turn → Guard includes: "Avoid verbosity (seen=5×)"
```

**Session 2 (different user/room):**

```
Fetch patterns → learned_patterns returns top patterns
  → "BREVITY_ISSUE" (occurrence_count=7, last_seen=recent)
  → "HALLUCINATION" (occurrence_count=12)

Guard includes: "From global knowledge..." + new session patterns
→ LLM learns from accumulated patterns across all sessions
```

## Implementation Details

### Clustering Functions

**`_normalize_keywords(keywords: list[str]) -> set[str]`**

- Converts to lowercase, deduplicates
- Filters out short noise (<3 chars)

**`_keyword_overlap(kw_set1, kw_set2) -> float`**

- Jaccard similarity: intersection / union
- Returns 0.0 (disjoint) to 1.0 (identical)

**`_string_similarity(s1, s2) -> float`**

- Uses `SequenceMatcher` for reason text matching
- Returns 0.0 to 1.0

**`_cluster_bad_cases(bad_cases) -> List[Dict]`**

- Groups by category + keyword overlap + reason similarity
- Threshold: 60% combined similarity to merge clusters
- Returns: Category, keywords, pattern description, remediation, count

### Storage Functions

**`fetch_learned_patterns(category, settings) -> List[Dict]`**

- Fetches from `learned_patterns` table
- Returns top 50 patterns sorted by `occurrence_count DESC`
- Optional category filter
- Returns empty list on any network error (graceful degradation)

**`upsert_pattern_cluster(cluster, settings) -> None`**

- Stores cluster dict as new row in `learned_patterns` table
- In future: could check for exact keyword match to increment instead of insert
- Fails gracefully (logged, does not crash)

**`build_session_guard(session_id, settings)`**

- Main orchestrator function
  1. Fetch session's bad cases
  2. Cluster them (deduplication)
  3. Store clusters in DB
  4. Fetch top learned patterns from DB
  5. Build guard from both fresh + accumulated patterns

### Policy Building

**`_build_prompt_policy(bad_cases, learned_patterns)`**

- Takes fresh bad cases + accumulated patterns
- Counts category frequencies from both sources
- Weights learned patterns (× 1/3 for occurrence count)
- Extracts top keywords with priority labels
- Returns: (optimization_rules, constraints, corrections, scrutiny_checklist)

**`build_guard_prompt(bad_cases, learned_patterns) -> str`**

- Formats policy into system prompt
- Shows both fresh ("this session") and learned ("accumulated") counts
- Injects PROCESS-aligned blocks: P/O, R/C, Learned Corrections, S/S

## Usage

### 1. Apply Migration

```bash
# Set environment variables
export SUPABASE_URL="https://your-project.supabase.co"
export SUPABASE_SERVICE_ROLE_KEY="your-service-key"

# Run migration
bash supabase/apply_migrations.sh
```

Or manually in [Supabase SQL editor](https://app.supabase.com/):

- Open your project → SQL Editor
- Create new query
- Copy entire `supabase/migrations/001_chat_auditing.sql`
- Run it

### 2. Chat Flow

Same as before—no changes to chat UI:

```
1. User sends message
2. LLM generates response
3. User flags with "Flag as bad: [reason]"
4. Reason + category stored in bad_cases table
5. Next turn:
   a. Fetch session's bad cases
   b. Cluster them → deduplicate similar issues
   c. Store clusters in learned_patterns DB
   d. Fetch top accumulated patterns from DB
   e. Inject guard with both fresh + global patterns
   f. LLM generates next response (improved)
```

### 3. Monitoring Patterns

**In Supabase dashboard:**

- Go to "Table Editor" → `learned_patterns`
- Sort by `occurrence_count DESC` to see top issues
- Check `last_seen` to see if patterns are getting recent hits
- Monitor growth: count increases = pattern accumulating evidence

**In code (for debugging):**

```python
# In feedback.py or test script
patterns = await fetch_learned_patterns(None, settings)
for p in patterns[:5]:
    print(f"{p['category']}: {p['pattern_description']} (x{p['occurrence_count']})")
```

## Key Benefits

| Benefit                    | How It Works                                                            |
| -------------------------- | ----------------------------------------------------------------------- |
| **No repetition**          | Clustering deduplicates "too long", "verbose", "short" into one pattern |
| **Cross-session learning** | Patterns persist in DB, reused by all sessions                          |
| **Efficient**              | Clusters stored once, reused many times; not recomputed each turn       |
| **Auditable**              | See exactly which patterns accumulate and how often                     |
| **Scalable**               | Learned patterns ranked by frequency; always uses top-K                 |
| **Safe**                   | Clustering failures don't crash—graceful fallback to raw bad cases      |

## Example Behavior

### Before Clustering

Session 1:

```
Bad flag 1: "too long"
Guard contains: "...too long (seen 1×)"

Bad flag 2: "verbose"
Guard contains: "...too long (seen 1×), verbose (seen 1×)"  ← separate

Bad flag 3: "too many words"
Guide contains: "...too long (seen 1×), verbose (seen 1×), too many words (seen 1×)" ← tripled
```

Session 2:

```
Guard starts empty—no patterns carry over
Doesn't know about "brevity" issues from Session 1
```

### After Clustering

Session 1:

```
Bad flag 1: "too long"
Cluster: "BREVITY_ISSUE", stored with keywords=["long"]

Bad flag 2: "verbose"
Matches cluster (reason similarity 0.85 > 0.6)
→ Cluster updated: keywords=["long", "verbose"], occurrence=2

Bad flag 3: "too many words"
Matches cluster (keyword + reason match)
→ Cluster updated: occurrence=3

Guard shows: "Brevity constraint (seen 3×)" ← unified!
Stored in learned_patterns NOW
```

Session 2:

```
Fetch learned_patterns → finds "BREVITY_ISSUE" (occurrence=3)
User has not flagged brevity yet → but guard includes it from global knowledge!
→ LLM learns about brevity from accumulated history
```

## Configuration

No separate config—uses existing `Settings` object:

- `supabase_url`: Your project URL
- `supabase_service_role_key`: Service role key for writes

Clustering thresholds (tunable in code):

- Similarity threshold: `0.6` (60% match to merge clusters)
  - Increase for stricter clustering (fewer merges)
  - Decrease for looser clustering (more merges)
- Keyword minimum length: `2` chars
  - Filters out noise like "a", "is"
- Pattern keyword boost: `2×` for learned patterns
  - Emphasizes accumulated keywords over fresh ones
  - Tune if needed for your use case

## Troubleshooting

**Q: Why is my guard showing patterns from other sessions?**
A: That's the feature! Top learned patterns accumulate across all sessions. This helps the LLM learn global constraints.

**Q: How do I prevent cross-session learning?**
A: Cluster only within session (current design). Filtering by `session_id` in the fetch would do it—open a feature request!

**Q: My pattern isn't showing up.**
A: Check:

1. Bad case was flagged with a category
2. Migration was applied (`learned_patterns` table exists)
3. `upsert_pattern_cluster` didn't encounter network errors (check server logs)
4. Pattern occurrence count is high enough to appear in top-50 results

**Q: Can I manually edit learned patterns?**
A: Yes! In Supabase SQL editor:

```sql
DELETE FROM learned_patterns
WHERE pattern_description LIKE '%old pattern%';

UPDATE learned_patterns
SET occurrence_count = 1
WHERE category = 'user_experience';
```

## Next Steps

1. **Apply migration** with `supabase/apply_migrations.sh`
2. **Test clustering** by flagging similar bad cases in same session
   - Should see count increment, not repeated entries
3. **Monitor patterns** in Supabase dashboard
4. **Tune thresholds** if clustering is too aggressive/loose
5. **(Future)** Add semantic clustering using embeddings for richer deduplication

---

**Built for:** PROCESS AI Review Framework  
**Updated:** 2024-03-19

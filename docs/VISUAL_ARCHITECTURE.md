# Visual System Architecture

## Before vs After

```
╔══════════════════════════════════════════════════════════════════════╗
║                           BEFORE                                    ║
╚══════════════════════════════════════════════════════════════════════╝

Bad Case 1: "too long"      ─┐
Bad Case 2: "verbose"       ─┼─→ Compute policy each turn
Bad Case 3: "too many"      ─┤   (recompute, redundant, session-scoped)
                             │
                             └─→ Guard: "too long", "verbose", "too many" (3× separate)
                                                          ↓
                                                    Lost after session


╔══════════════════════════════════════════════════════════════════════╗
║                           AFTER                                     ║
╚══════════════════════════════════════════════════════════════════════╝

Bad Case 1: "too long"      ─┬─→ Clustering (Similarity > 60%)
Bad Case 2: "verbose"       ─┼─→ Merge 3 cases into 1 pattern
Bad Case 3: "too many"      ─┘   "BREVITY_ISSUE" (count=3)
                                           ↓
                                    Store in DB
                                           ↓
                                    Guard: "Brevity (3×)" ← unified!
                                           ↓
                                  Persist in learned_patterns
                                           ↓
                        Reuse by all future sessions!
```

## Component Interaction

```
                ┌──────────────────────────────────┐
                │      Chat Session Endpoint       │
                │    /chat/{session_id}            │
                └──────────────┬───────────────────┘
                               │
                               ↓
                    ┌──────────────────────┐
                    │ build_session_guard()│◄══════════ Entry Point
                    └──────────┬───────────┘
                               │
          ┌────────────────────┼────────────────────┐
          │                    │                    │
          ↓                    ↓                    ↓
    ┌─────────────┐    ┌─────────────┐    ┌──────────────────┐
    │   Fetch     │    │  Cluster    │    │   Fetch          │
    │   Bad Cases │    │   Bad Cases │    │   Learned        │
    │   (Session) │    │             │    │   Patterns (DB)  │
    └────┬────────┘    └────┬────────┘    └────┬─────────────┘
         │                   │                   │
         │ [N cases]         │ [M clusters]      │ [K patterns]
         │                   ↓                   │
         │            ┌─────────────┐           │
         │            │   Upsert    │           │
         │            │   Clusters  │           │
         │            │   to DB     │           │
         │            └─────────────┘           │
         │                                       │
         └───────────────┬───────────────────────┘
                         │
                         ↓
            ┌────────────────────────────┐
            │  build_guard_prompt()      │
            │                            │
            │ Merge:                     │
            │ - Fresh cases (N)          │
            │ - Learned patterns (K)     │
            │                            │
            │ Output: Guard string       │
            └────────────┬───────────────┘
                         │
                         ↓
            ┌────────────────────────────┐
            │ inject_guard_prompt()      │
            │ Prepend to LLM messages    │
            └────────────┬───────────────┘
                         │
                         ↓
            ┌────────────────────────────┐
            │   LLM Generates Response   │
            │   (Using guard + context)  │
            └────────────┬───────────────┘
                         │
                         ↓
            ┌────────────────────────────┐
            │    Return to Frontend      │
            └────────────────────────────┘
```

## Database Schema

```
┌─────────────────────────────────────────────────────────────┐
│                   SUPABASE DATABASE                         │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ TABLE: bad_cases                                            │
├─────────────────────────────────────────────────────────────┤
│ id (UUID)             Primary Key                           │
│ message_id (UUID FK)  Points to chat_messages               │
│ session_id (UUID FK)  Points to chat_sessions               │
│ reason (TEXT)         e.g., "response too long"            │
│ category (TEXT)       e.g., "user_experience"              │
│ ignored_keywords (JSONB)  ["brevity", "concise"]           │
│ root_cause (TEXT)     Why the issue occurred               │
│ expected_output (TEXT) What should have happened           │
│ actual_output (TEXT)   What actually happened              │
│ created_at (TIMESTAMP) When flagged                        │
│                                                             │
│ Indexes:                                                    │
│  - session_id (for quick lookup)                           │
│  - category (for filtering)                                │
│  - created_at (for time-based queries)                     │
└─────────────────────────────────────────────────────────────┘

                          ↕ (Clustering)

┌─────────────────────────────────────────────────────────────┐
│ TABLE: learned_patterns  ← NEW!                             │
├─────────────────────────────────────────────────────────────┤
│ id (UUID)                 Primary Key                       │
│ category (TEXT)           e.g., "user_experience"          │
│ pattern_keywords (JSONB)  ["brevity", "concise", ...]     │
│ pattern_description (TEXT) "Response too long, verbose"   │
│ remediation_guidance (TEXT) "Keep answer concise..."       │
│ occurrence_count (INT)     How many times seen [1, ∞]     │
│ last_seen (TIMESTAMP)      When last encountered           │
│ created_at (TIMESTAMP)     When pattern first recorded     │
│                                                             │
│ Indexes:                                                    │
│  - category (for filtering by type)                        │
│  - occurrence_count DESC (for finding top patterns)        │
│  - last_seen DESC (for finding recent patterns)            │
└─────────────────────────────────────────────────────────────┘

                        ← Feedback from LLM

┌─────────────────────────────────────────────────────────────┐
│ TABLE: chat_sessions                                        │
│ TABLE: chat_messages                                        │
│ TABLE: ai_audits                                            │
│ TABLE: process_reports                                      │
│ (Other tables unchanged - full compatibility)              │
└─────────────────────────────────────────────────────────────┘
```

## Processing Pipeline

```
USER INPUT
    │
    ↓ ┌─────────────────────────────────────────┐
    │ │ 1. LLM Generates Response               │
    │ │    (System prompt, user message)        │
    │ └─────────────────────────────────────────┘
    │
    ↓ ┌─────────────────────────────────────────┐
    │ │ 2. User Reviews & Flags                 │
    │ │    "Flag as bad: response too long"     │
    │ └─────────────────────────────────────────┘
    │
    ↓ ┌─────────────────────────────────────────┐
    │ │ 3. Audit Records Bad Case               │
    │ │    → bad_cases table                    │
    │ └─────────────────────────────────────────┘
    │
    ↓ ┌─────────────────────────────────────────┐
    │ │ 4. Next LLM Turn                        │
    │ │    build_session_guard() triggered      │
    │ └─────────────────────────────────────────┘
    │
    ├─ 4a. Fetch bad_cases (session) ──→ [1 case]
    ├─ 4b. _cluster_bad_cases() ────────→ [1 cluster]
    ├─ 4c. upsert_pattern_cluster() ──→ learned_patterns table ✓
    ├─ 4d. fetch_learned_patterns() ──→ [top 50 patterns]
    ├─ 4e. build_guard_prompt() ─────→ Guard string
    └─ 4f. inject_guard_prompt() ────→ Prepend to messages

    ↓ ┌─────────────────────────────────────────┐
    │ │ 5. Guard Injected into LLM              │
    │ │    [AUDIT FEEDBACK - DO NOT IGNORE]     │
    │ │    Brevity issue (seen 1×)              │
    │ └─────────────────────────────────────────┘
    │
    ↓ ┌─────────────────────────────────────────┐
    │ │ 6. LLM Generates BETTER Response        │
    │ │    (Informed by guard + feedback)       │
    │ └─────────────────────────────────────────┘
    │
    ↓
USER SEES IMPROVED RESPONSE
    │
    └─ Process repeats, patterns accumulate! 🔄
```

## Clustering Algorithm

```
INPUT: List of bad_cases
        [case1, case2, ...]

FOR EACH bad_case:
    │
    ├─ Extract: category, keywords, reason
    │
    ├─ SCAN existing clusters:
    │   FOR each cluster:
    │       ├─ Check: same category?
    │       ├─ Calculate: keyword_overlap (Jaccard)
    │       ├─ Calculate: string_similarity (SequenceMatcher)
    │       ├─ Calculate: combined_similarity
    │       │   = 0.7 × keyword_overlap + 0.3 × string_similarity
    │       │
    │       └─ IF combined_similarity > 0.6:  ← THRESHOLD
    │           ├─ MERGE into cluster
    │           ├─ Increment occurrence_count
    │           └─ Merge keywords
    │
    ├─ ELSE (no match or too low similarity):
    │   └─ CREATE new cluster
    │
    └─ Add to results list

OUTPUT: Deduplicated clusters [cluster1, cluster2, ...]
        Each with aggregated:
        - keywords
        - occurrence_count
        - description
```

## Similarity Scoring

```
Example: Comparing "too long" vs "verbose"

┌─────────────────────────────────────────────────────┐
│ 1. KEYWORD OVERLAP (Jaccard)                        │
├─────────────────────────────────────────────────────┤
│ case1 keywords: ["brevity", "concise"]             │
│ case2 keywords: ["concise", "short"]               │
│                                                     │
│ Intersection: ["concise"]     size = 1              │
│ Union:        ["brevity", "concise", "short"] = 3   │
│                                                     │
│ Similarity = 1/3 = 0.33 (33%)                       │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│ 2. STRING SIMILARITY (SequenceMatcher)              │
├─────────────────────────────────────────────────────┤
│ case1 reason: "response too long"                   │
│ case2 reason: "verbose output"                      │
│                                                     │
│ Common subsequences: "vs", "e", " ", "o"...        │
│ Similarity ≈ 0.45 (45%)                            │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│ 3. COMBINED SCORE                                   │
├─────────────────────────────────────────────────────┤
│ combined = 0.7 × keyword + 0.3 × string            │
│          = 0.7 × 0.33 + 0.3 × 0.45                │
│          = 0.231 + 0.135                          │
│          = 0.366 (36.6%)                           │
│                                                     │
│ Threshold: 0.6 (60%)                              │
│ Result: 0.366 < 0.60 → DON'T MERGE                │
│ (Too different)                                    │
└─────────────────────────────────────────────────────┘

But if we had:
  case1: "too long", keywords: ["brevity"]
  case2: "too many words", keywords: ["brevity"]

  Keyword overlap: 1/1 = 1.0 (100%)
  String similarity: 0.75 (very similar)
  Combined = 0.7 × 1.0 + 0.3 × 0.75 = 0.925 ✓
  Result: 0.925 > 0.60 → MERGE!
```

## Cross-Session Knowledge Transfer

```
┌─────────────────────────┐           ┌─────────────────────────┐
│   SESSION 1             │           │   SESSION 2             │
│   User A, Room X        │           │   User B, Room Y        │
├─────────────────────────┤           ├─────────────────────────┤
│ Message 1               │           │ Message 1               │
│ Flag: "too long"        │           │ (no flag yet)           │
│                         │           │                         │
│ → Store in             │           │ build_session_guard():  │
│   bad_cases table       │           │ ├─ Fetch bad_cases: []  │
│ → Cluster: BREVITY      │           │ ├─ Cluster: []          │
│ → Store in             │           │ ├─ Fetch patterns: ✓   │
│   learned_patterns      │           │ │  (Gets BREVITY from  │
│                         │  ───────→ │   Session 1!)          │
│ learned_patterns DB:    │           │ └─ Guard includes:     │
│ {                       │           │    "Brevity (x1)"      │
│   category: UX,         │           │                         │
│   keywords: ["brevity"] │           │ → LLM learns without   │
│   count: 1,             │           │   user flagging!       │
│ }                       │           │                         │
└─────────────────────────┘           └─────────────────────────┘

RESULT: Cross-session knowledge transfer ✅
        User B benefits from User A's feedback
```

## Code Flow Map

```
process_framework/api/main.py
    │
    ├─ routes/chat.py
    │   └─ POST /chat/{session_id}
    │       ├─ receive message
    │       ├─ fetch guard ──────→ build_session_guard()
    │       │                       │
    │       └─ WITH guard:   process_framework/api/feedback.py
    │           ├─ fetch_session_bad_cases()
    │           ├─ _cluster_bad_cases()        ← NEW
    │           ├─ upsert_pattern_cluster()    ← NEW
    │           ├─ fetch_learned_patterns()    ← NEW
    │           ├─ _build_prompt_policy()      (updated)
    │           ├─ build_guard_prompt()        (updated)
    │           └─ inject_guard_prompt()
    │
    ├─ routes/audit.py
    │   └─ POST /audit/{session_id}/{message_id}
    │       └─ mark as bad_case
    │           └─ next turn triggers guard rebuild
    │
    └─ routes/process.py
        └─ GET /process/{session_id}
            └─ audits messages (separate pipeline)
```

---

**Complete Visual Documentation:** ✅ Ready  
**System Understanding:** ✅ Clear  
**Ready to Deploy:** ✅ YES

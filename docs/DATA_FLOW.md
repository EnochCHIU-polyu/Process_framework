# Data Flow & System Architecture

## Complete Data Flow: From Bad Flag to Learned Pattern

```
┌─────────────────────────────────────────────────────────────────────┐
│                    CHAT SESSION START                              │
│              User initiates conversation                           │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ↓
        ┌───────────────────────────────────────┐
        │ MESSAGE 1 from User                   │
        │ "Can you explain quantum computing?" │
        └───────────────────────────────────────┘
                              │
                              ↓
        ┌─────────────────────────────────────────────┐
        │ LLM generates response                      │
        │ (using system prompt, no guard yet)        │
        └─────────────────────────────────────────────┘
                              │
                              ↓
        ┌─────────────────────────────────────────────┐
        │ User flags bad case:                        │
        │ "Flag as bad: response too long"           │
        │                                             │
        │ Audit creates record:                      │
        │ - reason: "response too long"              │
        │ - category: user_experience                │
        │ - ignored_keywords: ["brevity"]            │
        │ - expected_output: "Keep to 2-3 sentences" │
        └─────────────────────────────────────────────┘
                              │
                              ↓
        ┌─────────────────────────────────────────────┐
        │ STORED IN: bad_cases table                 │
        │ ┌─────────────────────────────────────┐   │
        │ │ id: abc-123                         │   │
        │ │ session_id: session-456             │   │
        │ │ reason: "response too long"         │   │
        │ │ category: user_experience           │   │
        │ │ ignored_keywords: ["brevity"]       │   │
        │ │ expected_output: "Keep brief"       │   │
        │ │ created_at: 2024-03-19 14:30:00    │   │
        │ └─────────────────────────────────────┘   │
        └─────────────────────────────────────────────┘
                              │
                              ↓
                    ✅ USER CAN NOW
                    CONTINUE CHATTING
                              │
                              ↓
        ┌───────────────────────────────────────┐
        │ MESSAGE 2 from User                   │
        │ "More about superpositioning"         │
        │ [BEFORE SENDING LLM RESPONSE]         │
        │ Trigger: build_session_guard()        │
        └───────────────────────────────────────┘
                              │
                              ↓
    ╔═════════════════════════════════════════════════════════════════╗
    ║           CLUSTERING & PATTERN EXTRACTION PHASE                ║
    ╚═════════════════════════════════════════════════════════════════╝
                              │
        ┌─────────────────────────────────────────────────┐
        │ 1. fetch_session_bad_cases(session_id)         │
        │    Query: SELECT * FROM bad_cases              │
        │           WHERE session_id = 'session-456'     │
        │    Result: [bad_case_1]  ← 1 case              │
        └─────────────────────────────────────────────────┘
                              │
                              ↓
        ┌─────────────────────────────────────────────────┐
        │ 2. _cluster_bad_cases([bad_case_1])            │
        │                                                 │
        │    Input:                                       │
        │    {                                            │
        │      reason: "response too long",              │
        │      keyword: ["brevity"],                     │
        │      category: "user_experience"               │
        │    }                                            │
        │                                                 │
        │    Process:                                     │
        │    - First case in session → create new cluster │
        │    - Cluster name: user_experience_0            │
        │    - occurrence_count: 1                        │
        │                                                 │
        │    Output:                                      │
        │    [{                                           │
        │      cluster_id: "user_exp_0",                 │
        │      category: "user_experience",              │
        │      pattern_keywords: ["brevity"],            │
        │      pattern_description: "response too long", │
        │      occurrence_count: 1                        │
        │    }]                                           │
        └─────────────────────────────────────────────────┘
                              │
                              ↓
        ┌─────────────────────────────────────────────────┐
        │ 3. upsert_pattern_cluster(cluster)              │
        │    Store cluster in learned_patterns table      │
        │                                                 │
        │    INSERT INTO learned_patterns:               │
        │    {                                            │
        │      id: "new-uuid",                           │
        │      category: "user_experience",              │
        │      pattern_keywords: ["brevity"],            │
        │      pattern_description: "response too long", │
        │      remediation_guidance: "[...from DB]",     │
        │      occurrence_count: 1,                      │
        │      last_seen: NOW(),                         │
        │      created_at: NOW()                         │
        │    }                                            │
        └─────────────────────────────────────────────────┘
                              │
                              ↓
        ┌─────────────────────────────────────────────────┐
        │ 4. fetch_learned_patterns()                     │
        │    Query: SELECT * FROM learned_patterns       │
        │           ORDER BY occurrence_count DESC       │
        │           LIMIT 50                             │
        │                                                 │
        │    Result: [pattern_brevity (count=1)]         │
        │            ← This is the pattern we just added!│
        └─────────────────────────────────────────────────┘
                              │
                              ↓
        ┌─────────────────────────────────────────────────┐
        │ 5. build_guard_prompt(bad_cases, patterns)     │
        │                                                 │
        │    Input:                                       │
        │    - bad_cases: [1 raw case]                   │
        │    - patterns: [1 pattern from DB]             │
        │                                                 │
        │    Process:                                     │
        │    - Merge both sources                        │
        │    - Count: 1 fresh + 1 learned = "x1"        │
        │    - Build policy blocks (P/O, R/C, S/S)      │
        │    - Format as system message                   │
        │                                                 │
        │    Output: Guard string (500+ chars)           │
        │    [AUDIT FEEDBACK - DO NOT IGNORE]            │
        │    Fresh issues: 1                              │
        │    Learned patterns: 1 clusters                │
        │    [USER EXPERIENCE] x1: Keep answer concise...│
        │    [R/C - CONSTRAINTS]                         │
        │    - brevity (HIGH, seen=1)                    │
        │    [...more sections...]                       │
        └─────────────────────────────────────────────────┘
                              │
                              ↓
        ┌─────────────────────────────────────────────────┐
        │ 6. inject_guard_prompt(messages, guard)        │
        │    Prepend guard to message list:              │
        │                                                 │
        │    Final messages for LLM:                     │
        │    [                                            │
        │      {role: "system",                          │
        │       content: "[AUDIT FEEDBACK...]\n..."},   │
        │      {role: "user", content: "More about..."}  │
        │    ]                                            │
        └─────────────────────────────────────────────────┘
                              │
                              ↓
        ┌─────────────────────────────────────────────────┐
        │ LLM SEES GUARD:                                │
        │ "Keep answer concise..."                       │
        │ "Avoid: too long responses"                    │
        │ "Brevity is HIGH priority"                     │
        │                                                 │
        │ LLM generates BETTER response:                │
        │ (Shorter, more direct!)                        │
        └─────────────────────────────────────────────────┘
                              │
                              ↓
        ┌───────────────────────────────────────┐
        │ User sees improved response           │
        │ (Addresses the earlier critique!)     │
        └───────────────────────────────────────┘
                              │
                              ↓
                    ✅ CONTINUE CHATTING
```

## Scenario: Multiple Similar Flags (Clustering in Action)

```
SESSION 1, FLAG 2: CLUSTERING KICKS IN
────────────────────────────────────────

MESSAGE 3 from User flags again:
"Flag as bad: verbose output"

⚙️  CLUSTERING DETECTS SIMILARITY ⚙️

_cluster_bad_cases() compares:
  New case: reason="verbose", keywords=["concise", "short"]
  vs
  Existing cluster: reason="response too long", keywords=["brevity"]

  Keyword overlap: ["concise"] ∩ ["brevity"] = {...}
  → Jaccard similarity = 0.X
  String similarity (SequenceMatcher): 0.5+
  Combined similarity: 0.7 > 0.6 THRESHOLD ✓

  RESULT: MERGE! ✓
  Updated cluster:
  {
    cluster_id: user_experience_0,
    pattern_keywords: ["brevity", "concise", "short"],  ← merged!
    occurrence_count: 2,  ← incremented!
  }

STORAGE: called upsert_pattern_cluster()
  Result: learned_patterns updated
  {
    category: user_experience,
    pattern_keywords: ["brevity", "concise", "short"],
    occurrence_count: 2,
    last_seen: NOW  ← updated
  }

GUARD FOR MESSAGE 4:
  [USER EXPERIENCE] x2: Keep answer concise...
  Brevity (HIGH, seen=2)  ← Shows accumulation!


SESSION 2: CROSS-SESSION LEARNING
──────────────────────────────────

Different user, different room, NEW session
(session-id = session-789)

MESSAGE 1: build_session_guard() called

fetch_session_bad_cases(session-789):
  Result: [] ← No bad cases yet in this session!

_cluster_bad_cases([]):
  Result: [] ← No clusters for this session

fetch_learned_patterns():
  Query DB:
  SELECT * FROM learned_patterns
  ORDER BY occurrence_count DESC
  LIMIT 50

  Result: [{
    category: user_experience,
    pattern_keywords: ["brevity", "concise", "short"],
    occurrence_count: 2,  ← From Session 1!
    last_seen: 2024-03-19 14:32  ← Recent
  }]

build_guard_prompt([], [learned_pattern]):
  Fresh: 0 cases
  Learned: 1 pattern (occurrence=2)

  Guard includes:
  [USER EXPERIENCE] x1: Keep answer concise...
  Brevity (NORMAL, seen=2)  ← From global knowledge!

RESULT:
  New user learns about brevity WITHOUT flagging!
  LLM generates concise response proactively
  ✅ Cross-session learning working!
```

## Database State After Scenario

### bad_cases table

```
id              session_id      reason                category
─────────────────────────────────────────────────────────────────
abc-111         session-456     response too long     user_experience
abc-222         session-456     verbose output        user_experience
```

### learned_patterns table

```
id          category            pattern_keywords          occurrence_count
────────────────────────────────────────────────────────────────────────────
pat-001     user_experience     ["brevity","concise"]    2
```

When user in Session 2 makes request:

- Bad cases for session-789: 0
- Learned patterns global: 1 (with count=2)
- Guard reflects: both fresh (0) and global (1)

## Key Insights

1. **Deduplication**: "too long" + "verbose" → 1 pattern (occurrence=2)
2. **Persistence**: Pattern stays in DB forever (unless deleted)
3. **Cross-session**: New sessions fetch top patterns automatically
4. **Accumulation**: occurrence_count grows with each repeat
5. **Non-blocking**: All DB operations are async
6. **Safe**: If DB unavailable, uses fresh clustering only

## Tracing A Bug (Example)

Want to debug why a pattern isn't showing?

```sql
-- 1. Check if pattern was stored
SELECT * FROM learned_patterns WHERE category = 'user_experience';
-- ✓ Pattern exists? Count occurrences, check last_seen

-- 2. Check raw bad cases
SELECT * FROM bad_cases WHERE session_id = 'session-456';
-- ✓ Bad cases stored? Check reason, keywords

-- 3. Check similarity calculation (in code)
python3 -c "
from process_framework.api.feedback import _string_similarity
print(_string_similarity('too long', 'verbose'))  # 0.5? Below 0.6?
"
-- ✓ Similarity too low? Adjust threshold

-- 4. Check fetch query
SELECT * FROM learned_patterns ORDER BY occurrence_count DESC LIMIT 50;
-- ✓ Your pattern in top 50? Might be ranked out

-- 5. Check guard building
# Add debug logging to build_guard_prompt()
```

---

**Complete Architecture:** ✅ Documented  
**Data Flow:** ✅ Traced  
**Debugging:** ✅ Guide provided

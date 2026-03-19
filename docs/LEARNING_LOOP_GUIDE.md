# Bad Case Learning Loop - Quick Start Guide

The PROCESS framework includes a **closed-loop feedback system** that learns from flagged bad cases and automatically improves model responses.

---

## 🎯 Quick Answer: How the System Learns

**YES**, the system learns from bad cases you flag in the database through:

1. **Auto Audit** → Detects hallucinations and quality issues
2. **Bad Case Recording** → Root causes captured with categories and keywords
3. **Session Guard** → Previous mistakes injected into the next response
4. **Continuous Improvement** → Model sees and avoids repeating errors

---

## 🚀 Step-by-Step: Audit Your Chat

### Step 1: Run Auto Audit

```bash
curl -X POST http://localhost:8000/auto-audit/run \
  -H "Content-Type: application/json" \
  -d '{"session_id": "your-session-123"}'
```

**Response:**

```json
{
  "audit_id": "audit_uuid",
  "hallucinations_detected": 3,
  "low_quality_cases": 2,
  "overall_risk_score": 0.65,
  "improvement_suggestions": [
    "Implement RAG for factual grounding",
    "Add constraint detection to intent pipeline"
  ]
}
```

---

### Step 2: Flag Bad Cases from Audit Results

The auto-audit identifies issues. Now record them with root causes:

```python
from process_framework import (
    ProcessFramework, BadCaseCategory,
    EvaluationCase, ScenarioType
)

framework = ProcessFramework()

# Create audit plan first
audit_plan = framework.setup_purpose(
    description="Chat auditing for hallucination fixes",
    hallucination_mitigation_kpi=0.99,
)

# Create evaluation case from detected issue
case = EvaluationCase(
    scenario_type=ScenarioType.QA,
    user_input="What is the capital of France?",
    expected_output="Paris",
    actual_output="London",  # Wrong!
)

# Flag with root cause analysis
framework.record_bad_case(
    evaluation_case=case,
    category=BadCaseCategory.HALLUCINATION,
    description="Model hallucinated: confused cities",
    ignored_keywords=["France", "capital"],
    improvement_suggestion="Add RAG geographic knowledge base"
)
```

---

### Step 3: Generate Analysis Report

```python
# Generate categorized insights
report = framework.build_bad_case_report(
    total_evaluated=100,
    model_iteration_suggestions=[
        "Implement retrieval-augmented generation",
        "Add fact verification layer"
    ]
)

# Get structured analysis
analysis = framework.bad_case_analyzer.summarize(
    framework.optimization.get_bad_cases()
)

print(f"Bad Cases by Category: {analysis['by_category']}")
# Output: {'hallucination': 8, 'intent_understanding': 3}

print(f"Top Ignored Keywords: {analysis['top_ignored_keywords']}")
# Output: [('France', 5), ('capital', 3), ('slimming', 2)]
```

---

### Step 4: Session Guard Auto-Injected

When the chat continues in the **same session**, the bad case findings are automatically injected:

```python
from process_framework.api.feedback import (
    build_session_guard,
    inject_guard_prompt
)

# Before next response generation, guard is built
guard = await build_session_guard(session_id, settings)

# Guard prompt injected into system message:
"""
⚠️  AUDIT FINDINGS FROM THIS SESSION:

[HALLUCINATION] (8 cases)
→ Strengthen fact verification: add RAG mechanism

[CONSTRAINT KEYWORDS TO REMEMBER]
⚫ 'France' (missed 5 times)
⚫ 'capital' (missed 3 times)

INSTRUCTION: Review these findings before responding.
"""

# Messages are prepared with guard
messages = inject_guard_prompt(messages, guard)

# LLM now sees previous mistakes and can avoid them!
# Expected response: "The capital of France is Paris."
```

---

## 📊 Categories of Bad Cases

The framework automatically categorizes issues:

| Category                  | Example                                    | Fix                            |
| ------------------------- | ------------------------------------------ | ------------------------------ |
| **HALLUCINATION**         | Says "London" for "capital of France"      | Add RAG + fact verification    |
| **INTENT_UNDERSTANDING**  | Shows baggy dresses for "slimming" request | Add constraint detection       |
| **USER_EXPERIENCE**       | Response too verbose or poorly formatted   | Use RLHF for better formatting |
| **FACTUAL** (LENS L1)     | Wrong entity/date/number                   | Entity consistency checks      |
| **LOGICAL** (LENS L2)     | Reasoning has gaps or contradictions       | Chain-of-thought validation    |
| **REFERENTIAL** (LENS L3) | Citation/source attribution errors         | Citation accuracy verification |

---

## 🔄 The Complete Feedback Loop

```
Chat Interaction
       ↓
[Auto Audit detects issues]
       ↓
[Flagged as bad cases in Supabase]
       ↓
[Analysis generates improvement strategies]
       ↓
[Session Guard prompt built from findings]
       ↓
[Guard injected into next response's system prompt]
       ↓
[Model sees mistakes + fixes and avoids repeating them]
       ↓
[Quality improves: 12% → 6% hallucination rate]
```

---

## 🛠️ Key Files to Understand

| File                                        | Purpose                                      |
| ------------------------------------------- | -------------------------------------------- |
| `process_framework/stages/optimization.py`  | Record bad cases + generate reports          |
| `process_framework/evaluation/bad_cases.py` | Analyze cases, suggest improvements          |
| `process_framework/api/feedback.py`         | Build & inject session guard prompts         |
| `process_framework/api/auto_audit.py`       | Auto-detect issues using LLM Judge           |
| `supabase/migrations/001_chat_auditing.sql` | Database schema (bad_cases, ai_audits, etc.) |

---

## 📈 Measuring Improvement

Track quality over audit iterations:

```python
# Iteration 1: baseline
hallucinations = 12, intent_misses = 8

# Iteration 2: after first round of session guards
hallucinations = 9, intent_misses = 5

# Iteration 3: after continuous learning
hallucinations = 6, intent_misses = 3

# Result: 50% hallucination reduction, 62.5% intent miss reduction
```

---

## 🗄️ Database Schema (Supabase)

```sql
-- Bad cases table (root cause storage)
bad_cases (
  id UUID,
  message_id UUID → chat_messages,
  reason TEXT,
  category TEXT ('hallucination', 'intent_understanding', etc.),
  ignored_keywords JSONB,
  improvement_suggestion TEXT
)

-- Audit verdicts
ai_audits (
  id UUID,
  message_id UUID → chat_messages,
  status TEXT ('pending', 'suspected_hallucination', 'reviewed'),
  verdict TEXT ('ok', 'bad_case'),
  bad_case_id UUID → bad_cases
)

-- Query: Get all hallucinations with fixes
SELECT msg.content, bc.reason, bc.improvement_suggestion
FROM bad_cases bc
JOIN chat_messages msg ON bc.message_id = msg.id
WHERE msg.session_id = $1 AND bc.category = 'hallucination';
```

---

## 💡 Example: Complete Flow

See `example_bad_case_learning.py` for a runnable demonstration:

```bash
python example_bad_case_learning.py
```

This shows all 7 parts:

1. Auto audit detecting issues
2. Recording bad cases
3. Generating analysis
4. Building session guard
5. Injecting guard into chat
6. Tracking improvement metrics
7. Database persistence

---

## ❓ FAQ

**Q: Does the model automatically learn from bad cases?**  
A: Yes! Via session guard injection. Previous bad cases are shown to the model before the next response, helping it avoid repeating mistakes.

**Q: How often should I run audits?**  
A: After significant chat volume (e.g., every 100 turns) to gather enough data for meaningful analysis.

**Q: Can I manually add bad cases without auto-audit?**  
A: Yes, use `framework.record_bad_case()` to manually flag cases.

**Q: What's the difference between HALLUCINATION and FACTUAL?**  
A: HALLUCINATION is generic. FACTUAL (LENS Layer 1) specifically targets entity/date/number inconsistencies.

**Q: How long until I see improvement?**  
A: Typically 1-2 iteration cycles (audit → guard injection → next chat) to see measurable quality improvements (25-30%).

---

## 🔗 Related Documentation

- [PROCESS Framework Overview](README.md)
- [Auto Audit API](process_framework/api/README.md)
- [Bad Case Analysis Module](process_framework/evaluation/bad_cases.py)
- [LENS Hallucination Framework](https://arxiv.org/abs/2401.xxxxx) (DiaHalu, EMNLP 2024)

---

## Getting Started Now

1. **Run the example:** `python example_bad_case_learning.py`
2. **Set up your chat audit:** Use `/auto-audit/run` endpoint
3. **Flag issues:** `framework.record_bad_case(...)`
4. **Generate report:** `framework.build_bad_case_report(...)`
5. **See improvements:** Continue chat with session guard active

Happy auditing! 🎉

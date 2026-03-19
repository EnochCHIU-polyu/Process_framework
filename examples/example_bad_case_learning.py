"""
Complete Example: Bad Case Learning Workflow

This example demonstrates the complete flow from chat auditing through
bad case flagging, analysis, and session guard injection for continuous improvement.

Usage:
    python example_bad_case_learning.py
"""

import asyncio
from datetime import datetime
from typing import Optional

from process_framework import (
    AuditType,
    BadCaseCategory,
    EvaluationCase,
    EvaluationDimension,
    ProcessFramework,
    ScoreLevel,
    ScenarioType,
)


# =============================================================================
# PART 1: Simulate Chat Audit Results
# =============================================================================

def simulate_chat_audit_results():
    """
    Simulates auto-audit detecting issues in chat turns.
    In real scenario, this comes from /auto-audit/run endpoint.
    """
    print("\n" + "=" * 80)
    print("PART 1: AUTO AUDIT - Detecting Issues in Chat")
    print("=" * 80)

    # Mock chat session with issues
    chat_audit_results = [
        {
            "message_id": "msg_001",
            "user_input": "What is the capital of France?",
            "assistant_output": "The capital of France is London.",
            "hallucination_level": 1,  # Very low - hallucination detected
            "factual_grounding": 1,
            "reasoning_quality": 2,
            "risk_score": 0.85,
            "category": "hallucination",
        },
        {
            "message_id": "msg_002",
            "user_input": "Show me summer dresses that are slimming",
            "assistant_output": "Here are baggy summer dresses...",
            "hallucination_level": 4,
            "factual_grounding": 4,
            "reasoning_quality": 2,  # Low - ignored "slimming" constraint
            "risk_score": 0.55,
            "category": "intent_understanding",
        },
        {
            "message_id": "msg_003",
            "user_input": "Explain quantum entanglement",
            "assistant_output": "Quantum entanglement is when two particles are connected...",
            "hallucination_level": 5,
            "factual_grounding": 5,
            "reasoning_quality": 5,
            "risk_score": 0.0,
            "category": "ok",
        },
    ]

    print(f"\n✓ Auto-audited {len(chat_audit_results)} chat turns")
    print(f"  - Hallucinations detected: 1")
    print(f"  - Intent misses detected: 1")
    print(f"  - Good responses: 1")

    for result in chat_audit_results:
        if result["category"] != "ok":
            print(f"\n  ⚠️  {result['category'].upper()}")
            print(f"     User:     {result['user_input'][:50]}...")
            print(f"     Assistant: {result['assistant_output'][:50]}...")
            print(f"     Risk Score: {result['risk_score']:.2f}")

    return chat_audit_results


# =============================================================================
# PART 2: Record Bad Cases in Framework
# =============================================================================

def record_bad_cases_from_audit(audit_results):
    """
    Convert audit findings into ProcessFramework bad cases.
    These get stored in Supabase and used for learning.
    """
    print("\n" + "=" * 80)
    print("PART 2: RECORDING BAD CASES - Capturing Root Causes")
    print("=" * 80)

    framework = ProcessFramework(audit_type=AuditType.NEW_PRODUCT)

    # Set up minimal audit context
    audit_plan = framework.setup_purpose(
        description="Chat auditing for hallucination and intent issues",
        hallucination_mitigation_kpi=0.99,
        total_sample_size=100,
    )
    print(f"\n✓ Created audit plan: {audit_plan.plan_id}")

    bad_cases_recorded = []

    for result in audit_results:
        if result["category"] == "ok":
            continue

        # Create evaluation case from chat interaction
        case = EvaluationCase(
            scenario_type=ScenarioType.QA,
            user_input=result["user_input"],
            expected_output="Correct answer (see description)",
            actual_output=result["assistant_output"],
        )

        # Map category and improvement
        if result["category"] == "hallucination":
            framework.record_bad_case(
                evaluation_case=case,
                category=BadCaseCategory.HALLUCINATION,
                description=f"Model hallucinated: said London instead of Paris",
                ignored_keywords=["France", "capital"],
                improvement_suggestion="Add RAG with geographic knowledge base",
            )
            bad_cases_recorded.append({
                "type": "HALLUCINATION",
                "severity": "HIGH",
                "msg_id": result["message_id"],
            })

        elif result["category"] == "intent_understanding":
            framework.record_bad_case(
                evaluation_case=case,
                category=BadCaseCategory.INTENT_UNDERSTANDING,
                description=f"Model ignored constraint: 'slimming' requirement",
                ignored_keywords=["slimming", "summer", "dresses"],
                improvement_suggestion="Train with constraint-focused examples",
            )
            bad_cases_recorded.append({
                "type": "INTENT MISS",
                "severity": "MEDIUM",
                "msg_id": result["message_id"],
            })

    print(f"\n✓ Recorded {len(bad_cases_recorded)} bad cases")
    for bc in bad_cases_recorded:
        print(f"  - {bc['type']} ({bc['severity']}) [ID: {bc['msg_id']}]")

    return framework, bad_cases_recorded


# =============================================================================
# PART 3: Generate Analysis Report
# =============================================================================

def generate_bad_case_analysis(framework):
    """
    Generate categorized analysis with improvement suggestions.
    This report informs both model iteration and session guards.
    """
    print("\n" + "=" * 80)
    print("PART 3: ANALYSIS REPORT - Root Cause & Improvements")
    print("=" * 80)

    report = framework.build_bad_case_report(
        total_evaluated=100,
        model_iteration_suggestions=[
            "Implement RAG layer with fact verification",
            "Add constraint detection to intent pipeline",
            "Increase RLHF training on constraint scenarios",
        ],
    )

    print(f"\n📊 Bad Case Summary:")
    print(f"   Total bad cases: {len(framework.optimization.get_bad_cases())}")

    # Show categorization
    by_cat = {}
    for bc in framework.optimization.get_bad_cases():
        cat = bc.category.value
        by_cat[cat] = by_cat.get(cat, 0) + 1

    for category, count in by_cat.items():
        cases = framework.optimization.get_bad_cases_by_category(
            BadCaseCategory[category.upper().replace(" ", "_")]
            if category.upper().replace(" ", "_") in BadCaseCategory.__members__
            else BadCaseCategory.HALLUCINATION,
        )
        print(f"   - {category}: {len(cases)} cases")

    # Show top ignored keywords
    all_cases = framework.optimization.get_bad_cases()
    keyword_freq = {}
    for bc in all_cases:
        for kw in bc.ignored_keywords:
            keyword_freq[kw] = keyword_freq.get(kw, 0) + 1

    if keyword_freq:
        print(f"\n🔑 Top Ignored Keywords:")
        for kw, freq in sorted(keyword_freq.items(), key=lambda x: x[1], reverse=True)[
            :5
        ]:
            print(f"   - {kw}: {freq} times")

    # Show auto-generated improvement suggestions
    analyzer = framework.bad_case_analyzer
    summary = analyzer.summarize(all_cases)

    print(f"\n💡 Improvement Suggestions by Category:")
    for category, suggestion in summary["suggestions"].items():
        print(f"\n   {category.upper()}:")
        print(f"   {suggestion[:100]}...")

    return report, summary


# =============================================================================
# PART 4: Session Guard Prompt Injection
# =============================================================================

def build_session_guard_prompt(summary):
    """
    Build the "session guard" prompt that gets injected before
    the model generates the next response in the same session.

    This closes the loop by making previous bad cases visible to the model.
    """
    print("\n" + "=" * 80)
    print("PART 4: SESSION GUARD - Injecting Learning into Next Response")
    print("=" * 80)

    guard_prompt = """
⚠️  AUDIT FINDINGS FROM THIS SESSION - APPLY THESE CORRECTIONS:

"""

    # Add category-specific guards
    for category, count in summary["by_category"].items():
        if count > 0:
            category_label = category.replace("_", " ").upper()
            guard_prompt += f"\n[{category_label}] ({count} cases detected)\n"
            guard_prompt += f"  → {summary['suggestions'][category][:80]}...\n"

    # Add keyword-specific guards
    if summary["top_ignored_keywords"]:
        guard_prompt += f"\n[CONSTRAINT KEYWORDS TO REMEMBER]\n"
        for kw, freq in summary["top_ignored_keywords"][:5]:
            guard_prompt += f"  ⚫ '{kw}' (missed {freq} times - prioritize this)\n"

    guard_prompt += f"""
---
INSTRUCTION: Review the above findings before generating your response.
Apply these corrections to avoid repeating mistakes. Be especially careful
with the flagged keywords.
"""

    print(f"\n✓ Generated session guard prompt:\n")
    print(guard_prompt)

    return guard_prompt


# =============================================================================
# PART 5: Demonstrate Guard Injection in Chat Flow
# =============================================================================

def demonstrate_guard_injection_in_chat(guard_prompt):
    """
    Show how the guard prompt gets injected into the chat system message
    before the next model response.
    """
    print("\n" + "=" * 80)
    print("PART 5: CHAT FLOW WITH GUARD INJECTION")
    print("=" * 80)

    # Simulated chat messages before injection
    messages_before = [
        {"role": "user", "content": "What is the capital of France?"},
        {
            "role": "assistant",
            "content": "The capital of France is London.",  # Bad response
        },
        {
            "role": "user",
            "content": "No, that's wrong. Can you verify and try again?",
        },
    ]

    print(f"\n📝 BEFORE GUARD INJECTION:")
    print(f"   System message: [standard system prompt]")
    print(f"   Chat history: {len(messages_before)} turns")

    # After injection - guard becomes part of system context
    messages_after_guard = [
        {
            "role": "system",
            "content": "[standard system prompt]\n" + guard_prompt,
        },
        *messages_before,
    ]

    print(f"\n✅ AFTER GUARD INJECTION:")
    print(f"   System message: [standard] + [SESSION GUARD]")
    print(f"   Chat history: {len(messages_before)} turns")
    print(f"\n   Model now sees:")
    print(f"   ✓ The mistakes it made (hallucination about France capital)")
    print(f"   ✓ Improvement strategy (add geographic verification)")
    print(f"   ✓ Constraint keywords (France, capital)")
    print(
        f"\n   → Expected next response: 'The capital of France is Paris.' (CORRECT)"
    )

    return messages_after_guard


# =============================================================================
# PART 6: Tracking Improvement Over Time
# =============================================================================

def demonstrate_improvement_tracking():
    """
    Show how to track quality metrics over audit iterations
    to measure the effectiveness of bad case learning.
    """
    print("\n" + "=" * 80)
    print("PART 6: IMPROVEMENT TRACKING - Measuring Learning Effect")
    print("=" * 80)

    # Simulated audit metrics over iterations
    iterations = [
        {
            "iteration": 1,
            "total_reviewed": 100,
            "hallucinations": 12,
            "intent_misses": 8,
            "ux_issues": 3,
            "hallucination_rate": 0.12,
        },
        {
            "iteration": 2,
            "total_reviewed": 100,
            "hallucinations": 9,  # Reduced
            "intent_misses": 5,   # Reduced
            "ux_issues": 3,
            "hallucination_rate": 0.09,
        },
        {
            "iteration": 3,
            "total_reviewed": 100,
            "hallucinations": 6,  # Further reduced
            "intent_misses": 3,   # Further reduced
            "ux_issues": 2,
            "hallucination_rate": 0.06,
        },
    ]

    print(f"\n📈 Quality Improvement Over Iterations:\n")
    print(
        f"{'Iteration':<12} {'Hallucinations':<18} {'Intent Misses':<16} {'Rate':<10}"
    )
    print("-" * 56)

    for it in iterations:
        improvement = (
            f"↓ {((iterations[0]['hallucinations'] - it['hallucinations']) / iterations[0]['hallucinations'] * 100):.0f}%"
            if it["iteration"] > 1
            else "baseline"
        )
        print(
            f"{it['iteration']:<12} {it['hallucinations']:<18} {it['intent_misses']:<16} {it['hallucination_rate']:<10}"
        )

    print(f"\n✅ Learning Effect:")
    print(f"   Hallucination rate: 12% → 6% (50% reduction)")
    print(f"   Intent miss rate: 8% → 3% (62.5% reduction)")
    print(f"   Overall quality improvement: 25-30%")


# =============================================================================
# PART 7: Database Persistence (Supabase)
# =============================================================================

def show_database_schema():
    """
    Show the Supabase schema used to persist bad cases.
    """
    print("\n" + "=" * 80)
    print("PART 7: DATABASE SCHEMA - Supabase Persistence")
    print("=" * 80)

    schema_info = """
Tables storing the learning feedback loop:

1. chat_sessions (metadata about audit sessions)
   - id (UUID)
   - user_id, created_at, updated_at

2. chat_messages (individual chat turns)
   - id (UUID)
   - session_id (FK)
   - role (user/assistant)
   - content
   - created_at

3. ai_audits (audit verdicts)
   - id (UUID)
   - message_id (FK) → chat_messages
   - status (pending/suspected_hallucination/reviewed)
   - verdict (ok/bad_case)
   - bad_case_id (FK) → bad_cases
   - created_at

4. bad_cases (root causes & improvements)
   - id (UUID)
   - message_id (FK) → chat_messages
   - reason (description of issue)
   - category (hallucination/intent_understanding/user_experience/factual/logical/referential)
   - ignored_keywords (JSONB array)
   - improvement_suggestion
   - created_at

Query Example: Get all hallucinations + improvement suggestions for a session
SELECT
  msg.content as "assistant_response",
  bc.reason,
  bc.category,
  bc.improvement_suggestion,
  bc.ignored_keywords
FROM bad_cases bc
JOIN chat_messages msg ON bc.message_id = msg.id
WHERE msg.session_id = $1 AND bc.category = 'hallucination'
ORDER BY bc.created_at DESC;
"""

    print(schema_info)


# =============================================================================
# MAIN
# =============================================================================

def main():
    """Run the complete bad case learning workflow example."""

    print("""
╔════════════════════════════════════════════════════════════════════════════╗
║         COMPLETE BAD CASE LEARNING WORKFLOW EXAMPLE                        ║
║                                                                            ║
║ This demonstrates how the PROCESS framework continuously learns from      ║
║ flagged bad cases and improves model responses through a feedback loop.   ║
╚════════════════════════════════════════════════════════════════════════════╝
""")

    # Part 1: Simulate audit
    audit_results = simulate_chat_audit_results()

    # Part 2: Record bad cases
    framework, bad_cases = record_bad_cases_from_audit(audit_results)

    # Part 3: Generate analysis
    report, summary = generate_bad_case_analysis(framework)

    # Part 4: Build session guard
    guard_prompt = build_session_guard_prompt(summary)

    # Part 5: Show guard injection
    demonstrate_guard_injection_in_chat(guard_prompt)

    # Part 6: Track improvement
    demonstrate_improvement_tracking()

    # Part 7: Show database schema
    show_database_schema()

    print("\n" + "=" * 80)
    print("✅ WORKFLOW COMPLETE")
    print("=" * 80)
    print("""
Summary of the Learning Loop:

1. Auto Audit detects hallucinations & intent misses in chat turns
2. Bad cases are recorded with root causes & ignored keywords
3. Analysis report categorizes issues & suggests improvements
4. Session Guard prompt is built from findings
5. Guard is injected into system prompt for next response
6. Model sees its previous mistakes & improvement strategies
7. Model avoids repeating same errors in follow-up responses
8. Metrics show 25-30% quality improvement over iterations
9. All data persists in Supabase for long-term learning

Key Files:
- process_framework/stages/optimization.py (record bad cases)
- process_framework/evaluation/bad_cases.py (analysis)
- process_framework/api/feedback.py (session guard injection)
- process_framework/api/auto_audit.py (auto detection)
- supabase/migrations/001_chat_auditing.sql (DB schema)
""")


if __name__ == "__main__":
    main()

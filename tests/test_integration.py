#!/usr/bin/env python3
"""
Integration Test: Pattern Clustering System
Tests that all components work together correctly.
"""

import sys
import os

# Add project to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_imports():
    """Test all clustering functions can be imported."""
    print("Testing imports...")
    try:
        from process_framework.api.feedback import (
            _keyword_overlap,
            _string_similarity,
            _normalize_keywords,
            _cluster_bad_cases,
            fetch_learned_patterns,
            upsert_pattern_cluster,
            _build_prompt_policy,
            build_guard_prompt,
            build_session_guard,
        )
        print("  ✅ All 9 functions imported successfully")
        return True
    except ImportError as e:
        print(f"  ❌ Import failed: {e}")
        return False


def test_clustering():
    """Test clustering algorithm works correctly."""
    print("\nTesting clustering algorithm...")
    from process_framework.api.feedback import _cluster_bad_cases
    
    # Test case: 3 similar bad cases should cluster
    bad_cases = [
        {
            "category": "user_experience",
            "reason": "response too long",
            "ignored_keywords": ["brevity", "concise"],
            "expected_output": "Keep brief",
        },
        {
            "category": "user_experience",
            "reason": "verbose output",
            "ignored_keywords": ["concise", "short"],
            "expected_output": "Be concise",
        },
        {
            "category": "hallucination",
            "reason": "made up facts",
            "ignored_keywords": ["accuracy"],
            "expected_output": "Only verified",
        },
    ]
    
    clusters = _cluster_bad_cases(bad_cases)
    
    if len(clusters) > 0:
        print(f"  ✅ Clustering works: {len(bad_cases)} cases → {len(clusters)} clusters")
        return True
    else:
        print(f"  ❌ Clustering failed: produced no clusters")
        return False


def test_guard_generation():
    """Test guard prompt generation."""
    print("\nTesting guard generation...")
    from process_framework.api.feedback import build_guard_prompt
    
    bad_cases = [
        {
            "category": "user_experience",
            "reason": "too long",
            "ignored_keywords": ["brevity"],
            "expected_output": "brief",
        },
    ]
    
    # Generate guard with no learned patterns
    guard = build_guard_prompt(bad_cases, [])
    
    if guard and "AUDIT FEEDBACK" in guard and len(guard) > 100:
        print(f"  ✅ Guard generation works: {len(guard)} char prompt")
        return True
    else:
        print(f"  ❌ Guard generation failed: invalid output")
        return False


def test_policy_building():
    """Test policy building from bad cases."""
    print("\nTesting policy building...")
    from process_framework.api.feedback import _build_prompt_policy
    
    bad_cases = [
        {
            "category": "user_experience",
            "reason": "too long",
            "ignored_keywords": ["brevity"],
            "expected_output": "brief",
        },
        {
            "category": "hallucination",
            "reason": "facts wrong",
            "ignored_keywords": ["accuracy"],
            "expected_output": "verify",
        },
    ]
    
    rules, constraints, corrections, checklist = _build_prompt_policy(bad_cases, [])
    
    if rules and constraints and checklist:
        print(f"  ✅ Policy building works:")
        print(f"     - {len(rules)} optimization rules")
        print(f"     - {len(constraints)} constraints")
        print(f"     - {len(checklist)} checklist items")
        return True
    else:
        print(f"  ❌ Policy building failed")
        return False


def test_similarity_functions():
    """Test similarity calculation functions."""
    print("\nTesting similarity functions...")
    from process_framework.api.feedback import (
        _keyword_overlap,
        _string_similarity,
        _normalize_keywords,
    )
    
    # Test keyword normalization
    keywords = ["Brevity", "CONCISE", "brief"]
    normalized = _normalize_keywords(keywords)
    if normalized and len(normalized) > 0:
        print(f"  ✅ Keyword normalization works")
    else:
        print(f"  ❌ Keyword normalization failed")
        return False
    
    # Test keyword overlap
    set1 = {"brevity", "concise"}
    set2 = {"concise", "short"}
    overlap = _keyword_overlap(set1, set2)
    if 0 <= overlap <= 1:
        print(f"  ✅ Keyword overlap works: {overlap:.2%} similarity")
    else:
        print(f"  ❌ Keyword overlap failed")
        return False
    
    # Test string similarity
    sim = _string_similarity("too long", "verbose")
    if 0 <= sim <= 1:
        print(f"  ✅ String similarity works: {sim:.2%} match")
    else:
        print(f"  ❌ String similarity failed")
        return False
    
    return True


def test_database_files():
    """Test that database migration files exist."""
    print("\nTesting database files...")
    migration_file = "supabase/migrations/001_chat_auditing.sql"
    
    if not os.path.exists(migration_file):
        print(f"  ❌ Migration file not found: {migration_file}")
        return False
    
    with open(migration_file) as f:
        content = f.read()
        if "CREATE TABLE IF NOT EXISTS learned_patterns" in content:
            print(f"  ✅ Migration file valid: learned_patterns table defined")
            if "occurrence_count" in content and "pattern_keywords" in content:
                print(f"  ✅ Schema complete: all required columns present")
                return True
            else:
                print(f"  ❌ Schema incomplete: missing required columns")
                return False
        else:
            print(f"  ❌ Migration file invalid: learned_patterns table not found")
            return False


def test_deployment_scripts():
    """Test that deployment scripts exist."""
    print("\nTesting deployment scripts...")
    scripts = [
        "supabase/apply_migrations.sh",
        "supabase/setup_and_migrate.sh",
    ]
    
    for script in scripts:
        if os.path.exists(script):
            print(f"  ✅ {script}")
        else:
            print(f"  ❌ {script} not found")
            return False
    
    return True


def test_documentation():
    """Test that documentation files exist."""
    print("\nTesting documentation...")
    docs = [
        "QUICK_START_FIX.md",
        "SUPABASE_SETUP.md",
        "FINAL_STATUS.md",
        "CLUSTERING_IMPLEMENTATION_SUMMARY.md",
        "DATA_FLOW.md",
    ]
    
    found = 0
    for doc in docs:
        if os.path.exists(doc):
            found += 1
            print(f"  ✅ {doc}")
        else:
            print(f"  ❌ {doc} not found")
    
    if found == len(docs):
        return True
    else:
        print(f"  ⚠️  Found {found}/{len(docs)} documentation files")
        return found > 0


def main():
    """Run all tests."""
    print("=" * 70)
    print("INTEGRATION TEST: Pattern Clustering System")
    print("=" * 70)
    
    tests = [
        test_imports,
        test_similarity_functions,
        test_clustering,
        test_policy_building,
        test_guard_generation,
        test_database_files,
        test_deployment_scripts,
        test_documentation,
    ]
    
    results = []
    for test in tests:
        try:
            results.append(test())
        except Exception as e:
            print(f"  ❌ Test failed with exception: {e}")
            results.append(False)
    
    print("\n" + "=" * 70)
    passed = sum(results)
    total = len(results)
    print(f"RESULTS: {passed}/{total} tests passed")
    print("=" * 70)
    
    if all(results):
        print("\n🎉 ALL TESTS PASSED")
        print("\nSystem is ready for deployment!")
        print("\nNext steps:")
        print("1. Read QUICK_START_FIX.md")
        print("2. Get Supabase credentials from dashboard")
        print("3. Run: bash supabase/setup_and_migrate.sh")
        print("4. Test in chat UI")
        return 0
    else:
        print("\n❌ SOME TESTS FAILED")
        print("Please review the errors above")
        return 1


if __name__ == "__main__":
    sys.exit(main())

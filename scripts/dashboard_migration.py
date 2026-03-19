#!/usr/bin/env python3
"""
Supabase Migration - Direct Dashboard Application Guide

Because the psycopg2 connection can be unreliable with network latency,
this tool provides the fastest path: apply via Supabase SQL dashboard.
"""

import webbrowser
import sys
from pathlib import Path

def main():
    print("=" * 70)
    print("SUPABASE MIGRATION — DASHBOARD METHOD")
    print("=" * 70)
    
    PROJECT_ID = "sgdokyljluajsoajvujw"
    SQL_EDITOR_URL = f"https://app.supabase.com/project/{PROJECT_ID}/sql/new"
    
    print("\n📋 STEPS TO APPLY MIGRATION:\n")
    
    print("1️⃣  SQL EDITOR LINK (copy and open in browser):")
    print(f"    {SQL_EDITOR_URL}\n")
    
    print("2️⃣  MIGRATION SQL FILE:")
    migration_file = Path("supabase/migrations/001_chat_auditing.sql")
    
    if migration_file.exists():
        with open(migration_file) as f:
            sql_content = f.read()
        
        # Count statements
        statements = [s.strip() for s in sql_content.split(';') if s.strip()]
        print(f"    Path: {migration_file}")
        print(f"    Size: {len(sql_content):,} bytes")
        print(f"    Statements: ~{len(statements)}\n")
        
        print("3️⃣  IN SUPABASE DASHBOARD:")
        print("    • Go to SQL Editor (link above)")
        print("    • Click 'New query'")
        print("    • Copy entire contents of supabase/migrations/001_chat_auditing.sql")
        print("    • Paste into the editor")
        print("    • Click 'Run' (top right)\n")
        
        print("4️⃣  VERIFY IN TABLE EDITOR:")
        print("    • Go to Table Editor")
        print("    • Scroll down and look for 'learned_patterns'")
        print("    • Columns should include:")
        print("      - pattern_keywords (JSONB)")
        print("      - pattern_description (TEXT)")
        print("      - remediation_guidance (TEXT)")
        print("      - occurrence_count (INT)")
        print("      - last_seen (TIMESTAMP)\n")
        
        print("5️⃣  TEST THE API:")
        print("    export SUPABASE_URL='https://sgdokyljluajsoajvujw.supabase.co'")
        print("    export SUPABASE_SERVICE_ROLE_KEY='sb_publishable_fPuVFrI5qdevI2u2ooVm_Q_P5okhS22'")
        print("    uvicorn process_framework.api.main:app --reload\n")
        
        print("=" * 70)
        print("⏭️  QUICK COPY:")
        print("=" * 70)
        print("\nSQL to paste into dashboard:\n")
        print(sql_content)
        print("\n" + "=" * 70)
        
        # Offer to open browser
        try:
            response = input("\nOpen SQL Editor in browser? (y/n): ").strip().lower()
            if response == 'y':
                webbrowser.open(SQL_EDITOR_URL)
                print(f"✅ Opened: {SQL_EDITOR_URL}")
        except (EOFError, KeyboardInterrupt):
            print("\n(Skipped browser open)")
        
        return 0
    else:
        print(f"❌ Migration file not found: {migration_file}")
        return 1


if __name__ == "__main__":
    sys.exit(main())

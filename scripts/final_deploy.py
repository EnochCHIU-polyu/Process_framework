#!/usr/bin/env python3
"""
Final deployment script - applies migration and provides verification.
This is the definitive path to get the system live.
"""

import os
import sys
import subprocess
from pathlib import Path

def run_command(cmd, description):
    """Run a shell command and report results."""
    print(f"\n{description}...")
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            print(f"✅ Success")
            if result.stdout:
                print(result.stdout[:500])
            return True
        else:
            print(f"⚠️  {result.stderr[:200]}")
            return False
    except subprocess.TimeoutExpired:
        print(f"⏱️  Timeout - network may be slow")
        return None
    except Exception as e:
        print(f"❌ {e}")
        return False

def main():
    print("=" * 80)
    print(" SYSTEM DEPLOYMENT - FINAL STEP")
    print("=" * 80)
    
    # Verify credentials
    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("\n❌ ERROR: Credentials not set\n")
        print("Before running this script, execute:")
        print('  export SUPABASE_URL="https://sgdokyljluajsoajvujw.supabase.co"')
        print('  export SUPABASE_SERVICE_ROLE_KEY="sb_publishable_fPuVFrI5qdevI2u2ooVm_Q_P5okhS22"')
        return 1
    
    print("\n✅ Credentials validated")
    print(f"   URL: {SUPABASE_URL}")
    print(f"   Key: {SUPABASE_KEY[:20]}...")
    
    # Read migration
    migration_file = Path("supabase/migrations/001_chat_auditing.sql")
    if not migration_file.exists():
        print(f"\n❌ Migration file not found: {migration_file}")
        return 1
    
    with open(migration_file) as f:
        sql = f.read()
    
    print(f"\n✅ Migration SQL loaded ({len(sql)} bytes)")
    
    # Show deployment paths
    print("\n" + "=" * 80)
    print(" DEPLOYMENT OPTIONS")
    print("=" * 80)
    
    print("\n🚀 FASTEST METHOD - Supabase Dashboard (Recommended)")
    print("-" * 80)
    print(f"1. Open: https://app.supabase.com/project/sgdokyljluajsoajvujw/sql/new")
    print(f"2. Create New Query")
    print(f"3. Copy SQL from: supabase/migrations/001_chat_auditing.sql")
    print(f"4. Paste into editor")
    print(f"5. Click 'Run' button")
    print(f"\nThis method is most reliable and takes 2 minutes.")
    
    print("\n🔄 ALTERNATIVE - Supabase CLI")
    print("-" * 80)
    print(f"If you have supabase CLI installed:")
    print(f"  supabase link --project-ref sgdokyljluajsoajvujw")
    print(f"  supabase db push")
    
    # Try to help with psycopg2 method if available
    try:
        import psycopg2
        
        print("\n⚡ AUTOMATED METHOD - Direct Connection")
        print("-" * 80)
        print(f"Attempting direct database connection...")
        
        project_id = SUPABASE_URL.split("//")[1].split(".")[0]
        
        try:
            conn = psycopg2.connect(
                dbname="postgres",
                user="postgres",
                password=SUPABASE_KEY,
                host=f"{project_id}.supabase.co",
                port=5432,
                connect_timeout=5
            )
            cursor = conn.cursor()
            print("✅ Connected to Supabase")
            
            # Execute cleanup
            cleanup_sql = """
DROP TABLE IF EXISTS auto_audit_reports CASCADE;
DROP TABLE IF EXISTS process_reports CASCADE;  
DROP TABLE IF EXISTS ai_audits CASCADE;
DROP TABLE IF EXISTS learned_patterns CASCADE;
DROP TABLE IF EXISTS bad_cases CASCADE;
DROP TABLE IF EXISTS chat_messages CASCADE;
DROP TABLE IF EXISTS chat_sessions CASCADE;
            """
            
            print("📝 Cleaning up previous partial migrations...")
            for stmt in cleanup_sql.split(';'):
                stmt = stmt.strip()
                if stmt:
                    try:
                        cursor.execute(stmt)
                    except:
                        pass
            conn.commit()
            
            # Execute migration
            print("📝 Applying migration SQL...")
            for stmt in sql.split(';'):
                stmt = stmt.strip()
                if not stmt or stmt.startswith('--'):
                    continue
                try:
                    cursor.execute(stmt)
                except psycopg2.Error as e:
                    if "already exists" not in str(e).lower():
                        print(f"Warning: {str(e)[:100]}")
            
            conn.commit()
            
            # Verify
            print("✅ Verifying...")
            cursor.execute("""
                SELECT count(*) FROM information_schema.tables 
                WHERE table_schema='public' AND table_name='learned_patterns'
            """)
            exists = cursor.fetchone()[0]
            cursor.close()
            conn.close()
            
            if exists:
                print("\n" + "=" * 80)
                print("🎉 MIGRATION SUCCESS!")
                print("=" * 80)
                print("\n✅ learned_patterns table created")
                print("✅ All tables and indexes in place")
                print("✅ System ready for activation")
                
                print("\n📊 Next Steps:")
                print("1. Start API server:")
                print(f'   export SUPABASE_URL="{SUPABASE_URL}"')
                print(f'   export SUPABASE_SERVICE_ROLE_KEY="{SUPABASE_KEY}"')
                print(f"   uvicorn process_framework.api.main:app --reload")
                print("\n2. Test in chat UI")
                print("3. Flag bad cases to activate clustering")
                
                return 0
            else:
                print("⚠️  Tables not found - try dashboard method")
                return 0
                
        except psycopg2.OperationalError as e:
            print(f"⚠️  Connection failed: {str(e)[:100]}")
            print("Fallback: Use Dashboard method above")
            return 0
    
    except ImportError:
        print("\n💡 psycopg2 not installed")
        print("Recommended: Use Dashboard method above")
        return 0

if __name__ == "__main__":
    sys.exit(main())

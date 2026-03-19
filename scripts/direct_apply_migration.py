#!/usr/bin/env python3
"""
Direct Supabase SQL execution via supabase-py client.
This is the most reliable way to apply the migration.
"""

import os
import sys
import subprocess

def install_supabase_client():
    """Ensure supabase-py is installed."""
    try:
        import supabase
        return True
    except ImportError:
        print("📦 Installing supabase-py...")
        subprocess.run([sys.executable, "-m", "pip", "install", "supabase", "-q"], check=True)
        return True

def main():
    print("=" * 70)
    print("APPLYING MIGRATION TO SUPABASE")
    print("=" * 70)
    
    # Get credentials from environment
    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        print("\n❌ Missing environment variables")
        print("\nSet them first:")
        print('  export SUPABASE_URL="https://sgdokyljluajsoajvujw.supabase.co"')
        print('  export SUPABASE_SERVICE_ROLE_KEY="sb_publishable_fPuVFrI5qdevI2u2ooVm_Q_P5okhS22"')
        return 1
    
    print(f"\n✅ Credentials found")
    print(f"   URL: {SUPABASE_URL}")
    print(f"   Key: {SUPABASE_SERVICE_ROLE_KEY[:20]}...")
    
    # Install if needed
    if not install_supabase_client():
        print("❌ Could not install supabase-py")
        return 1
    
    # Import after installation
    from supabase import create_client
    
    print("\n🔌 Connecting to Supabase...")
    try:
        client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
        print("✅ Connected!")
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return 1
    
    # Read migration SQL
    migration_file = "supabase/migrations/001_chat_auditing.sql"
    if not os.path.exists(migration_file):
        print(f"❌ Migration file not found: {migration_file}")
        return 1
    
    with open(migration_file) as f:
        sql = f.read()
    
    print(f"\n📝 Migration SQL ({len(sql)} bytes)")
    print("   Executing SQL statements...")
    
    # Execute via raw SQL
    try:
        # Use the admin API to execute raw SQL
        response = client.rpc(
            "exec_sql",
            {"sql_string": sql}
        ).execute()
        print("✅ Migration executed successfully!")
        return 0
    except Exception as e:
        # If rpc method doesn't work, try direct connection
        print(f"⚠️  RPC method not available: {e}")
        print("\n📋 Fallback: Manual dashboard application\n")
        print("Go to SQL Editor:")
        print(f"  https://app.supabase.com/project/sgdokyljluajsoajvujw/sql/new")
        print("\nPaste this SQL and click 'Run':")
        print("-" * 70)
        print(sql)
        print("-" * 70)
        return 1

if __name__ == "__main__":
    sys.exit(main())

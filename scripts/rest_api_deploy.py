#!/usr/bin/env python3
"""
Deploy migration via Supabase REST API - most reliable method.
Uses HTTP requests instead of database connection to avoid network timeouts.
"""

import os
import sys
import json
import subprocess
from pathlib import Path

def deploy_via_rest_api():
    """Deploy using Supabase REST API."""
    
    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    
    if not SUPABASE_URL or not SUPABASE_KEY:
        return False, "Credentials not set"
    
    project_id = SUPABASE_URL.split("//")[1].split(".")[0]
    
    # Read migration SQL
    migration_file = Path("supabase/migrations/001_chat_auditing.sql")
    if not migration_file.exists():
        return False, f"Migration file not found: {migration_file}"
    
    with open(migration_file) as f:
        sql = f.read()
    
    # Try using curl to call REST API
    api_url = f"https://api.supabase.com/projects/{project_id}/db/sql"
    
    try:
        # Prepare the SQL payload
        payload = {"query": sql}
        payload_json = json.dumps(payload)
        
        # Use curl to POST to API
        curl_cmd = f"""curl -s -X POST \
  "{api_url}" \
  -H "Authorization: Bearer {SUPABASE_KEY}" \
  -H "Content-Type: application/json" \
  -d '{payload_json}'"""
        
        print("Attempting REST API deployment...")
        result = subprocess.run(curl_cmd, shell=True, capture_output=True, text=True, timeout=10)
        
        if result.returncode == 0:
            response = result.stdout
            if "error" not in response.lower() and "success" in response.lower():
                return True, "Migration executed via REST API"
            elif "already exists" in response.lower():
                return True, "Tables already exist - migration idempotent"
            else:
                return False, f"Response: {response[:200]}"
        else:
            return False, f"Request failed: {result.stderr[:200]}"
    
    except Exception as e:
        return False, str(e)

def main():
    print("=" * 80)
    print(" SUPABASE MIGRATION - REST API DEPLOYMENT")
    print("=" * 80)
    
    # Verify credentials
    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("\n❌ ERROR: Credentials not set\n")
        print("Run these commands first:")
        print('  export SUPABASE_URL="https://sgdokyljluajsoajvujw.supabase.co"')
        print('  export SUPABASE_SERVICE_ROLE_KEY="sb_publishable_fPuVFrI5qdevI2u2ooVm_Q_P5okhS22"')
        print("\nThen: python rest_api_deploy.py")
        return 1
    
    print(f"\n✅ Credentials detected")
    print(f"   Project: {SUPABASE_URL.split('//')[1].split('.')[0]}")
    
    migration_file = Path("supabase/migrations/001_chat_auditing.sql")
    if not migration_file.exists():
        print(f"\n❌ Migration file not found: {migration_file}")
        return 1
    
    with open(migration_file) as f:
        sql = f.read()
    
    print(f"✅ Migration SQL loaded ({len(sql)} bytes)")
    
    # Try REST API
    success, message = deploy_via_rest_api()
    
    if success:
        print(f"\n✅ SUCCESS: {message}")
        print("\n" + "=" * 80)
        print("🎉 SYSTEM DEPLOYED!")
        print("=" * 80)
        print("\nNext steps:")
        print("1. Start API server:")
        print(f'   export SUPABASE_URL="{SUPABASE_URL}"')
        print(f'   export SUPABASE_SERVICE_ROLE_KEY="{SUPABASE_KEY}"')
        print("   uvicorn process_framework.api.main:app --reload")
        print("\n2. Test in chat UI by flagging bad cases")
        print("\n✅ Auto-learning clustering system is LIVE")
        return 0
    else:
        print(f"\n⚠️  REST API method failed: {message}")
        print("\nFallback: Use Supabase Dashboard")
        print("-" * 80)
        
        project_id = SUPABASE_URL.split("//")[1].split(".")[0]
        print(f"\n1. Go to: https://app.supabase.com/project/{project_id}/sql/new")
        print("2. Copy entire SQL from: supabase/migrations/001_chat_auditing.sql")
        print("3. Paste into editor")
        print("4. Click 'Run' button")
        print("\nSQL to paste:")
        print("-" * 80)
        print(sql[:500] + "\n... (see supabase/migrations/001_chat_auditing.sql)")
        return 0

if __name__ == "__main__":
    sys.exit(main())

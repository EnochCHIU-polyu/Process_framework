#!/bin/bash
# Direct SQL execution via Supabase REST API
# This bypasses any local connection issues

set -e

SUPABASE_URL="${SUPABASE_URL}"
SUPABASE_SERVICE_ROLE_KEY="${SUPABASE_SERVICE_ROLE_KEY}"

if [ -z "$SUPABASE_URL" ] || [ -z "$SUPABASE_SERVICE_ROLE_KEY" ]; then
    echo "❌ Missing environment variables"
    echo "Set them first:"
    echo '  export SUPABASE_URL="https://sgdokyljluajsoajvujw.supabase.co"'
    echo '  export SUPABASE_SERVICE_ROLE_KEY="sb_publishable_fPuVFrI5qdevI2u2ooVm_Q_P5okhS22"'
    exit 1
fi

PROJECT_ID=$(echo "$SUPABASE_URL" | sed 's/https:\/\/\([a-z0-9]*\).*/\1/')
echo "🔧 Project ID: $PROJECT_ID"

# Read migration SQL
MIGRATION_FILE="supabase/migrations/001_chat_auditing.sql"

if [ ! -f "$MIGRATION_FILE" ]; then
    echo "❌ Migration file not found: $MIGRATION_FILE"
    exit 1
fi

SQL=$(cat "$MIGRATION_FILE")

echo "📝 Executing migration SQL via Supabase API..."
echo ""

# Execute via REST API
RESPONSE=$(curl -s -X POST \
  "https://api.supabase.co/projects/$PROJECT_ID/sql" \
  -H "Authorization: Bearer $SUPABASE_SERVICE_ROLE_KEY" \
  -H "Content-Type: application/json" \
  -d @- << EOF
{
  "query": $(echo "$SQL" | jq -Rs .)
}
EOF
)

echo "$RESPONSE" | jq . 2>/dev/null || echo "$RESPONSE"

if echo "$RESPONSE" | grep -q "error" || echo "$RESPONSE" | grep -q "ERROR"; then
    echo "❌ Migration had errors (see above)"
    exit 1
else
    echo ""
    echo "✅ Migration applied successfully!"
    echo ""
    echo "📊 Next: Verify in Supabase Table Editor"
    echo "   Look for 'learned_patterns' table"
fi

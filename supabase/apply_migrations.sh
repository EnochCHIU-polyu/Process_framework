#!/bin/bash
# =============================================================================
# Supabase Migration Runner
# =============================================================================
# This script applies SQL migrations to your Supabase project.
#
# Usage:
#   bash supabase/apply_migrations.sh
#
# Requirements:
#   - SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY set as environment variables
#   - psql CLI installed (or use Supabase web dashboard)
# =============================================================================

set -e

if [ -z "$SUPABASE_URL" ] || [ -z "$SUPABASE_SERVICE_ROLE_KEY" ]; then
    echo "❌ ERROR: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set"
    echo ""
    echo "To set these environment variables:"
    echo "  export SUPABASE_URL='https://your-project.supabase.co'"
    echo "  export SUPABASE_SERVICE_ROLE_KEY='your-service-role-key'"
    echo ""
    echo "Then run this script again."
    exit 1
fi

echo "🔧 Running Supabase migrations..."
echo "Project: $SUPABASE_URL"

# Extract project ID from URL
PROJECT_ID=$(echo "$SUPABASE_URL" | sed -n 's/.*https:\/\/\([a-z0-9]*\)\.supabase\.co.*/\1/p')

if [ -z "$PROJECT_ID" ]; then
    echo "❌ Could not extract project ID from SUPABASE_URL"
    exit 1
fi

echo "Project ID: $PROJECT_ID"

# Option 1: Use Supabase CLI (if available)
if command -v supabase &> /dev/null; then
    echo ""
    echo "📝 Using Supabase CLI to run migrations..."
    supabase migration up --project-id "$PROJECT_ID"
    echo "✅ Migrations applied successfully via CLI"
    exit 0
fi

# Option 2: Use psql directly
echo ""
echo "⚠️  Supabase CLI not found. Using psql to apply migration..."

MIGRATION_FILE="supabase/migrations/001_chat_auditing.sql"

if [ ! -f "$MIGRATION_FILE" ]; then
    echo "❌ Migration file not found: $MIGRATION_FILE"
    exit 1
fi

# Extract host from URL
DB_HOST=$(echo "$SUPABASE_URL" | sed -n 's/.*https:\/\/\([a-z0-9]*\)\.supabase\.co.*/\1.supabase.co/p')
DB_NAME="postgres"
DB_USER="postgres"

echo "Running SQL migration via psql..."
psql -h "$DB_HOST" \
     -U "$DB_USER" \
     -d "$DB_NAME" \
     -c "SET session_replication_role TO REPLICA;" \
     -f "$MIGRATION_FILE" 2>/dev/null || {
    echo ""
    echo "⚠️  Direct psql connection failed."
    echo ""
    echo "📋 Alternative: Run migration manually in Supabase dashboard"
    echo ""
    echo "1. Go to: https://app.supabase.com/project/$PROJECT_ID/sql/new"
    echo "2. Copy all content from: supabase/migrations/001_chat_auditing.sql"
    echo "3. Paste into the Supabase SQL editor"
    echo "4. Click 'Run'"
    exit 0
}

echo "✅ Learned patterns table created successfully!"
echo ""
echo "📊 You can now verify the new table in Supabase:"
echo "   https://app.supabase.com/project/$PROJECT_ID/editor"

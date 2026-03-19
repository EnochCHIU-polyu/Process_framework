#!/bin/bash
# =============================================================================
# Supabase Credential Setup Guide
# =============================================================================
# This script helps you find and verify your Supabase credentials
# =============================================================================

echo "╔════════════════════════════════════════════════════════════════════╗"
echo "║  Supabase Credential Setup & Migration Runner                     ║"
echo "╚════════════════════════════════════════════════════════════════════╝"
echo ""

# Check if credentials are already set
if [ -z "$SUPABASE_URL" ] || [ -z "$SUPABASE_SERVICE_ROLE_KEY" ]; then
    echo "❌ Environment variables not set"
    echo ""
    echo "FOLLOW THESE STEPS TO GET YOUR CREDENTIALS:"
    echo ""
    echo "1️⃣  Go to: https://app.supabase.com/projects"
    echo "   (Sign in with your Supabase account)"
    echo ""
    echo "2️⃣  Select your project - or create one if needed"
    echo ""
    echo "3️⃣  Go to: Settings → API (left sidebar)"
    echo ""
    echo "4️⃣  Copy two values:"
    echo ""
    echo "   📋 PROJECT URL (looks like https://xxxxx.supabase.co)"
    echo "      This is your SUPABASE_URL"
    echo ""
    echo "   🔑 SERVICE ROLE KEY (starts with 'eyJ...')"
    echo "      This is your SUPABASE_SERVICE_ROLE_KEY"
    echo ""
    echo "5️⃣  Set environment variables in your terminal:"
    echo ""
    echo "   export SUPABASE_URL='https://your-actual-project.supabase.co'"
    echo "   export SUPABASE_SERVICE_ROLE_KEY='your-actual-service-role-key'"
    echo ""
    echo "6️⃣  Verify they're set:"
    echo ""
    echo "   echo \$SUPABASE_URL"
    echo "   echo \$SUPABASE_SERVICE_ROLE_KEY"
    echo ""
    echo "7️⃣  Then run this same script again, or run the migration:"
    echo ""
    echo "   bash supabase/apply_migrations.sh"
    echo ""
    exit 1
fi

# Credentials are set - validate them
echo "✅ Environment variables detected"
echo ""
echo "Project URL: $SUPABASE_URL"
echo "Service Key: ${SUPABASE_SERVICE_ROLE_KEY:0:20}... (hidden for security)"
echo ""

# Extract and validate project ID
PROJECT_ID=$(echo "$SUPABASE_URL" | sed -n 's/.*https:\/\/\([a-z0-9]*\)\.supabase\.co.*/\1/p')

if [ -z "$PROJECT_ID" ]; then
    echo "❌ Could not extract project ID from URL"
    echo ""
    echo "Expected format: https://your-project-id.supabase.co"
    echo "Got: $SUPABASE_URL"
    echo ""
    echo "Check your SUPABASE_URL and try again"
    exit 1
fi

if [ ${#PROJECT_ID} -lt 10 ]; then
    echo "⚠️  Project ID seems too short: $PROJECT_ID"
    echo "Expected: typically 20+ characters"
    echo ""
    exit 1
fi

echo "✅ Project ID extracted: $PROJECT_ID"
echo ""
echo "🚀 Ready to apply migrations!"
echo ""
echo "Would you like to continue? (y/n)"
read -r response

if [ "$response" != "y" ] && [ "$response" != "Y" ]; then
    echo "Cancelled."
    exit 0
fi

echo ""
echo "Applying migrations from: supabase/migrations/001_chat_auditing.sql"
echo ""

# Try Supabase CLI first
if command -v supabase &> /dev/null; then
    echo "📝 Using Supabase CLI..."
    supabase migration up --project-id "$PROJECT_ID"
    if [ $? -eq 0 ]; then
        echo "✅ Migrations applied successfully!"
        exit 0
    fi
fi

# Try psql
if command -v psql &> /dev/null; then
    echo "📝 Using psql..."
    DB_HOST="${PROJECT_ID}.supabase.co"
    DB_NAME="postgres"
    DB_USER="postgres"
    
    psql -h "$DB_HOST" \
         -U "$DB_USER" \
         -d "$DB_NAME" \
         -f supabase/migrations/001_chat_auditing.sql
    
    if [ $? -eq 0 ]; then
        echo "✅ Migrations applied successfully!"
        exit 0
    fi
fi

# Fallback: provide manual instructions
echo ""
echo "⚠️  Could not auto-apply migrations"
echo ""
echo "📋 APPLY MANUALLY IN SUPABASE DASHBOARD:"
echo ""
echo "1. Go to: https://app.supabase.com/project/$PROJECT_ID/sql/new"
echo "2. Create new query"
echo "3. Open file: supabase/migrations/001_chat_auditing.sql"
echo "4. Copy entire content into the Supabase SQL editor"
echo "5. Click 'Run'"
echo ""
echo "After running, verify the new table:"
echo "1. Go to: Table Editor in Supabase dashboard"
echo "2. Look for: 'learned_patterns' table"
echo "3. It should have columns: id, category, pattern_keywords, etc."

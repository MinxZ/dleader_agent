#!/usr/bin/env python3
"""
Migration Script: Set Default is_shared: False for All Sessions

This script updates all existing multi-turn sessions in MongoDB to have:
- is_shared: false (if not already set)
- shared_at: null (if not already set)
- Removes old fields: share_tags, share_title, share_description
"""

import os
import sys
from datetime import datetime

# Add s3_mongodb directory to path for imports
script_dir = os.path.dirname(os.path.abspath(__file__))
s3_mongodb_dir = os.path.join(script_dir, 's3_mongodb')
sys.path.insert(0, s3_mongodb_dir)

from func_mongodb import get_mongodb_collection

def migrate_multiturn_sessions():
    """Migrate all multi-turn sessions to have default sharing fields"""

    print("=" * 70)
    print("MongoDB Multi-Turn Sessions Migration")
    print("Setting default is_shared: false for all sessions")
    print("=" * 70)

    # Get MongoDB collection
    database_name = os.getenv("SESSION_DB_NAME", "dleader_agent")
    collection_name = "multiturn_sessions"

    print(f"\nConnecting to MongoDB...")
    print(f"Database: {database_name}")
    print(f"Collection: {collection_name}")

    collection = get_mongodb_collection(database_name, collection_name)

    if collection is None:
        print("❌ Error: Could not connect to MongoDB")
        print("Please check your MongoDB connection settings")
        return False

    print("✅ Connected to MongoDB successfully")

    # Count total documents
    total_count = collection.count_documents({})
    print(f"\nTotal sessions in collection: {total_count}")

    if total_count == 0:
        print("ℹ️  No sessions found. Migration not needed.")
        return True

    # Find sessions that need migration
    print("\nAnalyzing sessions...")

    # Count sessions without is_shared field
    missing_is_shared = collection.count_documents({"is_shared": {"$exists": False}})

    # Count sessions with old fields
    has_share_tags = collection.count_documents({"share_tags": {"$exists": True}})
    has_share_title = collection.count_documents({"share_title": {"$exists": True}})
    has_share_description = collection.count_documents({"share_description": {"$exists": True}})

    print(f"  Sessions missing 'is_shared': {missing_is_shared}")
    print(f"  Sessions with 'share_tags': {has_share_tags}")
    print(f"  Sessions with 'share_title': {has_share_title}")
    print(f"  Sessions with 'share_description': {has_share_description}")

    # Confirm migration
    print("\n" + "=" * 70)
    print("Migration will perform the following operations:")
    print("1. Set is_shared: false for all sessions (if not set)")
    print("2. Set shared_at: null for all sessions (if not set)")
    print("3. Remove old fields: share_tags, share_title, share_description")
    print("=" * 70)

    response = input("\nProceed with migration? (yes/no): ").strip().lower()
    if response != 'yes':
        print("❌ Migration cancelled by user")
        return False

    print("\n🔄 Starting migration...")

    # Migration 1: Set default is_shared and shared_at for sessions without them
    print("\n1. Setting default is_shared: false and shared_at: null...")
    result1 = collection.update_many(
        {"is_shared": {"$exists": False}},
        {"$set": {
            "is_shared": False,
            "shared_at": None,
            "last_updated": datetime.now().isoformat()
        }}
    )
    print(f"   ✅ Updated {result1.modified_count} sessions with default values")

    # Migration 2: Remove old fields
    print("\n2. Removing deprecated fields (share_tags, share_title, share_description)...")
    result2 = collection.update_many(
        {},
        {"$unset": {
            "share_tags": "",
            "share_title": "",
            "share_description": "",
            "share_visibility": ""  # Also remove if exists
        }}
    )
    print(f"   ✅ Cleaned up {result2.modified_count} sessions")

    # Migration 3: Ensure all sessions have is_shared explicitly set
    print("\n3. Ensuring all sessions have is_shared field...")
    result3 = collection.update_many(
        {},
        {"$set": {
            "is_shared": False  # Default to false if not already true
        }},
        upsert=False
    )
    print(f"   ✅ Ensured {result3.matched_count} sessions have is_shared field")

    # Verification
    print("\n" + "=" * 70)
    print("Verification")
    print("=" * 70)

    # Count after migration
    all_with_is_shared = collection.count_documents({"is_shared": {"$exists": True}})
    shared_true = collection.count_documents({"is_shared": True})
    shared_false = collection.count_documents({"is_shared": False})

    remaining_share_tags = collection.count_documents({"share_tags": {"$exists": True}})
    remaining_share_title = collection.count_documents({"share_title": {"$exists": True}})
    remaining_share_description = collection.count_documents({"share_description": {"$exists": True}})

    print(f"Sessions with 'is_shared' field: {all_with_is_shared}/{total_count}")
    print(f"  - is_shared: true: {shared_true}")
    print(f"  - is_shared: false: {shared_false}")
    print(f"\nRemaining deprecated fields:")
    print(f"  - share_tags: {remaining_share_tags}")
    print(f"  - share_title: {remaining_share_title}")
    print(f"  - share_description: {remaining_share_description}")

    if all_with_is_shared == total_count and remaining_share_tags == 0:
        print("\n✅ Migration completed successfully!")
        print("All sessions now have is_shared: false by default")
        return True
    else:
        print("\n⚠️  Migration completed with warnings")
        print("Some sessions may need manual review")
        return False

def main():
    """Main entry point"""
    try:
        success = migrate_multiturn_sessions()

        if success:
            print("\n" + "=" * 70)
            print("✅ Migration Complete")
            print("=" * 70)
            print("\nNext steps:")
            print("1. Verify sessions via API: GET /multiturn-sessions")
            print("2. Check MongoDB directly if needed")
            print("3. Share/unshare APIs now work with simplified metadata")
            sys.exit(0)
        else:
            print("\n❌ Migration failed or was cancelled")
            sys.exit(1)

    except Exception as e:
        print(f"\n❌ Migration error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()

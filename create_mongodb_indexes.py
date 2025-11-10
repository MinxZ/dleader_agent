#!/usr/bin/env python3
"""
Create MongoDB indexes for optimized session queries

This script creates the necessary indexes for fast querying of multiturn_sessions.
Run this script to improve /multiturn-sessions endpoint performance.

Usage:
    python create_mongodb_indexes.py
"""

import os
import sys
from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import OperationFailure


def get_mongodb_client():
    """Get MongoDB client from environment"""
    mongodb_uri = os.getenv("MONGODB_URI")
    if not mongodb_uri:
        print("❌ Error: MONGODB_URI environment variable not set")
        print("\nPlease set it in your .env file or export it:")
        print("export MONGODB_URI='mongodb://...'")
        sys.exit(1)

    try:
        client = MongoClient(mongodb_uri)
        # Test connection
        client.admin.command('ping')
        print(f"✅ Connected to MongoDB")
        return client
    except Exception as e:
        print(f"❌ Failed to connect to MongoDB: {e}")
        sys.exit(1)


def create_indexes(db_name="dleader_agent"):
    """Create indexes for multiturn_sessions collection"""
    client = get_mongodb_client()
    db = client[db_name]
    collection = db.multiturn_sessions

    print(f"\n📊 Database: {db_name}")
    print(f"📦 Collection: multiturn_sessions")

    # Get existing indexes
    print("\n🔍 Checking existing indexes...")
    existing_indexes = list(collection.list_indexes())
    existing_index_names = [idx['name'] for idx in existing_indexes]

    print(f"\nExisting indexes ({len(existing_indexes)}):")
    for idx in existing_indexes:
        print(f"  - {idx['name']}: {idx.get('key', {})}")

    # Define indexes to create
    indexes_to_create = [
        {
            "name": "user_id_last_updated",
            "keys": [("user_id", ASCENDING), ("last_updated", DESCENDING)],
            "description": "For sorted queries by user and last_updated (most important!)"
        },
        {
            "name": "session_id_unique",
            "keys": [("session_id", ASCENDING)],
            "description": "Unique index on session_id for fast lookups by session ID",
            "unique": True
        },
        {
            "name": "user_id_session_status",
            "keys": [("user_id", ASCENDING), ("session_status", ASCENDING)],
            "description": "For filtering by user and status"
        }
    ]

    print("\n🏗️  Creating indexes...")
    created_count = 0
    skipped_count = 0

    for index_spec in indexes_to_create:
        index_name = index_spec["name"]

        if index_name in existing_index_names:
            print(f"  ⏭️  Skipping '{index_name}' (already exists)")
            skipped_count += 1
            continue

        try:
            # Build index options
            index_options = {
                "name": index_name,
                "background": True  # Don't block other operations
            }
            # Add unique constraint if specified
            if index_spec.get("unique", False):
                index_options["unique"] = True

            collection.create_index(
                index_spec["keys"],
                **index_options
            )
            unique_str = " (UNIQUE)" if index_spec.get("unique", False) else ""
            print(f"  ✅ Created '{index_name}'{unique_str}")
            print(f"     Description: {index_spec['description']}")
            created_count += 1
        except OperationFailure as e:
            print(f"  ❌ Failed to create '{index_name}': {e}")

    # Get updated indexes
    print("\n📊 Final index list:")
    final_indexes = list(collection.list_indexes())
    for idx in final_indexes:
        print(f"  - {idx['name']}: {idx.get('key', {})}")

    print(f"\n✨ Summary:")
    print(f"  - Created: {created_count} new indexes")
    print(f"  - Skipped: {skipped_count} (already existed)")
    print(f"  - Total: {len(final_indexes)} indexes")

    # Test query with explain
    print("\n🧪 Testing query performance...")
    test_user = "Test user"

    try:
        explain_result = collection.find(
            {"user_id": test_user}
        ).sort("last_updated", -1).limit(10).explain()

        winning_plan = explain_result.get("executionStats", {}).get("executionStages", {})
        stage = winning_plan.get("stage", "UNKNOWN")

        if stage == "IXSCAN" or "indexName" in str(winning_plan):
            print(f"  ✅ Query uses INDEX SCAN (fast!)")
        elif stage == "COLLSCAN":
            print(f"  ⚠️  Query uses COLLECTION SCAN (slow!)")
            print(f"      This might happen if there's no data yet.")
        else:
            print(f"  ℹ️  Query execution stage: {stage}")

        # Show execution stats
        exec_stats = explain_result.get("executionStats", {})
        if exec_stats:
            print(f"\n  📈 Execution Stats:")
            print(f"     - Documents examined: {exec_stats.get('totalDocsExamined', 'N/A')}")
            print(f"     - Documents returned: {exec_stats.get('nReturned', 'N/A')}")
            print(f"     - Execution time: {exec_stats.get('executionTimeMillis', 'N/A')} ms")
    except Exception as e:
        print(f"  ⚠️  Could not test query: {e}")

    print("\n✅ Done! Indexes created successfully.")
    print("\nNext steps:")
    print("  1. Restart your FastAPI server to use the optimized code")
    print("  2. Test the /multiturn-sessions endpoint")
    print("  3. Expected response time: < 200ms")

    client.close()


if __name__ == "__main__":
    print("=" * 60)
    print("MongoDB Index Creation for dleader_agent")
    print("=" * 60)

    try:
        create_indexes()
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

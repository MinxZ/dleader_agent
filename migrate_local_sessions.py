#!/usr/bin/env python3
"""
Migration Script: Add is_shared and shared_at to Local JSON Files

This script updates all local multiturn session JSON files to explicitly include:
- is_shared: false
- shared_at: null
"""

import os
import json
from datetime import datetime

def migrate_local_multiturn_sessions():
    """Migrate all local multiturn session JSON files"""

    print("=" * 70)
    print("Local Multi-Turn Sessions Migration")
    print("Adding is_shared and shared_at to local JSON files")
    print("=" * 70)

    multiturn_dir = os.path.join(os.getcwd(), "multiturn_sessions")

    if not os.path.exists(multiturn_dir):
        print(f"\n❌ Directory not found: {multiturn_dir}")
        print("No local sessions to migrate.")
        return True

    # Get all JSON files
    json_files = [f for f in os.listdir(multiturn_dir) if f.endswith('.json')]

    if not json_files:
        print(f"\nℹ️  No JSON files found in {multiturn_dir}")
        print("No migration needed.")
        return True

    print(f"\nFound {len(json_files)} session files")

    # Count files needing migration
    files_needing_migration = 0
    for filename in json_files:
        filepath = os.path.join(multiturn_dir, filename)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if 'is_shared' not in data:
                    files_needing_migration += 1
        except Exception as e:
            print(f"  ⚠️  Error reading {filename}: {e}")

    print(f"Files needing migration: {files_needing_migration}")

    if files_needing_migration == 0:
        print("\n✅ All files already have is_shared and shared_at fields")
        return True

    # Confirm migration
    print("\n" + "=" * 70)
    print("Migration will add to each file:")
    print('  "is_shared": false')
    print('  "shared_at": null')
    print("=" * 70)

    response = input("\nProceed with migration? (yes/no): ").strip().lower()
    if response != 'yes':
        print("❌ Migration cancelled by user")
        return False

    # Perform migration
    print("\n🔄 Starting migration...")
    migrated_count = 0
    error_count = 0

    for filename in json_files:
        filepath = os.path.join(multiturn_dir, filename)
        try:
            # Read existing data
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Add fields if missing
            modified = False
            if 'is_shared' not in data:
                data['is_shared'] = False
                modified = True
            if 'shared_at' not in data:
                data['shared_at'] = None
                modified = True

            # Save back if modified
            if modified:
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                migrated_count += 1
                print(f"  ✅ {filename}")

        except Exception as e:
            error_count += 1
            print(f"  ❌ {filename}: {e}")

    # Summary
    print("\n" + "=" * 70)
    print("Migration Summary")
    print("=" * 70)
    print(f"Total files: {len(json_files)}")
    print(f"Migrated: {migrated_count}")
    print(f"Errors: {error_count}")
    print(f"Already up-to-date: {len(json_files) - migrated_count - error_count}")

    if error_count == 0:
        print("\n✅ Migration completed successfully!")
        return True
    else:
        print(f"\n⚠️  Migration completed with {error_count} errors")
        return False

def main():
    """Main entry point"""
    try:
        success = migrate_local_multiturn_sessions()

        if success:
            print("\n" + "=" * 70)
            print("✅ Local Migration Complete")
            print("=" * 70)
            print("\nNext steps:")
            print("1. Restart the server if running")
            print("2. New sessions will automatically include these fields")
            print("3. Old sessions will use default values (is_shared: false)")
            return 0
        else:
            print("\n❌ Migration failed or was cancelled")
            return 1

    except Exception as e:
        print(f"\n❌ Migration error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    import sys
    sys.exit(main())

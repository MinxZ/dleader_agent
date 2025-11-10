#!/usr/bin/env python3
"""
Script to delete all multi-turn sessions for a specific user
Usage: python delete_user_sessions.py --user-id Tom [--dry-run] [--server-url http://localhost:8001]
"""

import argparse
import asyncio
import sys
from typing import List, Dict, Any
import aiohttp


async def get_all_sessions(server_url: str, user_id: str) -> List[Dict[str, Any]]:
    """Get all sessions for a user"""
    url = f"{server_url}/all-sessions"
    params = {"user_id": user_id}

    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as response:
            if response.status == 200:
                data = await response.json()
                return data.get("sessions", [])
            else:
                print(f"Error getting sessions: {response.status}")
                text = await response.text()
                print(f"Response: {text}")
                return []


async def hard_delete_session(server_url: str, session_id: str, user_id: str) -> Dict[str, Any]:
    """Hard delete a single session"""
    url = f"{server_url}/hard-delete/{session_id}"
    params = {
        "user_id": user_id,
        "confirm": True
    }

    async with aiohttp.ClientSession() as session:
        async with session.delete(url, params=params) as response:
            if response.status == 200:
                result = await response.json()
                return {"success": True, "session_id": session_id, "result": result}
            else:
                text = await response.text()
                return {"success": False, "session_id": session_id, "error": text}


async def delete_all_user_sessions(
    server_url: str,
    user_id: str,
    dry_run: bool = False,
    session_type: str = "all"
) -> None:
    """Delete all sessions for a user

    Args:
        server_url: The FastAPI server URL
        user_id: The user ID to delete sessions for
        dry_run: If True, only list sessions without deleting
        session_type: Type of sessions to delete: "multiturn", "single", or "all"
    """
    print(f"{'[DRY RUN] ' if dry_run else ''}Fetching sessions for user: {user_id}")
    print(f"Server: {server_url}")
    print("-" * 80)

    # Get all sessions
    all_sessions = await get_all_sessions(server_url, user_id)

    if not all_sessions:
        print(f"No sessions found for user: {user_id}")
        return

    # Filter sessions based on type
    sessions_to_delete = []
    for session in all_sessions:
        session_id = session.get("session_id")
        is_multiturn = session.get("is_multiturn", False)
        total_turns = session.get("total_turns", 0)

        # Determine if this is a multi-turn session
        if session_type == "multiturn" and not is_multiturn:
            continue
        elif session_type == "single" and is_multiturn:
            continue

        sessions_to_delete.append(session)

    print(f"Found {len(sessions_to_delete)} session(s) to delete (type: {session_type})")
    print("-" * 80)

    # List sessions
    for i, session in enumerate(sessions_to_delete, 1):
        session_id = session.get("session_id")
        session_name = session.get("session_name", "N/A")
        is_multiturn = session.get("is_multiturn", False)
        total_turns = session.get("total_turns", 0)
        created_at = session.get("created_at", "N/A")
        storage_location = session.get("_storage_location", "unknown")

        print(f"{i}. Session ID: {session_id[:16]}...")
        print(f"   Name: {session_name}")
        print(f"   Type: {'Multi-turn' if is_multiturn else 'Single-turn'}")
        if is_multiturn:
            print(f"   Turns: {total_turns}")
        print(f"   Created: {created_at}")
        print(f"   Storage: {storage_location}")
        print()

    if dry_run:
        print("[DRY RUN] No sessions were deleted. Remove --dry-run to actually delete.")
        return

    # Confirm deletion
    print("-" * 80)
    print(f"WARNING: This will PERMANENTLY delete {len(sessions_to_delete)} session(s)!")
    print("This action CANNOT be undone!")
    print("-" * 80)

    confirmation = input("Type 'DELETE' to confirm: ")
    if confirmation != "DELETE":
        print("Deletion cancelled.")
        return

    print("\nDeleting sessions...")
    print("-" * 80)

    # Delete sessions in parallel
    delete_tasks = [
        hard_delete_session(server_url, session["session_id"], user_id)
        for session in sessions_to_delete
    ]

    results = await asyncio.gather(*delete_tasks, return_exceptions=True)

    # Report results
    success_count = 0
    failed_count = 0

    for i, result in enumerate(results, 1):
        if isinstance(result, Exception):
            print(f"❌ Error deleting session {i}: {result}")
            failed_count += 1
        elif result.get("success"):
            session_id = result["session_id"]
            deleted_items = result["result"].get("deleted_items", {})
            local_files = len(deleted_items.get("local_files", []))
            s3_files = len(deleted_items.get("s3_files", []))
            mongo_docs = len(deleted_items.get("mongodb_docs", []))

            print(f"✓ Deleted session {i}/{len(sessions_to_delete)}: {session_id[:16]}...")
            print(f"  - Local files: {local_files}")
            print(f"  - S3 files: {s3_files}")
            print(f"  - MongoDB docs: {mongo_docs}")
            success_count += 1
        else:
            print(f"❌ Failed to delete session {i}: {result.get('error')}")
            failed_count += 1

    print("-" * 80)
    print(f"Deletion complete!")
    print(f"✓ Successfully deleted: {success_count}")
    if failed_count > 0:
        print(f"❌ Failed: {failed_count}")


def main():
    parser = argparse.ArgumentParser(
        description="Delete all multi-turn sessions for a specific user"
    )
    parser.add_argument(
        "--user-id",
        required=True,
        help="User ID to delete sessions for (e.g., 'Tom')"
    )
    parser.add_argument(
        "--server-url",
        default="http://localhost:8001",
        help="FastAPI server URL (default: http://localhost:8001)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List sessions without deleting them"
    )
    parser.add_argument(
        "--type",
        choices=["all", "multiturn", "single"],
        default="multiturn",
        help="Type of sessions to delete: 'all', 'multiturn', or 'single' (default: multiturn)"
    )

    args = parser.parse_args()

    # Run async deletion
    asyncio.run(delete_all_user_sessions(
        server_url=args.server_url,
        user_id=args.user_id,
        dry_run=args.dry_run,
        session_type=args.type
    ))


if __name__ == "__main__":
    main()

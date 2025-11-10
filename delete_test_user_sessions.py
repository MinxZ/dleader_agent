#!/usr/bin/env python3
"""
Script to delete all sessions for user test_user_dleader
"""

import asyncio
import aiohttp

SERVER_URL = "http://localhost:8001"
USER_ID = "test_user_dleader"

# All test_user_dleader's session IDs
SESSION_IDS = [
    "9260fc04-b053-466e-8f66-79599eb5f231",
    "915ee0b9-7687-4762-a637-647e455284b4",
    "189f7716-0b84-47a9-8a8e-61cd12229376",
    "1514daf3-bd00-4338-b812-1820fec2105e",
    "66f48dfa-78cc-4566-b20b-cac3190976d6",
    "1ad00b5e-1e43-4332-9f33-c92a6192b7d1",
    "e92d9dd1-3274-4b00-9abd-66491ca4f1f8",
    "4f915360-de2a-4183-a340-50455ebe5ce2",
    "5ffdbd5e-7692-48a5-8b32-629974bcbf46",
    "247ed26b-36be-4e71-aa29-570529299b55",
    "ce3470e4-99ec-4b1b-a2cf-238a390ebd07",
    "c42cc7a7-8d98-4f30-8db3-310afacd08ac",
    "4417bd0e-4462-48ac-ad16-48bc17cbc616",
    "e8cb2141-03b3-4cc2-b7b4-92d80bbe095b",
    "a805cbcf-9a73-4851-8b04-921df6b382dd",
    "23bb4f11-27b1-4659-a12c-a29b8df3aa7a",
    "75d918bf-7736-4627-891c-0d9e1a5f561b",
    "c17b2854-e92f-4edd-b470-57c5a0fe6f4c",
    "e183663e-02d3-4bb9-9393-f5d2fcc3f55b",
    "3d9b3c23-4ec7-4144-8df0-0d02f073f6aa",
    "d0dfb134-4a37-455e-b1ff-6821ad0a15b3",
    "84fbb104-31ee-489e-8a97-875ef416989f",
    "2f1a7be9-e829-43ec-977b-766ddcd7848d",
    "27dbe0bb-a737-476d-958d-232706702529",
    "eb6aa81c-87aa-4b66-aa28-4583a910ffa0",
]


async def hard_delete_session(session_id: str, user_id: str):
    """Hard delete a single session"""
    url = f"{SERVER_URL}/hard-delete/{session_id}"
    params = {
        "user_id": user_id,
        "confirm": "true"
    }

    async with aiohttp.ClientSession() as session:
        try:
            async with session.delete(url, params=params) as response:
                if response.status == 200:
                    result = await response.json()
                    return {"success": True, "session_id": session_id, "result": result}
                else:
                    text = await response.text()
                    return {"success": False, "session_id": session_id, "error": text, "status": response.status}
        except Exception as e:
            return {"success": False, "session_id": session_id, "error": str(e)}


async def main():
    print(f"Deleting {len(SESSION_IDS)} sessions for user: {USER_ID}")
    print("=" * 80)

    # Delete all sessions in parallel
    tasks = [hard_delete_session(session_id, USER_ID) for session_id in SESSION_IDS]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Report results
    success_count = 0
    failed_count = 0

    for i, result in enumerate(results, 1):
        session_id = SESSION_IDS[i-1]

        if isinstance(result, Exception):
            print(f"❌ [{i}/{len(SESSION_IDS)}] Error: {session_id[:16]}... - {result}")
            failed_count += 1
        elif result.get("success"):
            deleted_items = result["result"].get("deleted_items", {})
            local_files = len(deleted_items.get("local_files", []))
            s3_files = len(deleted_items.get("s3_files", []))
            mongo_docs = len(deleted_items.get("mongodb_docs", []))

            print(f"✓ [{i}/{len(SESSION_IDS)}] Deleted: {session_id[:16]}... (Local: {local_files}, S3: {s3_files}, Mongo: {mongo_docs})")
            success_count += 1
        else:
            error = result.get("error", "Unknown error")
            status = result.get("status", "N/A")
            print(f"❌ [{i}/{len(SESSION_IDS)}] Failed: {session_id[:16]}... - Status {status}: {error[:100]}")
            failed_count += 1

    print("=" * 80)
    print(f"Deletion complete!")
    print(f"✓ Successfully deleted: {success_count}")
    print(f"❌ Failed: {failed_count}")


if __name__ == "__main__":
    asyncio.run(main())

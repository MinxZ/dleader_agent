#!/usr/bin/env python3
"""
Script to delete all sessions for user Tom
"""

import asyncio
import aiohttp

SERVER_URL = "http://localhost:8001"
USER_ID = "Tom"

# All Tom's session IDs
SESSION_IDS = [
    "82be1738-d0bf-4653-b5c1-34123853a6a6",
    "60b147ea-45d8-4bf8-a8fa-3df9ae409727",
    "83fdcbbc-7ce2-4f26-ac8e-471371f02def",
    "2244ef06-e377-46b1-a0ac-34c80b305609",
    "bc9d8b8b-880e-440b-bffb-1f703224904e",
    "1985bdfe-f108-4efe-a1bc-f01e2ed10298",
    "a2ec4414-a5c5-47a1-b116-01839e6a60f3",
    "488b88ee-3843-4c8f-8ef4-784c811340a9",
    "027c0179-f11e-45df-a22a-39f93f73b395",
    "eb86a9d5-536d-4a56-9eb1-fba74f37f078",
    "61dd35e2-789d-4998-ab85-df27db36f1b2",
    "0bd4672d-4297-4b30-bd6d-166702ea1c0d",
    "3c4c1069-90df-4d09-b547-416dd24b4e2a",
    "910faffe-a804-4066-aff2-1ef5fd642f1c",
    "ec0e4bfc-0ed9-4446-8fa0-b7f2a8836ad2",
    "27a4b46e-ab4c-478e-a684-5dcc9fbaa941",
    "70875831-d1eb-438d-acc8-555b4226245b",
    "8091b90e-f72b-43e0-aee6-961ac6597b7d",
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
            print(f"❌ [{i}/18] Error: {session_id[:16]}... - {result}")
            failed_count += 1
        elif result.get("success"):
            deleted_items = result["result"].get("deleted_items", {})
            local_files = len(deleted_items.get("local_files", []))
            s3_files = len(deleted_items.get("s3_files", []))
            mongo_docs = len(deleted_items.get("mongodb_docs", []))

            print(f"✓ [{i}/18] Deleted: {session_id[:16]}... (Local: {local_files}, S3: {s3_files}, Mongo: {mongo_docs})")
            success_count += 1
        else:
            error = result.get("error", "Unknown error")
            status = result.get("status", "N/A")
            print(f"❌ [{i}/18] Failed: {session_id[:16]}... - Status {status}: {error[:100]}")
            failed_count += 1

    print("=" * 80)
    print(f"Deletion complete!")
    print(f"✓ Successfully deleted: {success_count}")
    print(f"❌ Failed: {failed_count}")


if __name__ == "__main__":
    asyncio.run(main())

"""
Trash Management API Endpoints

This module contains all trash-related functionality for session management:
- Move to trash (soft delete)
- Restore from trash
- Permanent delete from trash
- View trash contents
- Empty trash

The hard-delete endpoint remains in the main API file as it's a direct operation.
"""

import os
import json
import glob
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
import logging

# Import necessary dependencies
from unified_session_manager import get_unified_session_manager
from cloud_storage_manager import cloud_storage_manager
from allowed_emails import is_user_allowed

# Configure logging
logger = logging.getLogger(__name__)

# Create router for trash endpoints
router = APIRouter(prefix="/trash", tags=["trash"])


@router.post("/move/{session_id}")
async def move_to_trash(session_id: str, user_id: str):
    """Soft delete - Move session to trash (mark as deleted but keep data)"""
    # Check if user is in the allowed list
    if not is_user_allowed(user_id):
        logger.warning(f"Access denied for user_id in /trash/move: {user_id}")
        raise HTTPException(status_code=403, detail=f"Access denied: User '{user_id}' is not in the allowed list")

    try:
        # Get unified session manager - need queue_manager from main app
        from agent_fastapi_server_multiturn import queue_manager
        unified_manager = get_unified_session_manager(queue_manager)

        # Verify user owns this session
        session_data = await unified_manager.get_session_by_id(session_id)
        if not session_data:
            raise HTTPException(status_code=404, detail="Session not found")

        session_user_id = session_data.get("user_id")
        if session_user_id and session_user_id != user_id:
            raise HTTPException(status_code=403, detail="Access denied: Session belongs to different user")

        # Mark as trashed (soft delete)
        trashed_at = datetime.now().isoformat()

        # Update session data with trash metadata
        session_data["is_trashed"] = True
        session_data["trashed_at"] = trashed_at
        session_data["trashed_by"] = user_id

        # Save updated session data
        session_file = f"session_storage/{session_id}.json"
        if os.path.exists(session_file):
            with open(session_file, 'w') as f:
                json.dump(session_data, f, indent=2)

        # Also update cloud storage metadata if it exists
        try:
            await cloud_storage_manager.update_session_metadata(session_id, {
                "is_trashed": True,
                "trashed_at": trashed_at,
                "trashed_by": user_id
            })
        except:
            pass  # Cloud storage update is optional

        return {
            "status": "success",
            "message": "Session moved to trash",
            "session_id": session_id,
            "trashed_at": trashed_at
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error moving session to trash: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/restore/{session_id}")
async def restore_from_trash(session_id: str, user_id: str):
    """Restore session from trash"""
    # Check if user is in the allowed list
    if not is_user_allowed(user_id):
        logger.warning(f"Access denied for user_id in /trash/restore: {user_id}")
        raise HTTPException(status_code=403, detail=f"Access denied: User '{user_id}' is not in the allowed list")

    try:
        # Get unified session manager
        from agent_fastapi_server_multiturn import queue_manager
        unified_manager = get_unified_session_manager(queue_manager)

        # Verify user owns this session
        session_data = await unified_manager.get_session_by_id(session_id)
        if not session_data:
            raise HTTPException(status_code=404, detail="Session not found")

        session_user_id = session_data.get("user_id")
        if session_user_id and session_user_id != user_id:
            raise HTTPException(status_code=403, detail="Access denied: Session belongs to different user")

        if not session_data.get("is_trashed"):
            raise HTTPException(status_code=400, detail="Session is not in trash")

        # Remove trash metadata
        session_data.pop("is_trashed", None)
        session_data.pop("trashed_at", None)
        session_data.pop("trashed_by", None)
        session_data["restored_at"] = datetime.now().isoformat()

        # Save updated session data
        session_file = f"session_storage/{session_id}.json"
        if os.path.exists(session_file):
            with open(session_file, 'w') as f:
                json.dump(session_data, f, indent=2)

        # Also update cloud storage metadata if it exists
        try:
            await cloud_storage_manager.update_session_metadata(session_id, {
                "is_trashed": False,
                "restored_at": session_data["restored_at"]
            })
        except:
            pass  # Cloud storage update is optional

        return {
            "status": "success",
            "message": "Session restored from trash",
            "session_id": session_id,
            "restored_at": session_data["restored_at"]
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error restoring session from trash: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/permanent/{session_id}")
async def permanent_delete_session(session_id: str, user_id: str, confirm: bool = False):
    """Permanently delete session from trash - removes all data from S3, MongoDB, and local storage"""
    # Check if user is in the allowed list
    if not is_user_allowed(user_id):
        logger.warning(f"Access denied for user_id in /trash/permanent: {user_id}")
        raise HTTPException(status_code=403, detail=f"Access denied: User '{user_id}' is not in the allowed list")

    try:
        if not confirm:
            raise HTTPException(status_code=400, detail="Must confirm permanent deletion with confirm=true")

        # Get unified session manager
        from agent_fastapi_server_multiturn import queue_manager
        unified_manager = get_unified_session_manager(queue_manager)

        # Verify user owns this session
        session_data = await unified_manager.get_session_by_id(session_id)
        if not session_data:
            raise HTTPException(status_code=404, detail="Session not found")

        session_user_id = session_data.get("user_id")
        if session_user_id and session_user_id != user_id:
            raise HTTPException(status_code=403, detail="Access denied: Session belongs to different user")

        # Check if session is in trash (optional - can delete directly)
        if not session_data.get("is_trashed"):
            print(f"Warning: Permanently deleting session {session_id} that is not in trash")

        deleted_items = {
            "local_files": [],
            "s3_files": [],
            "mongodb_docs": []
        }

        # 1. Delete local files
        # Delete session storage JSON
        session_file = f"session_storage/{session_id}.json"
        if os.path.exists(session_file):
            os.remove(session_file)
            deleted_items["local_files"].append(session_file)

        # Delete multi-turn session file if exists
        multiturn_file = f"multiturn_sessions/{session_id}.json"
        if os.path.exists(multiturn_file):
            os.remove(multiturn_file)
            deleted_items["local_files"].append(multiturn_file)

        # Delete any turn-specific files
        turn_files = glob.glob(f"session_storage/{session_id}_turn_*.json")
        for turn_file in turn_files:
            if os.path.exists(turn_file):
                os.remove(turn_file)
                deleted_items["local_files"].append(turn_file)

        # Delete zip files
        zip_files = glob.glob(f"chat_zips/*{session_id[:8]}*.zip")
        for zip_file in zip_files:
            if os.path.exists(zip_file):
                os.remove(zip_file)
                deleted_items["local_files"].append(zip_file)

        # Delete session folders
        session_folders = glob.glob(f"chat_sessions/*{session_id[:8]}*")
        for folder in session_folders:
            if os.path.exists(folder):
                import shutil
                shutil.rmtree(folder)
                deleted_items["local_files"].append(folder)

        # 2. Delete from S3 (if cloud storage manager available)
        try:
            if cloud_storage_manager and cloud_storage_manager.s3_client:
                s3_deleted = await cloud_storage_manager.delete_session_from_s3(session_id)
                if s3_deleted:
                    deleted_items["s3_files"] = s3_deleted.get("deleted_objects", [])
        except Exception as e:
            print(f"Warning: Could not delete S3 files for {session_id}: {e}")

        # 3. Delete from MongoDB (if configured)
        try:
            if cloud_storage_manager and cloud_storage_manager.mongodb_uri:
                mongodb_deleted = await cloud_storage_manager.delete_session_from_mongodb(session_id)
                if mongodb_deleted:
                    deleted_items["mongodb_docs"] = mongodb_deleted.get("deleted_docs", [])
        except Exception as e:
            print(f"Warning: Could not delete MongoDB docs for {session_id}: {e}")

        return {
            "status": "success",
            "message": f"Session {session_id} permanently deleted",
            "session_id": session_id,
            "deleted_at": datetime.now().isoformat(),
            "deleted_items": deleted_items,
            "total_deleted": {
                "local": len(deleted_items["local_files"]),
                "s3": len(deleted_items["s3_files"]),
                "mongodb": len(deleted_items["mongodb_docs"])
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error permanently deleting session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions")
async def get_trash_sessions(user_id: str):
    """Get all sessions in trash for a user"""
    # Check if user is in the allowed list
    if not is_user_allowed(user_id):
        logger.warning(f"Access denied for user_id in /trash/sessions: {user_id}")
        raise HTTPException(status_code=403, detail=f"Access denied: User '{user_id}' is not in the allowed list")

    try:
        # Get unified session manager
        from agent_fastapi_server_multiturn import queue_manager
        unified_manager = get_unified_session_manager(queue_manager)

        # Get all sessions (including trashed)
        all_sessions = await unified_manager.get_all_sessions(include_cloud=True, user_id=user_id)

        # Filter for trashed sessions
        trashed_sessions = []
        for session in all_sessions:
            if session.get("is_trashed"):
                # Add summary info
                summary = {
                    "session_id": session.get("session_id"),
                    "query": session.get("query", "No query"),
                    "status": session.get("status"),
                    "created_at": session.get("created_at"),
                    "trashed_at": session.get("trashed_at"),
                    "trashed_by": session.get("trashed_by"),
                    "user_id": session.get("user_id")
                }
                trashed_sessions.append(summary)

        # Sort by trashed_at (most recent first)
        trashed_sessions.sort(key=lambda x: x.get("trashed_at", ""), reverse=True)

        return {
            "status": "success",
            "count": len(trashed_sessions),
            "sessions": trashed_sessions
        }

    except Exception as e:
        print(f"Error getting trash sessions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/empty")
async def empty_trash(user_id: str, confirm: bool = False):
    """Empty all trash for a user - permanently delete all trashed sessions"""
    # Check if user is in the allowed list
    if not is_user_allowed(user_id):
        logger.warning(f"Access denied for user_id in /trash/empty: {user_id}")
        raise HTTPException(status_code=403, detail=f"Access denied: User '{user_id}' is not in the allowed list")

    try:
        if not confirm:
            raise HTTPException(status_code=400, detail="Must confirm emptying trash with confirm=true")

        # Get all trashed sessions
        trash_response = await get_trash_sessions(user_id)
        trashed_sessions = trash_response.get("sessions", [])

        if not trashed_sessions:
            return {
                "status": "success",
                "message": "Trash is already empty",
                "deleted_count": 0
            }

        deleted_sessions = []
        failed_deletions = []

        # Delete each trashed session
        for session in trashed_sessions:
            session_id = session["session_id"]
            try:
                # Call permanent delete
                await permanent_delete_session(session_id, user_id, confirm=True)
                deleted_sessions.append(session_id)
            except Exception as e:
                print(f"Failed to delete session {session_id}: {e}")
                failed_deletions.append({"session_id": session_id, "error": str(e)})

        return {
            "status": "success" if not failed_deletions else "partial",
            "message": f"Deleted {len(deleted_sessions)} sessions from trash",
            "deleted_count": len(deleted_sessions),
            "deleted_sessions": deleted_sessions,
            "failed_deletions": failed_deletions,
            "emptied_at": datetime.now().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error emptying trash: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Alternative endpoint mappings for backward compatibility
# These maintain the original URL structure but route to the new organization

@router.post("/{session_id}")
async def move_to_trash_alt(session_id: str, user_id: str):
    """Backward compatibility endpoint for /trash/{session_id}"""
    return await move_to_trash(session_id, user_id)


@router.get("/")
async def get_trash_sessions_alt(user_id: str):
    """Backward compatibility endpoint for /trash"""
    return await get_trash_sessions(user_id)
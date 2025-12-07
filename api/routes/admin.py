"""
Admin route handlers for dleader_agent API.
"""

from typing import List, Optional

from datetime import datetime
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from api import queue_manager
from api.models import (
    ConversationTurn,
    Language,
    MultiTurnSession,
    RenameMultiSessionRequest,
    ShareSessionRequest,
    Template,
    TemplateListRequest,
    TemplateResponse,
)
from api.utils import (
    create_session_zip,
    generate_file_urls,
    get_template_retriever,
)
from cloud_storage_manager import cloud_storage_manager
from unified_session_manager import UnifiedSessionManager
from unified_session_manager import get_unified_session_manager

router = APIRouter(tags=["admin"])


@router.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "queue_size": queue_manager.request_queue.qsize(),
        "is_processing": queue_manager.is_processing,
        "current_session": queue_manager.current_processing_session,
        "multiturn_sessions": len(queue_manager.multiturn_sessions)
    }

# ============= USER MANAGEMENT ENDPOINTS =============



@router.delete("/hard-delete/{session_id}")
async def hard_delete_session(session_id: str, user_id: str, confirm: bool = False):
    """
    Hard delete - Immediately and permanently delete a session without moving to trash
    This action cannot be undone!
    """
    # Validate user_id
    if not user_id or user_id.strip() == "":
        raise HTTPException(status_code=400, detail="user_id is required and cannot be empty")

    try:
        if not confirm:
            raise HTTPException(
                status_code=400,
                detail="Must confirm hard deletion with confirm=true. This action cannot be undone!"
            )

        # Get unified session manager
        unified_manager = get_unified_session_manager(queue_manager)

        # Verify the session exists and user owns it
        session_data = await unified_manager.get_session_by_id(session_id)
        if not session_data:
            raise HTTPException(status_code=404, detail="Session not found")

        # Verify user owns this session
        session_user_id = session_data.get("user_id")
        if session_user_id and session_user_id != user_id:
            raise HTTPException(status_code=403, detail="Access denied: Session belongs to different user")

        deleted_items = {
            "local_files": [],
            "s3_files": [],
            "mongodb_docs": []
        }

        # 1. Delete all local files and folders
        # Delete from session_storage
        session_file = f"session_storage/{session_id}.json"
        if os.path.exists(session_file):
            os.remove(session_file)
            deleted_items["local_files"].append(session_file)

        # Delete from multiturn_sessions
        multiturn_file = f"multiturn_sessions/{session_id}.json"
        if os.path.exists(multiturn_file):
            os.remove(multiturn_file)
            deleted_items["local_files"].append(multiturn_file)

        # Remove from in-memory multiturn sessions
        if session_id in queue_manager.multiturn_sessions:
            del queue_manager.multiturn_sessions[session_id]
            deleted_items["local_files"].append(f"In-memory multiturn session")

        # Remove from active sessions if present
        if session_id in queue_manager.active_sessions:
            del queue_manager.active_sessions[session_id]
            deleted_items["local_files"].append(f"Active session")

        # Delete any turn-specific files
        import glob
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

        # 2-4. Delete from S3, MongoDB, and community_sessions in parallel
        async def delete_from_s3():
            try:
                s3_deleted = await cloud_storage_manager.delete_session_from_s3(session_id)
                return ("s3", s3_deleted, None)
            except Exception as e:
                print(f"S3 deletion error (continuing): {e}")
                return ("s3", [], str(e))

        async def delete_from_mongodb():
            try:
                mongo_deleted = await cloud_storage_manager.delete_session_from_mongodb(session_id)
                return ("mongodb", mongo_deleted, None)
            except Exception as e:
                print(f"MongoDB deletion error (continuing): {e}")
                return ("mongodb", [], str(e))

        async def delete_from_community():
            try:
                await cloud_storage_manager.remove_shared_session(session_id)
                return ("community", ["community_sessions"], None)
            except Exception as e:
                print(f"Community session deletion error (continuing): {e}")
                return ("community", [], str(e))

        # Run all cloud deletions in parallel
        import asyncio
        results = await asyncio.gather(
            delete_from_s3(),
            delete_from_mongodb(),
            delete_from_community(),
            return_exceptions=True
        )

        # Process results
        for result in results:
            if isinstance(result, Exception):
                print(f"Deletion error: {result}")
                continue

            deletion_type, deleted_list, error = result
            if deletion_type == "s3":
                deleted_items["s3_files"] = deleted_list
            elif deletion_type in ("mongodb", "community"):
                deleted_items["mongodb_docs"].extend(deleted_list)

        return {
            "status": "success",
            "message": "Session hard deleted permanently",
            "session_id": session_id,
            "deleted_items": deleted_items,
            "deleted_at": datetime.now().isoformat(),
            "deleted_by": user_id
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error hard deleting session: {e}")
        raise HTTPException(status_code=500, detail=f"Error hard deleting session: {str(e)}")






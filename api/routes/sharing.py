"""
Sharing route handlers for dleader_agent API.
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

router = APIRouter(tags=["sharing"])


@router.post("/share-session")
async def share_session(request: ShareSessionRequest):
    """Share a multi-turn session with the community"""
    try:
        # Get the session to share
        multiturn_session = queue_manager.multiturn_sessions.get(request.session_id)
        if not multiturn_session:
            # Try to get from cloud storage
            unified_manager = get_unified_session_manager(queue_manager)
            session_data = await unified_manager.get_session_by_id(request.session_id)
            if not session_data:
                raise HTTPException(status_code=404, detail="Session not found")

            # Convert to MultiTurnSession if from cloud
            multiturn_session = MultiTurnSession(**session_data)

        # Verify user owns this session
        if multiturn_session.user_id and multiturn_session.user_id != request.user_id:
            raise HTTPException(status_code=403, detail="Access denied: Session belongs to different user")

        # Update sharing metadata
        multiturn_session.is_shared = True
        multiturn_session.shared_at = datetime.now().isoformat()

        # Save updated session (in-memory cache + MongoDB)
        queue_manager.multiturn_sessions[request.session_id] = multiturn_session
        queue_manager._save_multiturn_session(multiturn_session)

        # Also upload to cloud storage for community access (separate collection)
        if cloud_storage_manager:
            # Prepare shared session data
            shared_data = {
                "session_id": multiturn_session.session_id,
                "shared_by": request.user_id,
                "shared_at": multiturn_session.shared_at,
                "total_turns": multiturn_session.total_turns,
                "language": multiturn_session.language,
                "first_query": multiturn_session.first_query,
                "last_query": multiturn_session.latest_query,
                "turns": [turn.dict() for turn in multiturn_session.turns],
                "created_at": multiturn_session.created_at,
                "last_updated": multiturn_session.last_updated
            }

            # Store in community collection
            await cloud_storage_manager.store_shared_session(shared_data)

        return {
            "success": True,
            "session_id": request.session_id,
            "shared_at": multiturn_session.shared_at,
            "message": "Session shared successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error sharing session: {e}")
        raise HTTPException(status_code=500, detail=f"Error sharing session: {str(e)}")



@router.post("/unshare-session")
async def unshare_session(session_id: str, user_id: str):
    """Remove a session from community sharing"""
    try:
        # Get the session
        multiturn_session = queue_manager.multiturn_sessions.get(session_id)
        if not multiturn_session:
            raise HTTPException(status_code=404, detail="Session not found")

        # Verify user owns this session
        if multiturn_session.user_id and multiturn_session.user_id != user_id:
            raise HTTPException(status_code=403, detail="Access denied: Session belongs to different user")

        # Update sharing metadata
        multiturn_session.is_shared = False
        multiturn_session.shared_at = None

        # Save updated session (in-memory cache + MongoDB)
        queue_manager.multiturn_sessions[session_id] = multiturn_session
        queue_manager._save_multiturn_session(multiturn_session)

        # Remove from cloud community collection
        if cloud_storage_manager:
            await cloud_storage_manager.remove_shared_session(session_id)

        return {
            "success": True,
            "session_id": session_id,
            "message": "Session unshared successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error unsharing session: {e}")
        raise HTTPException(status_code=500, detail=f"Error unsharing session: {str(e)}")



@router.get("/shared-sessions")
async def get_shared_sessions(limit: int = 50, offset: int = 0):
    """Get all publicly shared sessions from the community"""
    try:
        if not cloud_storage_manager:
            return {"sessions": [], "total": 0, "limit": limit, "offset": offset}

        # Get from MongoDB community_sessions collection
        from s3_mongodb.func_mongodb import get_mongodb_collection
        collection = get_mongodb_collection(
            os.getenv("SESSION_DB_NAME", "dleader_agent"),
            "community_sessions"
        )

        if collection is None:
            return {"sessions": [], "total": 0, "limit": limit, "offset": offset}

        # Query all shared sessions, sorted by shared_at (newest first)
        total_count = collection.count_documents({})
        shared_sessions = list(
            collection.find({})
            .sort("shared_at", -1)
            .skip(offset)
            .limit(limit)
        )

        # Remove MongoDB _id field from results
        for session in shared_sessions:
            session.pop("_id", None)

        return {
            "sessions": shared_sessions,
            "total": total_count,
            "limit": limit,
            "offset": offset
        }

    except Exception as e:
        print(f"Error getting shared sessions: {e}")
        raise HTTPException(status_code=500, detail=f"Error retrieving shared sessions: {str(e)}")





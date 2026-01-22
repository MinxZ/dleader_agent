"""
Multiturn route handlers for dleader_agent API.
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

router = APIRouter(tags=["multiturn"])


@router.get("/multiturn-session/{session_id}")
async def get_multiturn_session(session_id: str, user_id: str, include_thinking: bool = False):
    """Get complete multi-turn session history using Unified Session Manager

    Args:
        session_id: The session ID
        user_id: The user ID
        include_thinking: If True, includes thinking process (response_content) in each turn.
                         Default is False to reduce response size for sessions with many turns.
    """
    try:
        # Use Unified Session Manager to get session from any storage location
        unified_manager = get_unified_session_manager(queue_manager)
        session = await unified_manager.get_multiturn_session_by_id(session_id)

        if not session:
            raise HTTPException(status_code=404, detail="Multi-turn session not found")

        # Verify user owns this session
        session_user_id = session.get("user_id")
        if session_user_id and session_user_id != user_id:
            raise HTTPException(status_code=403, detail="Access denied: Session belongs to different user")

        # Get cloud session data in case we need S3 files
        cloud_session = None

        # Process turns: generate URLs and optionally exclude thinking process
        if "turns" in session and isinstance(session["turns"], list):
            for turn in session["turns"]:
                # Generate URLs for files in each turn
                if "files" in turn:
                    # Check if local files are missing
                    files = turn["files"]
                    has_missing_files = False
                    import os

                    if isinstance(files, dict):
                        for key, value in files.items():
                            if isinstance(value, list):
                                for item in value:
                                    # Handle both string paths and dict objects
                                    if isinstance(item, str):
                                        if not os.path.exists(item):
                                            has_missing_files = True
                                            break
                                    elif isinstance(item, dict) and "path" in item:
                                        if not os.path.exists(item["path"]):
                                            has_missing_files = True
                                            break
                            elif isinstance(value, dict) and "path" in value:
                                if not os.path.exists(value["path"]):
                                    has_missing_files = True
                                    break
                            elif isinstance(value, str):
                                # Handle single string path
                                if not os.path.exists(value):
                                    has_missing_files = True
                                    break
                            if has_missing_files:
                                break

                    # If local files are missing, try to get S3 files from cloud (once)
                    if has_missing_files and cloud_session is None:
                        try:
                            cloud_session = await cloud_storage_manager.retrieve_session_from_cloud(session_id)
                            if cloud_session:
                                print(
                                    f"Local files missing for session {session_id}, fetched S3 files from cloud storage"
                                )
                        except Exception as e:
                            print(f"Warning: Could not retrieve S3 files from cloud for session {session_id}: {e}")
                            cloud_session = {}  # Set to empty dict to avoid retrying

                    # If we have cloud S3 files, merge them for this turn
                    if has_missing_files and cloud_session and "s3_files" in cloud_session:
                        turn["files"] = cloud_session["s3_files"]

                    turn["files"] = generate_file_urls(turn["files"], session_id)

                # Remove thinking process unless explicitly requested
                if not include_thinking:
                    # Remove response_content (thinking process) to reduce payload size
                    turn.pop("response_content", None)
                    # Keep final_report as it's the main output

        return session

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error getting multiturn session: {e}")
        import traceback

        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error retrieving session: {str(e)}")


@router.get("/multiturn-sessions")
async def get_all_multiturn_sessions(user_id: Optional[str] = None, limit: int = 10, offset: int = 0):
    """Get multi-turn sessions with pagination

    Args:
        user_id: User ID to filter sessions (required)
        limit: Number of sessions to return (default: 10)
        offset: Number of sessions to skip (default: 0)

    Returns:
        {
            "sessions": [...],
            "total": total_count,
            "limit": limit,
            "offset": offset
        }

    Examples:
        - Get first 10 sessions: ?user_id=xxx&limit=10&offset=0
        - Get sessions 10-20: ?user_id=xxx&limit=10&offset=10
        - Get sessions 20-30: ?user_id=xxx&limit=10&offset=20
    """
    try:
        # Require user_id for security - prevent unauthorized access to all sessions
        if not user_id or user_id.strip() == "":
            return {
                "sessions": [],
                "total": 0,
                "limit": limit,
                "offset": offset,
                "error": "user_id is required",
                "message": "Please provide a valid user_id",
            }

        # Get unified session manager
        unified_manager = get_unified_session_manager(queue_manager)

        # Get multi-turn sessions with pagination
        result = await unified_manager.get_multiturn_sessions(
            include_cloud=True, user_id=user_id, limit=limit, offset=offset
        )

        return result
    except Exception as e:
        print(f"Error getting multi-turn sessions: {e}")
        import traceback

        traceback.print_exc()
        # Fallback to local-only sessions with pagination
        sessions = []
        for session_id, session in queue_manager.multiturn_sessions.items():
            # Determine current_status by checking active UserRequests
            current_status = None
            current_turn = getattr(session, "current_turn", None)
            if current_turn:
                turn_session_id = f"{session_id}_turn_{current_turn}"
                if turn_session_id in queue_manager.active_sessions:
                    user_request = queue_manager.active_sessions[turn_session_id]
                    current_status = user_request.status
                elif session_id in queue_manager.active_sessions:
                    user_request = queue_manager.active_sessions[session_id]
                    current_status = user_request.status
            if not current_status:
                current_status = "completed" if session.session_status != "error" else "error"

            session_summary = {
                "session_id": session_id,
                "created_at": session.created_at,
                "last_updated": session.last_updated,
                "total_turns": session.total_turns,
                "language": session.language,
                "session_status": session.session_status,
                "current_status": current_status,  # Rich status (queued, processing, completed, error, cancelled)
                "first_query": session.turns[0].query if session.turns else "No queries",
                "latest_query": session.turns[-1].query if session.turns else "No queries",
                "_storage_location": "local",
            }
            sessions.append(session_summary)

        # Sort and paginate fallback sessions
        sessions.sort(key=lambda x: x.get("last_updated", x.get("created_at", "")), reverse=True)
        total = len(sessions)
        paginated = sessions[offset : offset + limit]

        return {"sessions": paginated, "total": total, "limit": limit, "offset": offset}


@router.get("/turn-report/{session_id}/{turn_number}")
async def get_turn_report(session_id: str, turn_number: int, user_id: str):
    """Get specific turn report from multi-turn session"""
    multiturn_session = queue_manager.multiturn_sessions.get(session_id)
    if not multiturn_session:
        raise HTTPException(status_code=404, detail="Multi-turn session not found")

    # Verify user owns this session
    if multiturn_session.user_id and multiturn_session.user_id != user_id:
        raise HTTPException(status_code=403, detail="Access denied: Session belongs to different user")

    # Find the specific turn
    for turn in multiturn_session.turns:
        if turn.turn_number == turn_number:
            return {
                "session_id": session_id,
                "turn_number": turn_number,
                "query": turn.query,
                "final_report": turn.final_report,
                "response_content": turn.response_content,
                "files": turn.files,
                "timestamp": turn.timestamp,
                "status": turn.status,
            }

    raise HTTPException(status_code=404, detail=f"Turn {turn_number} not found in session")


@router.get("/session-context/{session_id}")
async def get_session_context(session_id: str, user_id: str):
    """Get accumulated context for a multi-turn session"""
    multiturn_session = queue_manager.multiturn_sessions.get(session_id)
    if not multiturn_session:
        raise HTTPException(status_code=404, detail="Multi-turn session not found")

    # Verify user owns this session
    if multiturn_session.user_id and multiturn_session.user_id != user_id:
        raise HTTPException(status_code=403, detail="Access denied: Session belongs to different user")

    return {
        "session_id": session_id,
        "accumulated_context": multiturn_session.accumulated_context,
        "total_turns": multiturn_session.total_turns,
    }


# ============= SESSION SHARING ENDPOINTS =============


@router.post("/rename-multisession")
async def rename_multisession(request: RenameMultiSessionRequest):
    """Rename a multi-turn session using Unified Session Manager"""
    import time

    start_total = time.time()

    try:
        session_id = request.session_id
        new_name = request.new_name
        user_id = request.user_id

        # Use Unified Session Manager to get and update the session
        start_init = time.time()
        unified_manager = get_unified_session_manager(queue_manager)
        print(f"⏱️  [RENAME] Init manager: {(time.time() - start_init) * 1000:.2f} ms")

        # Get the session from any storage location (memory, local, or MongoDB)
        start_get = time.time()
        session = await unified_manager.get_multiturn_session_by_id(session_id)
        print(f"⏱️  [RENAME] Get session: {(time.time() - start_get) * 1000:.2f} ms")

        if not session:
            raise HTTPException(status_code=404, detail="Multi-turn session not found")

        # Verify user owns this session
        start_verify = time.time()
        session_user_id = session.get("user_id")
        if session_user_id and session_user_id != user_id:
            raise HTTPException(status_code=403, detail="Access denied: Session belongs to different user")
        print(f"⏱️  [RENAME] Verify user: {(time.time() - start_verify) * 1000:.2f} ms")

        # Update the session using Unified Session Manager
        # This will update memory, local storage, and MongoDB automatically
        try:
            updates = {"session_name": new_name}
            start_update = time.time()
            success = await unified_manager.update_multiturn_session(
                session_id=session_id, updates=updates, user_id=user_id
            )
            update_time = (time.time() - start_update) * 1000
            print(f"⏱️  [RENAME] Update session: {update_time:.2f} ms")

            if not success:
                raise HTTPException(status_code=500, detail="Failed to update session")

            total_time = (time.time() - start_total) * 1000
            print(f"⏱️  [RENAME] TOTAL TIME: {total_time:.2f} ms")

            return {
                "success": True,
                "session_id": session_id,
                "new_name": new_name,
                "message": "Session renamed successfully",
                "timing": {"total_ms": round(total_time, 2), "update_ms": round(update_time, 2)},
            }

        except PermissionError as e:
            raise HTTPException(status_code=403, detail=str(e))

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error renaming session: {e}")
        import traceback

        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error renaming session: {str(e)}")


# ============= RNA STRUCTURE VISUALIZATION ENDPOINTS =============


@router.get("/rna-structures/{session_id}")
async def get_rna_structures(session_id: str, user_id: str, turn_number: Optional[int] = None):
    """Get RNA structure data for visualization

    Args:
        session_id: The session ID
        user_id: User ID for authentication
        turn_number: Optional - specific turn (default: all turns)

    Returns:
        {
            "session_id": "abc123",
            "structures": [
                {
                    "turn_number": 1,
                    "rna_structures": [
                        {
                            "id": "seq_1",
                            "sequence": "GCGCGCGCGC",
                            "structure": "((((..))))",
                            "length": 10,
                            "base_pairs": 4,
                            "method": "rnafm"
                        }
                    ]
                }
            ]
        }
    """
    try:
        unified_manager = get_unified_session_manager(queue_manager)
        session = await unified_manager.get_multiturn_session_by_id(session_id)

        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        # Verify user ownership
        session_user_id = session.get("user_id")
        if session_user_id and session_user_id != user_id:
            raise HTTPException(status_code=403, detail="Access denied")

        result = {"session_id": session_id, "structures": []}

        for turn in session.get("turns", []):
            if turn_number and turn.get("turn_number") != turn_number:
                continue

            structured_data = turn.get("structured_data") or {}
            rna_structures = structured_data.get("rna_structures", [])

            if rna_structures:
                result["structures"].append({"turn_number": turn.get("turn_number"), "rna_structures": rna_structures})

        return result

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error getting RNA structures: {e}")
        import traceback

        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error retrieving RNA structures: {str(e)}")

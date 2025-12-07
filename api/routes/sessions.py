"""
Sessions route handlers for dleader_agent API.
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
    append_images_to_report,
    create_session_zip,
    generate_file_urls,
    get_template_retriever,
)
from cloud_storage_manager import cloud_storage_manager
from unified_session_manager import UnifiedSessionManager
from unified_session_manager import get_unified_session_manager

router = APIRouter(tags=["sessions"])


@router.get("/progress/{session_id}")
async def get_progress(session_id: str, user_id: str):
    """Get current progress for a session (alias for /status for backward compatibility)"""
    return await get_status(session_id, user_id)



@router.get("/status/{session_id}")
async def get_status(session_id: str, user_id: str, turn_number: Optional[int] = None):
    """Get current status and progress for a session from local or cloud storage

    Args:
        session_id: The session ID
        user_id: The user ID
        turn_number: Optional turn number to retrieve. If not provided, returns current/latest turn.
    """
    # Validate user_id
    if not user_id or user_id.strip() == "":
        raise HTTPException(status_code=400, detail="user_id is required and cannot be empty")

    try:
        # Get unified session manager
        unified_manager = get_unified_session_manager(queue_manager)

        # Get session status using unified manager (handles local/cloud intelligently)
        status_data = await unified_manager.get_session_status(session_id)
        if not status_data:
            raise HTTPException(status_code=404, detail="Session not found")

        # Verify user owns this session
        session_user_id = status_data.get("user_id")
        if session_user_id and session_user_id != user_id:
            raise HTTPException(status_code=403, detail="Access denied: Session belongs to different user")

        # Get multi-turn session info to determine turn number
        multiturn_session = queue_manager.multiturn_sessions.get(session_id)
        current_turn = None
        total_turns = None
        if multiturn_session:
            current_turn = multiturn_session.current_turn
            total_turns = multiturn_session.total_turns
            # If turn_number not specified, use current turn
            if turn_number is None:
                turn_number = current_turn
            # Validate turn_number is within range
            elif turn_number < 1 or turn_number > total_turns:
                raise HTTPException(status_code=400, detail=f"Invalid turn_number. Must be between 1 and {total_turns}")

        # For active sessions, get queue status
        queue_status = None
        if status_data.get("storage_location") == "active":
            queue_status = queue_manager.get_queue_status(session_id)

        response = {
            "session_id": session_id,
            "status": status_data.get("status", "unknown"),
            "is_complete": status_data.get("is_complete", False),
            "is_cancelled": status_data.get("is_cancelled", False),
            "created_at": status_data.get("created_at", datetime.now().isoformat())
        }

        # Add turn information if this is a multi-turn session
        if multiturn_session:
            response["current_turn"] = current_turn
            response["total_turns"] = total_turns
            response["turn_number"] = turn_number  # The turn number for this status response

        # Add queue information for active sessions
        if queue_status:
            response["queue_position"] = queue_status.position
            response["estimated_wait_time"] = queue_status.estimated_wait_time
            response["total_users_in_queue"] = queue_status.total_users_in_queue

        # Add error information if present
        if status_data.get("error"):
            response["error"] = status_data["error"]

        # Handle progress updates based on storage location
        storage_location = status_data.get("storage_location", "unknown")

        if storage_location == "active":
            # Active sessions: include real-time progress updates
            response["progress_updates"] = status_data.get("progress_updates", [])

            # Extract final report for completed active sessions
            if status_data["is_complete"]:
                for update in status_data.get("progress_updates", []):
                    if update.get("type") == "completion":
                        response["final_report"] = update.get("final_report")
                        response["thinking_content"] = update.get("thinking_content", "")
                        response["session_path"] = update.get("session_path")
                        break

        elif storage_location == "cloud":
            # Cloud sessions: show summary data (progress is summarized)
            response["progress_summary"] = status_data.get("progress_summary", {})
            response["cloud_info"] = {
                "uploaded_at": status_data.get("uploaded_to_cloud_at"),
                "files_available": True
            }

        elif storage_location == "local":
            # Local stored sessions: include available progress data
            response["progress_updates"] = status_data.get("progress_updates", [])

        # Add storage location for debugging
        response["_storage_location"] = storage_location

        return response

    except HTTPException:
        # Re-raise HTTP exceptions (like 404) without modification
        raise
    except Exception as e:
        print(f"Error getting status for session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Error retrieving session status: {str(e)}")

# REMOVED: /upload/{session_id} endpoint - not needed for multi-turn chat workflow
# File uploads can be handled during initial session creation if needed


# REMOVED: /sessions endpoint - was insecure (exposed all users' sessions)
# Use /all-sessions with user_id filtering instead



@router.get("/results/{session_id}")
async def get_session_results(session_id: str, user_id: str, turn_number: Optional[int] = None):
    """Get structured JSON results for a completed session

    Args:
        session_id: The session ID
        user_id: The user ID
        turn_number: Optional turn number to retrieve. If not provided, returns current/latest turn results.
    """
    # Validate user_id
    if not user_id or user_id.strip() == "":
        raise HTTPException(status_code=400, detail="user_id is required and cannot be empty")

    # Get multi-turn session info to determine turn number and sharing status
    # First check in-memory sessions
    multiturn_session = queue_manager.multiturn_sessions.get(session_id)
    current_turn = None
    total_turns = None
    is_shared = False
    session_owner_id = None

    # If not in memory, try to get from MongoDB/cloud
    if not multiturn_session:
        try:
            unified_manager = get_unified_session_manager(queue_manager)
            cloud_multiturn_session = await unified_manager.get_multiturn_session_by_id(session_id)
            if cloud_multiturn_session:
                current_turn = cloud_multiturn_session.get("current_turn")
                total_turns = cloud_multiturn_session.get("total_turns")
                is_shared = cloud_multiturn_session.get("is_shared", False)
                session_owner_id = cloud_multiturn_session.get("user_id")
        except Exception as e:
            print(f"Could not load multiturn session info from cloud: {e}")
    else:
        current_turn = multiturn_session.current_turn
        total_turns = multiturn_session.total_turns
        is_shared = multiturn_session.is_shared if hasattr(multiturn_session, 'is_shared') else False
        session_owner_id = multiturn_session.user_id if hasattr(multiturn_session, 'user_id') else None

    # Process turn_number if we have turn information
    if current_turn is not None and total_turns is not None:
        # If turn_number not specified, use current turn
        if turn_number is None:
            turn_number = current_turn
        # Validate turn_number is within range
        elif turn_number < 1 or turn_number > total_turns:
            raise HTTPException(status_code=400, detail=f"Invalid turn_number. Must be between 1 and {total_turns}")

    # Check access: Allow if session is shared OR user owns the session
    # This check happens early using multiturn metadata for efficiency
    # If we have ownership info and it's not shared and user doesn't own it, deny access
    if session_owner_id and session_owner_id != user_id and not is_shared:
        raise HTTPException(status_code=403, detail="Access denied: Session belongs to different user")

    # Use unified session manager to check both local and cloud storage
    unified_manager = get_unified_session_manager(queue_manager)
    session_data = await unified_manager.get_session_by_id(session_id)

    if not session_data:
        raise HTTPException(status_code=404, detail="Session not found")

    # Fallback check: if we didn't have multiturn metadata, check from session_data
    # This handles cases where session exists but isn't in multiturn_sessions collection
    if not session_owner_id:
        session_user_id_fallback = session_data.get("user_id")
        is_shared_fallback = session_data.get("is_shared", False)
        if session_user_id_fallback and session_user_id_fallback != user_id and not is_shared_fallback:
            raise HTTPException(status_code=403, detail="Access denied: Session belongs to different user")

    if not session_data.get("is_complete", False):
        raise HTTPException(status_code=400, detail="Session is not yet complete")

    # For multi-turn sessions with specific turn_number, return turn-specific results
    if turn_number is not None and (current_turn is not None or total_turns is not None):
        # Load full multiturn session to get turn data
        unified_manager_mt = get_unified_session_manager(queue_manager)
        cloud_multiturn_session = await unified_manager_mt.get_multiturn_session_by_id(session_id)

        if cloud_multiturn_session and "turns" in cloud_multiturn_session:
            turns = cloud_multiturn_session["turns"]
            # Find the specified turn
            target_turn = None
            if isinstance(turns, list):
                for turn in turns:
                    if turn.get("turn_number") == turn_number:
                        target_turn = turn
                        break

            if target_turn:
                # Get turn-specific results
                turn_files = target_turn.get("files", {})

                # Try to include S3 files (like images) from cloud storage
                try:
                    cloud_session = await cloud_storage_manager.retrieve_session_from_cloud(session_id)
                    if cloud_session and "s3_files" in cloud_session:
                        s3_files = cloud_session["s3_files"]
                        # Merge S3 files (especially images) into turn files
                        if isinstance(turn_files, dict):
                            # Add images from S3 if not already in turn_files
                            if "images" in s3_files and "images" not in turn_files:
                                turn_files["images"] = s3_files["images"]
                except Exception as e:
                    print(f"Warning: Could not retrieve S3 files for turn results: {e}")

                # Generate URLs for turn files
                if turn_files:
                    turn_files = generate_file_urls(turn_files, session_id)

                # Append images and download links to final report
                final_report = target_turn.get("final_report", "")
                print(f"[RESULTS] Turn files keys: {list(turn_files.keys()) if turn_files else 'None'}")
                final_report_with_images = append_images_to_report(final_report, turn_files)

                # Return turn-specific results (NO thinking_content, NO snapshots)
                result = {
                    "session_id": session_id,
                    "turn_number": turn_number,
                    "current_turn": current_turn,
                    "total_turns": total_turns,
                    "status": target_turn.get("status", "completed"),
                    "timestamp": target_turn.get("timestamp"),
                    "language": cloud_multiturn_session.get("language", "en"),
                    "query": target_turn.get("query"),
                    "files": turn_files,
                    "content": {
                        "final_report": final_report_with_images
                    }
                }
                return result

    # For cloud sessions, retrieve from MongoDB
    storage_location = session_data.get("_storage_location", "unknown")
    if storage_location == "cloud":
        # Get full session data from cloud
        cloud_session = await cloud_storage_manager.retrieve_session_from_cloud(session_id)
        if cloud_session:
            # Generate URLs for S3 files
            s3_files = cloud_session.get("s3_files", {})
            s3_files_with_urls = generate_file_urls(s3_files, session_id)

            # Append images to final report
            final_report = cloud_session.get("final_report", "")
            final_report_with_images = append_images_to_report(final_report, s3_files_with_urls)

            # Return structured result (NO thinking_content, NO snapshots)
            result = {
                "session_id": session_id,
                "status": cloud_session.get("status", "completed"),
                "content": {
                    "final_report": final_report_with_images
                },
                "files": s3_files_with_urls,  # Changed from s3_files to files for consistency
                "result_summary": cloud_session.get("result_summary", {})
            }
            # Add turn information if available
            if current_turn is not None and total_turns is not None:
                result["turn_number"] = turn_number
                result["current_turn"] = current_turn
                result["total_turns"] = total_turns
            return result

    # For local/active sessions, use existing json_result
    json_result = session_data.get("json_result")
    if not json_result:
        # Session completed but no JSON result (possibly old session or error)
        result = {
            "session_id": session_id,
            "status": session_data.get("status", "unknown"),
            "error": "No structured results available for this session",
            "legacy_result": {
                "result": session_data.get("result"),
                "error": session_data.get("error"),
                "created_at": session_data.get("created_at")
            }
        }
        # Add turn information if available
        if current_turn is not None and total_turns is not None:
            result["turn_number"] = turn_number
            result["current_turn"] = current_turn
            result["total_turns"] = total_turns
        return result

    # Check if local files exist, if not try to get S3 files from cloud storage
    if "files" in json_result:
        # Check if any local files are missing
        files = json_result["files"]
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

        # If local files are missing, try to get S3 files from cloud
        if has_missing_files:
            try:
                cloud_session = await cloud_storage_manager.retrieve_session_from_cloud(session_id)
                if cloud_session and "s3_files" in cloud_session:
                    # Merge cloud S3 files into json_result
                    print(f"Local files missing for session {session_id}, using S3 files from cloud storage")
                    json_result["files"] = cloud_session["s3_files"]
            except Exception as e:
                print(f"Warning: Could not retrieve S3 files from cloud for session {session_id}: {e}")

    # Generate URLs for any files in the result
    if "files" in json_result:
        json_result["files"] = generate_file_urls(json_result["files"], session_id)
    if "s3_files" in json_result:
        json_result["s3_files"] = generate_file_urls(json_result["s3_files"], session_id)

    # Append images to final report
    if "content" in json_result and isinstance(json_result["content"], dict):
        if "final_report" in json_result["content"]:
            files_for_images = json_result.get("files") or json_result.get("s3_files", {})
            json_result["content"]["final_report"] = append_images_to_report(
                json_result["content"]["final_report"],
                files_for_images
            )

    # Add turn information if available
    if current_turn is not None and total_turns is not None:
        json_result["turn_number"] = turn_number
        json_result["current_turn"] = current_turn
        json_result["total_turns"] = total_turns

    # Remove thinking_content and snapshots from response (not needed in /results)
    if "content" in json_result and isinstance(json_result["content"], dict):
        if "thinking_content" in json_result["content"]:
            del json_result["content"]["thinking_content"]
            print(f"Removed thinking_content from /results response for session {session_id}")

    # Remove snapshots from top level if present
    if "snapshots" in json_result:
        del json_result["snapshots"]
        print(f"Removed snapshots from /results response for session {session_id}")

    return json_result




@router.post("/stop/{session_id}")
async def stop_task(session_id: str, user_id: str):
    """Stop a running or queued task"""
    # Validate user_id
    if not user_id or user_id.strip() == "":
        raise HTTPException(status_code=400, detail="user_id is required and cannot be empty")

    # First verify user owns this session
    if session_id in queue_manager.active_sessions:
        session_user_id = getattr(queue_manager.active_sessions[session_id], 'user_id', None)
        if session_user_id and session_user_id != user_id:
            raise HTTPException(status_code=403, detail="Access denied: Session belongs to different user")

    success = queue_manager.stop_session(session_id)
    if success:
        return {
            "message": f"Task {session_id} has been cancelled",
            "session_id": session_id,
            "status": "cancelled"
        }
    else:
        raise HTTPException(status_code=404, detail="Session not found")


# REMOVED: /ws/{session_id} endpoint - WebSocket not used by Gradio and doesn't validate user_id


# REMOVED: /stream/{session_id} endpoint - SSE streaming not used by Gradio (uses polling instead)




@router.get("/snapshots/{session_id}")
async def get_session_snapshots(session_id: str, user_id: str, turn_number: Optional[int] = None):
    """Get all periodic snapshots for a session

    Args:
        session_id: The session ID
        user_id: The user ID
        turn_number: Optional turn number to retrieve snapshots for. If not provided, returns current/latest turn snapshots.
    """
    # Validate user_id
    if not user_id or user_id.strip() == "":
        raise HTTPException(status_code=400, detail="user_id is required and cannot be empty")

    # Get multi-turn session info to determine turn number
    multiturn_session = queue_manager.multiturn_sessions.get(session_id)
    current_turn = None
    total_turns = None

    # If not in memory, try to load from cloud
    if not multiturn_session:
        try:
            unified_manager = get_unified_session_manager(queue_manager)
            cloud_multiturn_session = await unified_manager.get_multiturn_session_by_id(session_id)
            if cloud_multiturn_session:
                current_turn = cloud_multiturn_session.get("current_turn")
                total_turns = cloud_multiturn_session.get("total_turns")
        except Exception as e:
            print(f"Could not load multiturn session info from cloud: {e}")
    else:
        current_turn = multiturn_session.current_turn
        total_turns = multiturn_session.total_turns

    # Process turn_number if we have turn information
    if current_turn is not None and total_turns is not None:
        # If turn_number not specified, use current turn (latest)
        if turn_number is None:
            turn_number = current_turn
        # Validate turn_number is within range
        elif turn_number < 1 or turn_number > total_turns:
            raise HTTPException(status_code=400, detail=f"Invalid turn_number. Must be between 1 and {total_turns}")

    # Use unified session manager to check both local and cloud storage
    unified_manager = get_unified_session_manager(queue_manager)
    session_data = await unified_manager.get_session_by_id(session_id)

    if not session_data:
        raise HTTPException(status_code=404, detail="Session not found")

    # Verify user owns this session
    session_user_id = session_data.get("user_id")
    if session_user_id and session_user_id != user_id:
        raise HTTPException(status_code=403, detail="Access denied: Session belongs to different user")

    # For multi-turn sessions with specific turn_number, return turn-specific snapshot
    if turn_number is not None and (current_turn is not None or total_turns is not None):
        # Load full multiturn session to get turn data
        unified_manager_mt = get_unified_session_manager(queue_manager)
        cloud_multiturn_session = await unified_manager_mt.get_multiturn_session_by_id(session_id)

        if cloud_multiturn_session and "turns" in cloud_multiturn_session:
            turns = cloud_multiturn_session["turns"]
            # Find the specified turn
            target_turn = None
            if isinstance(turns, list):
                for turn in turns:
                    if turn.get("turn_number") == turn_number:
                        target_turn = turn
                        break

            if target_turn:
                # Return ONLY the thinking process TEXT for this turn
                turn_files = target_turn.get("files", {})
                thinking_process_file = turn_files.get("thinking_process") if turn_files else None

                print(f"[SNAPSHOTS DEBUG] Turn {turn_number} found")
                print(f"[SNAPSHOTS DEBUG] turn_files keys: {list(turn_files.keys()) if turn_files else 'None'}")
                print(f"[SNAPSHOTS DEBUG] thinking_process_file: {thinking_process_file}")

                # Read the thinking process text content
                thinking_process_text = None
                if thinking_process_file:
                    try:
                        # Handle both string paths (local) and dict (cloud metadata or enhanced metadata)
                        if isinstance(thinking_process_file, str):
                            # Local file path - check if exists and read
                            print(f"[SNAPSHOTS DEBUG] Thinking process file is a string path: {thinking_process_file}")
                            print(f"[SNAPSHOTS DEBUG] File exists: {os.path.exists(thinking_process_file)}")
                            if os.path.exists(thinking_process_file):
                                with open(thinking_process_file, 'r', encoding='utf-8') as f:
                                    thinking_process_text = f.read()
                                print(f"[SNAPSHOTS DEBUG] Read {len(thinking_process_text)} characters from file")
                            else:
                                print(f"[SNAPSHOTS DEBUG] File does not exist at path: {thinking_process_file}")
                        elif isinstance(thinking_process_file, dict):
                            # Dict can be either: 1) enhanced metadata with 'path', or 2) cloud S3 metadata with 's3_key'

                            # First try 'path' key (enhanced local metadata)
                            file_path = thinking_process_file.get("path")
                            if file_path:
                                print(f"[SNAPSHOTS DEBUG] Thinking process file is a dict with path: {file_path}")
                                print(f"[SNAPSHOTS DEBUG] File exists: {os.path.exists(file_path)}")
                                if os.path.exists(file_path):
                                    with open(file_path, 'r', encoding='utf-8') as f:
                                        thinking_process_text = f.read()
                                    print(f"[SNAPSHOTS DEBUG] Read {len(thinking_process_text)} characters from file")
                                else:
                                    print(f"[SNAPSHOTS DEBUG] File does not exist locally at path: {file_path}")
                                    print(f"[SNAPSHOTS DEBUG] Will try to retrieve from cloud storage...")

                            # If no 'path', try 's3_key' (cloud metadata)
                            elif thinking_process_file.get("s3_key"):
                                s3_key = thinking_process_file.get("s3_key")
                                print(f"[SNAPSHOTS DEBUG] Thinking process file is a dict with s3_key: {s3_key}")
                                try:
                                    # Download content from S3 (synchronous method)
                                    content = cloud_storage_manager.download_file_content(s3_key)
                                    if content:
                                        thinking_process_text = content.decode('utf-8')
                                        print(f"[SNAPSHOTS DEBUG] Downloaded {len(thinking_process_text)} characters from S3")
                                except Exception as e:
                                    print(f"Warning: Could not download thinking process from S3: {e}")

                        # If still not found, try to retrieve from cloud storage
                        if not thinking_process_text:
                            print(f"[SNAPSHOTS DEBUG] Attempting to retrieve from cloud storage...")
                            try:
                                cloud_session = await cloud_storage_manager.retrieve_session_from_cloud(session_id)
                                print(f"[SNAPSHOTS DEBUG] Cloud session found: {cloud_session is not None}")
                                if cloud_session and "s3_files" in cloud_session:
                                    s3_files = cloud_session["s3_files"]
                                    print(f"[SNAPSHOTS DEBUG] s3_files keys: {list(s3_files.keys())}")

                                    # Look for thinking process in S3 files
                                    thinking_process_files = s3_files.get("thinking_process")
                                    print(f"[SNAPSHOTS DEBUG] thinking_process files in S3: {thinking_process_files}")

                                    if thinking_process_files:
                                        # Handle both dict (single file) and list (multiple files)
                                        files_to_check = []
                                        if isinstance(thinking_process_files, dict):
                                            files_to_check = [thinking_process_files]
                                        elif isinstance(thinking_process_files, list):
                                            files_to_check = thinking_process_files

                                        for file_info in files_to_check:
                                            if isinstance(file_info, dict) and "s3_key" in file_info:
                                                print(f"[SNAPSHOTS DEBUG] Downloading from S3 key: {file_info['s3_key']}")
                                                # Download content from S3 (synchronous method)
                                                content = cloud_storage_manager.download_file_content(file_info["s3_key"])
                                                if content:
                                                    thinking_process_text = content.decode('utf-8')
                                                    print(f"[SNAPSHOTS DEBUG] Downloaded {len(thinking_process_text)} characters from S3")
                                                    break
                                else:
                                    print(f"[SNAPSHOTS DEBUG] No s3_files in cloud session")
                            except Exception as e:
                                print(f"[SNAPSHOTS DEBUG] Error retrieving from cloud: {e}")
                                import traceback
                                traceback.print_exc()
                    except Exception as e:
                        print(f"Error reading thinking process file: {e}")

                print(f"[SNAPSHOTS DEBUG] Final thinking_process_text length: {len(thinking_process_text) if thinking_process_text else 0}")
                print(f"[SNAPSHOTS DEBUG] thinking_process_text is None: {thinking_process_text is None}")

                result = {
                    "session_id": session_id,
                    "turn_number": turn_number,
                    "current_turn": current_turn,
                    "total_turns": total_turns,
                    "thinking_process": thinking_process_text,
                    "storage_location": "turn_specific"
                }
                return result

    # For cloud sessions, get session-level snapshots from S3
    storage_location = session_data.get("_storage_location", "unknown")
    if storage_location == "cloud":
        cloud_session = await cloud_storage_manager.retrieve_session_from_cloud(session_id)
        if cloud_session:
            s3_files = cloud_session.get("s3_files", {})
            snapshots_info = s3_files.get("snapshots", [])

            # Generate presigned URLs for snapshot files
            snapshots_with_urls = []
            for snapshot in snapshots_info:
                if isinstance(snapshot, dict) and "s3_key" in snapshot:
                    url = cloud_storage_manager.generate_presigned_url(snapshot["s3_key"])
                    snapshots_with_urls.append({
                        "filename": snapshot.get("filename"),
                        "url": url,
                        "file_size": snapshot.get("file_size", 0),
                        "uploaded_at": snapshot.get("uploaded_at")
                    })

            result = {
                "session_id": session_id,
                "snapshot_count": len(snapshots_with_urls),
                "snapshots": snapshots_with_urls,
                "storage_location": "cloud"
            }
            # Add turn information
            if current_turn is not None:
                result["turn_number"] = turn_number
                result["current_turn"] = current_turn
                result["total_turns"] = total_turns
            return result

    # For local/active sessions (in-progress), extract thinking process from periodic snapshots
    periodic_snapshots = session_data.get("periodic_snapshots", [])
    thinking_process_text = None

    # Extract thinking content from the latest periodic snapshot
    if periodic_snapshots and len(periodic_snapshots) > 0:
        latest_snapshot = periodic_snapshots[-1]  # Get the most recent snapshot
        print(f"[SNAPSHOTS DEBUG] Latest snapshot keys: {list(latest_snapshot.keys()) if isinstance(latest_snapshot, dict) else 'not a dict'}")

        if isinstance(latest_snapshot, dict):
            # Try to get thinking_content from the nested content object
            content = latest_snapshot.get("content")
            if isinstance(content, dict):
                thinking_process_text = content.get("thinking_content")
            # Fallback: try direct access
            if not thinking_process_text:
                thinking_process_text = latest_snapshot.get("thinking_content")

    print(f"[SNAPSHOTS DEBUG] Local/active session - periodic_snapshots count: {len(periodic_snapshots)}")
    print(f"[SNAPSHOTS DEBUG] Extracted thinking_process length: {len(thinking_process_text) if thinking_process_text else 0}")

    result = {
        "session_id": session_id,
        "turn_number": turn_number,
        "current_turn": current_turn,
        "total_turns": total_turns,
        "thinking_process": thinking_process_text,
        "storage_location": storage_location
    }
    return result




@router.get("/all-sessions")
async def get_all_sessions(user_id: Optional[str] = None):
    """Get all sessions from both local and cloud storage"""
    try:
        # Require user_id for security - prevent unauthorized access to all sessions
        if not user_id or user_id.strip() == "":
            return {"sessions": [], "error": "user_id is required", "message": "Please provide a valid user_id"}

        # Get unified session manager
        unified_manager = get_unified_session_manager(queue_manager)

        # Get all sessions (local + cloud) filtered by user_id
        all_sessions = await unified_manager.get_all_sessions(include_cloud=True, user_id=user_id)

        # Convert to expected format for compatibility
        formatted_sessions = []
        for session in all_sessions:
            # Handle both old and new session formats
            query = session.get("query", session.get("message", ""))

            session_info = {
                "session_id": session["session_id"],
                "query": query[:200] + ("..." if len(query) > 200 else ""),
                "full_query": query,
                "language": session.get("language", "en"),
                "files_count": len(session.get("uploaded_files", [])),
                "timestamp": session.get("timestamp", session.get("created_at", "")),
                "status": session.get("status", "unknown"),
                "is_complete": session.get("is_complete", False),
                # Add storage info for debugging (remove in production)
                "_source": session.get("_storage_location", "unknown")
            }
            formatted_sessions.append(session_info)

        return {"sessions": formatted_sessions}
    except Exception as e:
        print(f"Error getting all sessions: {e}")
        # Fallback to original local-only logic if unified manager fails
        return {"sessions": []}


# Multi-Turn Conversation Endpoints





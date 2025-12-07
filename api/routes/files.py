"""
Files route handlers for dleader_agent API.
"""

from typing import List, Optional

import pandas as pd
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

router = APIRouter(tags=["files"])


@router.get("/download/{session_id}")
async def download_session_zip(session_id: str, user_id: str):
    """Download session zip file from local or cloud storage"""
    # Validate user_id
    if not user_id or user_id.strip() == "":
        raise HTTPException(status_code=400, detail="user_id is required and cannot be empty")

    import requests
    from fastapi.responses import RedirectResponse

    try:
        # For multi-turn sessions, extract base session ID
        base_session_id = session_id
        if "_turn_" in session_id:
            base_session_id = session_id.split("_turn_")[0]
            print(f"Multi-turn download request: {session_id} -> base: {base_session_id}")

        # Get unified session manager
        unified_manager = get_unified_session_manager(queue_manager)

        # First verify user owns this session (try both session IDs)
        session_data = await unified_manager.get_session_by_id(session_id)
        if not session_data and base_session_id != session_id:
            session_data = await unified_manager.get_session_by_id(base_session_id)

        if not session_data:
            raise HTTPException(status_code=404, detail="Session not found")

        session_user_id = session_data.get("user_id")
        if session_user_id and session_user_id != user_id:
            raise HTTPException(status_code=403, detail="Access denied: Session belongs to different user")

        # Get session files info using unified manager (use base session ID for files)
        files_info = await unified_manager.get_session_files(base_session_id)
        if not files_info:
            raise HTTPException(status_code=404, detail="Session files not found")

        download_method = files_info.get("download_method", "none")

        if download_method == "local_zip":
            # Local session: serve zip file directly
            zip_path = files_info.get("zip_path")
            if zip_path and os.path.exists(zip_path):
                return FileResponse(
                    zip_path,
                    media_type='application/zip',
                    filename=os.path.basename(zip_path)
                )
            else:
                raise HTTPException(status_code=404, detail="Local zip file not found")

        elif download_method == "s3_keys":
            # Cloud session: generate fresh presigned URL
            s3_files = files_info.get("s3_files", {})
            session_zip_info = s3_files.get("session_zip")

            if session_zip_info and isinstance(session_zip_info, dict):
                s3_key = session_zip_info.get("s3_key")
                if s3_key:
                    # Generate fresh presigned URL (2 hours)
                    fresh_url = cloud_storage_manager.generate_presigned_url(s3_key, expiry_seconds=7200)
                    # Redirect to fresh S3 presigned URL
                    return RedirectResponse(url=fresh_url)
                else:
                    raise HTTPException(status_code=404, detail="Cloud zip S3 key not available")
            else:
                raise HTTPException(status_code=404, detail="Cloud zip file not found")

        elif download_method == "none":
            # Active session: files not ready yet
            message = files_info.get("message", "Session files not ready for download")
            raise HTTPException(status_code=425, detail=message)

        else:
            raise HTTPException(status_code=500, detail=f"Unknown download method: {download_method}")

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        print(f"Error in download endpoint for session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Error preparing download: {str(e)}")


# REMOVED: /list-zips endpoint - was insecure (exposed all zip files)
# Use session-specific download endpoints with user_id validation instead




@router.get("/download-file/{session_id}/{filename:path}")
async def download_individual_file(session_id: str, filename: str, user_id: str):
    """Download individual file from a session

    Args:
        session_id: The session ID
        filename: The filename to download (can include subdirectories)
        user_id: User identifier for access control
    """
    # Validate user_id
    if not user_id or user_id.strip() == "":
        raise HTTPException(status_code=400, detail="user_id is required and cannot be empty")

    try:
        # Get unified session manager
        unified_manager = get_unified_session_manager(queue_manager)

        # Get session data to verify ownership and find files
        session_data = await unified_manager.get_session_by_id(session_id)
        if not session_data:
            raise HTTPException(status_code=404, detail="Session not found")

        # Verify user owns this session
        session_user_id = session_data.get("user_id")
        if session_user_id and session_user_id != user_id:
            raise HTTPException(status_code=403, detail="Access denied: Session belongs to different user")

        storage_location = session_data.get("_storage_location", "unknown")

        # For cloud sessions, try to get file from S3
        if storage_location == "cloud":
            cloud_session = await cloud_storage_manager.retrieve_session_from_cloud(session_id)
            if cloud_session:
                s3_files = cloud_session.get("s3_files", {})

                # Search for the file in s3_files
                file_s3_key = None

                # Check images
                if "images" in s3_files:
                    for img in s3_files["images"]:
                        if isinstance(img, dict) and img.get("filename") == filename:
                            file_s3_key = img.get("s3_key")
                            break

                # Check other file types if not found in images
                if not file_s3_key:
                    for file_type, file_data in s3_files.items():
                        if isinstance(file_data, dict) and file_data.get("filename") == filename:
                            file_s3_key = file_data.get("s3_key")
                            break
                        elif isinstance(file_data, list):
                            for item in file_data:
                                if isinstance(item, dict) and item.get("filename") == filename:
                                    file_s3_key = item.get("s3_key")
                                    break
                            if file_s3_key:
                                break

                if file_s3_key:
                    # Generate presigned URL and redirect
                    fresh_url = cloud_storage_manager.generate_presigned_url(file_s3_key, expiry_seconds=7200)
                    return RedirectResponse(url=fresh_url)
                else:
                    raise HTTPException(status_code=404, detail=f"File '{filename}' not found in cloud storage")

        # For local sessions, serve from local filesystem
        session_path = session_data.get("session_path")
        if not session_path:
            # Try to find session folder
            import glob
            patterns = [
                f"chat_sessions/*{session_id[:8]}*",
                f"chat_sessions/multiturn_*{session_id[:8]}*"
            ]
            for pattern in patterns:
                matches = glob.glob(pattern)
                if matches:
                    session_path = matches[0]
                    break

        if session_path and os.path.exists(session_path):
            # Construct file path (handle both direct filename and subdirectory/filename)
            file_path = os.path.join(session_path, filename)

            # Security check: ensure file is within session directory
            file_path = os.path.abspath(file_path)
            session_path = os.path.abspath(session_path)
            if not file_path.startswith(session_path):
                raise HTTPException(status_code=403, detail="Access denied: Invalid file path")

            if os.path.exists(file_path) and os.path.isfile(file_path):
                # Determine media type based on extension
                import mimetypes
                media_type, _ = mimetypes.guess_type(file_path)
                if not media_type:
                    media_type = "application/octet-stream"

                return FileResponse(
                    file_path,
                    media_type=media_type,
                    filename=os.path.basename(file_path)
                )
            else:
                raise HTTPException(status_code=404, detail=f"File '{filename}' not found in local storage")

        raise HTTPException(status_code=404, detail="Session files not available")

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error downloading file {filename} from session {session_id}: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error downloading file: {str(e)}")




@router.get("/download-urls/{session_id}")
async def get_session_download_urls(session_id: str, user_id: str, turn_number: Optional[int] = None):
    """Get download URLs for session files (always prefer S3/cloud)

    Args:
        session_id: The session ID
        user_id: The user ID
        turn_number: Optional turn number to retrieve files for. If not provided, returns current/latest turn files.
    """
    try:
        # For multi-turn sessions, extract base session ID
        base_session_id = session_id
        if "_turn_" in session_id:
            base_session_id = session_id.split("_turn_")[0]
            print(f"Multi-turn session detected: {session_id} -> base: {base_session_id}")

        # Get multi-turn session info to determine turn number
        multiturn_session = queue_manager.multiturn_sessions.get(base_session_id)
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

        # Use unified session manager to check both local and cloud storage
        unified_manager = get_unified_session_manager(queue_manager)

        # Try both session IDs (with and without turn suffix)
        session_data = await unified_manager.get_session_by_id(session_id)
        if not session_data and base_session_id != session_id:
            session_data = await unified_manager.get_session_by_id(base_session_id)

        if not session_data:
            raise HTTPException(status_code=404, detail="Session not found")

        # Verify user owns this session
        session_user_id = session_data.get("user_id")
        if session_user_id and session_user_id != user_id:
            raise HTTPException(status_code=403, detail="Access denied: Session belongs to different user")

        storage_location = session_data.get("_storage_location", "unknown")

        # For cloud sessions, get presigned URLs from S3
        if storage_location == "cloud":
            download_data = await cloud_storage_manager.get_session_download_urls(base_session_id)
            if download_data:
                # Add turn information
                if multiturn_session:
                    download_data["turn_number"] = turn_number
                    download_data["current_turn"] = current_turn
                    download_data["total_turns"] = total_turns
                return download_data
            else:
                raise HTTPException(status_code=500, detail="Failed to generate download URLs from cloud storage")

        # For local sessions, try to create/find local zip OR check cloud storage
        session_path = session_data.get("session_path")
        if not session_path and session_data.get("is_complete"):
            # Try to find session folder
            import glob
            patterns = [
                f"chat_sessions/*{session_id[:8]}*",
                f"chat_sessions/multiturn_*{session_id[:8]}*"
            ]
            for pattern in patterns:
                matches = glob.glob(pattern)
                if matches:
                    session_path = matches[0]
                    break

        if session_path and os.path.exists(session_path):
            # Create zip if it doesn't exist
            zip_filename = f"session_{session_id[:8]}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
            zip_path = os.path.join("chat_zips", zip_filename)

            if not os.path.exists(zip_path):
                zip_path = create_session_zip(session_path, save_to_chat_zips=True)

            # Return local download URL
            result = {
                "session_id": session_id,
                "download_url": f"/download/{session_id}?user_id={user_id}",
                "zip_available": True,
                "storage_type": storage_location
            }
            # Add turn information
            if multiturn_session:
                result["turn_number"] = turn_number
                result["current_turn"] = current_turn
                result["total_turns"] = total_turns
            return result

        # Local folder not found - try cloud storage as fallback
        # (files may have been uploaded to S3 even if storage_location is "local")
        try:
            download_data = await cloud_storage_manager.get_session_download_urls(base_session_id)
            if download_data:
                print(f"Local folder not found for session {session_id}, using cloud storage download URLs")
                # Add turn information
                if multiturn_session:
                    download_data["turn_number"] = turn_number
                    download_data["current_turn"] = current_turn
                    download_data["total_turns"] = total_turns
                return download_data
        except Exception as e:
            print(f"Warning: Could not retrieve download URLs from cloud: {e}")

        # No files found anywhere
        raise HTTPException(status_code=404, detail="No downloadable files found for session")

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error getting download URLs for session {session_id}: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error generating download URLs: {str(e)}")


# Note: Cloud storage is now integrated transparently into all endpoints
# Sessions are automatically uploaded to cloud when completed
# Use the standard endpoints (/all-sessions, /status/{id}, etc.) to access both local and cloud data

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="FastAPI Agent Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8001, help="Port to bind to")
    parser.add_argument("--no-reload", action="store_true", help="Disable auto-reload (auto-reload is enabled by default)")

    args = parser.parse_args()

    # Enable reload by default, disable only if --no-reload is specified
    reload_enabled = not args.no_reload

    uvicorn.run(
        "agent_fastapi_server_multiturn:app",
        host=args.host,
        port=args.port,
        reload=reload_enabled
    )




"""
Chat route handlers for dleader_agent API.
"""

from typing import List, Optional

import uuid
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
    UserRequest,
)
from api.utils import (
    create_session_zip,
    generate_file_urls,
    get_template_retriever,
)
from cloud_storage_manager import cloud_storage_manager
from unified_session_manager import UnifiedSessionManager
from unified_session_manager import get_unified_session_manager

router = APIRouter(tags=["chat"])


@router.post("/chat-queue")
async def start_chat_queue(
    message: str = Form(...),
    language: Language = Form(Language.EN),
    user_id: str = Form(...),
    session_id: Optional[str] = Form(None),
    use_template: bool = Form(True),
    files: List[UploadFile] = File(default=[])
):
    """Add chat request to queue with S3 file uploads

    Args:
        message: User's message/query
        language: Language for response (en/jp)
        user_id: User identifier
        session_id: Optional session ID (creates new if not provided)
        use_template: Whether to use template matching (default: True)
        files: Uploaded files
    """
    # Validate user_id
    if not user_id or user_id.strip() == "":
        raise HTTPException(status_code=400, detail="user_id is required and cannot be empty")

    session_id = session_id or str(uuid.uuid4())

    # Create or get multi-turn session first to get turn number
    multiturn_session = queue_manager.create_or_get_multiturn_session(session_id, language, user_id, initial_query=message)
    turn_number = queue_manager.add_turn_to_session(session_id, message)

    # Handle file uploads with S3 storage
    uploaded_file_paths = []
    s3_file_metadata = {}  # Store S3 metadata for files
    rejected_files = []  # Track rejected files

    if files and any(file.filename for file in files):
        # Create temporary upload directory for this session
        upload_dir = os.path.join(os.getcwd(), "temp_uploads", session_id)
        os.makedirs(upload_dir, exist_ok=True)

        for file in files:
            if file.filename:
                # Read file content
                content = await file.read()
                file_size = len(content)
                file_size_mb = file_size / (1024 * 1024)

                # Check file size
                if file_size > MAX_FILE_SIZE_BYTES:
                    rejected_files.append({
                        "filename": file.filename,
                        "size_mb": round(file_size_mb, 2),
                        "reason": f"File size {file_size_mb:.2f}MB exceeds maximum {MAX_FILE_SIZE_MB}MB"
                    })
                    logger.warning(f"Rejected file {file.filename}: size {file_size_mb:.2f}MB > {MAX_FILE_SIZE_MB}MB limit")
                    continue

                # Save file temporarily
                temp_file_path = os.path.join(upload_dir, file.filename)
                with open(temp_file_path, "wb") as buffer:
                    buffer.write(content)

                # Upload to S3 if cloud storage is configured
                if cloud_storage_manager and cloud_storage_manager.s3_client:
                    try:
                        # Generate S3 object name with session and turn context
                        s3_object_name = f"sessions/{session_id}/turn{turn_number}_{file.filename}"

                        # Upload to S3
                        cloud_storage_manager.s3_client.upload_file(
                            temp_file_path,
                            cloud_storage_manager.bucket_name,
                            s3_object_name
                        )

                        # Store S3 metadata
                        s3_file_metadata[file.filename] = {
                            "s3_key": s3_object_name,
                            "bucket": cloud_storage_manager.bucket_name,
                            "local_path": temp_file_path,
                            "turn_number": turn_number,
                            "upload_time": datetime.now().isoformat(),
                            "file_size": file_size,
                            "file_size_mb": round(file_size_mb, 2)
                        }

                        logger.info(f"Uploaded {file.filename} to S3: {s3_object_name} (size: {file_size_mb:.2f}MB)")
                    except Exception as e:
                        logger.error(f"Failed to upload {file.filename} to S3: {e}")
                        # Continue with local file path as fallback

                uploaded_file_paths.append(temp_file_path)

    # Check if all files were rejected
    if rejected_files and not uploaded_file_paths:
        error_msg = f"All files rejected due to size limits. Maximum file size is {MAX_FILE_SIZE_MB}MB. "
        error_msg += "Rejected files: " + ", ".join([f"{f['filename']} ({f['size_mb']}MB)" for f in rejected_files])
        raise HTTPException(status_code=413, detail=error_msg)

    # Store S3 metadata in turn data for future retrieval
    if s3_file_metadata:
        # Store S3 metadata in the current turn (will be saved when turn completes)
        # For now, store it temporarily in queue_manager for processing
        if not hasattr(queue_manager, '_temp_s3_metadata'):
            queue_manager._temp_s3_metadata = {}
        queue_manager._temp_s3_metadata[f"{session_id}_turn_{turn_number}"] = s3_file_metadata

    # Create user request with both local paths and S3 metadata
    user_request = UserRequest(
        session_id=session_id,
        message=message,
        language=language,
        uploaded_files=uploaded_file_paths,
        turn_number=turn_number,
        user_id=user_id,
        use_template=use_template
    )

    # Store S3 metadata in user request for processing
    user_request.s3_file_metadata = s3_file_metadata

    # Store reference to original multi-turn session
    user_request.original_session_id = session_id

    # Add to queue
    position = queue_manager.add_request(user_request)

    response = {
        "session_id": session_id,
        "turn_number": turn_number,
        "status": "queued",
        "position": position,
        "uploaded_files": len(uploaded_file_paths),
        "s3_files": list(s3_file_metadata.keys()) if s3_file_metadata else [],
        "message": "Request added to queue. Files uploaded to S3. Use /status/{session_id} to check progress."
    }

    # Add rejected files info if any
    if rejected_files:
        response["rejected_files"] = rejected_files
        response["message"] = f"Request added to queue. {len(uploaded_file_paths)} files uploaded, {len(rejected_files)} rejected (>10MB)."

    return response



@router.post("/continue-session")
async def continue_session(
    session_id: str = Form(...),
    message: str = Form(...),
    language: Language = Form(Language.EN),
    user_id: str = Form(...),
    use_template: bool = Form(True),
    files: List[UploadFile] = File(default=[])
):
    """Continue an existing multi-turn session with S3 file handling

    Args:
        session_id: The session ID to continue
        message: User's message/query
        language: Language for response (en/jp)
        user_id: User identifier
        use_template: Whether to use template matching (default: True)
        files: Uploaded files
    """
    # Validate user_id
    if not user_id or user_id.strip() == "":
        raise HTTPException(status_code=400, detail="user_id is required and cannot be empty")

    # Check if multi-turn session exists in memory
    multiturn_session = queue_manager.multiturn_sessions.get(session_id)

    # If not in memory, try to load from cloud storage
    if not multiturn_session:
        try:
            unified_manager = get_unified_session_manager(queue_manager)
            cloud_session_data = await unified_manager.get_multiturn_session_by_id(session_id)

            if cloud_session_data:
                # Verify user owns this session before restoring
                session_user_id = cloud_session_data.get("user_id")
                if session_user_id and session_user_id != user_id:
                    raise HTTPException(status_code=403, detail="Access denied: Session belongs to different user")

                # Restore session to memory from cloud data
                multiturn_session = MultiTurnSession(
                    session_id=cloud_session_data.get("session_id"),
                    user_id=cloud_session_data.get("user_id"),
                    language=cloud_session_data.get("language", "en"),
                    created_at=cloud_session_data.get("created_at", datetime.now().isoformat()),
                    last_updated=cloud_session_data.get("last_updated", datetime.now().isoformat()),
                    total_turns=cloud_session_data.get("total_turns", 0),
                    current_turn=cloud_session_data.get("current_turn", 0),
                    accumulated_context=cloud_session_data.get("accumulated_context", ""),
                    session_status=cloud_session_data.get("session_status", "active"),
                    session_name=cloud_session_data.get("session_name", "")
                )

                # Restore turns
                if "turns" in cloud_session_data and isinstance(cloud_session_data["turns"], list):
                    for turn_data in cloud_session_data["turns"]:
                        turn = ConversationTurn(
                            turn_number=turn_data.get("turn_number"),
                            query=turn_data.get("query", ""),
                            final_report=turn_data.get("final_report"),
                            response_content=turn_data.get("response_content"),
                            files=turn_data.get("files"),
                            timestamp=turn_data.get("timestamp", datetime.now().isoformat()),
                            status=turn_data.get("status", "completed")
                        )
                        multiturn_session.turns.append(turn)

                # Add back to in-memory sessions
                queue_manager.multiturn_sessions[session_id] = multiturn_session
                print(f"Restored session {session_id} from cloud storage to continue conversation")
            else:
                raise HTTPException(status_code=404, detail="Multi-turn session not found")
        except HTTPException:
            raise
        except Exception as e:
            print(f"Error loading session from cloud: {e}")
            import traceback
            traceback.print_exc()
            raise HTTPException(status_code=404, detail="Multi-turn session not found")

    # Verify user owns this session
    if multiturn_session.user_id and multiturn_session.user_id != user_id:
        raise HTTPException(status_code=403, detail="Access denied: Session belongs to different user")

    # Add new turn to session first to get turn number
    try:
        turn_number = queue_manager.add_turn_to_session(session_id, message)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Handle file uploads with S3 storage
    uploaded_file_paths = []
    s3_file_metadata = {}  # Store S3 metadata for new files
    rejected_files = []  # Track rejected files

    if files and any(file.filename for file in files):
        # Create temporary upload directory for this session
        upload_dir = os.path.join(os.getcwd(), "temp_uploads", session_id)
        os.makedirs(upload_dir, exist_ok=True)

        for file in files:
            if file.filename:
                # Read file content
                content = await file.read()
                file_size = len(content)
                file_size_mb = file_size / (1024 * 1024)

                # Check file size
                if file_size > MAX_FILE_SIZE_BYTES:
                    rejected_files.append({
                        "filename": file.filename,
                        "size_mb": round(file_size_mb, 2),
                        "reason": f"File size {file_size_mb:.2f}MB exceeds maximum {MAX_FILE_SIZE_MB}MB"
                    })
                    logger.warning(f"Rejected file {file.filename}: size {file_size_mb:.2f}MB > {MAX_FILE_SIZE_MB}MB limit")
                    continue

                # Save file temporarily (without turn prefix for compatibility)
                temp_file_path = os.path.join(upload_dir, file.filename)
                with open(temp_file_path, "wb") as buffer:
                    buffer.write(content)

                # Upload to S3 if cloud storage is configured
                if cloud_storage_manager and cloud_storage_manager.s3_client:
                    try:
                        # Generate S3 object name with session and turn context
                        s3_object_name = f"sessions/{session_id}/turn{turn_number}_{file.filename}"

                        # Upload to S3
                        cloud_storage_manager.s3_client.upload_file(
                            temp_file_path,
                            cloud_storage_manager.bucket_name,
                            s3_object_name
                        )

                        # Store S3 metadata
                        s3_file_metadata[file.filename] = {
                            "s3_key": s3_object_name,
                            "bucket": cloud_storage_manager.bucket_name,
                            "local_path": temp_file_path,
                            "turn_number": turn_number,
                            "upload_time": datetime.now().isoformat(),
                            "file_size": file_size,
                            "file_size_mb": round(file_size_mb, 2)
                        }

                        logger.info(f"Uploaded {file.filename} to S3: {s3_object_name} (size: {file_size_mb:.2f}MB)")
                    except Exception as e:
                        logger.error(f"Failed to upload {file.filename} to S3: {e}")

                uploaded_file_paths.append(temp_file_path)

    # Check if all files were rejected
    if rejected_files and not uploaded_file_paths:
        error_msg = f"All files rejected due to size limits. Maximum file size is {MAX_FILE_SIZE_MB}MB. "
        error_msg += "Rejected files: " + ", ".join([f"{f['filename']} ({f['size_mb']}MB)" for f in rejected_files])
        raise HTTPException(status_code=413, detail=error_msg)

    # Store S3 metadata in turn data for future retrieval
    if s3_file_metadata:
        # Store S3 metadata in the current turn (will be saved when turn completes)
        # For now, store it temporarily in queue_manager for processing
        if not hasattr(queue_manager, '_temp_s3_metadata'):
            queue_manager._temp_s3_metadata = {}
        queue_manager._temp_s3_metadata[f"{session_id}_turn_{turn_number}"] = s3_file_metadata

    # Build enhanced context that includes S3 file references
    enhanced_context = queue_manager.multiturn_handler.build_enhanced_context(
        multiturn_session=multiturn_session,
        current_message=message,
        uploaded_files=uploaded_file_paths,
        include_file_list=True
    )

    # Add S3 metadata to context for file restoration
    # Check if we have stored S3 metadata for previous turns
    if hasattr(queue_manager, '_temp_s3_metadata'):
        for key, turn_files in queue_manager._temp_s3_metadata.items():
            if key.startswith(session_id):
                # Extract turn number from key
                turn_num = int(key.split('_turn_')[-1]) if '_turn_' in key else 1
                for filename, metadata in turn_files.items():
                    if filename not in enhanced_context.get('all_files', {}):
                        enhanced_context['all_files'][filename] = {
                            'turn': turn_num,
                            's3_key': metadata['s3_key'],
                            'bucket': metadata['bucket'],
                            'type': 'file',
                            'needs_download': True  # Flag for download from S3
                        }

    # Create user request with enhanced context
    user_request = UserRequest(
        session_id=f"{session_id}_turn_{turn_number}",  # Unique ID for this turn
        message=message,
        language=language,
        uploaded_files=uploaded_file_paths,
        is_continuation=True,
        previous_context=enhanced_context['enhanced_message'],
        turn_number=turn_number,
        user_id=user_id,
        use_template=use_template
    )

    # Store file metadata including S3 references
    user_request.all_turn_files = enhanced_context.get('all_files', {})
    user_request.s3_file_metadata = s3_file_metadata

    # Store reference to original multi-turn session
    user_request.original_session_id = session_id

    # Add to queue
    position = queue_manager.add_request(user_request)

    response = {
        "session_id": session_id,
        "turn_session_id": f"{session_id}_turn_{turn_number}",
        "turn_number": turn_number,
        "status": "queued",
        "position": position,
        "uploaded_files": len(uploaded_file_paths),
        "s3_files": list(s3_file_metadata.keys()) if s3_file_metadata else [],
        "message": f"Turn {turn_number} added to queue with S3 storage. Use /status/{session_id}_turn_{turn_number} to check progress."
    }

    # Add rejected files info if any
    if rejected_files:
        response["rejected_files"] = rejected_files
        response["message"] = f"Turn {turn_number} added. {len(uploaded_file_paths)} files uploaded, {len(rejected_files)} rejected (>10MB)."

    return response





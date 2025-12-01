"""
FastAPI Agent Server with Multi-Turn Conversation Support

This FastAPI server provides:
- Multi-turn conversation sessions
- Context preservation across conversation turns
- Multi-user concurrent handling with queue system
- Language support for English and Japanese
- Session management and file handling
- Real-time streaming of agent responses
- Thread-safe queue management
- Conversation history and turn-based interactions
- Integration with cloud storage for session persistence
- Template-based workflow initiation
- Enhanced error handling and logging
"""

import asyncio
import glob
import json
import logging
import multiprocessing
import os
import queue
import shutil
import signal
import sys
import tempfile
import threading
import time
import uuid
import zipfile
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from enum import Enum
from multiprocessing import Process
from multiprocessing import Queue as MPQueue
from typing import Any, Dict, List, Optional

import pandas as pd
import uvicorn
from fastapi import (FastAPI, File, Form, HTTPException, Request, UploadFile,
                     WebSocket, WebSocketDisconnect)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware

# Add current directory to path for imports
sys.path.insert(0, os.getcwd())

# Import cloud storage manager
from cloud_storage_manager import cloud_storage_manager
from dleader_agent.agent.a1 import A1
# Import enhanced multi-turn handler
from enhanced_multiturn_handler import EnhancedMultiTurnHandler
# Import template retriever for workflow template matching
from template_retriever import TemplateRetriever
# Import unified session manager
from unified_session_manager import get_unified_session_manager
# Import TurnType enum from models
from api.models import TurnType
# Import allowed users list
from allowed_emails import is_user_allowed, ALLOWED_EMAILS

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# File size limits
MAX_FILE_SIZE_MB = 10  # Maximum file size in MB
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024  # Convert to bytes

# Language and timezone configurations
JST = timezone(timedelta(hours=9))

class Language(str, Enum):
    EN = "en"
    JP = "jp"

def now_jst():
    """Get current time in JST (UTC+9)"""
    return datetime.now(JST)


def should_use_template_matching(query: str, language: str = "en") -> bool:
    """
    Use LLM to intelligently determine if a query needs template matching based on complexity.
    Uses the same LLM configuration as the main agent for consistency.

    The LLM will analyze the query to determine if it:
    - Is a simple query (e.g., "1+1", "hello", "what is DNA") -> No template matching
    - Requires complex biomedical workflow execution -> Template matching

    Args:
        query: The user's query string
        language: The language of the query ("en" or "jp")

    Returns:
        bool: True if template matching should be used, False otherwise
    """
    try:
        # Import Anthropic client
        from anthropic import Anthropic
        import os

        # Create Anthropic client
        client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

        # Use the same model as the main agent (Claude Sonnet 4.5)
        model = "claude-sonnet-4-5-20250929"

        # Prepare the prompt for the LLM
        if language == "jp":
            system_prompt = """あなたは、クエリが複雑なバイオメディカルワークフローテンプレートを必要とするかどうかを判断する分類器です。

次のようなシンプルなクエリには「NO」と答えてください：
- 簡単な数式（1+1、2*3など）
- 挨拶や基本的な会話
- 単純な定義の質問
- 単一の概念の簡単な説明

次のような複雑なクエリには「YES」と答えてください：
- バイオメディカル分析ワークフロー
- 多段階のデータ処理
- 統計分析やモデリング
- 複数のツールやステップを必要とするタスク

「YES」または「NO」のみで回答してください。"""
        else:
            system_prompt = """You are a classifier that determines if a query requires complex biomedical workflow template matching.

Answer "NO" for simple queries like:
- Simple math expressions (1+1, 2*3, etc.)
- Greetings and basic conversation
- Simple definition questions
- Brief explanations of single concepts
- General questions that don't require tool execution or workflows

Answer "YES" for complex queries that require:
- Biomedical analysis workflows
- Multi-step data processing
- Statistical analysis or modeling
- Tasks requiring multiple tools or steps
- Scientific research or experimental design

Respond with ONLY "YES" or "NO"."""

        # Call the LLM with same model as main agent
        response = client.messages.create(
            model=model,
            max_tokens=10,
            temperature=0,
            system=system_prompt,
            messages=[{
                "role": "user",
                "content": f"Query: {query}\n\nDoes this query require workflow template matching?"
            }]
        )

        # Parse response
        answer = response.content[0].text.strip().upper()

        # Extract YES/NO from response
        if "YES" in answer:
            logger.info(f"LLM decided: USE template matching for query: {query[:100]}")
            return True
        elif "NO" in answer:
            logger.info(f"LLM decided: SKIP template matching for query: {query[:100]}")
            return False
        else:
            # If unclear, default to using template matching (safer)
            logger.warning(f"LLM response unclear ('{answer}'), defaulting to template matching")
            return True

    except Exception as e:
        # If LLM call fails, default to template matching (safer)
        logger.error(f"Error in LLM-based template detection: {e}")
        logger.info("Falling back to default: using template matching")
        return True


# Request/Response Models
class ChatRequest(BaseModel):
    message: str
    language: Language = Language.EN
    session_id: Optional[str] = None
    user_id: Optional[str] = None

class ChatResponse(BaseModel):
    session_id: str
    status: str
    thinking_content: Optional[str] = None
    final_report: Optional[str] = None
    progress_updates: List[Dict[str, Any]] = []
    session_path: Optional[str] = None
    error: Optional[str] = None

class QueueStatus(BaseModel):
    position: int
    estimated_wait_time: int  # in seconds
    total_users_in_queue: int
    chats_ahead: int  # number of chats waiting before this one

class SessionInfo(BaseModel):
    session_id: str
    status: str
    created_at: str
    language: Language
    query: str

# Multi-Turn Data Structures
class ConversationTurn(BaseModel):
    turn_number: int
    turn_type: str = "execution"  # "planning" or "execution"
    query: str
    response_content: Optional[str] = None
    final_report: Optional[str] = None
    files: Optional[Dict[str, Any]] = None  # Changed to Any to support richer file metadata
    timestamp: str
    status: str = "processing"
    ready_for_execution: Optional[bool] = None  # Only relevant for planning turns

class MultiTurnSession(BaseModel):
    session_id: str
    session_name: str = ""  # Name for the multi-session (default: first 30 chars of first query)
    created_at: str
    last_updated: str
    language: Language
    user_id: Optional[str] = None
    total_turns: int = 0
    current_turn: int = 0
    turns: List[ConversationTurn] = []
    accumulated_context: str = ""
    session_status: str = "active"  # active, completed, error

    # Sharing metadata
    is_shared: bool = False
    shared_at: Optional[str] = None

    @property
    def first_query(self) -> str:
        """Get the first query from the turns"""
        return self.turns[0].query if self.turns else ""

    @property
    def latest_query(self) -> str:
        """Get the latest query from the turns"""
        return self.turns[-1].query if self.turns else ""

class ContinueRequest(BaseModel):
    session_id: str
    message: str
    language: Language = Language.EN
    user_id: Optional[str] = None

class RenameMultiSessionRequest(BaseModel):
    session_id: str
    new_name: str
    user_id: str

# Template Models
class Template(BaseModel):
    title: str
    running_time: str
    tools: int
    description: str
    prompt: Optional[str] = None
    query: Optional[str] = None
    change_suggestions: Optional[List[str]] = None
    session_id: Optional[str] = None

class TemplateListRequest(BaseModel):
    templates: List[Template]

class TemplateResponse(BaseModel):
    success: bool
    message: str
    total_templates: Optional[int] = None

# Sharing Models
class ShareSessionRequest(BaseModel):
    session_id: str
    user_id: Optional[str] = None

class SharedSessionInfo(BaseModel):
    session_id: str
    title: str
    description: Optional[str] = None
    tags: List[str]
    visibility: str
    shared_by: str
    shared_at: str
    total_turns: int
    language: str
    first_query: str
    last_query: str

# Queue Management System
class UserRequest:
    def __init__(self, session_id: str, message: str, language: Language, uploaded_files: List[str] = None,
                 is_continuation: bool = False, previous_context: str = "", turn_number: int = 1, user_id: str = None,
                 use_template: bool = True, turn_type: str = "execution"):
        self.session_id = session_id
        self.message = message
        self.language = language
        self.uploaded_files = uploaded_files or []
        self.created_at = datetime.now()
        self.status = "queued"
        self.progress_queue = queue.Queue()
        self.result = None
        self.error = None
        self.is_complete = False
        self.is_cancelled = False
        self.agent_thread = None  # Will be replaced with process
        self.agent_process = None  # Process for agent execution
        self.process_queue = None  # Multiprocessing queue for IPC
        self.json_result = None  # Store structured JSON result
        self.periodic_snapshots = []  # Store periodic JSON snapshots
        self.last_snapshot_time = None  # Track last snapshot time
        self.snapshot_files = []  # Track snapshot file paths for S3 upload
        self.session_path = None  # Store session path for JSON updates
        self.all_progress_updates = []  # Store all progress updates permanently
        self.user_id = user_id  # User ownership tracking
        self.task_start_time = None  # Track when task actually starts processing
        self.stop_requested = False  # Flag to signal stop request
        self.use_template = use_template  # Template matching control flag

        # Multi-turn specific attributes
        self.is_continuation = is_continuation
        self.previous_context = previous_context
        self.turn_number = turn_number
        self.turn_type = turn_type  # "planning" or "execution"
        self.enhanced_message = self._build_enhanced_message()

        # Planning mode specific attributes
        self.ready_for_execution = None  # Set after planning turn completes
        self.agent_config = None  # Custom agent config for planning mode

        # Template matching attributes
        self.template_matched = False
        self.template_title = None
        self.template_confidence = None
        self.template_reasoning = None
        self.template_modification = None
        self.augmented_query = None

    def _build_enhanced_message(self):
        """Build enhanced message with previous context for multi-turn conversations"""
        # For backward compatibility, keep the simple version
        # The actual enhanced context will be built when processing the request
        if self.is_continuation and self.previous_context:
            return f"""Previous conversation context:
{self.previous_context}

Current question/request:
{self.message}

Please provide a response that builds upon the previous analysis and addresses the current question."""
        return self.message

class QueueManager:
    def __init__(self, skip_startup_session_check: bool = False):
        """Initialize QueueManager

        Args:
            skip_startup_session_check: If True, skip scanning local session files on startup.
                                        This is safe since sessions are loaded on-demand from cloud storage.
        """
        self.request_queue = queue.Queue()
        self.active_sessions = {}  # session_id -> UserRequest
        self.session_history = {}  # session_id -> SessionManager
        self.processing_lock = threading.Lock()
        self.is_processing = False
        self.current_processing_session = None

        # Multi-turn session storage
        self.multiturn_sessions = {}  # session_id -> MultiTurnSession

        # Initialize enhanced multi-turn handler
        self.multiturn_handler = EnhancedMultiTurnHandler(cloud_storage_manager)

        # Create persistent storage directory
        self.sessions_storage_dir = os.path.join(os.getcwd(), "session_storage")
        self.multiturn_storage_dir = os.path.join(os.getcwd(), "multiturn_sessions")
        os.makedirs(self.sessions_storage_dir, exist_ok=True)
        os.makedirs(self.multiturn_storage_dir, exist_ok=True)

        # Load existing sessions from storage (optional - can be skipped for faster startup)
        if not skip_startup_session_check:
            self._load_sessions_from_storage()
        else:
            print("Skipping startup session check (sessions loaded on-demand from cloud storage)")
        # Note: Multi-turn sessions are now loaded from MongoDB on-demand, not from local files
        # self._load_multiturn_sessions()  # REMOVED: No longer loading from local JSON files

        # Start the queue processor
        self.processor_thread = threading.Thread(target=self._process_queue, daemon=True)
        self.processor_thread.start()

        # Start periodic cleanup thread for old cached sessions
        self.cleanup_thread = threading.Thread(target=self._periodic_cache_cleanup, daemon=True)
        self.cleanup_thread.start()
    
    def add_request(self, user_request: UserRequest) -> int:
        """Add request to queue and return position"""
        with self.processing_lock:
            self.active_sessions[user_request.session_id] = user_request
            self.request_queue.put(user_request)
            return self.request_queue.qsize()
    
    def get_queue_status(self, session_id: str) -> Optional[QueueStatus]:
        """Get current queue position for a session"""
        with self.processing_lock:
            if session_id == self.current_processing_session:
                # Currently processing - no one ahead in the queue
                return QueueStatus(
                    position=0,
                    estimated_wait_time=0,
                    total_users_in_queue=self.request_queue.qsize(),
                    chats_ahead=0
                )

            # Find position in queue
            temp_queue = []
            position = 0
            found = False

            while not self.request_queue.empty():
                req = self.request_queue.get()
                temp_queue.append(req)
                position += 1
                if req.session_id == session_id:
                    found = True
                    break

            # Put items back in queue
            for req in reversed(temp_queue):
                self.request_queue.put(req)

            if found:
                # chats_ahead = position - 1 (position is 1-indexed, so subtract 1)
                # Plus 1 if there's a currently processing session (it's ahead of everyone in queue)
                chats_ahead = position - 1
                if self.current_processing_session:
                    chats_ahead += 1

                # Estimate 2 minutes per request ahead
                estimated_wait = (chats_ahead + 1) * 120  # +1 for the current processing session if any
                return QueueStatus(
                    position=position,
                    estimated_wait_time=estimated_wait,
                    total_users_in_queue=self.request_queue.qsize(),
                    chats_ahead=chats_ahead
                )

            return None
    
    def get_session_progress(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get current progress for a session"""
        if session_id in self.active_sessions:
            user_request = self.active_sessions[session_id]

            # Get new progress updates without consuming them from the queue
            new_progress_updates = []
            temp_updates = []
            while not user_request.progress_queue.empty():
                try:
                    update = user_request.progress_queue.get_nowait()
                    new_progress_updates.append(update)
                    temp_updates.append(update)
                except queue.Empty:
                    break

            # Put the updates back in the queue
            for update in temp_updates:
                user_request.progress_queue.put(update)

            # Add new updates to permanent storage
            user_request.all_progress_updates.extend(new_progress_updates)

            # Keep only the latest snapshot_saved and thinking_update items
            def filter_latest_updates(updates):
                filtered = []
                latest_snapshot = None
                latest_thinking = None

                # Find the latest snapshot_saved and thinking_update
                for update in updates:
                    if update.get("type") == "snapshot_saved":
                        latest_snapshot = update
                    elif update.get("type") == "thinking_update":
                        latest_thinking = update
                    else:
                        # Keep all other types as they are
                        filtered.append(update)

                # Add only the latest snapshot_saved and thinking_update at the end
                if latest_snapshot:
                    filtered.append(latest_snapshot)
                if latest_thinking:
                    filtered.append(latest_thinking)

                return filtered

            # Apply filtering to keep only latest snapshot_saved and thinking_update
            user_request.all_progress_updates = filter_latest_updates(user_request.all_progress_updates)

            # Save session to persistent storage
            self._save_session_to_storage(user_request)

            return {
                "session_id": session_id,
                "status": user_request.status,
                "is_complete": user_request.is_complete,
                "is_cancelled": user_request.is_cancelled,
                "error": user_request.error,
                "result": user_request.result,
                "progress_updates": new_progress_updates,  # Only return new updates
                "all_progress_updates": user_request.all_progress_updates,  # All updates
                "created_at": user_request.created_at.isoformat(),
                "json_result": user_request.json_result,
                "periodic_snapshots": user_request.periodic_snapshots,
                "snapshot_count": len(user_request.periodic_snapshots),
                "user_id": getattr(user_request, 'user_id', None),  # Include user_id for security
                "storage_location": "active"  # Mark as active session for /status endpoint
            }

        # Try to load from persistent storage if not in active sessions
        return self._load_session_from_storage(session_id)

    def _clean_thinking_content(self, thinking_content: str, original_message: str) -> str:
        """Clean thinking content to show only original user message in Human Message sections"""
        if not thinking_content:
            return thinking_content

        # Find and replace enhanced message with original message in Human Message sections
        import re

        # Pattern to match Human Message sections with enhanced content
        pattern = r'(================================ Human Message =================================\n\n)(.*?)((?=\n================================== Ai Message|$))'

        def replace_human_message(match):
            prefix = match.group(1)
            suffix = match.group(3) if match.group(3) else ""
            # Replace the enhanced content with just the original message
            return f"{prefix}{original_message}{suffix}"

        cleaned_content = re.sub(pattern, replace_human_message, thinking_content, flags=re.DOTALL)
        return cleaned_content

    def _add_template_header(self, thinking_content: str, user_request: UserRequest) -> str:
        """Add template information header to thinking content if template was matched"""
        if not user_request.template_matched:
            return thinking_content

        template_header = f"""{'='*80}
WORKFLOW TEMPLATE MATCHED
{'='*80}

Template: {user_request.template_title}
Confidence: {user_request.template_confidence}
Reasoning: {user_request.template_reasoning}
"""
        if user_request.template_modification:
            template_header += f"Modification Applied: {user_request.template_modification}\n"

        template_header += f"\n{'='*80}\n\n"
        return template_header + thinking_content

    def create_json_snapshot(self, user_request: UserRequest, accumulated_thinking: str = "", session_path: str = "") -> dict:
        """Create a JSON snapshot of current progress"""
        # Collect image files from session if path exists
        # For multi-turn sessions, only include images created during this turn
        image_files = []
        if session_path and os.path.exists(session_path):
            image_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.svg', '.webp'}
            turn_start_time = user_request.turn_start_time if hasattr(user_request, 'turn_start_time') else None
            for file in os.listdir(session_path):
                if any(file.lower().endswith(ext) for ext in image_extensions):
                    file_path = os.path.join(session_path, file)
                    # Filter by turn_start_time for multi-turn sessions
                    if turn_start_time is not None:
                        file_mtime = os.path.getmtime(file_path)
                        if file_mtime < turn_start_time:
                            continue  # Skip images from previous turns
                    image_files.append(file_path)

        # Clean the thinking content to show only original user message and add template header
        cleaned_thinking = self._clean_thinking_content(accumulated_thinking, user_request.message)
        cleaned_thinking = self._add_template_header(cleaned_thinking, user_request)

        snapshot = {
            "session_id": user_request.session_id,
            "status": user_request.status,
            "timestamp": datetime.now().isoformat(),
            "language": user_request.language.value,
            "query": user_request.message,
            "files": {
                "images": image_files,
                "session_zip": None  # Will be set after completion
            },
            "content": {
                "thinking_content": cleaned_thinking,
                "thinking_length": len(cleaned_thinking),
                "raw_result": user_request.result
            },
            "error": user_request.error,
            "session_path": session_path,
            "is_complete": user_request.is_complete,
            "is_cancelled": user_request.is_cancelled
        }
        return snapshot

    def stop_session(self, session_id: str) -> dict:
        """Stop a running or queued session

        Returns:
            dict with 'success' (bool), 'was_queued' (bool), and 'was_running' (bool)
            Returns {'success': False} if session not found
        """
        with self.processing_lock:
            if session_id not in self.active_sessions:
                return {"success": False}

            user_request = self.active_sessions[session_id]

            # Determine if session is queued (not yet processing) or running
            was_queued = user_request.status == "queued"
            was_running = self.current_processing_session == session_id

            # Mark as cancelled
            user_request.is_cancelled = True
            user_request.status = "cancelled"
            user_request.is_complete = True
            user_request.error = "Task was cancelled by user"
            user_request.stop_requested = True  # Set stop flag

            # Add cancellation progress update
            user_request.progress_queue.put({
                "type": "cancelled",
                "message": "Task was cancelled by user",
                "was_queued": was_queued,
                "was_running": was_running,
                "timestamp": datetime.now().isoformat()
            })

            # Force stop the agent process if running
            if hasattr(user_request, 'agent_process') and user_request.agent_process and user_request.agent_process.is_alive():
                pid = user_request.agent_process.pid
                print(f"Terminating process tree for session {session_id} (PID: {pid})")

                try:
                    import psutil

                    # Get the process and all its children
                    parent = psutil.Process(pid)
                    children = parent.children(recursive=True)

                    # Terminate all children first
                    for child in children:
                        try:
                            print(f"  Terminating child process PID {child.pid}")
                            child.terminate()
                        except:
                            pass

                    # Then terminate parent
                    user_request.agent_process.terminate()

                    # Wait for graceful termination
                    try:
                        user_request.agent_process.join(timeout=2.0)
                    except:
                        pass

                    # If still alive, force kill everything
                    if user_request.agent_process.is_alive():
                        print(f"Force killing process tree for session {session_id}")

                        # Kill all children
                        for child in children:
                            try:
                                child.kill()
                            except:
                                pass

                        # Kill parent
                        user_request.agent_process.kill()
                        time.sleep(0.5)

                except Exception as e:
                    print(f"Error using psutil, falling back to simple kill: {e}")
                    # Fallback to simple terminate/kill
                    user_request.agent_process.terminate()
                    time.sleep(2)
                    if user_request.agent_process.is_alive():
                        user_request.agent_process.kill()

                # Verify it's dead
                if not user_request.agent_process.is_alive():
                    print(f"SUCCESS: Process tree for session {session_id} terminated successfully")
                else:
                    print(f"WARNING: Process for session {session_id} may still be running")

            # Also check for legacy thread-based execution
            elif hasattr(user_request, 'agent_thread') and user_request.agent_thread and user_request.agent_thread.is_alive():
                # Legacy thread handling
                print(f"WARNING: Session {session_id} using thread-based execution (cannot force kill)")
                stopped = self._wait_and_verify_stop(user_request, session_id, max_wait=3)
                if not stopped:
                    print(f"ERROR: Thread for session {session_id} could not be stopped gracefully!")

            # For queued sessions, no need for file cleanup or S3 upload (no work was done)
            if was_queued:
                print(f"Session {session_id} was cancelled while in queue (no processing occurred)")
                # Remove from active sessions immediately for queued cancellations
                if session_id in self.active_sessions:
                    del self.active_sessions[session_id]
                return {"success": True, "was_queued": True, "was_running": False}

            # Move any generated files to session folder to keep workspace clean
            self._move_generated_files_to_session(user_request)

            # Save cancelled session state to storage and trigger cloud upload
            self._save_session_to_storage(user_request)

            # Ensure S3 upload for cancelled session
            self._trigger_s3_upload_for_session(user_request)

            return {"success": True, "was_queued": False, "was_running": was_running}

    def _wait_and_verify_stop(self, user_request: UserRequest, session_id: str, max_wait: int = 10) -> bool:
        """Wait for thread to stop and verify it's really stopped"""
        if not hasattr(user_request, 'agent_thread') or not user_request.agent_thread:
            return True

        print(f"Waiting for thread {session_id} to stop (max {max_wait} seconds)...")

        # Check every 0.5 seconds
        for i in range(max_wait * 2):
            if not user_request.agent_thread.is_alive():
                print(f"Thread stopped after {i * 0.5} seconds")
                return True
            time.sleep(0.5)

        # Final check
        return not user_request.agent_thread.is_alive()

    def _trigger_s3_upload_for_session(self, user_request: UserRequest):
        """Trigger S3 upload for a completed/cancelled session"""
        try:
            # Create zip if session has files
            if user_request.session_path and os.path.exists(user_request.session_path):
                zip_path = create_session_zip(user_request.session_path, save_to_chat_zips=True)
                print(f"Created zip for S3 upload: {zip_path}")

                # Copy ZIP file to session folder so it gets uploaded to S3
                if zip_path and os.path.exists(zip_path):
                    import shutil
                    zip_filename = os.path.basename(zip_path)
                    session_zip_path = os.path.join(user_request.session_path, zip_filename)
                    shutil.copy2(zip_path, session_zip_path)
                    print(f"Copied ZIP to session folder: {session_zip_path}")

            # Prepare session data for cloud upload
            session_data = {
                "session_id": user_request.session_id,
                "message": user_request.message,
                "language": user_request.language.value if hasattr(user_request.language, 'value') else user_request.language,
                "status": user_request.status,
                "is_complete": user_request.is_complete,
                "is_cancelled": user_request.is_cancelled,
                "error": user_request.error,
                "result": user_request.result,
                "json_result": user_request.json_result,
                "user_id": user_request.user_id,
                "session_path": user_request.session_path,
                "created_at": user_request.created_at.isoformat() if hasattr(user_request.created_at, 'isoformat') else str(user_request.created_at)
            }

            # Upload to cloud asynchronously
            def upload_in_thread():
                import asyncio
                try:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    loop.run_until_complete(cloud_storage_manager.upload_session_to_cloud(
                        user_request.session_id, session_data
                    ))
                    loop.close()
                    print(f"Successfully uploaded session {user_request.session_id} to S3")
                except Exception as e:
                    print(f"Failed to upload session {user_request.session_id} to S3: {e}")

            upload_thread = threading.Thread(target=upload_in_thread, daemon=True)
            upload_thread.start()
            print(f"Initiated S3 upload for session {user_request.session_id}")

        except Exception as e:
            print(f"Error triggering S3 upload for session {user_request.session_id}: {e}")

    def _save_session_to_storage(self, user_request: UserRequest):
        """Save session data to persistent storage"""
        try:
            session_file = os.path.join(self.sessions_storage_dir, f"{user_request.session_id}.json")
            session_data = {
                "session_id": user_request.session_id,
                "message": user_request.message,
                "language": user_request.language.value,
                "uploaded_files": user_request.uploaded_files,
                "created_at": user_request.created_at.isoformat(),
                "status": user_request.status,
                "is_complete": user_request.is_complete,
                "is_cancelled": user_request.is_cancelled,
                "error": user_request.error,
                "result": user_request.result,
                "json_result": user_request.json_result,
                "periodic_snapshots": user_request.periodic_snapshots,
                "session_path": user_request.session_path,
                "all_progress_updates": user_request.all_progress_updates,
                "user_id": user_request.user_id
            }

            with open(session_file, 'w', encoding='utf-8') as f:
                json.dump(session_data, f, indent=2, ensure_ascii=False, default=str)
        except Exception as e:
            print(f"Error saving session {user_request.session_id} to storage: {e}")

    def _move_generated_files_to_session(self, user_request: UserRequest):
        """Move ANY newly generated files to session folder when task is cancelled or completed"""
        try:
            # Use existing session path - it should always be set during _process_user_request
            session_path = user_request.session_path
            if not session_path:
                print(f"ERROR: No session_path set for session {user_request.session_id} - skipping file cleanup")
                return

            # Ensure the folder exists
            if not os.path.exists(session_path):
                os.makedirs(session_path, exist_ok=True)
                print(f"Created session path {session_path}")

            # Only look for files created after the task started
            if not user_request.task_start_time:
                print(f"No task start time recorded for session {user_request.session_id}, skipping file cleanup")
                return

            task_start_timestamp = user_request.task_start_time.timestamp()

            # System files to never move
            system_files = {
                'requirements.txt', 'requirements_fastapi.txt', 'requirements-test.txt',
                'pytest.ini', 'README.md', 'CLOUD_STORAGE_README.md', 'TEST_SUMMARY.md',
                '.env', '.env.example', 'Dockerfile', 'docker-compose.yml', '.gitignore',
                'setup.py', 'setup.cfg', 'pyproject.toml', 'Makefile', 'dleader_logo.png'
            }

            # Application Python files to skip
            app_python_files = {
                'agent_fastapi_server_multiturn.py', 'agent_gradio_fastapi_multiturn.py',
                'cloud_storage_manager.py', 'unified_session_manager.py', 'a1.py',
                'agent_fastapi_server.py', 'agent_interface_gradio.py'
            }

            import glob
            import shutil

            moved_files = []
            moved_folders = []
            skipped_large_files = []

            # Directories to never move
            system_dirs = {
                'session_storage', 'results', 'chat_zips', 'multiturn_sessions',
                'chat_sessions', 's3_mongodb', 'tests', 'docs', '__pycache__',
                '.git', '.github', 'node_modules', 'venv', 'env', '.env',
                'build', 'dist', 'egg-info', '.pytest_cache', '.vscode'
            }

            # Scan ALL files and directories in current directory
            for file_path in glob.glob("*"):
                filename = os.path.basename(file_path)

                # Handle directories
                if os.path.isdir(file_path):
                    # Skip system directories
                    if filename in system_dirs:
                        continue

                    # Check if directory was created after task started
                    try:
                        dir_mtime = os.path.getmtime(file_path)
                        dir_ctime = os.path.getctime(file_path)
                        dir_time = max(dir_mtime, dir_ctime)

                        if dir_time >= task_start_timestamp:
                            # Move entire directory to session folder
                            dest_path = os.path.join(session_path, filename)

                            # Handle duplicate directory names
                            if os.path.exists(dest_path):
                                counter = 1
                                while os.path.exists(dest_path):
                                    new_dirname = f"{filename}_{counter}"
                                    dest_path = os.path.join(session_path, new_dirname)
                                    counter += 1

                            # Calculate total size of directory
                            total_size = 0
                            for dirpath, dirnames, filenames in os.walk(file_path):
                                for f in filenames:
                                    fp = os.path.join(dirpath, f)
                                    if os.path.exists(fp):
                                        total_size += os.path.getsize(fp)

                            total_size_mb = total_size / (1024 * 1024)

                            if total_size_mb > 500:
                                print(f"Directory {filename} is too large ({total_size_mb:.1f}MB > 500MB limit), deleting...")
                                shutil.rmtree(file_path)
                                skipped_large_files.append(f"{filename}/ ({total_size_mb:.1f}MB)")
                            else:
                                shutil.move(file_path, dest_path)
                                moved_folders.append(filename)
                                print(f"Moved directory {filename}/ to session folder ({total_size_mb:.1f}MB)")
                    except Exception as e:
                        print(f"Error handling directory {filename}: {e}")

                    continue  # Skip to next item

                # Handle regular files
                filename = os.path.basename(file_path)

                # Skip system files and app files
                if filename in system_files or filename in app_python_files:
                    continue

                # Skip test files
                if filename.startswith('test_') and filename.endswith('.py'):
                    continue

                # Skip compiled Python files
                if filename.endswith(('.pyc', '.pyo', '.pyd')):
                    continue

                # Check if file was created or modified after task started
                try:
                    file_mtime = os.path.getmtime(file_path)
                    file_ctime = os.path.getctime(file_path)
                    file_time = max(file_mtime, file_ctime)

                    if file_time >= task_start_timestamp:
                        # Check file size (skip/delete files > 500MB)
                        file_size = os.path.getsize(file_path)
                        file_size_mb = file_size / (1024 * 1024)

                        if file_size_mb > 500:
                            skipped_large_files.append(f"{filename} ({file_size_mb:.1f}MB)")
                            print(f"Deleting large file {filename} ({file_size_mb:.1f}MB > 500MB limit)")
                            try:
                                os.remove(file_path)
                                print(f"Deleted {filename}")
                            except Exception as del_error:
                                print(f"Could not delete {filename}: {del_error}")
                        else:
                            # Move file to session folder
                            dest_path = os.path.join(session_path, filename)

                            # Handle duplicate filenames
                            if os.path.exists(dest_path):
                                base, ext = os.path.splitext(filename)
                                counter = 1
                                while os.path.exists(dest_path):
                                    new_filename = f"{base}_{counter}{ext}"
                                    dest_path = os.path.join(session_path, new_filename)
                                    counter += 1

                            shutil.move(file_path, dest_path)
                            moved_files.append(filename)
                            print(f"Moved {filename} to session folder ({file_size_mb:.1f}MB)")

                except Exception as e:
                    # Continue with other files even if one fails
                    pass

            if moved_files or moved_folders or skipped_large_files:
                summary_parts = []
                if moved_files:
                    summary_parts.append(f"{len(moved_files)} files")
                if moved_folders:
                    summary_parts.append(f"{len(moved_folders)} folders")
                if summary_parts:
                    summary = f"Moved {' and '.join(summary_parts)} to session folder"
                else:
                    summary = ""

                if skipped_large_files:
                    if summary:
                        summary += f", deleted {len(skipped_large_files)} large items (>500MB)"
                    else:
                        summary = f"Deleted {len(skipped_large_files)} large items (>500MB)"
                    print(f"Large items deleted: {', '.join(skipped_large_files)}")

                print(f"{summary} for session {user_request.session_id}")

                # Add progress update about file cleanup
                user_request.progress_queue.put({
                    "type": "cleanup",
                    "message": summary,
                    "files_moved": moved_files,
                    "folders_moved": moved_folders,
                    "files_deleted": skipped_large_files,
                    "timestamp": datetime.now().isoformat()
                })
            else:
                print(f"No new files found to move for session {user_request.session_id}")

        except Exception as e:
            print(f"Error moving generated files for session {user_request.session_id}: {e}")

    def _load_session_from_storage(self, session_id: str, silent_errors: bool = False) -> Optional[Dict[str, Any]]:
        """Load session data from persistent storage

        Args:
            session_id: The session ID to load
            silent_errors: If True, silently skip corrupted files instead of printing errors
        """
        try:
            session_file = os.path.join(self.sessions_storage_dir, f"{session_id}.json")
            if not os.path.exists(session_file):
                return None

            with open(session_file, 'r', encoding='utf-8') as f:
                session_data = json.load(f)

            return {
                "session_id": session_data["session_id"],
                "status": session_data["status"],
                "is_complete": session_data["is_complete"],
                "is_cancelled": session_data["is_cancelled"],
                "error": session_data.get("error"),
                "result": session_data.get("result"),
                "progress_updates": [],  # Return empty for old sessions
                "all_progress_updates": session_data.get("all_progress_updates", []),
                "created_at": session_data["created_at"],
                "json_result": session_data.get("json_result"),
                "periodic_snapshots": session_data.get("periodic_snapshots", []),
                "snapshot_count": len(session_data.get("periodic_snapshots", [])),
                "session_path": session_data.get("session_path"),  # Include session path
                "user_id": session_data.get("user_id")  # Include user_id
            }
        except json.JSONDecodeError as e:
            # JSON parsing error - file is corrupted
            if not silent_errors:
                print(f"Skipping corrupted session file {session_id}: JSON parse error")
            return None
        except Exception as e:
            if not silent_errors:
                print(f"Error loading session {session_id} from storage: {e}")
            return None

    def _load_sessions_from_storage(self):
        """Load all existing sessions from storage on startup

        Note: This function validates session files but doesn't restore them to active sessions.
        Sessions are now loaded on-demand from MongoDB/cloud storage.
        Corrupted/incomplete local JSON files are skipped gracefully.
        """
        try:
            if not os.path.exists(self.sessions_storage_dir):
                return

            total_files = 0
            corrupted_files = 0
            incomplete_sessions = 0

            for filename in os.listdir(self.sessions_storage_dir):
                if filename.endswith('.json'):
                    total_files += 1
                    session_id = filename[:-5]  # Remove .json extension
                    try:
                        # Load with silent errors to avoid spam on startup
                        session_data = self._load_session_from_storage(session_id, silent_errors=True)
                        if session_data is None:
                            # File is corrupted or unreadable
                            corrupted_files += 1
                        elif not session_data.get("is_complete", False):
                            # Track incomplete sessions (for logging/debugging)
                            incomplete_sessions += 1
                            # Note: We don't restore these anymore - they're loaded on-demand from cloud
                            pass
                    except Exception as e:
                        # Unexpected error beyond JSON parsing
                        corrupted_files += 1

            # Log summary instead of individual errors
            if total_files > 0:
                print(f"Session storage check: {total_files} files scanned, {corrupted_files} corrupted/skipped, {incomplete_sessions} incomplete")
                if corrupted_files > 0:
                    print(f"Note: {corrupted_files} corrupted session files were skipped. Sessions are now managed via cloud storage.")
        except Exception as e:
            print(f"Error scanning session storage: {e}")

    # REMOVED: No longer loading multi-turn sessions from local JSON files
    # Multi-turn sessions are now stored in MongoDB only and loaded on-demand
    # def _load_multiturn_sessions(self):
    #     """Load all existing multi-turn sessions from storage on startup"""
    #     try:
    #         if not os.path.exists(self.multiturn_storage_dir):
    #             return
    #
    #         for filename in os.listdir(self.multiturn_storage_dir):
    #             if filename.endswith('.json'):
    #                 session_id = filename[:-5]  # Remove .json extension
    #                 try:
    #                     session_file = os.path.join(self.multiturn_storage_dir, filename)
    #                     with open(session_file, 'r', encoding='utf-8') as f:
    #                         session_data = json.load(f)
    #                         multiturn_session = MultiTurnSession(**session_data)
    #                         self.multiturn_sessions[session_id] = multiturn_session
    #                 except Exception as e:
    #                     print(f"Error loading multi-turn session {session_id}: {e}")
    #     except Exception as e:
    #         print(f"Error loading multi-turn sessions from storage: {e}")

    def _save_multiturn_session(self, session: MultiTurnSession):
        """Save multi-turn session to MongoDB only (no local JSON)"""
        try:
            from s3_mongodb.func_mongodb import get_mongodb_collection, upsert_wrapper

            # DEBUG: Print in-memory turn files before serialization
            print(f"\n[DEBUG _save_multiturn_session] Session {session.session_id}")
            print(f"[DEBUG] Total turns in memory: {len(session.turns)}")
            for turn in session.turns:
                files_info = turn.files
                if isinstance(files_info, dict):
                    tp_file = files_info.get('thinking_process', {})
                    if isinstance(tp_file, dict):
                        tp_filename = tp_file.get('filename', 'N/A')
                    else:
                        tp_filename = str(tp_file)[:50]
                else:
                    tp_filename = str(files_info)[:50] if files_info else 'None'
                print(f"[DEBUG]   Turn {turn.turn_number}: TP file = {tp_filename}")

            # Prepare session data for MongoDB
            session_data = session.dict()
            session_data["_id"] = session.session_id
            session_data["last_updated"] = datetime.now().isoformat()

            # DEBUG: Print serialized data going to MongoDB
            print(f"[DEBUG] Serialized data for MongoDB:")
            for i, turn in enumerate(session_data.get('turns', [])):
                files_info = turn.get('files', {})
                if isinstance(files_info, dict):
                    tp_file = files_info.get('thinking_process', {})
                    if isinstance(tp_file, dict):
                        tp_filename = tp_file.get('filename', 'N/A')
                    else:
                        tp_filename = str(tp_file)[:50]
                else:
                    tp_filename = str(files_info)[:50] if files_info else 'None'
                print(f"[DEBUG]   Turn {turn.get('turn_number')}: TP file = {tp_filename}")

            # Save to MongoDB
            event = {
                "database_name": os.getenv("SESSION_DB_NAME", "dleader_agent"),
                "collection_name": "multiturn_sessions",
                "items": [session_data],
                "id_field": "_id"
            }

            result = upsert_wrapper(event)
            if result.get("statusCode") != 200:
                print(f"Warning: MongoDB save failed for session {session.session_id}: {result}")
            else:
                print(f"[DEBUG] MongoDB save successful for session {session.session_id}\n")
        except Exception as e:
            print(f"Error saving multi-turn session {session.session_id} to MongoDB: {e}")

    def create_or_get_multiturn_session(self, session_id: str, language: Language, user_id: str = None, initial_query: str = None) -> MultiTurnSession:
        """Create new multi-turn session or get existing one from MongoDB"""
        # Check in-memory cache first
        if session_id in self.multiturn_sessions:
            return self.multiturn_sessions[session_id]

        # Try to load from MongoDB
        try:
            from s3_mongodb.func_mongodb import get_mongodb_collection
            collection = get_mongodb_collection(
                os.getenv("SESSION_DB_NAME", "dleader_agent"),
                "multiturn_sessions"
            )
            if collection is not None:
                session_data = collection.find_one({"session_id": session_id})
                if session_data:
                    # DEBUG: Log file references from MongoDB load
                    print(f"[DEBUG QUEUEMGR LOAD FROM MONGODB] Session {session_id} found in MongoDB")
                    if "turns" in session_data and isinstance(session_data["turns"], list):
                        print(f"[DEBUG QUEUEMGR LOAD FROM MONGODB] Session has {len(session_data['turns'])} turns:")
                        for t in session_data["turns"]:
                            turn_num = t.get("turn_number")
                            files = t.get("files", {})
                            tp_file = files.get("thinking_process", {}).get("filename", "NONE") if isinstance(files.get("thinking_process"), dict) else "NONE"
                            report_file = files.get("final_report", {}).get("filename", "NONE") if isinstance(files.get("final_report"), dict) else "NONE"
                            print(f"[DEBUG QUEUEMGR LOAD FROM MONGODB]   Turn {turn_num}: TP={tp_file}, Report={report_file}")

                    # Remove MongoDB _id field
                    session_data.pop("_id", None)
                    session_data.pop("uploaded_to_cloud_at", None)
                    session = MultiTurnSession(**session_data)
                    self.multiturn_sessions[session_id] = session
                    print(f"[DEBUG QUEUEMGR LOAD FROM MONGODB] Session restored to in-memory cache")
                    return session
        except Exception as e:
            print(f"Error loading session {session_id} from MongoDB: {e}")

        # Create new multi-turn session
        now = datetime.now().isoformat()
        # Generate initial session name from first 30 characters of query
        session_name = ""
        if initial_query:
            session_name = initial_query[:30]

        session = MultiTurnSession(
            session_id=session_id,
            session_name=session_name,
            created_at=now,
            last_updated=now,
            language=language,
            user_id=user_id
        )
        self.multiturn_sessions[session_id] = session
        self._save_multiturn_session(session)
        return session

    def add_turn_to_session(self, session_id: str, query: str) -> int:
        """Add a new turn to existing multi-turn session"""
        session = self.multiturn_sessions.get(session_id)
        if not session:
            raise ValueError(f"Multi-turn session {session_id} not found")

        turn_number = session.total_turns + 1
        now = datetime.now().isoformat()

        new_turn = ConversationTurn(
            turn_number=turn_number,
            query=query,
            timestamp=now,
            status="processing"
        )

        session.turns.append(new_turn)
        session.total_turns = turn_number
        session.current_turn = turn_number
        session.last_updated = now

        self._save_multiturn_session(session)
        return turn_number

    def complete_turn(self, session_id: str, turn_number: int, response_content: str,
                     final_report: str, files: Dict[str, str], turn_type: str = "execution",
                     ready_for_execution: bool = None):
        """Complete a turn with results

        Args:
            session_id: Session identifier
            turn_number: Turn number
            response_content: Response content (thinking process)
            final_report: Final report
            files: Generated files
            turn_type: Type of turn ("planning" or "execution")
            ready_for_execution: For planning turns, whether agent is ready to execute
        """
        # DEBUG: Print what files were passed in
        print(f"\n[DEBUG complete_turn] Session {session_id}, Turn {turn_number}")
        print(f"[DEBUG] Files passed in:")
        if isinstance(files, dict):
            for fname, fpath in files.items():
                if isinstance(fpath, str):
                    # Extract just the filename from path
                    filename_only = os.path.basename(fpath) if '/' in fpath else fpath
                    print(f"[DEBUG]   {fname}: {filename_only}")
                else:
                    print(f"[DEBUG]   {fname}: {str(fpath)[:50]}")
        else:
            print(f"[DEBUG]   {files}")

        session = self.multiturn_sessions.get(session_id)
        if not session:
            return

        # Find the turn and update it
        for turn in session.turns:
            if turn.turn_number == turn_number:
                turn.response_content = response_content
                turn.final_report = final_report
                turn.turn_type = turn_type  # NEW FIELD
                if ready_for_execution is not None:
                    turn.ready_for_execution = ready_for_execution  # NEW FIELD for planning

                # Enhanced file tracking with metadata
                if files:
                    # Convert simple file paths to richer metadata
                    enhanced_files = {}
                    for file_name, file_path in (files.items() if isinstance(files, dict) else enumerate(files)):
                        if isinstance(file_path, str):
                            # Extract filename from path
                            filename = os.path.basename(file_path) if '/' in file_path or '\\' in file_path else file_path
                            file_metadata = {
                                'path': file_path,
                                'filename': filename,
                                'turn': turn_number,
                                'created_at': datetime.now().isoformat()
                            }

                            # Check if we have S3 metadata for this file
                            turn_key = f"{session_id}_turn_{turn_number}"
                            if hasattr(self, '_temp_s3_metadata') and turn_key in self._temp_s3_metadata:
                                s3_metadata = self._temp_s3_metadata[turn_key].get(file_name, {})
                                if s3_metadata:
                                    file_metadata.update({
                                        's3_key': s3_metadata.get('s3_key'),
                                        'bucket': s3_metadata.get('bucket'),
                                        'file_size': s3_metadata.get('file_size')
                                    })

                            enhanced_files[file_name if isinstance(files, dict) else str(file_path)] = file_metadata
                        else:
                            enhanced_files[file_name] = file_path
                    turn.files = enhanced_files

                    # DEBUG: Print what turn.files was set to
                    print(f"[DEBUG] Turn.files SET TO:")
                    tp_file = enhanced_files.get('thinking_process', {})
                    if isinstance(tp_file, dict):
                        print(f"[DEBUG]   thinking_process: {tp_file.get('path', 'N/A')}")
                    else:
                        print(f"[DEBUG]   thinking_process: {str(tp_file)[:50]}")
                else:
                    # Check session folder for any generated files during this turn
                    session_path = f"session_storage/{session_id}_turn_{turn_number}"
                    if os.path.exists(session_path):
                        generated_files = {}
                        for file_name in os.listdir(session_path):
                            file_path = os.path.join(session_path, file_name)
                            if os.path.isfile(file_path):
                                generated_files[file_name] = {
                                    'path': file_path,
                                    'turn': turn_number,
                                    'created_at': datetime.now().isoformat()
                                }
                        if generated_files:
                            turn.files = generated_files
                    else:
                        turn.files = files

                turn.status = "completed"
                break

        # Update accumulated context
        if final_report:
            if session.accumulated_context:
                session.accumulated_context += f"\n\n--- Turn {turn_number} Report ---\n{final_report}"
            else:
                session.accumulated_context = f"--- Turn {turn_number} Report ---\n{final_report}"

        session.last_updated = datetime.now().isoformat()
        self._save_multiturn_session(session)

    def _process_queue(self):
        """Background thread to process queue requests"""
        while True:
            try:
                # Get next request from queue
                user_request = self.request_queue.get(timeout=1)

                # Check if request was cancelled while in queue
                if user_request.is_cancelled:
                    print(f"Skipping cancelled request {user_request.session_id} (was stopped while in queue)")
                    # Clean up the cancelled session from active_sessions
                    with self.processing_lock:
                        if user_request.session_id in self.active_sessions:
                            del self.active_sessions[user_request.session_id]
                    continue

                with self.processing_lock:
                    self.is_processing = True
                    self.current_processing_session = user_request.session_id

                # Process the request
                self._process_user_request(user_request)

                with self.processing_lock:
                    self.is_processing = False
                    self.current_processing_session = None

            except queue.Empty:
                continue
            except Exception as e:
                print(f"Error in queue processor: {e}")
                with self.processing_lock:
                    self.is_processing = False
                    self.current_processing_session = None

    def _periodic_cache_cleanup(self):
        """Periodically clean up old cached sessions from memory (keep cache fresh)"""
        while True:
            try:
                # Run cleanup every 30 minutes
                time.sleep(1800)

                sessions_to_remove = []
                current_time = datetime.now()

                # Check all multiturn sessions in memory
                for session_id, session in self.multiturn_sessions.items():
                    try:
                        # Parse last_updated timestamp
                        last_updated_str = session.last_updated
                        last_updated = datetime.fromisoformat(last_updated_str)
                        age_hours = (current_time - last_updated).total_seconds() / 3600

                        # Remove sessions older than 1 hour that are completed
                        if age_hours > 1.0 and session.session_status == "completed":
                            sessions_to_remove.append(session_id)
                    except Exception as e:
                        # If we can't parse the date, skip this session
                        print(f"Warning: Could not check age for session {session_id}: {e}")
                        continue

                # Remove identified sessions
                for session_id in sessions_to_remove:
                    try:
                        del self.multiturn_sessions[session_id]
                        print(f"[Cache Cleanup] Removed old completed session {session_id} from memory")
                    except Exception as e:
                        print(f"Warning: Could not remove session {session_id}: {e}")

                if sessions_to_remove:
                    print(f"[Cache Cleanup] Removed {len(sessions_to_remove)} old sessions from cache")
                else:
                    print(f"[Cache Cleanup] No old sessions to remove (current cache size: {len(self.multiturn_sessions)})")

            except Exception as e:
                print(f"Error in periodic cache cleanup: {e}")
                # Continue running even if there's an error
                continue

    def _process_user_request(self, user_request: UserRequest):
        """Process a single user request"""
        try:
            user_request.status = "processing"
            user_request.task_start_time = datetime.now()  # Record when task actually starts
            user_request.progress_queue.put({"type": "status", "message": "Starting agent initialization..."})

            # For multi-turn sessions, use shared session folder
            if hasattr(user_request, 'original_session_id') and user_request.original_session_id:
                # This is a continuation turn - use existing session folder
                original_session_id = user_request.original_session_id
                if original_session_id in self.session_history:
                    # Reuse existing session manager and folder
                    session_manager = self.session_history[original_session_id]
                    session_path = session_manager.get_session_path()
                    session_name = os.path.basename(session_path)
                else:
                    # Create new shared session folder for multi-turn
                    session_manager = SessionManager()
                    session_path, session_name = session_manager.create_multiturn_session_folder(original_session_id)
                    self.session_history[original_session_id] = session_manager

                # Also store for this turn's session ID for compatibility
                self.session_history[user_request.session_id] = session_manager
            else:
                # Single turn or first turn - create new session
                session_manager = SessionManager()
                session_path, session_name = session_manager.create_session_folder()
                self.session_history[user_request.session_id] = session_manager

            user_request.session_path = session_path

            # Record start time for new file tracking
            # Store on user_request so it can be used for filtering images created during this turn
            start_time = time.time()
            user_request.turn_start_time = start_time
            current_path = os.getcwd()
            chat_sessions_path = os.path.join(current_path, "chat_sessions")
            
            # Initialize agent
            agent = create_agent()
            
            # Handle uploaded files for this turn
            if user_request.uploaded_files:
                user_request.progress_queue.put({"type": "status", "message": "Processing uploaded files..."})
                print(f"Processing {len(user_request.uploaded_files)} uploaded files for session {user_request.session_id}")
                print(f"Session path: {session_path}")

                # Ensure session folder exists before copying files
                os.makedirs(session_path, exist_ok=True)

                # Copy files from temp_uploads to shared session folder
                for file_path in user_request.uploaded_files:
                    if os.path.exists(file_path):
                        filename = os.path.basename(file_path)
                        new_path = os.path.join(session_path, filename)
                        print(f"Copying {file_path} to {new_path}")
                        shutil.copy2(file_path, new_path)

                        # Verify copy was successful
                        if os.path.exists(new_path):
                            print(f"Successfully copied {filename} to session folder")
                        else:
                            print(f"ERROR: Failed to copy {filename} to session folder")

                        # Clean up temp file
                        try:
                            os.remove(file_path)
                        except:
                            pass  # Ignore cleanup errors
                    else:
                        print(f"WARNING: Source file doesn't exist: {file_path}")

            # For multi-turn sessions, ensure all previous files are available
            if user_request.is_continuation and hasattr(user_request, 'original_session_id'):
                user_request.progress_queue.put({"type": "status", "message": "Checking for files from previous turns..."})

                # Download files from S3 if cloud storage is configured
                if cloud_storage_manager and cloud_storage_manager.s3_client:
                    try:
                        user_request.progress_queue.put({"type": "status", "message": "Downloading files from previous turns..."})

                        # Download all files from S3 for this session
                        downloaded_files = asyncio.run(
                            cloud_storage_manager.download_turn_files_from_s3(
                                user_request.original_session_id,
                                session_path
                            )
                        )

                        if downloaded_files:
                            user_request.progress_queue.put({
                                "type": "status",
                                "message": f"Downloaded {len(downloaded_files)} files from previous turns"
                            })
                            print(f"Downloaded {len(downloaded_files)} files from S3: {list(downloaded_files.keys())}")
                        else:
                            print(f"No files to download from S3 for session {user_request.original_session_id}")

                    except Exception as e:
                        print(f"Error downloading files from S3: {e}")
                        user_request.progress_queue.put({
                            "type": "status",
                            "message": f"Warning: Could not download some files from previous turns: {str(e)}"
                        })

                # Verify USER-UPLOADED files are available locally (not system files)
                if hasattr(user_request, 'all_turn_files'):
                    missing_user_files = []
                    system_file_prefixes = ['query_', 'report_', 'thinking_process_', 'result_', 'snapshot_']

                    for filename, file_info in user_request.all_turn_files.items():
                        # Skip system-generated files (these are in MongoDB, not needed locally)
                        if any(filename.startswith(prefix) for prefix in system_file_prefixes):
                            continue
                        if filename.endswith('.zip'):
                            continue

                        local_path = os.path.join(session_path, filename)
                        if not os.path.exists(local_path):
                            missing_user_files.append(filename)
                            logger.warning(f"User file {filename} is still missing after S3 download")

                    if missing_user_files:
                        user_request.progress_queue.put({
                            "type": "status",
                            "message": f"Warning: {len(missing_user_files)} user files could not be retrieved: {', '.join(missing_user_files[:3])}"
                        })

            # Load ALL files from session folder into agent's data lake (including previous turns)
            agent.data_lake_dict = {}
            if os.path.exists(session_path):
                for filename in os.listdir(session_path):
                    file_path = os.path.join(session_path, filename)
                    if os.path.isfile(file_path) and not filename.startswith('.'):
                        try:
                            if filename.endswith('.csv'):
                                data = pd.read_csv(file_path)
                                agent.data_lake_dict[filename] = f"Dataset with {data.shape[0]} rows and {data.shape[1]} columns (Path: {file_path})"
                            elif filename.endswith(('.xlsx', '.xls')):
                                data = pd.read_excel(file_path)
                                agent.data_lake_dict[filename] = f"Excel file with {data.shape[0]} rows and {data.shape[1]} columns (Path: {file_path})"
                            elif filename.endswith(('.txt', '.md', '.json')):
                                agent.data_lake_dict[filename] = f"Text file (Path: {file_path})"
                            elif filename.endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.svg')):
                                agent.data_lake_dict[filename] = f"Image file (Path: {file_path})"
                            else:
                                agent.data_lake_dict[filename] = f"File (format auto-detected) (Path: {file_path})"
                        except:
                            agent.data_lake_dict[filename] = f"File (Path: {file_path})"

            # Configure agent with all available files
            if agent.data_lake_dict:
                agent.configure()
                user_request.progress_queue.put({
                    "type": "status",
                    "message": f"Loaded {len(agent.data_lake_dict)} files from session folder"
                })
            
            # Use process-based execution for true termination capability
            # Create multiprocessing queues for communication
            message_queue = MPQueue()
            result_queue = MPQueue()

            # Update turn_start_time to NOW (after downloading previous files)
            # This ensures we only capture images created during THIS turn's processing
            user_request.turn_start_time = time.time()

            # Store queues in user_request
            user_request.process_queue = result_queue

            # Create and start process
            agent_process = Process(
                target=run_agent_in_process,
                args=(message_queue, result_queue, user_request.enhanced_message, session_path,
                      user_request.use_template, user_request.turn_type, user_request.agent_config)
            )
            user_request.agent_process = agent_process
            agent_process.start()

            print(f"Started agent process with PID: {agent_process.pid}")

            # Monitor progress
            accumulated_thinking = ""
            last_content_length = 0
            user_request.last_snapshot_time = time.time()

            # Monitor process instead of thread
            while agent_process.is_alive():
                # Check if task was cancelled
                if user_request.is_cancelled:
                    user_request.progress_queue.put({
                        "type": "cancelled",
                        "message": "Task was cancelled by user"
                    })
                    # Terminate the process immediately
                    if agent_process.is_alive():
                        agent_process.terminate()
                        time.sleep(0.5)
                        if agent_process.is_alive():
                            agent_process.kill()  # Force kill if still alive
                    return  # Exit early if cancelled

                # Check for process results
                try:
                    while not result_queue.empty():
                        msg = result_queue.get_nowait()
                        if msg["type"] == "status":
                            user_request.progress_queue.put({
                                "type": "status",
                                "message": msg["content"]
                            })
                        elif msg["type"] == "template_matched":
                            # Store template information in UserRequest
                            user_request.template_matched = True
                            user_request.template_title = msg.get("template_title")
                            user_request.template_confidence = msg.get("confidence")
                            user_request.template_reasoning = msg.get("reasoning")
                            # Forward to progress queue
                            user_request.progress_queue.put({
                                "type": "template_matched",
                                "message": msg["content"],
                                "template_title": msg.get("template_title"),
                                "confidence": msg.get("confidence"),
                                "reasoning": msg.get("reasoning")
                            })
                        elif msg["type"] == "thinking_update":
                            accumulated_thinking = msg["content"]
                            user_request.progress_queue.put({
                                "type": "thinking_update",
                                "content": msg["content"],
                                "accumulated": accumulated_thinking
                            })
                        elif msg["type"] == "snapshot":
                            # Process snapshot from subprocess
                            accumulated_thinking = msg["content"]
                            snapshot = queue_manager.create_json_snapshot(
                                user_request,
                                accumulated_thinking,
                                session_path
                            )
                            user_request.periodic_snapshots.clear()
                            user_request.periodic_snapshots.append(snapshot)

                            # Save snapshot to file
                            try:
                                # IMPORTANT: Ensure session directory exists before saving snapshots
                                os.makedirs(session_path, exist_ok=True)

                                # Delete old snapshot files
                                for file in os.listdir(session_path):
                                    if file.startswith('snapshot_') and file.endswith('.json'):
                                        os.remove(os.path.join(session_path, file))

                                # Clear the snapshot_files list since we deleted the old files
                                # Only track the latest snapshot for S3 upload
                                user_request.snapshot_files.clear()

                                # Save new snapshot
                                snapshot_filename = f"snapshot_latest_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                                snapshot_path = os.path.join(session_path, snapshot_filename)
                                with open(snapshot_path, 'w', encoding='utf-8') as f:
                                    json.dump(snapshot, f, indent=2, ensure_ascii=False)

                                # Track snapshot file for S3 upload after completion
                                user_request.snapshot_files.append({
                                    'path': snapshot_path,
                                    'filename': snapshot_filename,
                                    'timestamp': datetime.now().isoformat()
                                })

                                user_request.progress_queue.put({
                                    "type": "snapshot_saved",
                                    "message": f"Snapshot saved: {snapshot_filename}",
                                    "snapshot": snapshot
                                })
                            except Exception as e:
                                print(f"Error saving snapshot: {e}")

                        elif msg["type"] == "final_snapshot":
                            accumulated_thinking = msg["content"]
                            user_request.result = msg.get("result", "")
                        elif msg["type"] == "result":
                            user_request.result = msg["content"]
                            accumulated_thinking = msg.get("output", "")
                            # Store planning mode fields
                            if msg.get("turn_type") == "planning":
                                user_request.ready_for_execution = msg.get("ready_for_execution", False)
                        elif msg["type"] == "error":
                            user_request.error = msg["content"]
                            print(f"Process error: {msg.get('traceback', msg['content'])}")
                except:
                    pass

                # Sleep briefly to avoid busy waiting
                time.sleep(0.1)
            
            # Wait for process completion
            agent_process.join()

            # Get final results from queue
            try:
                while not result_queue.empty():
                    msg = result_queue.get_nowait()
                    if msg["type"] == "result":
                        user_request.result = msg["content"]
                        accumulated_thinking = msg.get("output", accumulated_thinking)
                        # Store planning mode fields
                        if msg.get("turn_type") == "planning":
                            user_request.ready_for_execution = msg.get("ready_for_execution", False)
                        # Extract template info from final result
                        if "template_info" in msg:
                            template_info = msg["template_info"]
                            if template_info.get("matched"):
                                user_request.template_matched = True
                                user_request.template_title = template_info.get("title")
                                user_request.template_confidence = template_info.get("confidence")
                                user_request.template_reasoning = template_info.get("reasoning")
                                user_request.template_modification = template_info.get("modification")
                    elif msg["type"] == "error":
                        user_request.error = msg["content"]
            except:
                pass

            # Get final content (for backwards compatibility)
            final_content = accumulated_thinking
            if hasattr(locals(), 'stream_capture'):
                final_content = stream_capture.get_content()
            if len(final_content) > last_content_length:
                new_content = final_content[last_content_length:]
                accumulated_thinking += new_content
            
            # Scan for and move ALL new files created during processing
            try:
                # Define folders and files to exclude from scanning (working directories and system folders)
                exclude_dirs = {
                    # Working directories for this application
                    'chat_sessions', 'chat_zips', 'session_storage', 'multiturn_sessions', 'temp_uploads',

                    # Python cache and build directories
                    '__pycache__', '.pytest_cache', 'build', 'dist', '*.egg-info', '.eggs',

                    # Virtual environments
                    'venv', 'env', '.venv', '.env', 'virtualenv', 'ENV', 'env.bak', 'venv.bak',

                    # Version control
                    '.git', '.svn', '.hg', '.bzr',

                    # IDE and editor directories
                    '.vscode', '.idea', '.eclipse', '.sublime', '*.swp', '*.swo',

                    # JavaScript/Node
                    'node_modules', 'bower_components', '.npm',

                    # Testing and coverage
                    'tests', 'test', '.tox', '.coverage', 'htmlcov', '.hypothesis',

                    # Documentation
                    'docs', 'documentation', '.sphinx',

                    # Application specific
                    's3_mongodb', 'migrations', 'logs', 'log', 'tmp', 'temp', 'cache',

                    # OS specific
                    '.DS_Store', 'Thumbs.db', '.Trash',

                    # Jupyter/IPython
                    '.ipynb_checkpoints', '.jupyter',

                    # Database
                    'db', 'database', 'data'
                }

                # System files to never move
                system_files = {'requirements.txt', 'requirements_fastapi.txt', 'requirements-test.txt',
                               'pytest.ini', 'README.md', 'CLOUD_STORAGE_README.md', 'TEST_SUMMARY.md',
                               '.env', '.env.example', 'Dockerfile', 'docker-compose.yml', '.gitignore',
                               'setup.py', 'setup.cfg', 'pyproject.toml', 'Makefile'}

                # Python files that are part of the application
                app_files = {'agent_fastapi_server_multiturn.py', 'agent_gradio_fastapi_multiturn.py',
                            'cloud_storage_manager.py', 'unified_session_manager.py', 'a1.py'}

                all_new_files = []

                # Scan current directory and all subdirectories
                for root, dirs, files in os.walk(current_path):
                    # Skip excluded directories
                    dirs[:] = [d for d in dirs if d not in exclude_dirs]

                    # Skip if we're in an excluded directory
                    if any(excluded in root for excluded in exclude_dirs):
                        continue

                    for file in files:
                        # Skip system files and app files
                        if file in system_files or file in app_files:
                            continue

                        # Skip Python cache files and compiled files
                        if file.endswith(('.pyc', '.pyo', '.pyd', '.so', '.dll', '.dylib')):
                            continue

                        file_path = os.path.join(root, file)

                        # Check if file was created after task started
                        try:
                            file_mtime = os.path.getmtime(file_path)
                            if file_mtime > start_time:
                                # Check file size (skip files > 500MB)
                                file_size = os.path.getsize(file_path)
                                file_size_mb = file_size / (1024 * 1024)

                                if file_size_mb > 500:
                                    print(f"Skipping large file {file_path} ({file_size_mb:.1f}MB > 500MB limit)")
                                    # Optionally delete very large files
                                    try:
                                        os.remove(file_path)
                                        print(f"Deleted large file {file_path}")
                                    except:
                                        pass
                                    continue

                                # Add to list of files to move
                                all_new_files.append(file_path)

                        except OSError:
                            continue

                if all_new_files:
                    print(f"Found {len(all_new_files)} new files created during processing:")

                    # Group files by type for logging
                    image_files = [f for f in all_new_files if any(f.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.svg', '.webp'])]
                    data_files = [f for f in all_new_files if any(f.lower().endswith(ext) for ext in ['.csv', '.xlsx', '.xls', '.tsv', '.json'])]
                    other_files = [f for f in all_new_files if f not in image_files and f not in data_files]

                    print(f"  - {len(image_files)} image files")
                    print(f"  - {len(data_files)} data files")
                    print(f"  - {len(other_files)} other files")

                    # Move all files to session folder
                    moved_files = move_files_to_session(all_new_files, session_path)
                    print(f"Successfully moved {len(moved_files)} files to session folder: {session_path}")

                    user_request.progress_queue.put({
                        "type": "status",
                        "message": f"Moved {len(moved_files)} new files to session folder"
                    })
                else:
                    print(f"No new files found to move (checked from time: {start_time})")

            except Exception as e:
                print(f"Error handling new files: {e}")
                import traceback
                traceback.print_exc()

            # Save session files
            try:
                # Save report file
                if user_request.language == Language.JP:
                    report_filename = f"report_{now_jst().strftime('%Y%m%d_%H%M%S')}.md"
                else:
                    report_filename = f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"

                report_path = os.path.join(session_path, report_filename)

                # Format final report
                if user_request.error:
                    final_report_content = f"## ❌ Error Report\n\n```\n{user_request.error}\n```"
                else:
                    raw_result = user_request.result or 'Processing completed successfully.'

                    # Extract content from <solution> tags if present
                    if '<solution>' in raw_result and '</solution>' in raw_result:
                        start_idx = raw_result.find('<solution>') + len('<solution>')
                        end_idx = raw_result.find('</solution>')
                        solution_content = raw_result[start_idx:end_idx].strip()
                    else:
                        solution_content = raw_result

                    # Remove any remaining XML-like tags that might interfere with HTML/Markdown rendering
                    import re
                    # Remove all XML-like tags (e.g., <tag>, </tag>, <tag attr="value">)
                    solution_content = re.sub(r'</?[a-zA-Z_][a-zA-Z0-9_]*(?:\s+[^>]*)?>', '', solution_content)

                    final_report_content = f"## ✅ Final Report\n\n{solution_content}"

                with open(report_path, 'w', encoding='utf-8') as f:
                    f.write(final_report_content)

                # Save thinking process (cleaned version with template info)
                cleaned_thinking = queue_manager._clean_thinking_content(accumulated_thinking, user_request.message)
                cleaned_thinking = queue_manager._add_template_header(cleaned_thinking, user_request)

                thinking_filename = f"thinking_process_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
                thinking_path = os.path.join(session_path, thinking_filename)
                with open(thinking_path, 'w', encoding='utf-8') as f:
                    f.write(cleaned_thinking)

                # Save query/message for reference
                query_filename = f"query_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
                query_path = os.path.join(session_path, query_filename)
                with open(query_path, 'w', encoding='utf-8') as f:
                    f.write(f"Query: {user_request.message}\nTimestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

                # Collect image files from session
                # For multi-turn sessions, only include images created during this turn
                image_files = []
                image_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.svg', '.webp'}
                turn_start_time = user_request.turn_start_time if hasattr(user_request, 'turn_start_time') else None
                for file in os.listdir(session_path):
                    if any(file.lower().endswith(ext) for ext in image_extensions):
                        file_path = os.path.join(session_path, file)
                        # Filter by turn_start_time for multi-turn sessions
                        if turn_start_time is not None:
                            file_mtime = os.path.getmtime(file_path)
                            if file_mtime < turn_start_time:
                                continue  # Skip images from previous turns
                        image_files.append(file_path)

                # Create structured JSON result
                json_result = {
                    "session_id": user_request.session_id,
                    "status": "completed" if not user_request.error else "error",
                    "timestamp": datetime.now().isoformat(),
                    "language": user_request.language.value,
                    "query": user_request.message,
                    "files": {
                        "report_md": report_path,
                        "thinking_process": thinking_path,
                        "query_file": query_path,
                        "images": image_files,
                        "session_zip": None  # Will be set after zip creation
                    },
                    "content": {
                        "final_report": final_report_content,
                        "thinking_content": cleaned_thinking,
                        "raw_result": user_request.result
                    },
                    "error": user_request.error,
                    "session_path": session_path
                }

                # Store JSON result in user request
                user_request.json_result = json_result

                # Save JSON result to file
                json_filename = f"result_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                json_path = os.path.join(session_path, json_filename)
                with open(json_path, 'w', encoding='utf-8') as f:
                    json.dump(json_result, f, indent=2, ensure_ascii=False)

                # Add JSON file path to the result
                user_request.json_result["files"]["result_json"] = json_path

            except Exception as e:
                print(f"Error saving session files: {e}")

            # Generate PDF report with images before creating ZIP
            pdf_path = None
            try:
                # Check if we have the required variables for PDF generation
                report_content_for_pdf = locals().get('final_report_content')
                images_for_pdf = locals().get('image_files', [])

                if report_content_for_pdf and session_path:
                    user_request.progress_queue.put({
                        "type": "status",
                        "message": "Generating PDF report..."
                    })
                    pdf_path = generate_report_pdf(session_path, report_content_for_pdf, images_for_pdf)
                    if pdf_path:
                        print(f"Generated PDF report: {pdf_path}")
                        # Add PDF path to json_result files
                        if hasattr(user_request, 'json_result') and user_request.json_result:
                            user_request.json_result["files"]["report_pdf"] = pdf_path
                            # Re-save JSON with updated PDF path
                            if "result_json" in user_request.json_result["files"]:
                                json_path_for_update = user_request.json_result["files"]["result_json"]
                                with open(json_path_for_update, 'w', encoding='utf-8') as f:
                                    json.dump(user_request.json_result, f, indent=2, ensure_ascii=False)
                        user_request.progress_queue.put({
                            "type": "status",
                            "message": f"PDF report generated: {os.path.basename(pdf_path)}"
                        })
                    else:
                        print("PDF generation returned None")
                else:
                    print(f"Skipping PDF generation: report_content={bool(report_content_for_pdf)}, session_path={bool(session_path)}")
            except Exception as e:
                print(f"Error generating PDF report: {e}")
                import traceback
                traceback.print_exc()

            # Create ZIP files - both session-wide and per-turn
            zip_file_path = None
            turn_zip_file_path = None

            try:
                # Create session zip file
                # For multi-turn sessions, pass turn_number and start_time to create turn-specific zip files
                # containing only files created during this turn
                current_turn_number = None
                turn_start_time = None
                if hasattr(user_request, 'original_session_id') and user_request.original_session_id:
                    current_turn_number = user_request.turn_number
                    turn_start_time = start_time  # start_time was recorded at beginning of turn processing

                zip_file_path = create_session_zip(session_path, save_to_chat_zips=True, turn_number=current_turn_number, turn_start_time=turn_start_time)
                if zip_file_path:
                    # Update JSON result with zip path
                    if user_request.json_result:
                        user_request.json_result["files"]["session_zip"] = zip_file_path
                        # Re-save JSON with updated zip path
                        json_path = user_request.json_result["files"]["result_json"]
                        with open(json_path, 'w', encoding='utf-8') as f:
                            json.dump(user_request.json_result, f, indent=2, ensure_ascii=False)

                    user_request.progress_queue.put({
                        "type": "status",
                        "message": f"Session zip created: {os.path.basename(zip_file_path)}"
                    })

                # For multi-turn sessions, also create per-turn ZIP
                if hasattr(user_request, 'original_session_id') and user_request.original_session_id:
                    base_session_id = user_request.original_session_id
                    turn_number = user_request.turn_number

                    user_request.progress_queue.put({
                        "type": "status",
                        "message": f"Creating turn {turn_number} ZIP..."
                    })

                    turn_zip_result = create_turn_zip(
                        session_path,
                        base_session_id,
                        turn_number,
                        save_to_chat_zips=True
                    )

                    if turn_zip_result:
                        turn_zip_file_path = turn_zip_result['zip_path']
                        print(f"Created turn {turn_number} ZIP: {turn_zip_file_path} "
                              f"({turn_zip_result['file_count']} files, "
                              f"{turn_zip_result['total_size'] / 1024 / 1024:.2f}MB)")

                        user_request.progress_queue.put({
                            "type": "status",
                            "message": f"Turn {turn_number} ZIP created: {os.path.basename(turn_zip_file_path)}"
                        })

                        # Copy turn ZIP to session folder for S3 upload
                        turn_zip_filename = os.path.basename(turn_zip_file_path)
                        session_turn_zip_path = os.path.join(session_path, turn_zip_filename)
                        shutil.copy2(turn_zip_file_path, session_turn_zip_path)
                        print(f"Copied turn ZIP to session folder for S3 upload: {session_turn_zip_path}")
                    else:
                        print(f"Warning: Failed to create turn {turn_number} ZIP")

            except Exception as e:
                print(f"Error creating ZIP files: {e}")

            # Upload snapshots to S3 for persistence
            if hasattr(user_request, 'snapshot_files') and user_request.snapshot_files:
                try:
                    print(f"Uploading {len(user_request.snapshot_files)} snapshot(s) to S3...")
                    uploaded_snapshots = []

                    for snapshot_file in user_request.snapshot_files:
                        try:
                            # Determine session ID for S3 key
                            if hasattr(user_request, 'original_session_id') and user_request.original_session_id:
                                snapshot_session_id = user_request.original_session_id
                            else:
                                snapshot_session_id = user_request.session_id

                            s3_key = f"sessions/{snapshot_session_id}/snapshots/{snapshot_file['filename']}"

                            # Upload to S3
                            if os.path.exists(snapshot_file['path']):
                                asyncio.run(cloud_storage_manager.upload_file(
                                    snapshot_file['path'],
                                    s3_key
                                ))

                                uploaded_snapshots.append({
                                    'filename': snapshot_file['filename'],
                                    's3_key': s3_key,
                                    'timestamp': snapshot_file['timestamp']
                                })
                                print(f"Uploaded snapshot: {snapshot_file['filename']}")
                            else:
                                print(f"Snapshot file not found: {snapshot_file['path']}")

                        except Exception as e:
                            print(f"Failed to upload snapshot {snapshot_file['filename']}: {e}")

                    # Store snapshot metadata in session data for MongoDB
                    user_request.uploaded_snapshots = uploaded_snapshots
                    print(f"Successfully uploaded {len(uploaded_snapshots)} snapshot(s) to S3")

                except Exception as e:
                    print(f"Error uploading snapshots to S3: {e}")

            # Mark as complete
            user_request.status = "completed"
            user_request.is_complete = True

            # Move any generated files to session folder to keep workspace clean
            queue_manager._move_generated_files_to_session(user_request)

            # Trigger S3 upload for completed session
            queue_manager._trigger_s3_upload_for_session(user_request)

            # Clean thinking content for completion update and add template header
            cleaned_thinking = queue_manager._clean_thinking_content(accumulated_thinking, user_request.message)
            cleaned_thinking = queue_manager._add_template_header(cleaned_thinking, user_request)
            completion_update = {
                "type": "completion",
                "final_report": final_report_content,
                "thinking_content": cleaned_thinking,
                "session_path": session_path
            }
            user_request.progress_queue.put(completion_update)
            user_request.all_progress_updates.append(completion_update)

            # Clean up temp upload directory for this session
            if hasattr(user_request, 'original_session_id') and user_request.original_session_id:
                temp_upload_dir = os.path.join(os.getcwd(), "temp_uploads", user_request.original_session_id)
            else:
                temp_upload_dir = os.path.join(os.getcwd(), "temp_uploads", user_request.session_id)

            if os.path.exists(temp_upload_dir):
                try:
                    shutil.rmtree(temp_upload_dir)
                except Exception as e:
                    print(f"Warning: Could not clean up temp upload directory {temp_upload_dir}: {e}")

            # Save final session state to persistent storage
            queue_manager._save_session_to_storage(user_request)

            # Upload completed session to cloud storage
            try:
                session_data = {
                    "session_id": user_request.session_id,
                    "status": user_request.status,
                    "is_complete": user_request.is_complete,
                    "is_cancelled": user_request.is_cancelled,
                    "error": user_request.error,
                    "created_at": user_request.created_at.isoformat(),
                    "query": user_request.message,
                    "language": user_request.language,
                    "user_id": user_request.user_id,
                    "session_path": session_path,
                    "all_progress_updates": user_request.all_progress_updates,
                    "periodic_snapshots": user_request.periodic_snapshots,
                    "result": user_request.result,
                    "json_result": user_request.json_result,
                    # For multi-turn sessions, pass turn_start_time to filter images
                    "turn_start_time": user_request.turn_start_time if hasattr(user_request, 'turn_start_time') else None
                }

                # Add snapshot metadata if snapshots were uploaded
                if hasattr(user_request, 'uploaded_snapshots'):
                    session_data["snapshots"] = user_request.uploaded_snapshots
                # Upload to cloud asynchronously (don't wait for completion)
                def upload_in_thread():
                    import asyncio
                    try:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        loop.run_until_complete(cloud_storage_manager.upload_session_to_cloud(
                            user_request.session_id, session_data
                        ))
                        loop.close()
                    except Exception as e:
                        print(f"Background cloud upload failed for session {user_request.session_id}: {e}")

                upload_thread = threading.Thread(target=upload_in_thread, daemon=True)
                upload_thread.start()
                print(f"Initiated cloud upload for session {user_request.session_id}")
            except Exception as e:
                print(f"Failed to initiate cloud upload for session {user_request.session_id}: {e}")

            # Update multi-turn session if this is a turn
            if hasattr(user_request, 'original_session_id') and user_request.original_session_id:
                # Get file paths for the turn
                # For multi-turn sessions, use turn-specific zip as session_zip (so it shows in final report)
                turn_session_zip = turn_zip_file_path if turn_zip_file_path else zip_file_path
                files_dict = {
                    'report_md': report_path,
                    'thinking_process': thinking_path,
                    'query_file': query_path,
                    'session_zip': turn_session_zip,  # Use turn-specific zip for multi-turn
                    'result_json': json_path
                }

                # Also keep turn_zip for backwards compatibility
                if turn_zip_file_path:
                    files_dict['turn_zip'] = turn_zip_file_path
                    print(f"[DEBUG] Using turn ZIP as session_zip: {os.path.basename(turn_zip_file_path)}")

                # Complete the turn in multi-turn session
                queue_manager.complete_turn(
                    user_request.original_session_id,
                    user_request.turn_number,
                    cleaned_thinking,
                    final_report_content,
                    files_dict,
                    turn_type=user_request.turn_type,
                    ready_for_execution=getattr(user_request, 'ready_for_execution', None)
                )
            
        except Exception as e:
            user_request.status = "error"
            user_request.error = str(e)
            user_request.is_complete = True

            # Move any generated files to session folder even on error
            queue_manager._move_generated_files_to_session(user_request)

            error_update = {
                "type": "error",
                "error": str(e)
            }
            user_request.progress_queue.put(error_update)
            user_request.all_progress_updates.append(error_update)

            # Clean up temp upload directory even on error
            if hasattr(user_request, 'original_session_id') and user_request.original_session_id:
                temp_upload_dir = os.path.join(os.getcwd(), "temp_uploads", user_request.original_session_id)
            else:
                temp_upload_dir = os.path.join(os.getcwd(), "temp_uploads", user_request.session_id)

            if os.path.exists(temp_upload_dir):
                try:
                    shutil.rmtree(temp_upload_dir)
                except Exception as cleanup_error:
                    print(f"Warning: Could not clean up temp upload directory {temp_upload_dir}: {cleanup_error}")

            # Save failed session state to persistent storage
            queue_manager._save_session_to_storage(user_request)

            # Upload failed session to cloud storage
            try:
                session_data = {
                    "session_id": user_request.session_id,
                    "status": user_request.status,
                    "is_complete": user_request.is_complete,
                    "is_cancelled": user_request.is_cancelled,
                    "error": user_request.error,
                    "created_at": user_request.created_at.isoformat(),
                    "query": user_request.message,
                    "language": user_request.language,
                    "user_id": user_request.user_id,
                    "session_path": user_request.session_path,
                    "all_progress_updates": user_request.all_progress_updates,
                    "periodic_snapshots": user_request.periodic_snapshots,
                    "result": user_request.result,
                    "json_result": user_request.json_result
                }
                # Upload to cloud asynchronously (don't wait for completion)
                def upload_in_thread():
                    import asyncio
                    try:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        loop.run_until_complete(cloud_storage_manager.upload_session_to_cloud(
                            user_request.session_id, session_data
                        ))
                        loop.close()
                    except Exception as e:
                        print(f"Background cloud upload failed for session {user_request.session_id}: {e}")

                upload_thread = threading.Thread(target=upload_in_thread, daemon=True)
                upload_thread.start()
                print(f"Initiated cloud upload for failed session {user_request.session_id}")
            except Exception as e:
                print(f"Failed to initiate cloud upload for failed session {user_request.session_id}: {e}")

        finally:
            # Remove completed/cancelled sessions from active_sessions
            # This is crucial for proper download functionality
            if user_request.is_complete or user_request.is_cancelled:
                if user_request.session_id in self.active_sessions:
                    del self.active_sessions[user_request.session_id]
                    print(f"Removed completed/cancelled session {user_request.session_id} from active sessions")

    def get_all_stored_sessions(self) -> List[Dict[str, Any]]:
        """Get all stored sessions from persistent storage - needed for unified session manager"""
        sessions = []
        try:
            if os.path.exists(self.sessions_storage_dir):
                for filename in os.listdir(self.sessions_storage_dir):
                    if filename.endswith('.json'):
                        session_id = filename[:-5]  # Remove .json extension
                        try:
                            session_file = os.path.join(self.sessions_storage_dir, filename)
                            with open(session_file, 'r', encoding='utf-8') as f:
                                session_data = json.load(f)
                            sessions.append(session_data)
                        except Exception as e:
                            print(f"Error loading stored session {session_id}: {e}")
        except Exception as e:
            print(f"Error accessing stored sessions directory: {e}")
        return sessions

# Initialize queue manager
queue_manager = QueueManager()

# Process-based agent runner (defined at module level for pickling)
def run_agent_in_process(message_queue: MPQueue, result_queue: MPQueue, enhanced_message: str, session_path: str,
                         use_template: bool = True, turn_type: str = "execution", agent_config: dict = None):
    """
    Run agent in a separate process for true termination capability
    This function runs in a separate process and communicates via queues

    Args:
        message_queue: Queue for receiving messages
        result_queue: Queue for sending results
        enhanced_message: The message/query to process
        session_path: Path to session directory
        use_template: Whether to use template matching (default: True)
        turn_type: Type of turn - "planning" or "execution" (default: "execution")
        agent_config: Custom agent configuration for planning mode
    """
    import atexit
    import glob
    import io
    import os
    import shutil
    import sys
    import threading
    import time
    from contextlib import redirect_stdout

    import psutil

    # Record start time for file tracking
    process_start_time = time.time()

    # Track all child processes spawned by this process
    parent_process = psutil.Process()

    # Shared buffer for output capture
    output_buffer = io.StringIO()
    output_lock = threading.Lock()

    def cleanup_subprocesses():
        """Kill all child processes when parent terminates"""
        try:
            children = parent_process.children(recursive=True)
            for child in children:
                try:
                    print(f"Terminating subprocess PID {child.pid}")
                    child.terminate()
                except:
                    pass

            # Give them time to terminate gracefully
            _, alive = psutil.wait_procs(children, timeout=2)

            # Force kill any remaining
            for child in alive:
                try:
                    print(f"Force killing subprocess PID {child.pid}")
                    child.kill()
                except:
                    pass
        except:
            pass

    # Register cleanup function
    atexit.register(cleanup_subprocesses)

    # Also handle SIGTERM signal
    import signal
    def signal_handler(signum, frame):
        cleanup_subprocesses()
        sys.exit(0)

    signal.signal(signal.SIGTERM, signal_handler)

    def send_periodic_snapshots():
        """Send snapshots every 2 seconds while agent is running"""
        while not agent_complete.is_set():
            time.sleep(2)

            with output_lock:
                current_output = output_buffer.getvalue()

            # Send snapshot with current output
            result_queue.put({
                "type": "snapshot",
                "content": current_output,
                "timestamp": time.time()
            })

            # Also send as thinking update for real-time display
            if current_output:
                result_queue.put({
                    "type": "thinking_update",
                    "content": current_output
                })

    # Event to signal agent completion
    agent_complete = threading.Event()

    # Start snapshot thread
    snapshot_thread = threading.Thread(target=send_periodic_snapshots, daemon=True)
    snapshot_thread.start()

    try:
        with redirect_stdout(output_buffer):
            # Send status update
            result_queue.put({
                "type": "status",
                "content": "Agent starting in separate process with snapshot tracking..."
            })

            # Check if this is a planning turn
            if turn_type == "planning":
                # PLANNING MODE - No tools, just LLM reasoning
                result_queue.put({
                    "type": "status",
                    "content": "Planning mode: Agent will ask clarifying questions without executing tools..."
                })

                # Use direct LLM call without tools
                from langchain_anthropic import ChatAnthropic

                llm = ChatAnthropic(
                    model=agent_config.get("model", "claude-sonnet-4-5-20250929"),
                    temperature=agent_config.get("temperature", 0.7)
                )

                # Build prompt with system and user message
                system_prompt = agent_config.get("system_prompt", "You are a helpful assistant.")
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": enhanced_message}
                ]

                # Call LLM
                result_queue.put({
                    "type": "status",
                    "content": "Generating planning response..."
                })

                response = llm.invoke(messages)
                result_content = response.content

                # Check if agent signals readiness for execution
                ready_for_execution = "[READY_FOR_EXECUTION]" in result_content

                # Remove the signal from content (keep it clean for display)
                if ready_for_execution:
                    result_content = result_content.replace("[READY_FOR_EXECUTION]", "").strip()

                # Signal completion
                agent_complete.set()

                # Get final output
                with output_lock:
                    final_output = output_buffer.getvalue()

                # Send final result with readiness flag
                result_queue.put({
                    "type": "result",
                    "content": result_content,
                    "output": final_output,
                    "ready_for_execution": ready_for_execution,  # NEW FLAG
                    "turn_type": "planning",
                    "template_info": {"matched": False}  # No template matching in planning mode
                })

                # Send final snapshot
                result_queue.put({
                    "type": "final_snapshot",
                    "content": final_output,
                    "result": result_content,
                    "ready_for_execution": ready_for_execution,
                    "timestamp": time.time(),
                    "template_info": {"matched": False}
                })

                # Skip the rest of execution logic
                return

            # EXECUTION MODE - Full agent with tools
            # Create agent
            from agent_fastapi_server_multiturn import create_agent
            agent = create_agent()

            # Send status
            result_queue.put({
                "type": "status",
                "content": "Agent initialized, processing message..."
            })

            # === TEMPLATE MATCHING & QUERY AUGMENTATION ===
            # Try to match the query to a workflow template (if enabled)
            base_message = enhanced_message
            template_info = {
                "matched": False,
                "title": None,
                "confidence": None,
                "reasoning": None,
                "modification": None
            }

            # use_template parameter is passed to this function
            # Check if template matching is enabled
            if use_template:
                try:
                    result_queue.put({
                        "type": "status",
                        "content": "Checking for relevant workflow templates..."
                    })

                    from agent_fastapi_server_multiturn import get_template_retriever
                    retriever = get_template_retriever()

                    if retriever:
                        # Match query to templates
                        match_result = retriever.match_template(base_message)

                        if match_result.get("matched"):
                            template_title = match_result.get("template", {}).get("title", "Unknown")
                            confidence = match_result.get("confidence", "unknown")

                            # Store template info for later
                            template_info["matched"] = True
                            template_info["title"] = template_title
                            template_info["confidence"] = confidence
                            template_info["reasoning"] = match_result.get("reasoning", "")
                            template_info["modification"] = match_result.get("modification")

                            result_queue.put({
                                "type": "template_matched",
                                "content": f"Matched to template: {template_title} (confidence: {confidence})",
                                "template_title": template_title,
                                "confidence": confidence,
                                "reasoning": match_result.get("reasoning", "")
                            })

                            # Augment the query with template prompt
                            augmentation_result = retriever.augment_query_with_template(base_message, match_result)
                            enhanced_message = augmentation_result["augmented_query"]

                            print(f"✓ Template matched: {template_title} (confidence: {confidence})")
                            if augmentation_result.get("modification_applied"):
                                print(f"  Modification: {augmentation_result['modification_applied']}")
                        else:
                            print(f"✗ No template matched: {match_result.get('reasoning', 'Unknown reason')}")

                except Exception as e:
                    print(f"Warning: Template matching failed: {e}")
                    # Continue without template matching
            else:
                print("Template matching is not using")
                result_queue.put({
                    "type": "status",
                    "content": "Template matching is not using, proceeding with direct query..."
                })

            # === END TEMPLATE MATCHING ===

            # Add explicit file information to the message if not already included
            if session_path and os.path.exists(session_path):
                files_in_session = []
                for filename in os.listdir(session_path):
                    file_path = os.path.join(session_path, filename)
                    if os.path.isfile(file_path) and not filename.startswith('.'):
                        files_in_session.append(f"{filename} (Path: {file_path})")

                if files_in_session and "Available files" not in enhanced_message:
                    file_info = "\n\nAvailable files in your working directory:\n" + "\n".join([f"- {f}" for f in files_in_session])
                    enhanced_message = enhanced_message + file_info

            # Run agent (this blocks until complete)
            _, result = agent.go(enhanced_message)

            # Signal completion
            agent_complete.set()

            # Get final output
            with output_lock:
                final_output = output_buffer.getvalue()

            # Send final result with complete output and template info
            result_queue.put({
                "type": "result",
                "content": result,
                "output": final_output,
                "template_info": template_info
            })

            # Send final snapshot
            result_queue.put({
                "type": "final_snapshot",
                "content": final_output,
                "result": result,
                "timestamp": time.time(),
                "template_info": template_info
            })

    except Exception as e:
        import traceback
        agent_complete.set()

        with output_lock:
            error_output = output_buffer.getvalue()

        result_queue.put({
            "type": "error",
            "content": str(e),
            "traceback": traceback.format_exc(),
            "output": error_output
        })
    finally:
        # Move generated files to session folder before exiting process
        try:
            print(f"Process: Starting file collection for session path: {session_path}")
            print(f"Process: Session path exists: {os.path.exists(session_path)}")

            # Ensure session folder exists
            if not os.path.exists(session_path):
                os.makedirs(session_path, exist_ok=True)
                print(f"Process: Created session folder: {session_path}")

            # System files to never move
            system_files = {
                'requirements.txt', 'requirements_fastapi.txt', 'requirements-test.txt',
                'pytest.ini', 'README.md', 'CLOUD_STORAGE_README.md', 'TEST_SUMMARY.md',
                '.env', '.env.example', 'Dockerfile', 'docker-compose.yml', '.gitignore',
                'setup.py', 'setup.cfg', 'pyproject.toml', 'Makefile', 'dleader_logo.png'
            }

            # Application Python files to skip
            app_python_files = {
                'agent_fastapi_server_multiturn.py', 'agent_gradio_fastapi_multiturn.py',
                'cloud_storage_manager.py', 'unified_session_manager.py', 'a1.py',
                'agent_fastapi_server.py', 'agent_interface_gradio.py'
            }

            moved_count = 0
            image_count = 0

            # Scan for all files created during this process
            all_files = glob.glob("*") + glob.glob("*/*")
            print(f"Process: Scanning {len(all_files)} potential files")

            for file_path in all_files:
                # Skip directories and files in system folders
                if os.path.isdir(file_path):
                    continue

                # Skip files in system directories
                if any(file_path.startswith(d + '/') for d in ['chat_sessions', 'chat_zips',
                       'session_storage', 'multiturn_sessions', 'temp_uploads', 's3_mongodb']):
                    continue

                filename = os.path.basename(file_path)

                # Skip system files and app files
                if filename in system_files or filename in app_python_files:
                    continue

                # Skip test files
                if filename.startswith('test_') and filename.endswith('.py'):
                    continue

                # Skip compiled Python files
                if filename.endswith(('.pyc', '.pyo', '.pyd')):
                    continue

                # Check if file was created or modified after process started
                try:
                    file_mtime = os.path.getmtime(file_path)
                    file_ctime = os.path.getctime(file_path)
                    file_time = max(file_mtime, file_ctime)

                    if file_time >= process_start_time:
                        # Check file size (skip files > 500MB)
                        file_size = os.path.getsize(file_path)
                        file_size_mb = file_size / (1024 * 1024)

                        if file_size_mb > 500:
                            print(f"Process: Deleting large file {filename} ({file_size_mb:.1f}MB)")
                            os.remove(file_path)
                        else:
                            # Move file to session folder
                            dest_path = os.path.join(session_path, filename)

                            # Handle duplicate filenames
                            if os.path.exists(dest_path):
                                base, ext = os.path.splitext(filename)
                                counter = 1
                                while os.path.exists(dest_path):
                                    new_filename = f"{base}_{counter}{ext}"
                                    dest_path = os.path.join(session_path, new_filename)
                                    counter += 1

                            print(f"Process: Moving {file_path} -> {dest_path}")
                            shutil.move(file_path, dest_path)
                            moved_count += 1

                            # Count images
                            if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.bmp')):
                                image_count += 1
                                print(f"Process: This is an image file: {filename}")

                            print(f"Process: Successfully moved {filename} to session folder")

                except Exception as e:
                    print(f"Process: Error processing file {file_path}: {e}")
                    # Continue with other files even if one fails
                    pass

            if moved_count > 0:
                result_queue.put({
                    "type": "status",
                    "content": f"Process: Moved {moved_count} files to session ({image_count} images)"
                })
                print(f"Process: Successfully moved {moved_count} files ({image_count} images) to {session_path}")

        except Exception as e:
            print(f"Process: Error moving files: {e}")

        # Clean up any remaining subprocesses
        cleanup_subprocesses()

# Session and utility classes (reused from original files)
class SessionManager:
    """Manage session folders and file storage"""
    def __init__(self):
        self.sessions_dir = os.path.join(os.getcwd(), "chat_sessions")
        os.makedirs(self.sessions_dir, exist_ok=True)
        self.session_path = None  # Store the session path for this manager

    def create_session_folder(self):
        """Create a unique session folder"""
        session_id = str(uuid.uuid4())[:8]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        session_name = f"session_{timestamp}_{session_id}"
        session_path = os.path.join(self.sessions_dir, session_name)
        os.makedirs(session_path, exist_ok=True)
        self.session_path = session_path
        return session_path, session_name

    def create_multiturn_session_folder(self, multiturn_session_id: str):
        """Create a shared session folder for multi-turn sessions"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        session_name = f"multiturn_{timestamp}_{multiturn_session_id[:8]}"
        session_path = os.path.join(self.sessions_dir, session_name)
        os.makedirs(session_path, exist_ok=True)
        self.session_path = session_path
        return session_path, session_name

    def get_session_path(self):
        """Get the current session path"""
        return self.session_path

class StreamingCapture:
    """Capture stdout and provide real-time updates"""
    def __init__(self):
        self.content = ""
        self.original_stdout = sys.stdout
        
    def write(self, text):
        self.content += text
        self.original_stdout.write(text)
        self.original_stdout.flush()
        
    def flush(self):
        self.original_stdout.flush()
        
    def get_content(self):
        return self.content

def scan_for_new_files(current_path, start_time, exclude_folders=None):
    """Scan for files created after start_time, excluding specified folders"""
    if exclude_folders is None:
        exclude_folders = {'chat_sessions', 'chat_zips', '__pycache__', '.git', '.vscode', 'node_modules'}

    new_files = []
    try:
        for root, dirs, files in os.walk(current_path):
            # Skip excluded directories by modifying dirs in-place
            dirs[:] = [d for d in dirs if d not in exclude_folders]

            for file in files:
                file_path = os.path.join(root, file)
                try:
                    file_mtime = os.path.getmtime(file_path)
                    if file_mtime > start_time:
                        new_files.append(file_path)
                except OSError:
                    # Skip files that can't be accessed
                    continue
    except Exception as e:
        print(f"Error scanning for new files: {e}")

    return new_files


def move_files_to_session(file_paths, session_path):
    """Move files to session folder, handling duplicates by renaming"""
    moved_files = []

    for file_path in file_paths:
        try:
            filename = os.path.basename(file_path)
            destination = os.path.join(session_path, filename)

            # Handle duplicates by adding a counter
            counter = 1
            original_destination = destination
            while os.path.exists(destination):
                name, ext = os.path.splitext(filename)
                destination = os.path.join(session_path, f"{name}_{counter}{ext}")
                counter += 1

            # Move the file
            shutil.move(file_path, destination)
            moved_files.append(destination)
            print(f"Moved {file_path} to {destination}")

        except Exception as e:
            print(f"Error moving file {file_path}: {e}")

    return moved_files


def generate_report_pdf(session_path: str, report_content: str, image_files: list) -> Optional[str]:
    """Generate a PDF from the final report with embedded images.

    Args:
        session_path: Path to the session directory where PDF will be saved
        report_content: The markdown content of the final report
        image_files: List of image file paths to include in the PDF

    Returns:
        Path to the generated PDF file, or None if generation fails
    """
    try:
        from fpdf import FPDF
        from PIL import Image
        import re
        import html

        # Create PDF with UTF-8 support
        class UTF8PDF(FPDF):
            def __init__(self):
                super().__init__()
                # Use built-in fonts with latin-1 encoding fallback
                self.set_auto_page_break(auto=True, margin=15)

            def header(self):
                self.set_font('Helvetica', 'B', 10)
                self.set_text_color(128, 128, 128)
                self.cell(0, 10, 'DLeader Agent Report', align='C')
                self.ln(10)

            def footer(self):
                self.set_y(-15)
                self.set_font('Helvetica', 'I', 8)
                self.set_text_color(128, 128, 128)
                self.cell(0, 10, f'Page {self.page_no()}', align='C')

        pdf = UTF8PDF()
        pdf.add_page()

        # Helper function to clean text for PDF (handle non-latin characters)
        def clean_text(text):
            # Replace common problematic characters
            replacements = {
                '\u2018': "'", '\u2019': "'",  # Smart quotes
                '\u201c': '"', '\u201d': '"',
                '\u2013': '-', '\u2014': '--',
                '\u2026': '...',
                '\u00a0': ' ',  # Non-breaking space
                '\u2022': '*',  # Bullet
                '\u2713': '[x]',  # Checkmark
                '\u2717': '[ ]',  # X mark
            }
            for old, new in replacements.items():
                text = text.replace(old, new)
            # Encode to latin-1, replacing unknown chars
            return text.encode('latin-1', errors='replace').decode('latin-1')

        # Helper function to add text with word wrapping
        def add_paragraph(text, font='Helvetica', size=11, style=''):
            pdf.set_font(font, style, size)
            pdf.set_text_color(0, 0, 0)
            # Clean the text for PDF compatibility
            cleaned = clean_text(text)
            pdf.multi_cell(0, 6, cleaned)
            pdf.ln(2)

        # Helper function to add heading
        def add_heading(text, level=1):
            sizes = {1: 18, 2: 16, 3: 14, 4: 12}
            size = sizes.get(level, 12)
            pdf.set_font('Helvetica', 'B', size)
            pdf.set_text_color(0, 0, 0)
            cleaned = clean_text(text)
            pdf.multi_cell(0, 8, cleaned)
            pdf.ln(3)

        # Helper function to add code block
        def add_code_block(code):
            pdf.set_font('Courier', '', 9)
            pdf.set_fill_color(245, 245, 245)
            pdf.set_text_color(0, 0, 0)
            cleaned = clean_text(code)
            # Split into lines and add each line
            for line in cleaned.split('\n'):
                # Truncate very long lines
                if len(line) > 100:
                    line = line[:97] + '...'
                pdf.cell(0, 5, line, fill=True)
                pdf.ln()
            pdf.ln(3)

        # Helper function to add an image
        def add_image(image_path, caption=None):
            if not os.path.exists(image_path):
                return

            try:
                # Get image dimensions
                with Image.open(image_path) as img:
                    img_width, img_height = img.size

                # Calculate scaling to fit page width (max 180mm for A4)
                max_width = 180
                max_height = 200  # Leave room for caption and margins

                # Calculate aspect ratio
                aspect = img_height / img_width
                if img_width > max_width:
                    width = max_width
                    height = width * aspect
                else:
                    width = img_width * 0.264583  # Convert pixels to mm (assuming 96 DPI)
                    height = img_height * 0.264583

                # Scale down if too tall
                if height > max_height:
                    height = max_height
                    width = height / aspect

                # Check if we need a new page
                if pdf.get_y() + height + 20 > pdf.h - 20:
                    pdf.add_page()

                # Center the image
                x = (pdf.w - width) / 2

                # Add the image
                pdf.image(image_path, x=x, y=pdf.get_y(), w=width)
                pdf.ln(height + 5)

                # Add caption if provided
                if caption:
                    pdf.set_font('Helvetica', 'I', 9)
                    pdf.set_text_color(80, 80, 80)
                    cleaned_caption = clean_text(caption)
                    pdf.multi_cell(0, 5, cleaned_caption, align='C')
                    pdf.ln(5)

            except Exception as e:
                print(f"Error adding image {image_path} to PDF: {e}")

        # Parse markdown content and render to PDF
        lines = report_content.split('\n')
        in_code_block = False
        code_block_content = []
        i = 0

        while i < len(lines):
            line = lines[i]

            # Skip download links section
            if '## 📥 Downloads' in line or '## Downloads' in line:
                # Skip until next section or end
                i += 1
                while i < len(lines) and not lines[i].startswith('#'):
                    i += 1
                continue

            # Handle code blocks
            if line.strip().startswith('```'):
                if in_code_block:
                    # End of code block
                    add_code_block('\n'.join(code_block_content))
                    code_block_content = []
                    in_code_block = False
                else:
                    # Start of code block
                    in_code_block = True
                i += 1
                continue

            if in_code_block:
                code_block_content.append(line)
                i += 1
                continue

            # Handle headings
            heading_match = re.match(r'^(#{1,6})\s+(.+)$', line)
            if heading_match:
                level = len(heading_match.group(1))
                text = heading_match.group(2)
                add_heading(text, level)
                i += 1
                continue

            # Handle horizontal rule
            if re.match(r'^(-{3,}|_{3,}|\*{3,})$', line.strip()):
                pdf.line(10, pdf.get_y(), pdf.w - 10, pdf.get_y())
                pdf.ln(5)
                i += 1
                continue

            # Handle bullet points
            bullet_match = re.match(r'^(\s*)[-*+]\s+(.+)$', line)
            if bullet_match:
                indent = len(bullet_match.group(1)) // 2
                text = bullet_match.group(2)
                pdf.set_font('Helvetica', '', 11)
                prefix = '  ' * indent + '• '
                add_paragraph(prefix + text)
                i += 1
                continue

            # Handle numbered lists
            num_match = re.match(r'^(\s*)(\d+)\.\s+(.+)$', line)
            if num_match:
                indent = len(num_match.group(1)) // 2
                num = num_match.group(2)
                text = num_match.group(3)
                pdf.set_font('Helvetica', '', 11)
                prefix = '  ' * indent + f'{num}. '
                add_paragraph(prefix + text)
                i += 1
                continue

            # Handle inline images in markdown (skip external URLs)
            img_match = re.match(r'!\[([^\]]*)\]\(([^)]+)\)', line)
            if img_match and not img_match.group(2).startswith('http'):
                # Local image reference - try to find it
                img_ref = img_match.group(2)
                img_caption = img_match.group(1)
                if os.path.exists(img_ref):
                    add_image(img_ref, img_caption)
                i += 1
                continue

            # Handle regular paragraphs
            if line.strip():
                # Remove markdown formatting for bold/italic
                text = re.sub(r'\*\*(.+?)\*\*', r'\1', line)  # Bold
                text = re.sub(r'\*(.+?)\*', r'\1', text)  # Italic
                text = re.sub(r'`(.+?)`', r'\1', text)  # Inline code
                text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)  # Links
                add_paragraph(text)

            i += 1

        # Add images section
        if image_files:
            pdf.add_page()
            add_heading("Generated Images", 2)
            pdf.ln(5)

            for img_path in image_files:
                if os.path.exists(img_path):
                    # Use filename as caption
                    filename = os.path.basename(img_path)
                    caption = filename.replace('_', ' ').replace('-', ' ')
                    # Remove extension for cleaner caption
                    caption = os.path.splitext(caption)[0]
                    add_image(img_path, caption)

        # Generate filename with timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        pdf_filename = f"report_{timestamp}.pdf"
        pdf_path = os.path.join(session_path, pdf_filename)

        # Save the PDF
        pdf.output(pdf_path)
        print(f"Generated PDF report: {pdf_path}")
        return pdf_path

    except Exception as e:
        print(f"Error generating PDF report: {e}")
        import traceback
        traceback.print_exc()
        return None


def create_session_zip(session_path, save_to_chat_zips=True, turn_number=None, turn_start_time=None):
    """Create a zip file containing all session content and optionally save to chat_zips

    Args:
        session_path: Path to the session directory
        save_to_chat_zips: Whether to save to chat_zips directory
        turn_number: Optional turn number for multi-turn sessions (creates turn-specific filename)
        turn_start_time: Optional start time (epoch) for filtering files to only include those
                         created during this turn (files modified after this time)
    """
    if not os.path.exists(session_path):
        return None

    try:
        session_name = os.path.basename(session_path)

        # Create chat_zips directory if saving there
        if save_to_chat_zips:
            chat_zips_dir = os.path.join(os.getcwd(), "chat_zips")
            os.makedirs(chat_zips_dir, exist_ok=True)

            # Create zip file in chat_zips directory
            # For multi-turn sessions, include turn number to create unique filenames per turn
            if turn_number is not None:
                zip_filename = f"{session_name}_turn_{turn_number}.zip"
            else:
                zip_filename = f"{session_name}.zip"
            zip_file_path = os.path.join(chat_zips_dir, zip_filename)
        else:
            # Create temporary zip file
            zip_file = tempfile.NamedTemporaryFile(
                suffix='.zip',
                prefix=f"{'_'.join(session_name.split('_')[:-1])}_",
                delete=False
            )
            zip_file.close()
            zip_file_path = zip_file.name

        # Create zip archive
        with zipfile.ZipFile(zip_file_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            total_size = 0
            max_zip_size = 500 * 1024 * 1024  # 500MB max zip size
            skipped_files = []

            # Walk through all files in session directory
            for root, dirs, files in os.walk(session_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    file_size = os.path.getsize(file_path)

                    # For multi-turn sessions with turn_start_time, only include files created during this turn
                    if turn_start_time is not None:
                        file_mtime = os.path.getmtime(file_path)
                        if file_mtime < turn_start_time:
                            # File was created before this turn started, skip it
                            continue

                    # Skip individual files larger than 100MB
                    if file_size > 100 * 1024 * 1024:
                        skipped_files.append(f"{file} ({file_size / 1024 / 1024:.1f}MB)")
                        print(f"Skipping large file in zip: {file} ({file_size / 1024 / 1024:.1f}MB)")
                        continue

                    # Check total zip size limit
                    if total_size + file_size > max_zip_size:
                        skipped_files.append(f"{file} (would exceed 500MB zip limit)")
                        print(f"Skipping {file} - would exceed 500MB zip limit")
                        continue

                    # Add file to zip with relative path
                    arcname = os.path.relpath(file_path, session_path)
                    zipf.write(file_path, arcname)
                    total_size += file_size

            # Add a notice file if files were skipped
            if skipped_files:
                notice_content = "LARGE FILES EXCLUDED FROM ZIP:\n\n"
                notice_content += "\n".join(skipped_files)
                notice_content += "\n\nThese files were too large and excluded to keep download size manageable."
                zipf.writestr("SKIPPED_LARGE_FILES.txt", notice_content)

        print(f"Created session zip: {zip_file_path}")
        return zip_file_path
    except Exception as e:
        print(f"Error creating session zip: {e}")
        return None


def create_turn_zip(session_path, base_session_id, turn_number, save_to_chat_zips=True):
    """Create a ZIP file for a specific turn with all turn-generated files

    Args:
        session_path: Path to the session directory
        base_session_id: Base session ID (without _turn_X suffix)
        turn_number: Turn number (1, 2, 3, etc.)
        save_to_chat_zips: Whether to save to chat_zips directory

    Returns:
        Dictionary with zip_path, zip_filename, and metadata
    """
    if not os.path.exists(session_path):
        return None

    try:
        # Generate timestamp and ZIP filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        zip_filename = f"multiturn_{timestamp}_{base_session_id[:12]}_turn_{turn_number}.zip"

        if save_to_chat_zips:
            chat_zips_dir = os.path.join(os.getcwd(), "chat_zips")
            os.makedirs(chat_zips_dir, exist_ok=True)
            zip_file_path = os.path.join(chat_zips_dir, zip_filename)
        else:
            # Create temporary zip file
            zip_file = tempfile.NamedTemporaryFile(
                suffix='.zip',
                prefix=f"turn_{turn_number}_",
                delete=False
            )
            zip_file.close()
            zip_file_path = zip_file.name

        # Create ZIP archive
        with zipfile.ZipFile(zip_file_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            total_size = 0
            max_zip_size = 500 * 1024 * 1024  # 500MB max
            skipped_files = []
            included_files = []

            # Walk through all files in session directory
            for root, dirs, files in os.walk(session_path):
                for file in files:
                    file_path = os.path.join(root, file)

                    # Skip snapshot files (not needed in turn ZIP)
                    if file.startswith('snapshot_'):
                        continue

                    # For turn-specific ZIP, we want ALL files generated so far
                    # This includes all images, CSVs, and outputs from current and previous turns
                    # This way turn_2.zip contains everything from turn 1 and turn 2

                    file_size = os.path.getsize(file_path)

                    # Skip individual files larger than 100MB
                    if file_size > 100 * 1024 * 1024:
                        skipped_files.append(f"{file} ({file_size / 1024 / 1024:.1f}MB)")
                        continue

                    # Check total zip size limit
                    if total_size + file_size > max_zip_size:
                        skipped_files.append(f"{file} (would exceed 500MB limit)")
                        continue

                    # Add file to ZIP
                    arcname = os.path.relpath(file_path, session_path)
                    zipf.write(file_path, arcname)
                    total_size += file_size
                    included_files.append(file)

            # Add notice file if files were skipped
            if skipped_files:
                notice_content = "LARGE FILES EXCLUDED FROM ZIP:\n\n"
                notice_content += "\n".join(skipped_files)
                notice_content += "\n\nThese files were too large and excluded to keep download size manageable."
                zipf.writestr("SKIPPED_LARGE_FILES.txt", notice_content)

        print(f"Created turn {turn_number} zip: {zip_file_path} ({len(included_files)} files, {total_size / 1024 / 1024:.2f}MB)")

        return {
            'zip_path': zip_file_path,
            'zip_filename': zip_filename,
            'turn_number': turn_number,
            'file_count': len(included_files),
            'total_size': total_size
        }
    except Exception as e:
        print(f"Error creating turn {turn_number} zip: {e}")
        return None


def create_agent():
    """Create an agent configured for tasks"""
    agent = A1(
        use_tool_retriever=True,
        download_data_lake=False,
        llm='claude-sonnet-4-5-20250929'
    )
    return agent


def create_planning_agent(language: str = "en"):
    """
    Create a planning agent for clarification phase

    Uses same model as execution (Claude Sonnet 4) for high-quality planning,
    but with NO tool access and focused system prompt.

    Args:
        language: "en" or "jp" for language-specific prompts

    Returns:
        dict with agent configuration for planning mode
    """

    if language == "en":
        planning_system_prompt = """You are a helpful AI assistant in planning mode for biomedical data analysis.
Your goal is to understand the user's needs by asking clarifying questions.

DO NOT execute any analysis or use tools yet. Your job is to:
1. Ask 2-4 focused clarifying questions to understand:
   - What type of data/analysis they need
   - What their goals are
   - What outputs they expect
2. Help them refine their request
3. Build a clear plan of what you'll do

Keep responses concise (2-3 paragraphs max).

IMPORTANT - When to suggest execution:
- When you have enough information about: data type, analysis goals, and expected outputs
- When the user has answered your key questions
- When you can create a clear execution plan

Signal readiness by including this EXACT phrase at the end of your response:
"[READY_FOR_EXECUTION]"

When ready, structure your response like this:
1. Summarize what you understand
2. Outline the execution plan (3-5 steps)
3. End with: "I have enough information to proceed! [READY_FOR_EXECUTION]"

Example ready response:
"Great! I now understand you want to:
- Analyze gene expression data from your CSV file
- Perform hierarchical clustering
- Generate a heatmap and PCA plot

Here's my execution plan:
1. Load and validate the gene expression data
2. Perform data preprocessing and normalization
3. Apply hierarchical clustering
4. Generate heatmap visualization
5. Create PCA plot with cluster annotations

I have enough information to proceed! [READY_FOR_EXECUTION]"
"""
    else:  # Japanese
        planning_system_prompt = """あなたは計画モードのAIアシスタントです。
ユーザーのニーズを理解するために質問をすることが目標です。

まだ分析やツールの実行はしないでください。あなたの仕事は:
1. 2-4の焦点を絞った質問をして理解する:
   - どのようなデータ/分析が必要か
   - 目標は何か
   - どのような出力を期待しているか
2. リクエストを洗練させる
3. 実行計画を明確に作成する

回答は簡潔に（2-3段落以内）。

重要 - 実行を提案するタイミング:
- データタイプ、分析目標、期待される出力について十分な情報がある時
- ユーザーが重要な質問に答えた時
- 明確な実行計画を作成できる時

準備ができたら、このフレーズを応答の最後に含めてください:
"[READY_FOR_EXECUTION]"

準備ができた時の回答構造:
1. 理解した内容を要約
2. 実行計画を概説（3-5ステップ）
3. 最後に: "十分な情報が揃いました！実行に進むことができます。[READY_FOR_EXECUTION]"
"""

    return {
        "system_prompt": planning_system_prompt,
        "model": "claude-sonnet-4-5-20250929",  # Same model as execution
        "tools": [],  # NO TOOLS - key difference
        "timeout": 90,  # Shorter timeout (90s vs 600s)
        "temperature": 0.7,
        "mode": "planning"
    }


# Global template retriever instance (initialized once, reused for all requests)
template_retriever = None

def get_template_retriever():
    """Get or create the global template retriever instance"""
    global template_retriever
    if template_retriever is None:
        try:
            template_retriever = TemplateRetriever()
            print("Initialized template retriever")
        except Exception as e:
            print(f"Warning: Could not initialize template retriever: {e}")
            template_retriever = None
    return template_retriever

# Email allow list middleware to restrict API access
class EmailAllowListMiddleware(BaseHTTPMiddleware):
    """Middleware to check if the user_id is in the allowed list."""

    # Endpoints that don't require user authentication
    EXEMPT_PATHS = {
        "/health",
        "/docs",
        "/openapi.json",
        "/redoc",
        "/templates",
        "/shared-sessions",
    }

    async def dispatch(self, request: Request, call_next):
        # Skip OPTIONS requests (CORS preflight)
        if request.method == "OPTIONS":
            return await call_next(request)

        # Skip exempt paths
        path = request.url.path
        if path in self.EXEMPT_PATHS or path.startswith("/docs") or path.startswith("/redoc"):
            return await call_next(request)

        # Try to extract user_id from different sources
        user_id = None

        # 1. Try query parameters
        user_id = request.query_params.get("user_id")

        # 2. Try to read from form data (for POST requests)
        if not user_id and request.method == "POST":
            # We need to be careful here - reading the body consumes it
            # So we'll check the content type and handle form data
            content_type = request.headers.get("content-type", "")
            if "multipart/form-data" in content_type or "application/x-www-form-urlencoded" in content_type:
                # For form data, we can't easily peek without consuming
                # So we'll let the endpoint handle validation
                return await call_next(request)

        # 3. Try path parameters for endpoints like /user/{user_id}/name
        if not user_id:
            path_parts = path.split("/")
            if "user" in path_parts:
                user_idx = path_parts.index("user")
                if user_idx + 1 < len(path_parts):
                    user_id = path_parts[user_idx + 1]

        # If we found a user_id, validate it
        if user_id:
            if not is_user_allowed(user_id):
                logger.warning(f"Access denied for user_id: {user_id}")
                return JSONResponse(
                    status_code=403,
                    content={"detail": f"Access denied: User '{user_id}' is not in the allowed list"},
                    headers={
                        "Access-Control-Allow-Origin": "*",
                        "Access-Control-Allow-Credentials": "true",
                    }
                )

        return await call_next(request)


# Custom CORS middleware to ensure headers are always present
class CORSHeaderMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Handle preflight OPTIONS requests
        if request.method == "OPTIONS":
            return JSONResponse(
                content={"message": "OK"},
                headers={
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS, PATCH",
                    "Access-Control-Allow-Headers": "Content-Type, Authorization, x-api-key, Accept, Origin, X-Requested-With, Access-Control-Request-Method, Access-Control-Request-Headers",
                    "Access-Control-Max-Age": "3600",
                    "Access-Control-Allow-Credentials": "true",
                }
            )

        # Process the request
        response = await call_next(request)

        # Add CORS headers to all responses
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS, PATCH"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, x-api-key, Accept, Origin, X-Requested-With"

        return response

# FastAPI App
app = FastAPI(title="Agent Chat API", description="Multi-user agent chat with queue management")

# Add CORS middleware with explicit configuration for API Gateway and custom headers
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins (adjust for production security)
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],  # Explicit methods
    allow_headers=[
        "Content-Type",
        "Authorization",
        "x-api-key",  # Explicitly allow x-api-key header
        "Accept",
        "Origin",
        "X-Requested-With",
        "Access-Control-Request-Method",
        "Access-Control-Request-Headers",
    ],
    expose_headers=["*"],  # Allow frontend to read response headers
    max_age=3600,  # Cache preflight requests for 1 hour
)

# Add custom CORS header middleware (belt and suspenders approach)
app.add_middleware(CORSHeaderMiddleware)

# Add email allow list middleware to restrict API access
app.add_middleware(EmailAllowListMiddleware)

# Global OPTIONS handler for CORS preflight requests
@app.options("/{full_path:path}")
async def options_handler(full_path: str):
    """Handle OPTIONS preflight requests for all routes"""
    return {
        "message": "OK",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS, PATCH",
        "Access-Control-Allow-Headers": "Content-Type, Authorization, x-api-key, Accept, Origin, X-Requested-With",
        "Access-Control-Max-Age": "3600"
    }

# API Endpoints
# REMOVED: /chat endpoint - legacy blocking endpoint, use /chat-queue for modern queue-based multi-turn chat



@app.post("/chat-queue")
async def start_chat_queue(
    message: str = Form(...),
    language: Language = Form(Language.EN),
    user_id: str = Form(...),
    session_id: Optional[str] = Form(None),
    use_template: Optional[bool] = Form(None),
    files: List[UploadFile] = File(default=[])
):
    """Add chat request to queue with S3 file uploads

    Args:
        message: User's message/query
        language: Language for response (en/jp)
        user_id: User identifier
        session_id: Optional session ID (creates new if not provided)
        use_template: Whether to use template matching (None = auto-detect based on query complexity)
        files: Uploaded files
    """
    # Validate user_id
    if not user_id or user_id.strip() == "":
        raise HTTPException(status_code=400, detail="user_id is required and cannot be empty")

    # Check if user is in the allowed list
    if not is_user_allowed(user_id):
        logger.warning(f"Access denied for user_id in /chat-queue: {user_id}")
        raise HTTPException(status_code=403, detail=f"Access denied: User '{user_id}' is not in the allowed list")

    # Automatically determine if template matching should be used
    # If use_template is None (not specified), use LLM to auto-detect based on query complexity
    if use_template is None:
        use_template = should_use_template_matching(message, language=language.value)
        logger.info(f"LLM auto-detected template matching: {use_template} for query: {message[:100]}")

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

@app.get("/progress/{session_id}")
async def get_progress(session_id: str, user_id: str):
    """Get current progress for a session (alias for /status for backward compatibility)"""
    return await get_status(session_id, user_id)

@app.get("/status/{session_id}")
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

    # Check if user is in the allowed list
    if not is_user_allowed(user_id):
        logger.warning(f"Access denied for user_id in /status: {user_id}")
        raise HTTPException(status_code=403, detail=f"Access denied: User '{user_id}' is not in the allowed list")

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
            response["chats_ahead"] = queue_status.chats_ahead

        # Add error information if present
        if status_data.get("error"):
            response["error"] = status_data["error"]

        # Handle progress updates based on storage location
        storage_location = status_data.get("storage_location", "unknown")

        if storage_location == "active":
            # Active sessions: include real-time progress updates (but strip out full snapshot content to reduce payload)
            progress_updates = status_data.get("progress_updates", [])
            filtered_updates = []
            for update in progress_updates:
                if update.get("type") == "snapshot_saved":
                    # For snapshot updates, only include minimal metadata (not the full content)
                    filtered_update = {
                        "type": update.get("type"),
                        "message": update.get("message"),
                        "snapshot_summary": {
                            "timestamp": update.get("snapshot", {}).get("timestamp"),
                            "status": update.get("snapshot", {}).get("status"),
                            "thinking_length": update.get("snapshot", {}).get("content", {}).get("thinking_length", 0) if isinstance(update.get("snapshot", {}).get("content"), dict) else 0,
                            "is_complete": update.get("snapshot", {}).get("is_complete", False)
                        }
                    }
                    filtered_updates.append(filtered_update)
                else:
                    # Include other update types as-is
                    filtered_updates.append(update)
            response["progress_updates"] = filtered_updates

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

@app.get("/download/{session_id}")
async def download_session_zip(session_id: str, user_id: str):
    """Download session zip file from local or cloud storage"""
    # Validate user_id
    if not user_id or user_id.strip() == "":
        raise HTTPException(status_code=400, detail="user_id is required and cannot be empty")

    # Check if user is in the allowed list
    if not is_user_allowed(user_id):
        logger.warning(f"Access denied for user_id in /download: {user_id}")
        raise HTTPException(status_code=403, detail=f"Access denied: User '{user_id}' is not in the allowed list")

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


@app.get("/download-file/{session_id}/{filename:path}")
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

    # Check if user is in the allowed list
    if not is_user_allowed(user_id):
        logger.warning(f"Access denied for user_id in /download-file: {user_id}")
        raise HTTPException(status_code=403, detail=f"Access denied: User '{user_id}' is not in the allowed list")

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


def append_images_to_report(final_report: str, files_data: dict) -> str:
    """
    Append images and download links to the final report in Markdown format

    Args:
        final_report: The original final report content
        files_data: Dictionary containing file information with URLs

    Returns:
        Enhanced final report with images and downloads appended
    """
    if not files_data or not isinstance(files_data, dict):
        return final_report

    added_content = ""

    # Extract images from files_data
    images = files_data.get("images", [])
    if images:
        # Start building the images section
        images_section = "\n\n---\n\n## 📊 Generated Images\n\n"

        # Process each image
        image_count = 0
        for image_item in images:
            # Handle both dict and string formats
            if isinstance(image_item, dict):
                filename = image_item.get("filename", "image")
                url = image_item.get("url")
                s3_key = image_item.get("s3_key")

                if url:
                    # Use the presigned URL (works with S3 URLs even without .png/.jpg extension)
                    image_count += 1
                    # Extract a cleaner name from filename or s3_key
                    display_name = filename.replace("_", " ").replace("-", " ").title()
                    images_section += f"### {display_name}\n\n"
                    images_section += f"![{display_name}]({url})\n\n"
            elif isinstance(image_item, str):
                # Handle string URL directly
                image_count += 1
                display_name = f"Image {image_count}"
                images_section += f"### {display_name}\n\n"
                images_section += f"![{display_name}]({image_item})\n\n"

        # Only append the section if we found images
        if image_count > 0:
            added_content += images_section

    # Add download links section
    download_links = []

    # Check for session_zip or turn_zip
    for key in ["session_zip", "turn_zip"]:
        zip_info = files_data.get(key)
        # Handle zip being a list (from cloud storage) - use the last item (turn-specific zip)
        if zip_info and isinstance(zip_info, list) and len(zip_info) > 0:
            zip_info = zip_info[-1]

        if zip_info and isinstance(zip_info, dict):
            url = zip_info.get("url") or zip_info.get("download_url")
            filename = zip_info.get("filename", f"{key}.zip")
            file_size = zip_info.get("file_size")

            if url:
                # Format file size for display
                size_display = ""
                if file_size:
                    if file_size > 1024 * 1024:  # MB
                        size_display = f" ({file_size / (1024 * 1024):.2f} MB)"
                    elif file_size > 1024:  # KB
                        size_display = f" ({file_size / 1024:.2f} KB)"
                    else:
                        size_display = f" ({file_size} bytes)"

                download_links.append({
                    "name": f"Download All Files (ZIP){size_display}",
                    "url": url,
                    "icon": "📦"
                })
                break  # Only add one zip download link

    # Add other downloadable files (report_md only, exclude result_json)
    for key in ["report_md"]:
        file_info = files_data.get(key)
        if file_info and isinstance(file_info, dict):
            url = file_info.get("url") or file_info.get("download_url")
            if url:
                name = "Final Report (Markdown)"
                icon = "📄"
                download_links.append({
                    "name": name,
                    "url": url,
                    "icon": icon
                })

    # Build download links section
    if download_links:
        downloads_section = "\n\n---\n\n## 📥 Downloads\n\n"
        for link in download_links:
            downloads_section += f"- {link['icon']} **[{link['name']}]({link['url']})**\n"
        added_content += downloads_section

    return final_report + added_content


def generate_file_urls(files_data, session_id: str = None):
    """
    Helper function to convert file paths/S3 keys to accessible URLs

    IMPORTANT: Always returns S3 presigned URLs. If file is only available locally,
    it will be uploaded to S3 first before generating the URL.

    Args:
        files_data: Dictionary or list of file information (can be paths, dicts, or mixed)
        session_id: Optional session ID for generating download URLs

    Returns:
        Enhanced files_data with 'url' fields added (always S3 URLs)
    """
    from datetime import datetime, timedelta
    import os
    import time

    func_start = time.time()
    file_count = 0
    head_object_count = 0
    upload_count = 0

    def process_file_item(file_item):
        """Process a single file item to add S3 URL"""
        nonlocal file_count, head_object_count, upload_count
        file_count += 1

        # Handle string paths (convert to dict with URL)
        if isinstance(file_item, str):
            filename = file_item.split("/")[-1]
            file_path = file_item

            # Upload to S3 if file exists locally
            if os.path.exists(file_path) and session_id:
                try:
                    s3_key = f"sessions/{session_id}/files/{filename}"

                    # Check if file already exists in S3 to avoid re-uploading
                    try:
                        head_object_count += 1
                        cloud_storage_manager.s3_client.head_object(
                            Bucket=cloud_storage_manager.bucket_name,
                            Key=s3_key
                        )
                        # File exists in S3, just generate fresh presigned URL
                        url = cloud_storage_manager.generate_presigned_url(s3_key, expiry_seconds=7200)
                        return {
                            "path": file_path,
                            "filename": filename,
                            "s3_key": s3_key,
                            "url": url,
                            "expires_at": (datetime.now() + timedelta(hours=2)).isoformat()
                        }
                    except cloud_storage_manager.s3_client.exceptions.ClientError:
                        # File doesn't exist in S3, upload it once
                        upload_count += 1
                        cloud_storage_manager.s3_client.upload_file(
                            file_path,
                            cloud_storage_manager.bucket_name,
                            s3_key
                        )
                        # Generate presigned URL after upload
                        url = cloud_storage_manager.generate_presigned_url(s3_key, expiry_seconds=7200)
                        return {
                            "path": file_path,
                            "filename": filename,
                            "s3_key": s3_key,
                            "url": url,
                            "expires_at": (datetime.now() + timedelta(hours=2)).isoformat()
                        }
                except Exception as e:
                    print(f"Warning: Failed to upload {filename} to S3 or generate URL: {e}")
                    return {
                        "path": file_path,
                        "filename": filename,
                        "download_url": f"/download-file/{session_id}/{filename}" if session_id else None
                    }

            return {
                "path": file_path,
                "filename": filename,
                "download_url": f"/download-file/{session_id}/{filename}" if session_id else None
            }

        if not isinstance(file_item, dict):
            return file_item

        result = file_item.copy()

        # If it has S3 key, generate presigned URL
        if "s3_key" in file_item:
            try:
                url = cloud_storage_manager.generate_presigned_url(
                    file_item["s3_key"],
                    expiry_seconds=7200  # 2 hours
                )
                result["url"] = url
                result["expires_at"] = (datetime.now() + timedelta(hours=2)).isoformat()
            except Exception as e:
                print(f"Warning: Failed to generate presigned URL for {file_item.get('filename', 'unknown')}: {e}")

        # If it only has a local path, upload to S3 and get URL
        elif "path" in file_item and session_id:
            filename = file_item.get("filename") or file_item["path"].split("/")[-1]
            file_path = file_item["path"]

            # Check if file exists locally
            if os.path.exists(file_path):
                try:
                    # Determine S3 key based on file type
                    file_ext = filename.split('.')[-1].lower()
                    if file_ext in ['png', 'jpg', 'jpeg', 'gif', 'svg', 'pdf']:
                        s3_key = f"sessions/{session_id}/images/{filename}"
                    else:
                        s3_key = f"sessions/{session_id}/files/{filename}"

                    # Check if file already exists in S3 to avoid re-uploading
                    try:
                        head_object_count += 1
                        cloud_storage_manager.s3_client.head_object(
                            Bucket=cloud_storage_manager.bucket_name,
                            Key=s3_key
                        )
                        # File exists in S3, just generate fresh presigned URL
                        url = cloud_storage_manager.generate_presigned_url(s3_key, expiry_seconds=7200)
                        result["s3_key"] = s3_key
                        result["url"] = url
                        result["expires_at"] = (datetime.now() + timedelta(hours=2)).isoformat()
                    except cloud_storage_manager.s3_client.exceptions.ClientError:
                        # File doesn't exist in S3, upload it once
                        upload_count += 1
                        cloud_storage_manager.s3_client.upload_file(
                            file_path,
                            cloud_storage_manager.bucket_name,
                            s3_key
                        )
                        # Generate presigned URL after upload
                        url = cloud_storage_manager.generate_presigned_url(s3_key, expiry_seconds=7200)
                        result["s3_key"] = s3_key
                        result["url"] = url
                        result["expires_at"] = (datetime.now() + timedelta(hours=2)).isoformat()
                    except Exception as process_error:
                        # S3 operation failed, fall back to local download
                        result["download_url"] = f"/download-file/{session_id}/{filename}"
                        print(f"Warning: Failed to process {filename} with S3: {process_error}")
                except Exception as e:
                    print(f"Warning: Error processing {filename} for S3: {e}")
                    # Fall back to local download URL
                    result["download_url"] = f"/download-file/{session_id}/{filename}"
            else:
                # File doesn't exist locally, check if it exists in S3
                try:
                    # Determine S3 key based on filename pattern
                    # Files are organized in S3 by type: report_md/, result_json/, thinking_process/, query_file/, etc.
                    file_ext = filename.split('.')[-1].lower()

                    # Try to infer folder from filename prefix
                    if filename.startswith('report_'):
                        folder = 'report_md'
                    elif filename.startswith('result_'):
                        folder = 'result_json'
                    elif filename.startswith('thinking_'):
                        folder = 'thinking_process'
                    elif filename.startswith('query_'):
                        folder = 'query_file'
                    elif file_ext in ['png', 'jpg', 'jpeg', 'gif', 'svg', 'pdf']:
                        folder = 'images'
                    elif filename.endswith('.zip'):
                        folder = 'files'
                    else:
                        folder = 'files'

                    s3_key = f"sessions/{session_id}/{folder}/{filename}"

                    # Check if file exists in S3
                    head_object_count += 1
                    cloud_storage_manager.s3_client.head_object(
                        Bucket=cloud_storage_manager.bucket_name,
                        Key=s3_key
                    )
                    # File exists in S3, generate presigned URL
                    url = cloud_storage_manager.generate_presigned_url(s3_key, expiry_seconds=7200)
                    result["s3_key"] = s3_key
                    result["url"] = url
                    result["expires_at"] = (datetime.now() + timedelta(hours=2)).isoformat()
                    result["filename"] = filename
                except cloud_storage_manager.s3_client.exceptions.ClientError:
                    # File doesn't exist in S3 either, fall back to download URL
                    result["download_url"] = f"/download-file/{session_id}/{filename}"
                    result["filename"] = filename
                except Exception as e:
                    print(f"Warning: Error checking S3 for {filename}: {e}")
                    result["download_url"] = f"/download-file/{session_id}/{filename}"
                    result["filename"] = filename

        return result

    # Handle different data structures
    if isinstance(files_data, list):
        result = [process_file_item(item) for item in files_data]
    elif isinstance(files_data, dict):
        result = {}
        for key, value in files_data.items():
            if isinstance(value, list):
                result[key] = [process_file_item(item) for item in value]
            elif isinstance(value, dict):
                result[key] = process_file_item(value)
            elif isinstance(value, str):
                # Handle single string path
                result[key] = process_file_item(value)
            else:
                result[key] = value
    else:
        result = files_data

    # Print summary statistics
    total_time = (time.time() - func_start) * 1000
    print(f"[PERF generate_file_urls] Total: {total_time:.2f} ms | Files: {file_count} | head_object calls: {head_object_count} | Uploads: {upload_count}")

    return result


@app.get("/results/{session_id}")
async def get_session_results(session_id: str, user_id: str, turn_number: Optional[int] = None):
    """Get structured JSON results for a completed session

    Args:
        session_id: The session ID
        user_id: The user ID
        turn_number: Optional turn number to retrieve. If not provided, returns current/latest turn results.
    """
    import time
    start_time = time.time()
    print(f"[PERF /results] Started for session {session_id}")

    # Validate user_id
    if not user_id or user_id.strip() == "":
        raise HTTPException(status_code=400, detail="user_id is required and cannot be empty")

    # Check if user is in the allowed list
    if not is_user_allowed(user_id):
        logger.warning(f"Access denied for user_id in /results: {user_id}")
        raise HTTPException(status_code=403, detail=f"Access denied: User '{user_id}' is not in the allowed list")

    # Get unified_manager ONCE and reuse it throughout this function
    step1_start = time.time()
    unified_manager = get_unified_session_manager(queue_manager)
    print(f"[PERF /results] Step 1 (get_unified_manager): {(time.time() - step1_start) * 1000:.2f} ms")

    # Get multi-turn session info to determine turn number and sharing status
    # First check in-memory sessions
    step2_start = time.time()
    multiturn_session = queue_manager.multiturn_sessions.get(session_id)
    current_turn = None
    total_turns = None
    is_shared = False
    session_owner_id = None
    cloud_multiturn_session = None  # Cache this for reuse in Step 4

    # If not in memory, try to get from MongoDB/cloud
    if not multiturn_session:
        try:
            # Use projection (include_turns=False) to only fetch metadata, not full turn data
            # This is much faster since we only need: current_turn, total_turns, is_shared, user_id
            cloud_multiturn_session = await unified_manager.get_multiturn_session_by_id(session_id, include_turns=False)
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
    print(f"[PERF /results] Step 2 (get multiturn info): {(time.time() - step2_start) * 1000:.2f} ms")

    # Process turn_number if we have turn information
    if total_turns is not None:
        # If turn_number not specified, use current_turn (or fall back to total_turns for last turn)
        if turn_number is None:
            turn_number = current_turn if current_turn is not None else total_turns
        # Validate turn_number is within range
        elif turn_number < 1 or turn_number > total_turns:
            raise HTTPException(status_code=400, detail=f"Invalid turn_number. Must be between 1 and {total_turns}")

    # Check access: Allow if session is shared OR user owns the session
    # This check happens early using multiturn metadata for efficiency
    # If we have ownership info and it's not shared and user doesn't own it, deny access
    if session_owner_id and session_owner_id != user_id and not is_shared:
        raise HTTPException(status_code=403, detail="Access denied: Session belongs to different user")

    # Use unified session manager to check both local and cloud storage (reuse existing instance)
    step3_start = time.time()
    session_data = await unified_manager.get_session_by_id(session_id)
    print(f"[PERF /results] Step 3 (get_session_by_id): {(time.time() - step3_start) * 1000:.2f} ms")

    if not session_data:
        raise HTTPException(status_code=404, detail="Session not found")

    # Fallback check: if we didn't have multiturn metadata, check from session_data
    # This handles cases where session exists but isn't in multiturn_sessions collection
    if not session_owner_id:
        session_user_id_fallback = session_data.get("user_id")
        is_shared_fallback = session_data.get("is_shared", False)
        if session_user_id_fallback and session_user_id_fallback != user_id and not is_shared_fallback:
            raise HTTPException(status_code=403, detail="Access denied: Session belongs to different user")

    # For multi-turn sessions, check if the specific turn is complete (not the whole session)
    # The session might have is_complete=True from previous turns, but current turn might be processing
    if turn_number is not None and current_turn is not None:
        # Check if the requested turn is currently being processed
        turn_specific_id = f"{session_id}_turn_{turn_number}"
        if turn_specific_id in queue_manager.active_sessions or (turn_number == current_turn and session_id in queue_manager.active_sessions):
            # Return processing status instead of error
            return {
                "session_id": session_id,
                "turn_number": turn_number,
                "current_turn": current_turn,
                "total_turns": total_turns,
                "status": "processing",
                "is_complete": False,
                "message": f"Turn {turn_number} is still being processed"
            }
    elif not session_data.get("is_complete", False):
        raise HTTPException(status_code=400, detail="Session is not yet complete")

    # For multi-turn sessions with specific turn_number, return turn-specific results
    if turn_number is not None and (current_turn is not None or total_turns is not None):
        # Load full multiturn session to get turn data
        # Step 2 used projection (no turns), so we need to fetch the full data WITH turns here
        step4_start = time.time()
        if cloud_multiturn_session and "turns" not in cloud_multiturn_session:
            # Step 2 fetched metadata only (no turns) - need to fetch full session with turns
            cloud_multiturn_session = await unified_manager.get_multiturn_session_by_id(session_id, include_turns=True)
            print(f"[PERF /results] Step 4 (get full multiturn session with turns): {(time.time() - step4_start) * 1000:.2f} ms")
        elif not cloud_multiturn_session:
            # Not fetched at all yet
            cloud_multiturn_session = await unified_manager.get_multiturn_session_by_id(session_id, include_turns=True)
            print(f"[PERF /results] Step 4 (get full multiturn session): {(time.time() - step4_start) * 1000:.2f} ms")
        else:
            # Already has turns (unlikely path since Step 2 uses projection)
            print(f"[PERF /results] Step 4 (get full multiturn session): 0.01 ms (already had turns - CACHED!)")

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
                turn_files = target_turn.get("files", {}) or {}

                # DEBUG: Log what files we extracted from the turn
                print(f"[DEBUG /results] Turn {turn_number} files extracted:")
                print(f"[DEBUG /results]   Raw turn_files: {turn_files}")
                tp_file = turn_files.get("thinking_process", {}).get("filename", "NOT_FOUND") if isinstance(turn_files.get("thinking_process"), dict) else f"NOT_DICT: {turn_files.get('thinking_process')}"
                print(f"[DEBUG /results]   Extracted TP filename: {tp_file}")

                # OPTIMIZATION: Skip expensive sessions collection query if turn_files already has images
                # Only fetch S3 files from sessions collection if turn_files is missing images
                step5_start = time.time()
                should_fetch_s3 = isinstance(turn_files, dict) and "images" not in turn_files

                if should_fetch_s3:
                    try:
                        # Use turn-specific session ID for turn 2+ to get correct images
                        turn_session_id_for_s3 = f"{session_id}_turn_{turn_number}" if turn_number > 1 else session_id
                        cloud_session = await cloud_storage_manager.retrieve_session_from_cloud(turn_session_id_for_s3)
                        if cloud_session and "s3_files" in cloud_session:
                            s3_files = cloud_session["s3_files"]
                            # Merge S3 files (especially images) into turn files
                            if "images" in s3_files:
                                turn_files["images"] = s3_files["images"]
                    except Exception as e:
                        print(f"Warning: Could not retrieve S3 files for turn results: {e}")
                    print(f"[PERF /results] Step 5 (retrieve_session_from_cloud for S3 files): {(time.time() - step5_start) * 1000:.2f} ms - FETCHED")
                else:
                    print(f"[PERF /results] Step 5 (retrieve_session_from_cloud for S3 files): {(time.time() - step5_start) * 1000:.2f} ms - SKIPPED (already have files)")

                # Generate URLs for turn files (use turn-specific session ID for turn 2+)
                step6_start = time.time()
                if turn_files:
                    turn_session_id = f"{session_id}_turn_{turn_number}" if turn_number > 1 else session_id
                    turn_files = generate_file_urls(turn_files, turn_session_id)

                    # For existing data: if turn_zip exists, use it as session_zip (for backwards compatibility)
                    if isinstance(turn_files, dict):
                        if "turn_zip" in turn_files and turn_files["turn_zip"]:
                            # Prefer turn_zip over session_zip for turn-specific downloads
                            turn_files["session_zip"] = turn_files["turn_zip"]
                        elif "session_zip" in turn_files:
                            session_zips = turn_files["session_zip"]
                            # Handle session_zip being a list (from cloud storage)
                            if isinstance(session_zips, list) and len(session_zips) > 0:
                                # Find the zip for this specific turn
                                turn_zip_pattern = f"_turn_{turn_number}.zip"
                                matching_zip = None
                                for zip_item in session_zips:
                                    if isinstance(zip_item, dict):
                                        filename = zip_item.get("filename", "")
                                        if turn_zip_pattern in filename:
                                            matching_zip = zip_item
                                            break
                                # If no turn-specific zip found for turn 1, use one without _turn_ suffix
                                if not matching_zip and turn_number == 1:
                                    for zip_item in session_zips:
                                        if isinstance(zip_item, dict):
                                            filename = zip_item.get("filename", "")
                                            if "_turn_" not in filename:
                                                matching_zip = zip_item
                                                break
                                # If still no match, use the last item as fallback
                                if not matching_zip:
                                    matching_zip = session_zips[-1]
                                # Replace list with the single matching zip
                                turn_files["session_zip"] = matching_zip

                print(f"[PERF /results] Step 6 (generate_file_urls): {(time.time() - step6_start) * 1000:.2f} ms")

                # Append images to final report
                final_report = target_turn.get("final_report", "")
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
                    "turn_type": target_turn.get("turn_type", "execution"),  # NEW FIELD
                    "content": {
                        "final_report": final_report_with_images
                    }
                }

                # Add ready_for_execution flag for planning turns
                if target_turn.get("turn_type") == "planning":
                    result["ready_for_execution"] = target_turn.get("ready_for_execution", False)
                print(f"[PERF /results] TOTAL TIME: {(time.time() - start_time) * 1000:.2f} ms (turn-specific path)")
                return result

    # For cloud sessions, retrieve from MongoDB
    storage_location = session_data.get("_storage_location", "unknown")
    if storage_location == "cloud":
        # Get full session data from cloud
        step5_start = time.time()
        cloud_session = await cloud_storage_manager.retrieve_session_from_cloud(session_id)
        print(f"[PERF /results] Step 5 (retrieve_session_from_cloud): {(time.time() - step5_start) * 1000:.2f} ms")

        if cloud_session:
            # Generate URLs for S3 files
            step6_start = time.time()
            s3_files = cloud_session.get("s3_files", {})
            s3_files_with_urls = generate_file_urls(s3_files, session_id)
            print(f"[PERF /results] Step 6 (generate_file_urls): {(time.time() - step6_start) * 1000:.2f} ms")

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
            print(f"[PERF /results] TOTAL TIME: {(time.time() - start_time) * 1000:.2f} ms (cloud path)")
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


@app.post("/stop/{session_id}")
async def stop_task(session_id: str, user_id: str):
    """Stop a running or queued task"""
    # Validate user_id
    if not user_id or user_id.strip() == "":
        raise HTTPException(status_code=400, detail="user_id is required and cannot be empty")

    # Check if user is in the allowed list
    if not is_user_allowed(user_id):
        logger.warning(f"Access denied for user_id in /stop: {user_id}")
        raise HTTPException(status_code=403, detail=f"Access denied: User '{user_id}' is not in the allowed list")

    # First verify user owns this session
    if session_id in queue_manager.active_sessions:
        session_user_id = getattr(queue_manager.active_sessions[session_id], 'user_id', None)
        if session_user_id and session_user_id != user_id:
            raise HTTPException(status_code=403, detail="Access denied: Session belongs to different user")

    result = queue_manager.stop_session(session_id)
    if result.get("success"):
        was_queued = result.get("was_queued", False)
        was_running = result.get("was_running", False)

        if was_queued:
            message = f"Task {session_id} was removed from queue (was not yet processing)"
        elif was_running:
            message = f"Task {session_id} has been stopped (was actively processing)"
        else:
            message = f"Task {session_id} has been cancelled"

        return {
            "message": message,
            "session_id": session_id,
            "status": "cancelled",
            "was_queued": was_queued,
            "was_running": was_running
        }
    else:
        raise HTTPException(status_code=404, detail="Session not found")


# REMOVED: /ws/{session_id} endpoint - WebSocket not used by Gradio and doesn't validate user_id


# REMOVED: /stream/{session_id} endpoint - SSE streaming not used by Gradio (uses polling instead)


def filter_execute_blocks(text: str, include_execute: bool = False) -> str:
    """Filter out <execute>...</execute> blocks and verbose directory listings from text

    Args:
        text: The text to filter
        include_execute: If True, return text as-is. If False, remove execute blocks and hide verbose listings.

    Returns:
        Filtered text with execute blocks removed and directory listings summarized
    """
    if include_execute or not text:
        return text

    import re
    # Remove <execute>...</execute> blocks (including multiline)
    filtered_text = re.sub(r'<execute>.*?</execute>', '', text, flags=re.DOTALL)

    # Hide verbose directory listings - match "Current directory files:" followed by file list
    # Pattern: "Current directory files:\n  - file1\n  - file2\n..."
    def replace_file_listing(match):
        full_match = match.group(0)
        # Count number of files in the listing (lines starting with "  - ")
        file_count = len(re.findall(r'^\s+-\s+', full_match, re.MULTILINE))
        return f"Current directory files: Found {file_count} items. (Full listing hidden for readability)"

    # Replace verbose file listings with summary
    filtered_text = re.sub(
        r'Current directory files:.*?(?=\n\n|\n[A-Z]|\Z)',
        replace_file_listing,
        filtered_text,
        flags=re.DOTALL
    )

    return filtered_text


@app.get("/snapshots/{session_id}")
async def get_session_snapshots(
    session_id: str,
    user_id: str,
    turn_number: Optional[int] = None,
    include_execute: bool = False
):
    """Get all periodic snapshots for a session

    Args:
        session_id: The session ID (can be base session_id or turn-specific like session_id_turn_2)
        user_id: The user ID
        turn_number: Optional turn number to retrieve snapshots for. If not provided, returns current/latest turn snapshots.
        include_execute: If True, include <execute>...</execute> blocks in response. If False (default), exclude them.
    """
    # Validate user_id
    if not user_id or user_id.strip() == "":
        raise HTTPException(status_code=400, detail="user_id is required and cannot be empty")

    # Check if user is in the allowed list
    if not is_user_allowed(user_id):
        logger.warning(f"Access denied for user_id in /snapshots: {user_id}")
        raise HTTPException(status_code=403, detail=f"Access denied: User '{user_id}' is not in the allowed list")

    # Parse turn-specific session IDs (e.g., "session_id_turn_2")
    base_session_id = session_id
    turn_from_id = None
    if "_turn_" in session_id:
        parts = session_id.rsplit("_turn_", 1)
        if len(parts) == 2 and parts[1].isdigit():
            base_session_id = parts[0]
            turn_from_id = int(parts[1])
            if turn_number is None:
                turn_number = turn_from_id
            print(f"[SNAPSHOTS] Parsed turn-specific ID: base={base_session_id}, turn={turn_from_id}")

    # Get multi-turn session info to determine turn number
    # Try with base_session_id first, then fall back to original session_id
    multiturn_session = queue_manager.multiturn_sessions.get(base_session_id)
    if not multiturn_session:
        multiturn_session = queue_manager.multiturn_sessions.get(session_id)
    current_turn = None
    total_turns = None

    # If not in memory, try to load from cloud (use base_session_id)
    if not multiturn_session:
        try:
            unified_manager = get_unified_session_manager(queue_manager)
            cloud_multiturn_session = await unified_manager.get_multiturn_session_by_id(base_session_id)
            if cloud_multiturn_session:
                current_turn = cloud_multiturn_session.get("current_turn")
                total_turns = cloud_multiturn_session.get("total_turns")
        except Exception as e:
            print(f"Could not load multiturn session info from cloud: {e}")
    else:
        current_turn = multiturn_session.current_turn
        total_turns = multiturn_session.total_turns

    # Process turn_number if we have turn information
    # Default to current (latest) turn if not specified
    if turn_number is None and current_turn is not None:
        turn_number = current_turn
        print(f"[SNAPSHOTS] No turn_number specified, defaulting to current_turn={current_turn}")

    # Validate turn_number is within range (only if we have total_turns info)
    if turn_number is not None and total_turns is not None:
        if turn_number < 1 or turn_number > total_turns:
            raise HTTPException(status_code=400, detail=f"Invalid turn_number. Must be between 1 and {total_turns}")

    # Use unified session manager to check both local and cloud storage
    # Try with original session_id first (for turn-specific active sessions), then base_session_id
    unified_manager = get_unified_session_manager(queue_manager)
    session_data = await unified_manager.get_session_by_id(session_id)
    if not session_data and session_id != base_session_id:
        # For turn-specific IDs, also try with base session ID
        session_data = await unified_manager.get_session_by_id(base_session_id)

    if not session_data:
        raise HTTPException(status_code=404, detail="Session not found")

    # Verify user owns this session
    session_user_id = session_data.get("user_id")
    if session_user_id and session_user_id != user_id:
        raise HTTPException(status_code=403, detail="Access denied: Session belongs to different user")

    # Determine storage location to choose the right path
    # IMPORTANT: Check if session is actively processing FIRST before using storage_location from session_data
    # For multi-turn sessions, session_data from cloud might have storage_location="turn_specific" even if actively processing
    storage_location = session_data.get("_storage_location", "unknown")

    # Override storage_location to "active" if session is currently being processed
    # For multi-turn sessions, check turn-specific session IDs (e.g., base_session_id_turn_4)
    active_turn_session_id = None
    if session_id in queue_manager.active_sessions:
        storage_location = "active"
        active_turn_session_id = session_id
        print(f"[SNAPSHOTS] Overriding storage_location to 'active' for session_id={session_id}")
    elif base_session_id in queue_manager.active_sessions:
        storage_location = "active"
        active_turn_session_id = base_session_id
        print(f"[SNAPSHOTS] Overriding storage_location to 'active' for base_session_id={base_session_id}")
    elif current_turn is not None:
        # Check if there's an active session for the current turn
        turn_specific_id = f"{base_session_id}_turn_{current_turn}"
        if turn_specific_id in queue_manager.active_sessions:
            storage_location = "active"
            active_turn_session_id = turn_specific_id
            print(f"[SNAPSHOTS] Overriding storage_location to 'active' for turn_specific_id={turn_specific_id}")

    # For ACTIVE sessions (in-progress), use live snapshot extraction from progress_updates
    if storage_location == "active":
        # For active sessions, get real-time progress data from queue_manager using active_turn_session_id
        if active_turn_session_id:
            active_session_data = queue_manager.get_session_progress(active_turn_session_id)
            progress_updates = active_session_data.get("progress_updates", [])
            print(f"[SNAPSHOTS] Got active session data for: {active_turn_session_id}")
        else:
            # Fallback to session_data if not in active_sessions
            progress_updates = session_data.get("progress_updates", [])
            print(f"[SNAPSHOTS] Using session_data progress_updates (not in active_sessions)")
        snapshots_list = []
        latest_thinking_content = None

        # Extract all snapshots from progress_updates
        for update in progress_updates:
            if update.get("type") == "snapshot_saved":
                snapshot = update.get("snapshot")
                if snapshot:
                    snapshots_list.append({
                        "timestamp": snapshot.get("timestamp"),
                        "status": snapshot.get("status"),
                        "session_path": snapshot.get("session_path"),
                        "thinking_length": snapshot.get("content", {}).get("thinking_length", 0) if isinstance(snapshot.get("content"), dict) else 0,
                        "is_complete": snapshot.get("is_complete", False),
                        "is_cancelled": snapshot.get("is_cancelled", False),
                        "error": snapshot.get("error")
                    })
                    # Keep track of latest thinking content
                    if isinstance(snapshot.get("content"), dict):
                        content = snapshot.get("content")
                        if content.get("thinking_content"):
                            latest_thinking_content = content.get("thinking_content")

        print(f"[SNAPSHOTS DEBUG] Active session - extracted {len(snapshots_list)} snapshots from progress_updates")
        print(f"[SNAPSHOTS DEBUG] Latest thinking content length: {len(latest_thinking_content) if latest_thinking_content else 0}")

        result = {
            "session_id": session_id,
            "turn_number": turn_number,
            "current_turn": current_turn,
            "total_turns": total_turns,
            "snapshot_count": len(snapshots_list),
            "snapshots": snapshots_list,
            "thinking_process": filter_execute_blocks(latest_thinking_content, include_execute),
            "storage_location": storage_location
        }
        return result

    # For multi-turn sessions with turn structure available, use turn-specific snapshot logic
    if turn_number is not None and (current_turn is not None or total_turns is not None):
        # Load full multiturn session to get turn data (use base_session_id for multi-turn lookup)
        unified_manager_mt = get_unified_session_manager(queue_manager)
        cloud_multiturn_session = await unified_manager_mt.get_multiturn_session_by_id(base_session_id)

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

                        # If still not found, try to retrieve from cloud storage using the specific filename
                        if not thinking_process_text:
                            print(f"[SNAPSHOTS DEBUG] Attempting to retrieve from cloud storage...")
                            try:
                                # We have the correct filename from thinking_process_file
                                filename = thinking_process_file.get("filename")
                                if filename:
                                    # Construct the S3 key for this specific turn's file
                                    # For multi-turn sessions, files are uploaded with turn-specific session IDs:
                                    # - Turn 1: uses base_session_id
                                    # - Turn 2+: uses {base_session_id}_turn_{turn_number}
                                    if turn_number and turn_number > 1:
                                        turn_session_id = f"{base_session_id}_turn_{turn_number}"
                                    else:
                                        turn_session_id = base_session_id
                                    s3_key = f"sessions/{turn_session_id}/thinking_process/{filename}"
                                    print(f"[SNAPSHOTS DEBUG] Constructed S3 key from filename (using turn_session_id={turn_session_id}): {s3_key}")

                                    try:
                                        content = cloud_storage_manager.download_file_content(s3_key)
                                        if content:
                                            thinking_process_text = content.decode('utf-8')
                                            print(f"[SNAPSHOTS DEBUG] Downloaded {len(thinking_process_text)} characters from S3 using constructed key")
                                    except Exception as e:
                                        print(f"[SNAPSHOTS DEBUG] Failed to download with constructed key: {e}")

                                # Fallback: try session-level retrieval using turn-specific session ID
                                if not thinking_process_text:
                                    # Use turn-specific session ID for multi-turn sessions
                                    if turn_number and turn_number > 1:
                                        fallback_session_id = f"{base_session_id}_turn_{turn_number}"
                                    else:
                                        fallback_session_id = base_session_id
                                    cloud_session = await cloud_storage_manager.retrieve_session_from_cloud(fallback_session_id)
                                    print(f"[SNAPSHOTS DEBUG] Cloud session found for {fallback_session_id}: {cloud_session is not None}")
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

                                            # For multi-turn sessions, try to find the file matching this turn's filename
                                            if filename:
                                                print(f"[SNAPSHOTS DEBUG] Looking for file matching: {filename}")
                                                for file_info in files_to_check:
                                                    if isinstance(file_info, dict):
                                                        if file_info.get("filename") == filename and "s3_key" in file_info:
                                                            print(f"[SNAPSHOTS DEBUG] Found matching file, downloading from S3 key: {file_info['s3_key']}")
                                                            content = cloud_storage_manager.download_file_content(file_info["s3_key"])
                                                            if content:
                                                                thinking_process_text = content.decode('utf-8')
                                                                print(f"[SNAPSHOTS DEBUG] Downloaded {len(thinking_process_text)} characters from S3 (matched filename)")
                                                                break

                                            # If still not found, fall back to first available file
                                            if not thinking_process_text:
                                                print(f"[SNAPSHOTS DEBUG] No filename match, trying first available file")
                                                for file_info in files_to_check:
                                                    if isinstance(file_info, dict) and "s3_key" in file_info:
                                                        print(f"[SNAPSHOTS DEBUG] Downloading from S3 key: {file_info['s3_key']}")
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
                    "thinking_process": filter_execute_blocks(thinking_process_text, include_execute),
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

    # Fallback: no snapshots found
    return {
        "session_id": session_id,
        "turn_number": turn_number,
        "current_turn": current_turn,
        "total_turns": total_turns,
        "snapshot_count": 0,
        "snapshots": [],
        "thinking_process": None,
        "storage_location": storage_location,
        "message": "No snapshots found for this session"
    }


@app.get("/all-sessions")
async def get_all_sessions(user_id: Optional[str] = None):
    """Get all sessions from both local and cloud storage"""
    try:
        # Require user_id for security - prevent unauthorized access to all sessions
        if not user_id or user_id.strip() == "":
            return {"sessions": [], "error": "user_id is required", "message": "Please provide a valid user_id"}

        # Check if user is in the allowed list
        if not is_user_allowed(user_id):
            logger.warning(f"Access denied for user_id in /all-sessions: {user_id}")
            raise HTTPException(status_code=403, detail=f"Access denied: User '{user_id}' is not in the allowed list")

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

@app.post("/continue-session")
async def continue_session(
    session_id: str = Form(...),
    message: str = Form(...),
    language: Language = Form(Language.EN),
    user_id: str = Form(...),
    use_template: Optional[bool] = Form(None),
    files: List[UploadFile] = File(default=[])
):
    """Continue an existing multi-turn session with S3 file handling

    Args:
        session_id: The session ID to continue
        message: User's message/query
        language: Language for response (en/jp)
        user_id: User identifier
        use_template: Whether to use template matching (None = auto-detect based on query complexity)
        files: Uploaded files
    """
    # Validate user_id
    if not user_id or user_id.strip() == "":
        raise HTTPException(status_code=400, detail="user_id is required and cannot be empty")

    # Check if user is in the allowed list
    if not is_user_allowed(user_id):
        logger.warning(f"Access denied for user_id in /continue-session: {user_id}")
        raise HTTPException(status_code=403, detail=f"Access denied: User '{user_id}' is not in the allowed list")

    # Automatically determine if template matching should be used
    # If use_template is None (not specified), use LLM to auto-detect based on query complexity
    if use_template is None:
        use_template = should_use_template_matching(message, language=language.value)
        logger.info(f"LLM auto-detected template matching for continuation: {use_template} for query: {message[:100]}")

    # Check if multi-turn session exists in memory
    multiturn_session = queue_manager.multiturn_sessions.get(session_id)

    # If not in memory, try to load from cloud storage
    if not multiturn_session:
        try:
            print(f"[DEBUG /continue-session] Session {session_id} not in memory, loading from cloud...")
            unified_manager = get_unified_session_manager(queue_manager)
            cloud_session_data = await unified_manager.get_multiturn_session_by_id(session_id)

            if cloud_session_data:
                # DEBUG: Log what data we got from cloud
                print(f"[DEBUG /continue-session] Loaded session data from storage location: {cloud_session_data.get('_storage_location', 'unknown')}")
                if "turns" in cloud_session_data and isinstance(cloud_session_data["turns"], list):
                    print(f"[DEBUG /continue-session] Cloud data has {len(cloud_session_data['turns'])} turns:")
                    for t in cloud_session_data["turns"]:
                        turn_num = t.get("turn_number")
                        files = t.get("files", {})
                        tp_file = files.get("thinking_process", {}).get("filename", "NONE") if isinstance(files.get("thinking_process"), dict) else "NONE"
                        report_file = files.get("final_report", {}).get("filename", "NONE") if isinstance(files.get("final_report"), dict) else "NONE"
                        print(f"[DEBUG /continue-session]   Turn {turn_num}: TP={tp_file}, Report={report_file}")

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
                print(f"[DEBUG /continue-session] Session {session_id} restored to memory from cloud storage")
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

    # Handle files - could be UploadFile objects or strings (file paths)
    has_upload_files = files and any(
        (hasattr(file, 'filename') and file.filename) or (isinstance(file, str) and file)
        for file in files
    )

    if has_upload_files:
        # Create temporary upload directory for this session
        upload_dir = os.path.join(os.getcwd(), "temp_uploads", session_id)
        os.makedirs(upload_dir, exist_ok=True)

        for file in files:
            # Skip empty entries
            if isinstance(file, str):
                # File is already a path string - add directly if it exists
                if file and os.path.exists(file):
                    uploaded_file_paths.append(file)
                continue

            if not hasattr(file, 'filename') or not file.filename:
                continue

            # UploadFile object - read file content
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


@app.post("/plan-session")
async def plan_session(
    session_id: Optional[str] = Form(None),  # None for new session
    message: str = Form(...),
    language: Language = Form(Language.EN),
    user_id: str = Form(...),
    files: List[UploadFile] = File(default=[])
):
    """
    Planning/clarification endpoint - agent asks questions without tool execution

    This creates "planning" turns in the multi-turn session that will be included
    in context when execution starts.

    Args:
        session_id: Existing session ID (None for new session)
        message: User's message/question
        language: Response language (en/jp)
        user_id: User identifier
        files: Optional file uploads (stored but not analyzed yet)

    Returns:
        {
            "session_id": "abc123",
            "turn_session_id": "abc123_turn_1",
            "turn_number": 1,
            "turn_type": "planning",
            "status": "queued",
            "message": "Planning request queued"
        }
    """

    # Validate user_id
    if not user_id or user_id.strip() == "":
        raise HTTPException(status_code=400, detail="user_id is required")

    # Check if user is in the allowed list
    if not is_user_allowed(user_id):
        logger.warning(f"Access denied for user_id in /plan-session: {user_id}")
        raise HTTPException(status_code=403, detail=f"Access denied: User '{user_id}' is not in the allowed list")

    # Validate message
    if not message or message.strip() == "":
        raise HTTPException(status_code=400, detail="message is required")

    try:
        # Check if this is a new session or continuation
        if session_id:
            # Continue existing session in planning mode
            multiturn_session = queue_manager.multiturn_sessions.get(session_id)

            if not multiturn_session:
                # Try to load from cloud storage
                unified_manager = get_unified_session_manager(queue_manager)
                cloud_session_data = await unified_manager.get_multiturn_session_by_id(session_id)

                if not cloud_session_data:
                    raise HTTPException(status_code=404, detail="Session not found")

                # Verify user ownership
                if cloud_session_data.get("user_id") != user_id:
                    raise HTTPException(status_code=403, detail="Access denied")

                # Restore session to memory
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
                            turn_type=turn_data.get("turn_type", "execution"),
                            query=turn_data.get("query", ""),
                            final_report=turn_data.get("final_report"),
                            response_content=turn_data.get("response_content"),
                            files=turn_data.get("files"),
                            timestamp=turn_data.get("timestamp", datetime.now().isoformat()),
                            status=turn_data.get("status", "completed"),
                            ready_for_execution=turn_data.get("ready_for_execution")
                        )
                        multiturn_session.turns.append(turn)

                # Add back to in-memory sessions
                queue_manager.multiturn_sessions[session_id] = multiturn_session
                print(f"Restored session {session_id} from cloud storage for planning")
            else:
                # Verify user ownership for in-memory session
                if multiturn_session.user_id and multiturn_session.user_id != user_id:
                    raise HTTPException(status_code=403, detail="Access denied")

            # Add new planning turn
            turn_number = queue_manager.add_turn_to_session(session_id, message)

        else:
            # Create new session starting with planning
            session_id = str(uuid.uuid4())
            turn_number = 1

            # Create new multi-turn session
            multiturn_session = MultiTurnSession(
                session_id=session_id,
                user_id=user_id,
                language=language,
                created_at=datetime.now().isoformat(),
                last_updated=datetime.now().isoformat(),
                session_name=message[:50] + ("..." if len(message) > 50 else ""),
                total_turns=0,
                current_turn=0
            )
            queue_manager.multiturn_sessions[session_id] = multiturn_session

            # Add first turn
            turn_number = queue_manager.add_turn_to_session(session_id, message)

        # Handle file uploads (if any)
        uploaded_file_paths = []
        if files and any(file.filename for file in files):
            session_dir = os.path.join(os.getcwd(), "chat_sessions", session_id)
            os.makedirs(session_dir, exist_ok=True)

            for file in files:
                if file.filename:
                    file_path = os.path.join(session_dir, file.filename)
                    with open(file_path, "wb") as f:
                        content = await file.read()
                        f.write(content)
                    uploaded_file_paths.append(file_path)
                    logger.info(f"Saved file for planning: {file.filename}")

        # Build planning context (simpler than execution context)
        planning_context = ""
        if multiturn_session.turns:
            # Include previous planning turns for context
            for turn in multiturn_session.turns[:-1]:  # Exclude current turn
                planning_context += f"\nUser: {turn.query}"
                if turn.final_report:
                    planning_context += f"\nAssistant: {turn.final_report}"

        # Create user request with planning configuration
        turn_session_id = f"{session_id}_turn_{turn_number}"
        user_request = UserRequest(
            session_id=turn_session_id,
            message=message,
            language=language,
            uploaded_files=uploaded_file_paths,
            is_continuation=(turn_number > 1),
            previous_context=planning_context,
            turn_number=turn_number,
            user_id=user_id,
            turn_type="planning"  # Mark as planning turn
        )

        # Set planning agent configuration
        user_request.agent_config = create_planning_agent(language.value)
        user_request.original_session_id = session_id

        # Add to queue
        position = queue_manager.add_request(user_request)

        return JSONResponse({
            "session_id": session_id,
            "turn_session_id": turn_session_id,
            "turn_number": turn_number,
            "turn_type": "planning",
            "status": "queued",
            "position": position,
            "message": "Planning request queued successfully"
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in plan_session: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/multiturn-session/{session_id}")
async def get_multiturn_session(session_id: str, user_id: str, include_thinking: bool = False):
    """Get complete multi-turn session history using Unified Session Manager

    Args:
        session_id: The session ID
        user_id: The user ID
        include_thinking: If True, includes thinking process (response_content) in each turn.
                         Default is False to reduce response size for sessions with many turns.
    """
    # Check if user is in the allowed list
    if not is_user_allowed(user_id):
        logger.warning(f"Access denied for user_id in /multiturn-session: {user_id}")
        raise HTTPException(status_code=403, detail=f"Access denied: User '{user_id}' is not in the allowed list")

    import time
    start_time = time.time()
    print(f"[PERF /multiturn-session] Started for session {session_id}")

    try:
        # Use Unified Session Manager to get session from any storage location
        step1_start = time.time()
        unified_manager = get_unified_session_manager(queue_manager)
        session = await unified_manager.get_multiturn_session_by_id(session_id)
        print(f"[PERF /multiturn-session] Step 1 (get_multiturn_session_by_id): {(time.time() - step1_start) * 1000:.2f} ms")

        if not session:
            raise HTTPException(status_code=404, detail="Multi-turn session not found")

        # Verify user owns this session
        session_user_id = session.get("user_id")
        if session_user_id and session_user_id != user_id:
            raise HTTPException(status_code=403, detail="Access denied: Session belongs to different user")

        # Handle in-memory sessions: Extract turns from _session_object
        if session.get("_storage_location") == "memory" and "_session_object" in session:
            session_obj = session["_session_object"]
            if hasattr(session_obj, 'turns'):
                # Convert MultiTurnSession object's turns to dict format
                session["turns"] = []
                for turn in session_obj.turns:
                    turn_dict = {
                        "turn_number": turn.turn_number,
                        "turn_type": turn.turn_type,
                        "query": turn.query,
                        "final_report": turn.final_report,
                        "timestamp": turn.timestamp,
                        "status": turn.status,
                        "files": turn.files if hasattr(turn, 'files') else {}
                    }
                    if include_thinking and hasattr(turn, 'response_content'):
                        turn_dict["response_content"] = turn.response_content
                    session["turns"].append(turn_dict)

        # Process turns: generate URLs and optionally exclude thinking process
        step2_start = time.time()
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

                    # If local files are missing, try to get S3 files from cloud
                    # Use turn-specific session ID for turn 2+ to get correct images
                    turn_num = turn.get("turn_number", 1)
                    turn_session_id_for_cloud = f"{session_id}_turn_{turn_num}" if turn_num > 1 else session_id

                    if has_missing_files:
                        try:
                            cloud_fetch_start = time.time()
                            turn_cloud_session = await cloud_storage_manager.retrieve_session_from_cloud(turn_session_id_for_cloud)
                            print(f"[PERF /multiturn-session] Cloud fetch for turn {turn_num}: {(time.time() - cloud_fetch_start) * 1000:.2f} ms")
                            if turn_cloud_session:
                                print(f"Local files missing for turn {turn_num}, fetched S3 files from cloud storage")

                                # Merge S3 files into turn files
                                if "s3_files" in turn_cloud_session:
                                    s3_files = turn_cloud_session["s3_files"]
                                    if isinstance(s3_files, dict) and isinstance(turn["files"], dict):
                                        # Only merge keys that don't exist in turn files
                                        for key, value in s3_files.items():
                                            if key not in turn["files"]:
                                                turn["files"][key] = value
                                    elif not turn["files"]:
                                        # If turn has no files at all, use s3_files
                                        turn["files"] = s3_files
                        except Exception as e:
                            print(f"Warning: Could not retrieve S3 files from cloud for turn {turn_num}: {e}")

                    # Use turn-specific session ID for URL generation (turn 2+ use {session_id}_turn_N)
                    turn_num = turn.get("turn_number", 1)
                    turn_session_id = f"{session_id}_turn_{turn_num}" if turn_num > 1 else session_id

                    turn["files"] = generate_file_urls(turn["files"], turn_session_id)

                    # For existing data: if turn_zip exists, use it as session_zip (for backwards compatibility)
                    if isinstance(turn["files"], dict):
                        if "turn_zip" in turn["files"] and turn["files"]["turn_zip"]:
                            # Prefer turn_zip over session_zip for turn-specific downloads
                            turn["files"]["session_zip"] = turn["files"]["turn_zip"]
                        elif "session_zip" in turn["files"]:
                            session_zips = turn["files"]["session_zip"]
                            # Handle session_zip being a list (from cloud storage)
                            if isinstance(session_zips, list) and len(session_zips) > 0:
                                # Find the zip for this specific turn
                                turn_zip_pattern = f"_turn_{turn_num}.zip"
                                matching_zip = None
                                for zip_item in session_zips:
                                    if isinstance(zip_item, dict):
                                        filename = zip_item.get("filename", "")
                                        if turn_zip_pattern in filename:
                                            matching_zip = zip_item
                                            break
                                # If no turn-specific zip found for turn 1, use one without _turn_ suffix
                                if not matching_zip and turn_num == 1:
                                    for zip_item in session_zips:
                                        if isinstance(zip_item, dict):
                                            filename = zip_item.get("filename", "")
                                            if "_turn_" not in filename:
                                                matching_zip = zip_item
                                                break
                                # If still no match, use the last item as fallback
                                if not matching_zip:
                                    matching_zip = session_zips[-1]
                                # Replace list with the single matching zip
                                turn["files"]["session_zip"] = matching_zip

                    # Append images and download links to final_report (same as /results endpoint)
                    if "final_report" in turn and turn["files"]:
                        turn["final_report"] = append_images_to_report(turn["final_report"], turn["files"])

                # Remove thinking process unless explicitly requested
                if not include_thinking:
                    # Remove response_content (thinking process) to reduce payload size
                    turn.pop("response_content", None)
                    # Keep final_report as it's the main output

            print(f"[PERF /multiturn-session] Step 2 (process turns & generate URLs): {(time.time() - step2_start) * 1000:.2f} ms")

        print(f"[PERF /multiturn-session] TOTAL TIME: {(time.time() - start_time) * 1000:.2f} ms")
        return session

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error getting multiturn session: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error retrieving session: {str(e)}")

@app.get("/multiturn-sessions")
async def get_all_multiturn_sessions(
    user_id: Optional[str] = None,
    limit: int = 10,
    offset: int = 0
):
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
                "message": "Please provide a valid user_id"
            }

        # Check if user is in the allowed list
        if not is_user_allowed(user_id):
            logger.warning(f"Access denied for user_id in /multiturn-sessions: {user_id}")
            raise HTTPException(status_code=403, detail=f"Access denied: User '{user_id}' is not in the allowed list")

        # Get unified session manager
        unified_manager = get_unified_session_manager(queue_manager)

        # Get multi-turn sessions with pagination
        result = await unified_manager.get_multiturn_sessions(
            include_cloud=True,
            user_id=user_id,
            limit=limit,
            offset=offset
        )

        return result
    except Exception as e:
        print(f"Error getting multi-turn sessions: {e}")
        import traceback
        traceback.print_exc()
        # Fallback to local-only sessions with pagination
        sessions = []
        for session_id, session in queue_manager.multiturn_sessions.items():
            session_summary = {
                "session_id": session_id,
                "created_at": session.created_at,
                "last_updated": session.last_updated,
                "total_turns": session.total_turns,
                "language": session.language,
                "session_status": session.session_status,
                "first_query": session.turns[0].query if session.turns else "No queries",
                "latest_query": session.turns[-1].query if session.turns else "No queries",
                "_storage_location": "local"
            }
            sessions.append(session_summary)

        # Sort and paginate fallback sessions
        sessions.sort(key=lambda x: x.get('last_updated', x.get('created_at', '')), reverse=True)
        total = len(sessions)
        paginated = sessions[offset:offset + limit]

        return {
            "sessions": paginated,
            "total": total,
            "limit": limit,
            "offset": offset
        }

@app.get("/turn-report/{session_id}/{turn_number}")
async def get_turn_report(session_id: str, turn_number: int, user_id: str):
    """Get specific turn report from multi-turn session"""
    # Check if user is in the allowed list
    if not is_user_allowed(user_id):
        logger.warning(f"Access denied for user_id in /turn-report: {user_id}")
        raise HTTPException(status_code=403, detail=f"Access denied: User '{user_id}' is not in the allowed list")

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
                "status": turn.status
            }

    raise HTTPException(status_code=404, detail=f"Turn {turn_number} not found in session")

@app.get("/session-context/{session_id}")
async def get_session_context(session_id: str, user_id: str):
    """Get accumulated context for a multi-turn session"""
    # Check if user is in the allowed list
    if not is_user_allowed(user_id):
        logger.warning(f"Access denied for user_id in /session-context: {user_id}")
        raise HTTPException(status_code=403, detail=f"Access denied: User '{user_id}' is not in the allowed list")

    multiturn_session = queue_manager.multiturn_sessions.get(session_id)
    if not multiturn_session:
        raise HTTPException(status_code=404, detail="Multi-turn session not found")

    # Verify user owns this session
    if multiturn_session.user_id and multiturn_session.user_id != user_id:
        raise HTTPException(status_code=403, detail="Access denied: Session belongs to different user")

    return {
        "session_id": session_id,
        "accumulated_context": multiturn_session.accumulated_context,
        "total_turns": multiturn_session.total_turns
    }

# ============= SESSION SHARING ENDPOINTS =============

@app.post("/share-session")
async def share_session(request: ShareSessionRequest):
    """Share a multi-turn session with the community"""
    # Check if user is in the allowed list
    if request.user_id and not is_user_allowed(request.user_id):
        logger.warning(f"Access denied for user_id in /share-session: {request.user_id}")
        raise HTTPException(status_code=403, detail=f"Access denied: User '{request.user_id}' is not in the allowed list")

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

@app.post("/unshare-session")
async def unshare_session(session_id: str, user_id: str):
    """Remove a session from community sharing"""
    # Check if user is in the allowed list
    if not is_user_allowed(user_id):
        logger.warning(f"Access denied for user_id in /unshare-session: {user_id}")
        raise HTTPException(status_code=403, detail=f"Access denied: User '{user_id}' is not in the allowed list")

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

@app.get("/shared-sessions")
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

@app.post("/rename-multisession")
async def rename_multisession(request: RenameMultiSessionRequest):
    """Rename a multi-turn session using Unified Session Manager"""
    # Check if user is in the allowed list
    if not is_user_allowed(request.user_id):
        logger.warning(f"Access denied for user_id in /rename-multisession: {request.user_id}")
        raise HTTPException(status_code=403, detail=f"Access denied: User '{request.user_id}' is not in the allowed list")

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
                session_id=session_id,
                updates=updates,
                user_id=user_id
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
                "timing": {
                    "total_ms": round(total_time, 2),
                    "update_ms": round(update_time, 2)
                }
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

@app.post("/upload-template")
async def upload_template(request: TemplateListRequest):
    """Upload workflow templates to MongoDB"""
    try:
        from s3_mongodb.func_mongodb import (get_mongodb_collection,
                                             upsert_wrapper)

        # Get MongoDB collection
        collection = get_mongodb_collection(
            os.getenv("SESSION_DB_NAME", "dleader_agent"),
            "workflow_templates"
        )

        if collection is None:
            raise HTTPException(status_code=503, detail="MongoDB connection not available")

        # Prepare templates for MongoDB
        templates_to_upload = []
        for template in request.templates:
            template_data = template.dict()
            # Use title as _id for easy upsert
            template_data["_id"] = template.title
            template_data["uploaded_at"] = datetime.now().isoformat()
            templates_to_upload.append(template_data)

        # Upsert templates to MongoDB
        event = {
            "database_name": os.getenv("SESSION_DB_NAME", "dleader_agent"),
            "collection_name": "workflow_templates",
            "items": templates_to_upload,
            "id_field": "_id"
        }

        result = upsert_wrapper(event)

        if result.get("statusCode") != 200:
            raise Exception(f"MongoDB upsert failed: {result}")

        # Also save to local as backup
        templates_dir = os.path.join(os.getcwd(), "templates")
        os.makedirs(templates_dir, exist_ok=True)
        templates_file = os.path.join(templates_dir, "workflow_templates.json")
        templates_data = {"templates": [template.dict() for template in request.templates]}
        with open(templates_file, 'w', encoding='utf-8') as f:
            json.dump(templates_data, f, ensure_ascii=False, indent=2)

        return TemplateResponse(
            success=True,
            message="Templates uploaded successfully to MongoDB",
            total_templates=len(request.templates)
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error uploading templates: {e}")
        raise HTTPException(status_code=500, detail=f"Error uploading templates: {str(e)}")

@app.get("/templates")
async def get_templates():
    """Get all workflow templates from MongoDB"""
    try:
        from s3_mongodb.func_mongodb import get_mongodb_collection

        # Try to get from MongoDB first
        collection = get_mongodb_collection(
            os.getenv("SESSION_DB_NAME", "dleader_agent"),
            "workflow_templates"
        )

        if collection is not None:
            templates = list(collection.find({}).sort("title", 1))
            # Remove MongoDB _id field from response
            for template in templates:
                if "_id" in template:
                    template.pop("_id", None)
                if "uploaded_at" in template:
                    template.pop("uploaded_at", None)

            return {
                "templates": templates,
                "total": len(templates),
                "source": "mongodb"
            }

        # Fallback to local file if MongoDB not available
        templates_file = os.path.join(os.getcwd(), "templates", "workflow_templates.json")
        if not os.path.exists(templates_file):
            return {"templates": [], "total": 0, "source": "none"}

        with open(templates_file, 'r', encoding='utf-8') as f:
            templates_data = json.load(f)

        return {
            "templates": templates_data.get("templates", []),
            "total": len(templates_data.get("templates", [])),
            "source": "local_backup"
        }

    except Exception as e:
        print(f"Error retrieving templates: {e}")
        raise HTTPException(status_code=500, detail=f"Error retrieving templates: {str(e)}")

@app.get("/health")
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

@app.get("/user/{user_id}/name")
async def get_user_name(user_id: str):
    """
    Get username for a given user_id.
    Returns the user_id as the default name if no custom name is set.

    Args:
        user_id: The user identifier

    Returns:
        JSON with username (defaults to user_id if not set)
    """
    if not user_id or user_id.strip() == "":
        raise HTTPException(status_code=400, detail="user_id is required and cannot be empty")

    # Check if user is in the allowed list
    if not is_user_allowed(user_id):
        logger.warning(f"Access denied for user_id in /user/name (GET): {user_id}")
        raise HTTPException(status_code=403, detail=f"Access denied: User '{user_id}' is not in the allowed list")

    try:
        # Import MongoDB functions
        from s3_mongodb.func_mongodb import get_mongodb_collection

        # Get users collection
        users_collection = get_mongodb_collection(
            os.getenv("SESSION_DB_NAME", "dleader_agent"),
            "users"
        )

        if users_collection is None:
            # If MongoDB is not available, return user_id as default
            return {
                "user_id": user_id,
                "username": user_id,
                "source": "default"
            }

        # Find user in MongoDB
        user_doc = users_collection.find_one({"_id": user_id})

        if user_doc and "username" in user_doc:
            return {
                "user_id": user_id,
                "username": user_doc["username"],
                "source": "mongodb"
            }
        else:
            # No custom name set, return user_id as default
            return {
                "user_id": user_id,
                "username": user_id,
                "source": "default"
            }

    except Exception as e:
        logger.error(f"Error retrieving username for {user_id}: {e}")
        # On error, return user_id as fallback
        return {
            "user_id": user_id,
            "username": user_id,
            "source": "error_fallback"
        }

@app.put("/user/{user_id}/name")
async def update_user_name(user_id: str, request: Request):
    """
    Update username for a given user_id.

    Args:
        user_id: The user identifier
        request: Request body containing {"username": "new_name"}

    Returns:
        JSON with updated username
    """
    if not user_id or user_id.strip() == "":
        raise HTTPException(status_code=400, detail="user_id is required and cannot be empty")

    # Check if user is in the allowed list
    if not is_user_allowed(user_id):
        logger.warning(f"Access denied for user_id in /user/name (PUT): {user_id}")
        raise HTTPException(status_code=403, detail=f"Access denied: User '{user_id}' is not in the allowed list")

    try:
        # Parse request body
        body = await request.json()
        new_username = body.get("username", "").strip()

        if not new_username:
            raise HTTPException(status_code=400, detail="username is required and cannot be empty")

        # Import MongoDB functions
        from s3_mongodb.func_mongodb import get_mongodb_collection

        # Get users collection
        users_collection = get_mongodb_collection(
            os.getenv("SESSION_DB_NAME", "dleader_agent"),
            "users"
        )

        if users_collection is None:
            raise HTTPException(status_code=503, detail="Database unavailable")

        # Upsert user document with new username
        result = users_collection.update_one(
            {"_id": user_id},
            {
                "$set": {
                    "username": new_username,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                },
                "$setOnInsert": {
                    "created_at": datetime.now(timezone.utc).isoformat()
                }
            },
            upsert=True
        )

        return {
            "user_id": user_id,
            "username": new_username,
            "updated": result.modified_count > 0,
            "created": result.upserted_id is not None,
            "message": "Username updated successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating username for {user_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Error updating username: {str(e)}")

# ============= TRASH SYSTEM ENDPOINTS =============
# Most trash management endpoints have been moved to trash_api.py
# Only hard-delete remains here as it's a direct operation

# Import and include the trash router
from trash_api import router as trash_router

app.include_router(trash_router)

@app.delete("/hard-delete/{session_id}")
async def hard_delete_session(session_id: str, user_id: str, confirm: bool = False):
    """
    Hard delete - Immediately and permanently delete a session without moving to trash
    This action cannot be undone!
    """
    # Validate user_id
    if not user_id or user_id.strip() == "":
        raise HTTPException(status_code=400, detail="user_id is required and cannot be empty")

    # Check if user is in the allowed list
    if not is_user_allowed(user_id):
        logger.warning(f"Access denied for user_id in /hard-delete: {user_id}")
        raise HTTPException(status_code=403, detail=f"Access denied: User '{user_id}' is not in the allowed list")

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


@app.get("/download-urls/{session_id}")
async def get_session_download_urls(session_id: str, user_id: str, turn_number: Optional[int] = None):
    """Get download URLs for session files (always prefer S3/cloud)

    Args:
        session_id: The session ID
        user_id: The user ID
        turn_number: Optional turn number to retrieve files for. If not provided, returns current/latest turn files.
    """
    # Check if user is in the allowed list
    if not is_user_allowed(user_id):
        logger.warning(f"Access denied for user_id in /download-urls: {user_id}")
        raise HTTPException(status_code=403, detail=f"Access denied: User '{user_id}' is not in the allowed list")

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

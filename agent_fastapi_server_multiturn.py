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
from fastapi import (FastAPI, File, Form, HTTPException, UploadFile, WebSocket,
                     WebSocketDisconnect, Request)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware

# Add current directory to path for imports
sys.path.insert(0, os.getcwd())

# Import cloud storage manager
from cloud_storage_manager import cloud_storage_manager
from dleader_agent.agent.a1 import A1
# Import enhanced multi-turn handler
from enhanced_multiturn_handler import EnhancedMultiTurnHandler
# Import unified session manager
from unified_session_manager import get_unified_session_manager

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

class SessionInfo(BaseModel):
    session_id: str
    status: str
    created_at: str
    language: Language
    query: str

# Multi-Turn Data Structures
class ConversationTurn(BaseModel):
    turn_number: int
    query: str
    response_content: Optional[str] = None
    final_report: Optional[str] = None
    files: Optional[Dict[str, Any]] = None  # Changed to Any to support richer file metadata
    timestamp: str
    status: str = "processing"

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
                 is_continuation: bool = False, previous_context: str = "", turn_number: int = 1, user_id: str = None):
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
        self.session_path = None  # Store session path for JSON updates
        self.all_progress_updates = []  # Store all progress updates permanently
        self.user_id = user_id  # User ownership tracking
        self.task_start_time = None  # Track when task actually starts processing
        self.stop_requested = False  # Flag to signal stop request

        # Multi-turn specific attributes
        self.is_continuation = is_continuation
        self.previous_context = previous_context
        self.turn_number = turn_number
        self.enhanced_message = self._build_enhanced_message()

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
    def __init__(self):
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

        # Load existing sessions from storage
        self._load_sessions_from_storage()
        # Note: Multi-turn sessions are now loaded from MongoDB on-demand, not from local files
        # self._load_multiturn_sessions()  # REMOVED: No longer loading from local JSON files

        # Start the queue processor
        self.processor_thread = threading.Thread(target=self._process_queue, daemon=True)
        self.processor_thread.start()
    
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
                return QueueStatus(position=0, estimated_wait_time=0, total_users_in_queue=self.request_queue.qsize())
            
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
                # Estimate 2 minutes per request
                estimated_wait = position * 120
                return QueueStatus(
                    position=position, 
                    estimated_wait_time=estimated_wait,
                    total_users_in_queue=self.request_queue.qsize()
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
                "user_id": getattr(user_request, 'user_id', None)  # Include user_id for security
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

    def create_json_snapshot(self, user_request: UserRequest, accumulated_thinking: str = "", session_path: str = "") -> dict:
        """Create a JSON snapshot of current progress"""
        # Collect image files from session if path exists
        image_files = []
        if session_path and os.path.exists(session_path):
            image_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.svg', '.webp'}
            for file in os.listdir(session_path):
                if any(file.lower().endswith(ext) for ext in image_extensions):
                    image_files.append(os.path.join(session_path, file))

        # Clean the thinking content to show only original user message
        cleaned_thinking = self._clean_thinking_content(accumulated_thinking, user_request.message)

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

    def stop_session(self, session_id: str) -> bool:
        """Stop a running or queued session"""
        with self.processing_lock:
            if session_id not in self.active_sessions:
                return False

            user_request = self.active_sessions[session_id]

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

            # Move any generated files to session folder to keep workspace clean
            self._move_generated_files_to_session(user_request)

            # Save cancelled session state to storage and trigger cloud upload
            self._save_session_to_storage(user_request)

            # Ensure S3 upload for cancelled session
            self._trigger_s3_upload_for_session(user_request)

            return True

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

    def _load_session_from_storage(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Load session data from persistent storage"""
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
        except Exception as e:
            print(f"Error loading session {session_id} from storage: {e}")
            return None

    def _load_sessions_from_storage(self):
        """Load all existing sessions from storage on startup"""
        try:
            if not os.path.exists(self.sessions_storage_dir):
                return

            for filename in os.listdir(self.sessions_storage_dir):
                if filename.endswith('.json'):
                    session_id = filename[:-5]  # Remove .json extension
                    try:
                        session_data = self._load_session_from_storage(session_id)
                        if session_data and not session_data.get("is_complete", False):
                            # Only load incomplete sessions back into active sessions
                            # Complete sessions will be loaded on-demand
                            pass
                    except Exception as e:
                        print(f"Error loading session {session_id} on startup: {e}")
        except Exception as e:
            print(f"Error loading sessions from storage: {e}")

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
            from s3_mongodb.func_mongodb import get_mongodb_collection
            from s3_mongodb.mongodb_upsert import upsert_wrapper

            # Prepare session data for MongoDB
            session_data = session.dict()
            session_data["_id"] = session.session_id
            session_data["last_updated"] = datetime.now().isoformat()

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
                    # Remove MongoDB _id field
                    session_data.pop("_id", None)
                    session_data.pop("uploaded_to_cloud_at", None)
                    session = MultiTurnSession(**session_data)
                    self.multiturn_sessions[session_id] = session
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
                     final_report: str, files: Dict[str, str]):
        """Complete a turn with results"""
        session = self.multiturn_sessions.get(session_id)
        if not session:
            return

        # Find the turn and update it
        for turn in session.turns:
            if turn.turn_number == turn_number:
                turn.response_content = response_content
                turn.final_report = final_report

                # Enhanced file tracking with metadata
                if files:
                    # Convert simple file paths to richer metadata
                    enhanced_files = {}
                    for file_name, file_path in (files.items() if isinstance(files, dict) else enumerate(files)):
                        if isinstance(file_path, str):
                            file_metadata = {
                                'path': file_path,
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

        # Upload updated multi-turn session to cloud storage
        try:
            multiturn_session_data = {
                "session_id": session.session_id,
                "created_at": session.created_at,
                "last_updated": session.last_updated,
                "total_turns": session.total_turns,
                "language": session.language,
                "user_id": getattr(session, 'user_id', None),
                "session_status": session.session_status,
                "first_query": session.first_query,
                "latest_query": session.latest_query,
                "turns": [
                    {
                        "turn_number": turn.turn_number,
                        "query": turn.query,
                        "response_content": turn.response_content,
                        "final_report": turn.final_report,
                        "files": turn.files,
                        "status": turn.status,
                        "created_at": turn.timestamp
                    } for turn in session.turns
                ]
            }
            # Upload to cloud asynchronously
            def upload_multiturn_in_thread():
                import asyncio
                try:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    loop.run_until_complete(cloud_storage_manager.upload_multiturn_session(multiturn_session_data))
                    loop.close()
                except Exception as e:
                    print(f"Background multiturn cloud upload failed for session {session_id}: {e}")

            upload_thread = threading.Thread(target=upload_multiturn_in_thread, daemon=True)
            upload_thread.start()
            print(f"Initiated cloud upload for multi-turn session {session_id}")
        except Exception as e:
            print(f"Failed to initiate cloud upload for multi-turn session {session_id}: {e}")

    def _process_queue(self):
        """Background thread to process queue requests"""
        while True:
            try:
                # Get next request from queue
                user_request = self.request_queue.get(timeout=1)
                
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
            start_time = time.time()
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
            
            # Set up streaming capture
            stream_capture = StreamingCapture()
            
            # Process with agent
            user_request.progress_queue.put({"type": "status", "message": "Agent processing started..."})
            
            def run_agent():
                try:
                    with redirect_stdout(stream_capture):
                        # Use the enhanced message with multi-turn context
                        base_message = user_request.enhanced_message

                        # Get list of files in session folder
                        available_files = []
                        if os.path.exists(session_path):
                            for filename in os.listdir(session_path):
                                file_path = os.path.join(session_path, filename)
                                if os.path.isfile(file_path) and not filename.startswith('.'):
                                    available_files.append(f"{filename} (Path: {file_path})")

                        # Enhance message based on language
                        if user_request.language == Language.JP:
                            file_list_msg = ""
                            if available_files:
                                file_list_msg = "\n\n利用可能なファイル:\n" + "\n".join([f"- {f}" for f in available_files])

                            enhanced_message = f"""{base_message}{file_list_msg}

注意: アップロードされたファイルは次の作業フォルダに保存されています: {session_path} ファイルを生成あるいは保存する場合は、作業フォルダに保存してください。コメントはできるだけ日本語で記述し、最終レポートも日本語で作成すること。 use plt.rcParams['font.family'] = ['Noto Sans CJK JP', 'DejaVu Sans' ] when plot
重要 - 深い思考と洞察のガイドライン:
あなたの役割は、直接的な質問への回答を超えて、深く思考し価値ある洞察を提供することです。以下を心がけてください：
- 常により広範な含意と潜在的な改善点を考慮する
- データ分析（分子特性、データセットなど）では、違いやパターンを示すためのプロットや可視化を作成する
- 結果をどのように最適化または改善できるかについて一歩先まで考える
- 分析に基づいて実行可能な洞察と推奨事項を提供する

重要 - 分子解析の必須要件:
分子や化学化合物を扱う際は、以下を必ず実行してください：
- RDKit、py3Dmol等のツールを使用して分子構造をプロットし可視化する
- 重要な官能基や構造的特徴を視覚的に強調表示する
- 化合物間の違いを示す比較分子プロットを作成する
- 重要な構造要素を強調するためにカラーコーディングと注釈を使用する
- 官能基をハイライトした2D分子図を生成する
- 結合や相互作用の理解に関連する場合は3D分子可視化を作成する
- 分子特性分布（分子量、LogP、極性表面積など）をプロットする
- 分子プロットを通じて構造活性相関を可視化する
- 例：薬物分子を分析する場合：
  * 官能基を色分けした分子構造をプロットする
  * 活性化合物と非活性化合物の比較オーバーレイプロットを作成する
  * 結合部位と分子相互作用を可視化する
  * ファーマコフォア特徴と重要な構造モチーフをハイライトする"""
                        else:
                            file_list_msg = ""
                            if available_files:
                                file_list_msg = "\n\nAvailable files in your working directory:\n" + "\n".join([f"- {f}" for f in available_files])

                            enhanced_message = f"""{base_message}{file_list_msg}

Note: The uploaded files are stored in the folder: {session_path}. If saving file, also save in it, it is the working folder.
IMPORTANT - Enhanced Thinking and Insight Guidelines:
Your role is to think deeply and provide valuable insights beyond just answering the direct question. You should:
- Always consider the broader implications and potential improvements
- When analyzing data (e.g., molecular features, datasets), create visualizations and plots to show differences and patterns
- Think one step further about how results could be optimized or improved
- Provide actionable insights and recommendations based on your analysis

CRITICAL - Molecular Analysis Requirements:
When working with molecules or chemical compounds, you MUST:
- Plot and visualize molecular structures using tools like RDKit, py3Dmol, or similar libraries
- Highlight important functional groups and structural features visually
- Create comparative molecular plots showing differences between compounds
- Use color coding and annotations to emphasize key structural elements
- Generate 2D molecular diagrams with functional group highlighting
- Create 3D molecular visualizations when relevant for understanding binding or interactions
- Plot molecular property distributions (MW, LogP, polar surface area, etc.)
- Visualize structure-activity relationships through molecular plots
- For example, if analyzing drug molecules:
  * Plot molecular structures with functional groups color-coded
  * Create overlay plots comparing active vs inactive compounds
  * Visualize binding sites and molecular interactions
  * Highlight pharmacophore features and important structural motifs

🚨 CRITICAL REQUIREMENT - SAVING PLOTS AND FILES 🚨
- YOU MUST SAVE ALL PLOTS TO FILES - THIS IS ABSOLUTELY MANDATORY
- REPLACE plt.show() WITH plt.savefig() - ALWAYS!
- STEP-BY-STEP PROCESS FOR EVERY PLOT:
  1. Create your plot with plt.figure() or plt.subplots()
  2. Add your data and formatting
  3. SAVE the plot: plt.savefig('filename.svg', format='svg', bbox_inches='tight')
  4. Close the plot: plt.close()
  5. Verify file exists: print(f"Plot saved: {os.path.exists('filename.svg')}")

- NEVER EVER use plt.show() - it only displays but DOES NOT SAVE files
- ALWAYS use plt.savefig() or fig.savefig() to SAVE plots to files
- REPLACE any plt.show() with plt.savefig('descriptive_name.svg', format='svg', bbox_inches='tight')

- FORMAT EXAMPLES:
  * JPG for all charts/graphs: plt.savefig('molecular_structures.jpg', format='jpeg', dpi=300, bbox_inches='tight')
  * PNG only for transparency: plt.savefig('overlay_plot.png', format='png', dpi=300, bbox_inches='tight', transparent=True)

- MANDATORY VERIFICATION: After plt.savefig(), ALWAYS check:
  print(f"File saved successfully: {os.path.exists('your_filename.svg')}")

- THE USER CANNOT SEE plt.show() - THEY NEED SAVED FILES!"""
#   * SVG for all charts/graphs: plt.savefig('tpsa_pesticide_analysis.svg', format='svg', bbox_inches='tight')
                        _, result = agent.go(enhanced_message)
                        user_request.result = result
                except Exception as e:
                    import traceback

                    # Get detailed traceback information
                    tb_str = traceback.format_exc()
                    error_details = f"Agent execution error: {str(e)}\n\nFull traceback:\n{tb_str}"
                    user_request.error = error_details
                    print(f"Detailed agent error for session {user_request.session_id}:\n{error_details}")
            
            # Use process-based execution for true termination capability
            # Create multiprocessing queues for communication
            message_queue = MPQueue()
            result_queue = MPQueue()

            # Store queues in user_request
            user_request.process_queue = result_queue

            # Create and start process
            agent_process = Process(
                target=run_agent_in_process,
                args=(message_queue, result_queue, user_request.enhanced_message, session_path)
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
                                # Delete old snapshot files
                                for file in os.listdir(session_path):
                                    if file.startswith('snapshot_') and file.endswith('.json'):
                                        os.remove(os.path.join(session_path, file))

                                # Save new snapshot
                                snapshot_filename = f"snapshot_latest_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                                snapshot_path = os.path.join(session_path, snapshot_filename)
                                with open(snapshot_path, 'w', encoding='utf-8') as f:
                                    json.dump(snapshot, f, indent=2, ensure_ascii=False)

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
                    if '<solution>' in raw_result and '</solution>' in raw_result:
                        start_idx = raw_result.find('<solution>') + len('<solution>')
                        end_idx = raw_result.find('</solution>')
                        solution_content = raw_result[start_idx:end_idx].strip()
                    else:
                        solution_content = raw_result

                    final_report_content = f"## ✅ Final Report\n\n{solution_content}"

                with open(report_path, 'w', encoding='utf-8') as f:
                    f.write(final_report_content)

                # Save thinking process (cleaned version)
                cleaned_thinking = queue_manager._clean_thinking_content(accumulated_thinking, user_request.message)
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
                image_files = []
                image_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.svg', '.webp'}
                for file in os.listdir(session_path):
                    if any(file.lower().endswith(ext) for ext in image_extensions):
                        image_files.append(os.path.join(session_path, file))

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

            # Create session zip file and save to chat_zips
            try:
                zip_file_path = create_session_zip(session_path, save_to_chat_zips=True)
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
            except Exception as e:
                print(f"Error creating session zip: {e}")
            
            # Mark as complete
            user_request.status = "completed"
            user_request.is_complete = True

            # Move any generated files to session folder to keep workspace clean
            queue_manager._move_generated_files_to_session(user_request)

            # Trigger S3 upload for completed session
            queue_manager._trigger_s3_upload_for_session(user_request)

            # Clean thinking content for completion update
            cleaned_thinking = queue_manager._clean_thinking_content(accumulated_thinking, user_request.message)
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
                print(f"Initiated cloud upload for session {user_request.session_id}")
            except Exception as e:
                print(f"Failed to initiate cloud upload for session {user_request.session_id}: {e}")

            # Update multi-turn session if this is a turn
            if hasattr(user_request, 'original_session_id') and user_request.original_session_id:
                # Get file paths for the turn
                files_dict = {
                    'report_md': report_path,
                    'thinking_process': thinking_path,
                    'query_file': query_path,
                    'session_zip': zip_file_path,
                    'result_json': json_path
                }

                # Complete the turn in multi-turn session
                queue_manager.complete_turn(
                    user_request.original_session_id,
                    user_request.turn_number,
                    cleaned_thinking,
                    final_report_content,
                    files_dict
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
def run_agent_in_process(message_queue: MPQueue, result_queue: MPQueue, enhanced_message: str, session_path: str):
    """
    Run agent in a separate process for true termination capability
    This function runs in a separate process and communicates via queues
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

            # Create agent
            from agent_fastapi_server_multiturn import create_agent
            agent = create_agent()

            # Send status
            result_queue.put({
                "type": "status",
                "content": "Agent initialized, processing message..."
            })

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

            # Send final result with complete output
            result_queue.put({
                "type": "result",
                "content": result,
                "output": final_output
            })

            # Send final snapshot
            result_queue.put({
                "type": "final_snapshot",
                "content": final_output,
                "result": result,
                "timestamp": time.time()
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


def create_session_zip(session_path, save_to_chat_zips=True):
    """Create a zip file containing all session content and optionally save to chat_zips"""
    if not os.path.exists(session_path):
        return None

    try:
        session_name = os.path.basename(session_path)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        # Create chat_zips directory if saving there
        if save_to_chat_zips:
            chat_zips_dir = os.path.join(os.getcwd(), "chat_zips")
            os.makedirs(chat_zips_dir, exist_ok=True)

            # Create zip file in chat_zips directory
            zip_filename = f"{session_name}_{timestamp}.zip"
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


def create_agent():
    """Create an agent configured for tasks"""
    agent = A1(
        use_tool_retriever=True,
        download_data_lake=False,
        llm='claude-sonnet-4-20250514'
    )
    return agent

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
    files: List[UploadFile] = File(default=[])
):
    """Add chat request to queue with S3 file uploads"""
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
        user_id=user_id
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
async def get_status(session_id: str, user_id: str):
    """Get current status and progress for a session from local or cloud storage"""
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

@app.get("/download/{session_id}")
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


@app.get("/results/{session_id}")
async def get_session_results(session_id: str, user_id: str):
    """Get structured JSON results for a completed session"""
    # Validate user_id
    if not user_id or user_id.strip() == "":
        raise HTTPException(status_code=400, detail="user_id is required and cannot be empty")

    # Use unified session manager to check both local and cloud storage
    unified_manager = get_unified_session_manager(queue_manager)
    session_data = await unified_manager.get_session_by_id(session_id)

    if not session_data:
        raise HTTPException(status_code=404, detail="Session not found")

    # Verify user owns this session
    session_user_id = session_data.get("user_id")
    if session_user_id and session_user_id != user_id:
        raise HTTPException(status_code=403, detail="Access denied: Session belongs to different user")

    if not session_data.get("is_complete", False):
        raise HTTPException(status_code=400, detail="Session is not yet complete")

    # For cloud sessions, retrieve from MongoDB
    storage_location = session_data.get("_storage_location", "unknown")
    if storage_location == "cloud":
        # Get full session data from cloud
        cloud_session = await cloud_storage_manager.retrieve_session_from_cloud(session_id)
        if cloud_session:
            # Return structured result with thinking_process and final_report
            return {
                "session_id": session_id,
                "status": cloud_session.get("status", "completed"),
                "content": {
                    "thinking_content": cloud_session.get("thinking_process", ""),
                    "final_report": cloud_session.get("final_report", "")
                },
                "s3_files": cloud_session.get("s3_files", {}),
                "result_summary": cloud_session.get("result_summary", {})
            }

    # For local/active sessions, use existing json_result
    json_result = session_data.get("json_result")
    if not json_result:
        # Session completed but no JSON result (possibly old session or error)
        return {
            "session_id": session_id,
            "status": session_data.get("status", "unknown"),
            "error": "No structured results available for this session",
            "legacy_result": {
                "result": session_data.get("result"),
                "error": session_data.get("error"),
                "created_at": session_data.get("created_at")
            }
        }

    return json_result


@app.post("/stop/{session_id}")
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


@app.get("/snapshots/{session_id}")
async def get_session_snapshots(session_id: str, user_id: str):
    """Get all periodic snapshots for a session"""
    # Validate user_id
    if not user_id or user_id.strip() == "":
        raise HTTPException(status_code=400, detail="user_id is required and cannot be empty")

    # Use unified session manager to check both local and cloud storage
    unified_manager = get_unified_session_manager(queue_manager)
    session_data = await unified_manager.get_session_by_id(session_id)

    if not session_data:
        raise HTTPException(status_code=404, detail="Session not found")

    # Verify user owns this session
    session_user_id = session_data.get("user_id")
    if session_user_id and session_user_id != user_id:
        raise HTTPException(status_code=403, detail="Access denied: Session belongs to different user")

    # For cloud sessions, get snapshots from S3
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

            return {
                "session_id": session_id,
                "snapshot_count": len(snapshots_with_urls),
                "snapshots": snapshots_with_urls,
                "storage_location": "cloud"
            }

    # For local/active sessions, use existing snapshots
    return {
        "session_id": session_id,
        "snapshot_count": len(session_data.get("periodic_snapshots", [])),
        "snapshots": session_data.get("periodic_snapshots", []),
        "storage_location": storage_location
    }


@app.get("/all-sessions")
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

@app.post("/continue-session")
async def continue_session(
    session_id: str = Form(...),
    message: str = Form(...),
    language: Language = Form(Language.EN),
    user_id: str = Form(...),
    files: List[UploadFile] = File(default=[])
):
    """Continue an existing multi-turn session with S3 file handling"""
    # Validate user_id
    if not user_id or user_id.strip() == "":
        raise HTTPException(status_code=400, detail="user_id is required and cannot be empty")

    # Check if multi-turn session exists
    multiturn_session = queue_manager.multiturn_sessions.get(session_id)
    if not multiturn_session:
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
        user_id=user_id
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

@app.get("/multiturn-session/{session_id}")
async def get_multiturn_session(session_id: str, user_id: str):
    """Get complete multi-turn session history"""
    multiturn_session = queue_manager.multiturn_sessions.get(session_id)
    if not multiturn_session:
        raise HTTPException(status_code=404, detail="Multi-turn session not found")

    # Verify user owns this session
    if multiturn_session.user_id and multiturn_session.user_id != user_id:
        raise HTTPException(status_code=403, detail="Access denied: Session belongs to different user")

    return multiturn_session

@app.get("/multiturn-sessions")
async def get_all_multiturn_sessions(user_id: Optional[str] = None):
    """Get all multi-turn sessions from both local and cloud storage"""
    try:
        # Require user_id for security - prevent unauthorized access to all sessions
        if not user_id or user_id.strip() == "":
            return {"sessions": [], "error": "user_id is required", "message": "Please provide a valid user_id"}

        # Get unified session manager
        unified_manager = get_unified_session_manager(queue_manager)

        # Get all multi-turn sessions (local + cloud) filtered by user_id
        all_sessions = await unified_manager.get_multiturn_sessions(include_cloud=True, user_id=user_id)

        return {"sessions": all_sessions}
    except Exception as e:
        print(f"Error getting multi-turn sessions: {e}")
        # Fallback to local-only sessions
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
        return {"sessions": sessions}

@app.get("/turn-report/{session_id}/{turn_number}")
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
                "status": turn.status
            }

    raise HTTPException(status_code=404, detail=f"Turn {turn_number} not found in session")

@app.get("/session-context/{session_id}")
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
        "total_turns": multiturn_session.total_turns
    }

# ============= SESSION SHARING ENDPOINTS =============

@app.post("/share-session")
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

@app.post("/unshare-session")
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
    """Rename a multi-turn session"""
    try:
        session_id = request.session_id
        new_name = request.new_name
        user_id = request.user_id

        # Get the multi-turn session from local storage first
        multiturn_session = queue_manager.multiturn_sessions.get(session_id)

        # If not in memory, try to load from local storage
        if not multiturn_session:
            multiturn_file = os.path.join(queue_manager.multiturn_storage_dir, f"{session_id}.json")
            if os.path.exists(multiturn_file):
                with open(multiturn_file, 'r', encoding='utf-8') as f:
                    session_data = json.load(f)
                    multiturn_session = MultiTurnSession(**session_data)
                    queue_manager.multiturn_sessions[session_id] = multiturn_session

        if not multiturn_session:
            raise HTTPException(status_code=404, detail="Multi-turn session not found")

        # Verify user owns this session
        if multiturn_session.user_id and multiturn_session.user_id != user_id:
            raise HTTPException(status_code=403, detail="Access denied: Session belongs to different user")

        # Update the session name
        multiturn_session.session_name = new_name
        multiturn_session.last_updated = datetime.now().isoformat()

        # Save to local storage
        queue_manager.multiturn_sessions[session_id] = multiturn_session
        queue_manager._save_multiturn_session(multiturn_session)

        # Update in MongoDB if the session has been uploaded to cloud
        if cloud_storage_manager:
            try:
                from s3_mongodb.func_mongodb import get_mongodb_collection
                collection = get_mongodb_collection(
                    os.getenv("SESSION_DB_NAME", "dleader_agent"),
                    "multiturn_sessions"
                )
                if collection:
                    # Check if session exists in cloud
                    cloud_session = collection.find_one({"session_id": session_id})
                    if cloud_session:
                        # Update the session_name and last_updated in MongoDB
                        collection.update_one(
                            {"session_id": session_id},
                            {"$set": {
                                "session_name": new_name,
                                "last_updated": multiturn_session.last_updated
                            }}
                        )
            except Exception as cloud_error:
                print(f"Warning: Could not update session name in cloud: {cloud_error}")
                # Don't fail the request if cloud update fails

        return {
            "success": True,
            "session_id": session_id,
            "new_name": new_name,
            "message": "Session renamed successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error renaming session: {e}")
        raise HTTPException(status_code=500, detail=f"Error renaming session: {str(e)}")

@app.post("/upload-template")
async def upload_template(request: TemplateListRequest):
    """Upload workflow templates to MongoDB"""
    try:
        from s3_mongodb.func_mongodb import get_mongodb_collection
        from s3_mongodb.mongodb_upsert import upsert_wrapper

        # Get MongoDB collection
        collection = get_mongodb_collection(
            os.getenv("SESSION_DB_NAME", "dleader_agent"),
            "workflow_templates"
        )

        if not collection:
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

        if collection:
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

        # 2. Delete from S3 (if exists)
        try:
            s3_deleted = await cloud_storage_manager.delete_session_from_s3(session_id)
            deleted_items["s3_files"] = s3_deleted
        except Exception as e:
            print(f"S3 deletion error (continuing): {e}")

        # 3. Delete from MongoDB (if exists)
        try:
            mongo_deleted = await cloud_storage_manager.delete_session_from_mongodb(session_id)
            deleted_items["mongodb_docs"] = mongo_deleted
        except Exception as e:
            print(f"MongoDB deletion error (continuing): {e}")

        # 4. Delete from community_sessions if shared
        try:
            await cloud_storage_manager.remove_shared_session(session_id)
            deleted_items["mongodb_docs"].append("community_sessions")
        except Exception as e:
            print(f"Community session deletion error (continuing): {e}")

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
async def get_session_download_urls(session_id: str, user_id: str):
    """Get download URLs for session files (always prefer S3/cloud)"""
    try:
        # Wait briefly to ensure S3 upload completed
        await asyncio.sleep(1)

        # For multi-turn sessions, extract base session ID
        base_session_id = session_id
        if "_turn_" in session_id:
            base_session_id = session_id.split("_turn_")[0]
            print(f"Multi-turn session detected: {session_id} -> base: {base_session_id}")

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
                return download_data
            else:
                raise HTTPException(status_code=500, detail="Failed to generate download URLs from cloud storage")

        # For local sessions, try to create/find local zip
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
            return {
                "session_id": session_id,
                "download_url": f"/download/{session_id}?user_id={user_id}",
                "zip_available": True,
                "storage_type": storage_location
            }

        # No files found
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

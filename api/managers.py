"""
Manager classes for dleader_agent FastAPI server.

This module contains QueueManager, SessionManager, and StreamingCapture classes
that handle request queuing, session lifecycle, and output capturing.
"""

import asyncio
import glob
import json
import os
import queue
import shutil
import sys
import threading
import time
import uuid
from datetime import datetime
from multiprocessing import Process, Queue as MPQueue
from typing import Any, Dict, List, Optional

from api.models import (
    ConversationTurn,
    Language,
    MultiTurnSession,
    QueueStatus,
    UserRequest,
    now_jst
)

# External dependencies
from cloud_storage_manager import cloud_storage_manager
from enhanced_multiturn_handler import EnhancedMultiTurnHandler


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
        image_files = []
        if session_path and os.path.exists(session_path):
            image_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.svg', '.webp'}
            for file in os.listdir(session_path):
                if any(file.lower().endswith(ext) for ext in image_extensions):
                    image_files.append(os.path.join(session_path, file))

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
            # Upload to cloud asynchronously and cleanup memory after successful upload
            def upload_multiturn_in_thread():
                import asyncio
                try:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    loop.run_until_complete(cloud_storage_manager.upload_multiturn_session(multiturn_session_data))
                    loop.close()
                    print(f"Successfully uploaded multi-turn session {session_id} to cloud")

                    # If all turns are completed, clean up memory after delay (allow time for final queries)
                    if session and session.total_turns == turn_number:
                        print(f"All turns completed for session {session_id}, scheduling memory cleanup")
                        time.sleep(10)  # Wait 10 seconds to ensure upload is fully complete
                        if session_id in self.multiturn_sessions:
                            # Check session age - only remove if older than 1 hour or explicitly completed
                            session_obj = self.multiturn_sessions[session_id]
                            last_updated_str = session_obj.last_updated
                            try:
                                from datetime import datetime
                                last_updated = datetime.fromisoformat(last_updated_str)
                                age_hours = (datetime.now() - last_updated).total_seconds() / 3600
                                # Remove if older than 1 hour OR if session is marked completed
                                if age_hours > 1.0 or session_obj.session_status == "completed":
                                    del self.multiturn_sessions[session_id]
                                    print(f"Removed completed session {session_id} from memory (age: {age_hours:.2f}h)")
                                else:
                                    print(f"Keeping recent session {session_id} in cache (age: {age_hours:.2f}h)")
                            except Exception as e:
                                # If date parsing fails, just remove it
                                del self.multiturn_sessions[session_id]
                                print(f"Removed session {session_id} from memory: {e}")
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
            start_time = time.time()
            current_path = os.getcwd()
            chat_sessions_path = os.path.join(current_path, "chat_sessions")

            # Initialize agent (lazy import to avoid circular dependency)
            from api.utils import create_agent
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

            # Store queues in user_request
            user_request.process_queue = result_queue

            # Import run_agent_in_process (lazy import to avoid circular dependency)
            from api.utils import run_agent_in_process

            # Create and start process
            agent_process = Process(
                target=run_agent_in_process,
                args=(message_queue, result_queue, user_request.enhanced_message, session_path, user_request.use_template)
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
            # Initialize file paths to None in case of errors
            report_path = None
            thinking_path = None
            query_path = None
            json_path = None
            cleaned_thinking = ""
            final_report_content = ""

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
            zip_file_path = None  # Initialize to None in case zip creation fails
            print(f"DEBUG: zip_file_path initialized to None before zip creation")
            try:
                print(f"DEBUG: About to call create_session_zip for {session_path}")
                zip_file_path = create_session_zip(session_path, save_to_chat_zips=True)
                print(f"DEBUG: create_session_zip returned: {zip_file_path}")
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
                print(f"DEBUG: Creating files_dict - zip_file_path value: {zip_file_path}")

                # Extract images from json_result if available
                image_files = []
                if user_request.json_result and "files" in user_request.json_result:
                    image_files = user_request.json_result["files"].get("images", [])

                files_dict = {
                    'report_md': report_path,
                    'thinking_process': thinking_path,
                    'query_file': query_path,
                    'session_zip': zip_file_path,
                    'result_json': json_path,
                    'images': image_files
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


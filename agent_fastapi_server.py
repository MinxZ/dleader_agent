"""
FastAPI Agent Server with Multi-User Queue Support

This FastAPI server provides:
- Multi-user concurrent handling with queue system
- Language support for English and Japanese
- Session management and file handling
- Real-time streaming of agent responses
- Thread-safe queue management
"""

import asyncio
import os
import shutil
import sys
import tempfile
import threading
import time
import uuid
import zipfile
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import List, Optional, Dict, Any
import queue
import json

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
import uvicorn
import pandas as pd

# Add current directory to path for imports
sys.path.insert(0, os.getcwd())

from dleader_agent.agent.a1 import A1

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

# Queue Management System
class UserRequest:
    def __init__(self, session_id: str, message: str, language: Language, uploaded_files: List[str] = None):
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
        self.agent_thread = None
        self.json_result = None  # Store structured JSON result
        self.periodic_snapshots = []  # Store periodic JSON snapshots
        self.last_snapshot_time = None  # Track last snapshot time
        self.session_path = None  # Store session path for JSON updates
        self.all_progress_updates = []  # Store all progress updates permanently

class QueueManager:
    def __init__(self):
        self.request_queue = queue.Queue()
        self.active_sessions = {}  # session_id -> UserRequest
        self.session_history = {}  # session_id -> SessionManager
        self.processing_lock = threading.Lock()
        self.is_processing = False
        self.current_processing_session = None

        # Create persistent storage directory
        self.sessions_storage_dir = os.path.join(os.getcwd(), "session_storage")
        os.makedirs(self.sessions_storage_dir, exist_ok=True)

        # Load existing sessions from storage
        self._load_sessions_from_storage()

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
                "snapshot_count": len(user_request.periodic_snapshots)
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

            # Add cancellation progress update
            user_request.progress_queue.put({
                "type": "cancelled",
                "message": "Task was cancelled by user",
                "timestamp": datetime.now().isoformat()
            })

            # If currently processing, we can't directly stop the thread,
            # but the processing loop will check is_cancelled flag
            if user_request.agent_thread and user_request.agent_thread.is_alive():
                # The processing function will check is_cancelled periodically
                pass

            return True

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
                "all_progress_updates": user_request.all_progress_updates
            }

            with open(session_file, 'w', encoding='utf-8') as f:
                json.dump(session_data, f, indent=2, ensure_ascii=False, default=str)
        except Exception as e:
            print(f"Error saving session {user_request.session_id} to storage: {e}")

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
                "snapshot_count": len(session_data.get("periodic_snapshots", []))
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
            user_request.progress_queue.put({"type": "status", "message": "Starting agent initialization..."})

            # Create session manager
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
            
            # Handle uploaded files
            if user_request.uploaded_files:
                user_request.progress_queue.put({"type": "status", "message": "Processing uploaded files..."})
                # Copy files to session folder
                session_file_paths = []
                for file_path in user_request.uploaded_files:
                    if os.path.exists(file_path):
                        filename = os.path.basename(file_path)
                        new_path = os.path.join(session_path, filename)
                        shutil.copy2(file_path, new_path)
                        session_file_paths.append(new_path)
                
                # Add files to agent's data lake
                agent.data_lake_dict = {}
                for file_path in session_file_paths:
                    filename = os.path.basename(file_path)
                    try:
                        if filename.endswith('.csv'):
                            data = pd.read_csv(file_path)
                            agent.data_lake_dict[filename] = f"Dataset with {data.shape[0]} rows and {data.shape[1]} columns (Path: {file_path})"
                        elif filename.endswith(('.xlsx', '.xls')):
                            data = pd.read_excel(file_path)
                            agent.data_lake_dict[filename] = f"Excel file with {data.shape[0]} rows and {data.shape[1]} columns (Path: {file_path})"
                        else:
                            agent.data_lake_dict[filename] = f"File uploaded (format auto-detected) (Path: {file_path})"
                    except:
                        agent.data_lake_dict[filename] = f"File uploaded (format auto-detected) (Path: {file_path})"
                agent.configure()
            
            # Set up streaming capture
            stream_capture = StreamingCapture()
            
            # Process with agent
            user_request.progress_queue.put({"type": "status", "message": "Agent processing started..."})
            
            def run_agent():
                try:
                    with redirect_stdout(stream_capture):
                        # Enhance message based on language
                        if user_request.language == Language.JP:
                            enhanced_message = f"""{user_request.message}

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
                            enhanced_message = f"""{user_request.message}

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
  * Highlight pharmacophore features and important structural motifs"""
                        
                        _, result = agent.go(enhanced_message)
                        user_request.result = result
                except Exception as e:
                    user_request.error = str(e)
            
            # Start agent processing
            agent_thread = threading.Thread(target=run_agent)
            user_request.agent_thread = agent_thread
            agent_thread.start()

            # Monitor progress
            accumulated_thinking = ""
            last_content_length = 0
            user_request.last_snapshot_time = time.time()

            while agent_thread.is_alive():
                # Check if task was cancelled
                if user_request.is_cancelled:
                    user_request.progress_queue.put({
                        "type": "cancelled",
                        "message": "Task was cancelled by user"
                    })
                    return  # Exit early if cancelled

                current_content = stream_capture.get_content()
                if len(current_content) > last_content_length:
                    new_content = current_content[last_content_length:]
                    accumulated_thinking += new_content

                    user_request.progress_queue.put({
                        "type": "thinking_update",
                        "content": new_content,
                        "accumulated": accumulated_thinking
                    })
                    last_content_length = len(current_content)

                # Create periodic snapshots every 2 seconds
                current_time = time.time()
                if current_time - user_request.last_snapshot_time >= 2:
                    snapshot = queue_manager.create_json_snapshot(
                        user_request,
                        accumulated_thinking,
                        session_path
                    )

                    # Delete all previous snapshots and keep only the latest one
                    user_request.periodic_snapshots.clear()
                    user_request.periodic_snapshots.append(snapshot)
                    user_request.last_snapshot_time = current_time

                    # Delete previous snapshot files from session folder
                    try:
                        for file in os.listdir(session_path):
                            if file.startswith('snapshot_') and file.endswith('.json'):
                                os.remove(os.path.join(session_path, file))
                    except Exception as e:
                        print(f"Error deleting previous snapshot files: {e}")

                    # Save latest snapshot to file
                    try:
                        snapshot_filename = f"snapshot_latest_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                        snapshot_path = os.path.join(session_path, snapshot_filename)
                        with open(snapshot_path, 'w', encoding='utf-8') as f:
                            json.dump(snapshot, f, indent=2, ensure_ascii=False)

                        user_request.progress_queue.put({
                            "type": "snapshot_saved",
                            "message": f"Latest snapshot saved: {snapshot_filename}",
                            "snapshot_count": len(user_request.periodic_snapshots)
                        })
                    except Exception as e:
                        print(f"Error saving snapshot: {e}")

                time.sleep(0.5)
            
            # Wait for completion
            agent_thread.join()
            
            # Get final content
            final_content = stream_capture.get_content()
            if len(final_content) > last_content_length:
                new_content = final_content[last_content_length:]
                accumulated_thinking += new_content
            
            # Scan for and move new files created during processing
            try:
                exclude_paths = {'chat_sessions', 'chat_zips', '__pycache__', '.git', '.vscode', 'node_modules', chat_sessions_path}
                new_files = scan_for_new_files(current_path, start_time, exclude_paths)

                # Filter out files that are already in chat_sessions folder
                filtered_files = [f for f in new_files if not f.startswith(chat_sessions_path)]

                if filtered_files:
                    print(f"Found {len(filtered_files)} new files created during processing:")
                    for file in filtered_files:
                        print(f"  - {file}")
                    moved_files = move_files_to_session(filtered_files, session_path)
                    print(f"Moved {len(moved_files)} files to session folder")
                    user_request.progress_queue.put({
                        "type": "status",
                        "message": f"Moved {len(moved_files)} new files to session folder"
                    })
            except Exception as e:
                print(f"Error handling new files: {e}")

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

            # Save final session state to persistent storage
            queue_manager._save_session_to_storage(user_request)
            
        except Exception as e:
            user_request.status = "error"
            user_request.error = str(e)
            user_request.is_complete = True
            error_update = {
                "type": "error",
                "error": str(e)
            }
            user_request.progress_queue.put(error_update)
            user_request.all_progress_updates.append(error_update)

            # Save failed session state to persistent storage
            queue_manager._save_session_to_storage(user_request)

# Initialize queue manager
queue_manager = QueueManager()

# Session and utility classes (reused from original files)
class SessionManager:
    """Manage session folders and file storage"""
    def __init__(self):
        self.sessions_dir = os.path.join(os.getcwd(), "chat_sessions")
        os.makedirs(self.sessions_dir, exist_ok=True)
    
    def create_session_folder(self):
        """Create a unique session folder"""
        session_id = str(uuid.uuid4())[:8]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        session_name = f"session_{timestamp}_{session_id}"
        session_path = os.path.join(self.sessions_dir, session_name)
        os.makedirs(session_path, exist_ok=True)
        return session_path, session_name

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
            # Walk through all files in session directory
            for root, dirs, files in os.walk(session_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    # Add file to zip with relative path
                    arcname = os.path.relpath(file_path, session_path)
                    zipf.write(file_path, arcname)

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

# FastAPI App
app = FastAPI(title="Agent Chat API", description="Multi-user agent chat with queue management")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API Endpoints
@app.post("/chat", response_model=ChatResponse)
async def start_chat(request: ChatRequest):
    """Process chat request through queue and return complete results"""
    session_id = request.session_id or str(uuid.uuid4())

    # Create user request and add to queue
    user_request = UserRequest(
        session_id=session_id,
        message=request.message,
        language=request.language
    )

    # Add to queue
    position = queue_manager.add_request(user_request)

    # Wait for completion with timeout (max 30 minutes)
    max_wait_time = 30 * 60  # 30 minutes
    start_time = time.time()

    while not user_request.is_complete:
        if time.time() - start_time > max_wait_time:
            return ChatResponse(
                session_id=session_id,
                status="timeout",
                error="Request timed out after 30 minutes",
                progress_updates=[]
            )

        await asyncio.sleep(0.5)  # Check every 500ms

    # Collect all progress updates
    all_progress_updates = []
    while not user_request.progress_queue.empty():
        try:
            all_progress_updates.append(user_request.progress_queue.get_nowait())
        except queue.Empty:
            break

    # Return complete results
    if user_request.error:
        return ChatResponse(
            session_id=session_id,
            status="error",
            error=user_request.error,
            progress_updates=all_progress_updates
        )
    else:
        # Extract final report and thinking content from progress updates
        final_report = None
        thinking_content = ""
        session_path = None

        for update in all_progress_updates:
            if update.get("type") == "completion":
                final_report = update.get("final_report")
                thinking_content = update.get("thinking_content", "")
                session_path = update.get("session_path")
                break

        return ChatResponse(
            session_id=session_id,
            status="completed",
            thinking_content=thinking_content,
            final_report=final_report,
            progress_updates=all_progress_updates,
            session_path=session_path
        )



@app.post("/chat-queue")
async def start_chat_queue(request: ChatRequest):
    """Add chat request to queue and return session ID for status tracking"""
    session_id = request.session_id or str(uuid.uuid4())

    # Create user request and add to queue
    user_request = UserRequest(
        session_id=session_id,
        message=request.message,
        language=request.language
    )

    # Add to queue
    position = queue_manager.add_request(user_request)

    return {
        "session_id": session_id,
        "status": "queued",
        "position": position,
        "message": "Request added to queue. Use /status/{session_id} to check progress."
    }

@app.get("/status/{session_id}")
async def get_status(session_id: str):
    """Get current status and progress for a session"""
    # Check if session exists in active sessions
    progress = queue_manager.get_session_progress(session_id)
    if not progress:
        raise HTTPException(status_code=404, detail="Session not found")

    # Get queue status if still queued
    queue_status = queue_manager.get_queue_status(session_id)

    response = {
        "session_id": session_id,
        "status": progress["status"],
        "is_complete": progress["is_complete"],
        "created_at": progress["created_at"]
    }

    if queue_status:
        response["queue_position"] = queue_status.position
        response["estimated_wait_time"] = queue_status.estimated_wait_time
        response["total_users_in_queue"] = queue_status.total_users_in_queue

    if progress["error"]:
        response["error"] = progress["error"]

    if progress["result"] and progress["is_complete"]:
        # Extract final report and thinking content from progress updates
        all_progress_updates = progress["progress_updates"]
        final_report = None
        thinking_content = ""
        session_path = None

        for update in all_progress_updates:
            if update.get("type") == "completion":
                final_report = update.get("final_report")
                thinking_content = update.get("thinking_content", "")
                session_path = update.get("session_path")
                break

        response["final_report"] = final_report
        response["thinking_content"] = thinking_content
        response["session_path"] = session_path

    # Include latest progress updates
    response["progress_updates"] = progress["progress_updates"]

    return response

@app.post("/upload/{session_id}")
async def upload_files(session_id: str, files: List[UploadFile] = File(...)):
    """Upload files for a session"""
    if session_id not in queue_manager.active_sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    uploaded_paths = []
    temp_dir = tempfile.mkdtemp()

    for file in files:
        file_path = os.path.join(temp_dir, file.filename)
        with open(file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
        uploaded_paths.append(file_path)

    # Update session with file paths
    user_request = queue_manager.active_sessions[session_id]
    user_request.uploaded_files.extend(uploaded_paths)

    return {"message": f"Uploaded {len(files)} files", "file_paths": uploaded_paths}


@app.get("/sessions")
async def list_sessions():
    """List all active sessions"""
    sessions = []
    for session_id, user_request in queue_manager.active_sessions.items():
        sessions.append(SessionInfo(
            session_id=session_id,
            status=user_request.status,
            created_at=user_request.created_at.isoformat(),
            language=user_request.language,
            query=user_request.message
        ))

    return sessions

@app.get("/download/{session_id}")
async def download_session_zip(session_id: str):
    """Download session zip file"""
    # First try to get session info to find the zip path
    progress = queue_manager.get_session_progress(session_id)
    if not progress:
        raise HTTPException(status_code=404, detail="Session not found")

    # Try to get zip path from JSON result
    json_result = progress.get("json_result")
    if json_result and json_result.get("files", {}).get("session_zip"):
        zip_path = json_result["files"]["session_zip"]
        if os.path.exists(zip_path):
            return FileResponse(
                zip_path,
                media_type='application/zip',
                filename=os.path.basename(zip_path)
            )

    # Fallback: Look for session zip in chat_zips directory
    chat_zips_dir = os.path.join(os.getcwd(), "chat_zips")
    if not os.path.exists(chat_zips_dir):
        raise HTTPException(status_code=404, detail="Chat zips directory not found")

    # Find zip file for this session
    session_zip = None
    for filename in os.listdir(chat_zips_dir):
        if filename.startswith(f"session_") and session_id in filename and filename.endswith('.zip'):
            session_zip = os.path.join(chat_zips_dir, filename)
            break

    if not session_zip or not os.path.exists(session_zip):
        raise HTTPException(status_code=404, detail="Session zip file not found")

    return FileResponse(
        session_zip,
        media_type='application/zip',
        filename=os.path.basename(session_zip)
    )


@app.get("/list-zips")
async def list_chat_zips():
    """List all available chat zip files"""
    chat_zips_dir = os.path.join(os.getcwd(), "chat_zips")
    if not os.path.exists(chat_zips_dir):
        return {"zips": []}

    zip_files = []
    for filename in os.listdir(chat_zips_dir):
        if filename.endswith('.zip'):
            file_path = os.path.join(chat_zips_dir, filename)
            file_stat = os.stat(file_path)
            zip_files.append({
                "filename": filename,
                "size": file_stat.st_size,
                "created_at": datetime.fromtimestamp(file_stat.st_ctime).isoformat(),
                "modified_at": datetime.fromtimestamp(file_stat.st_mtime).isoformat()
            })

    # Sort by creation time (newest first)
    zip_files.sort(key=lambda x: x["created_at"], reverse=True)
    return {"zips": zip_files}


@app.get("/results/{session_id}")
async def get_session_results(session_id: str):
    """Get structured JSON results for a completed session"""
    progress = queue_manager.get_session_progress(session_id)
    if not progress:
        raise HTTPException(status_code=404, detail="Session not found")

    if not progress.get("is_complete", False):
        raise HTTPException(status_code=400, detail="Session is not yet complete")

    json_result = progress.get("json_result")
    if not json_result:
        # Session completed but no JSON result (possibly old session or error)
        return {
            "session_id": session_id,
            "status": progress.get("status", "unknown"),
            "error": "No structured results available for this session",
            "legacy_result": {
                "result": progress.get("result"),
                "error": progress.get("error"),
                "created_at": progress.get("created_at")
            }
        }

    return json_result


@app.post("/stop/{session_id}")
async def stop_task(session_id: str):
    """Stop a running or queued task"""
    success = queue_manager.stop_session(session_id)
    if success:
        return {
            "message": f"Task {session_id} has been cancelled",
            "session_id": session_id,
            "status": "cancelled"
        }
    else:
        raise HTTPException(status_code=404, detail="Session not found")


@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """WebSocket endpoint for real-time progress updates"""
    await websocket.accept()

    try:
        while True:
            progress = queue_manager.get_session_progress(session_id)
            if progress:
                await websocket.send_text(json.dumps(progress))

                if progress.get("is_complete"):
                    break

            await asyncio.sleep(1)

    except WebSocketDisconnect:
        pass


@app.get("/stream/{session_id}")
async def stream_progress(session_id: str):
    """Server-Sent Events endpoint for real-time progress updates"""
    async def generate():
        while True:
            progress = queue_manager.get_session_progress(session_id)
            if progress:
                yield f"data: {json.dumps(progress)}\n\n"

                if progress.get("is_complete"):
                    break

            await asyncio.sleep(1)

    return StreamingResponse(generate(), media_type="text/plain")


@app.get("/snapshots/{session_id}")
async def get_session_snapshots(session_id: str):
    """Get all periodic snapshots for a session"""
    progress = queue_manager.get_session_progress(session_id)
    if not progress:
        raise HTTPException(status_code=404, detail="Session not found")

    return {
        "session_id": session_id,
        "snapshot_count": progress.get("snapshot_count", 0),
        "snapshots": progress.get("periodic_snapshots", [])
    }


@app.get("/all-sessions")
async def get_all_sessions():
    """Get all sessions from storage"""
    try:
        sessions = []
        sessions_storage_dir = queue_manager.sessions_storage_dir

        if os.path.exists(sessions_storage_dir):
            for filename in os.listdir(sessions_storage_dir):
                if filename.endswith('.json'):
                    session_id = filename[:-5]  # Remove .json extension
                    try:
                        session_file = os.path.join(sessions_storage_dir, filename)
                        with open(session_file, 'r', encoding='utf-8') as f:
                            session_data = json.load(f)

                        # Extract relevant information for history
                        session_info = {
                            "session_id": session_data["session_id"],
                            "query": session_data["message"][:200] + ("..." if len(session_data["message"]) > 200 else ""),
                            "full_query": session_data["message"],
                            "language": session_data["language"],
                            "files_count": len(session_data.get("uploaded_files", [])),
                            "timestamp": session_data["created_at"],
                            "status": session_data["status"],
                            "is_complete": session_data["is_complete"]
                        }
                        sessions.append(session_info)
                    except Exception as e:
                        print(f"Error loading session {session_id}: {e}")
                        continue

        # Sort by timestamp (newest first)
        sessions.sort(key=lambda x: x["timestamp"], reverse=True)

        return {"sessions": sessions}
    except Exception as e:
        print(f"Error getting all sessions: {e}")
        return {"sessions": []}


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "queue_size": queue_manager.request_queue.qsize(),
        "is_processing": queue_manager.is_processing,
        "current_session": queue_manager.current_processing_session
    }

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="FastAPI Agent Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8001, help="Port to bind to")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload")
    
    args = parser.parse_args()
    
    uvicorn.run(
        "agent_fastapi_server:app",
        host=args.host,
        port=args.port,
        reload=args.reload
    )

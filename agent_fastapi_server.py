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

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
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

class QueueManager:
    def __init__(self):
        self.request_queue = queue.Queue()
        self.active_sessions = {}  # session_id -> UserRequest
        self.session_history = {}  # session_id -> SessionManager
        self.processing_lock = threading.Lock()
        self.is_processing = False
        self.current_processing_session = None
        
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
            
            # Get latest progress updates
            progress_updates = []
            while not user_request.progress_queue.empty():
                try:
                    progress_updates.append(user_request.progress_queue.get_nowait())
                except queue.Empty:
                    break
            
            return {
                "session_id": session_id,
                "status": user_request.status,
                "is_complete": user_request.is_complete,
                "error": user_request.error,
                "result": user_request.result,
                "progress_updates": progress_updates,
                "created_at": user_request.created_at.isoformat()
            }
        
        return None
    
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
                            enhanced_message = f"{user_request.message}\n\n注意: アップロードされたファイルは次の作業フォルダに保存されています: {session_path} ファイルを生成あるいは保存する場合は、作業フォルダに保存してください。コメントはできるだけ日本語で記述し、最終レポートも日本語で作成すること。 use plt.rcParams['font.family'] = ['Noto Sans CJK JP', 'DejaVu Sans' ] when plot"
                        else:
                            enhanced_message = f"{user_request.message}\n\nNote: The uploaded files are stored in the folder: {session_path}. If saving file, also save in it, it is the working folder."
                        
                        _, result = agent.go(enhanced_message)
                        user_request.result = result
                except Exception as e:
                    user_request.error = str(e)
            
            # Start agent processing
            agent_thread = threading.Thread(target=run_agent)
            agent_thread.start()
            
            # Monitor progress
            accumulated_thinking = ""
            last_content_length = 0
            
            while agent_thread.is_alive():
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
                
                time.sleep(0.5)
            
            # Wait for completion
            agent_thread.join()
            
            # Get final content
            final_content = stream_capture.get_content()
            if len(final_content) > last_content_length:
                new_content = final_content[last_content_length:]
                accumulated_thinking += new_content
            
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
                
                # Save thinking process
                thinking_filename = f"thinking_process_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
                thinking_path = os.path.join(session_path, thinking_filename)
                with open(thinking_path, 'w', encoding='utf-8') as f:
                    f.write(accumulated_thinking)
                
            except Exception as e:
                print(f"Error saving session files: {e}")
            
            # Mark as complete
            user_request.status = "completed"
            user_request.is_complete = True
            user_request.progress_queue.put({
                "type": "completion",
                "final_report": final_report_content,
                "thinking_content": accumulated_thinking,
                "session_path": session_path
            })
            
        except Exception as e:
            user_request.status = "error"
            user_request.error = str(e)
            user_request.is_complete = True
            user_request.progress_queue.put({
                "type": "error",
                "error": str(e)
            })

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
            language=user_request.language
        ))
    
    return sessions

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
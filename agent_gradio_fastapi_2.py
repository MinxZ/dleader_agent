"""
Gradio Interface for FastAPI Agent Server

This interface provides a clean Gradio frontend that communicates with the FastAPI agent server:
- Submits requests to the FastAPI server's queue system
- Polls for status updates and results
- Displays results without streaming (as requested)
- Handles file uploads through the API
"""

import argparse
import json
import os
import tempfile
import time
import uuid
from datetime import datetime
from typing import List, Optional

import gradio as gr
import requests
from PIL import Image


class SessionHistory:
    """Manage session history storage"""

    def __init__(self, history_file: str = "session_history.json"):
        self.history_file = history_file
        self.history = self.load_history()

    def load_history(self) -> List[dict]:
        """Load session history from file"""
        try:
            if os.path.exists(self.history_file):
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception:
            pass
        return []

    def save_history(self):
        """Save session history to file"""
        try:
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(self.history, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def add_session(self, session_id: str, query: str, language: str, files_count: int = 0):
        """Add a new session to history"""
        session_entry = {
            "session_id": session_id,
            "query": query[:200] + ("..." if len(query) > 200 else ""),
            "full_query": query,
            "language": language,
            "files_count": files_count,
            "timestamp": datetime.now().isoformat(),
            "status": "queued"
        }
        self.history.insert(0, session_entry)  # Add to beginning

        # Keep only last 50 sessions
        if len(self.history) > 50:
            self.history = self.history[:50]

        self.save_history()

    def update_session_status(self, session_id: str, status: str, is_complete: bool = False):
        """Update session status"""
        for session in self.history:
            if session["session_id"] == session_id:
                session["status"] = status
                session["is_complete"] = is_complete
                session["last_updated"] = datetime.now().isoformat()
                break
        self.save_history()

    def get_history(self) -> List[dict]:
        """Get session history"""
        return self.history


class FastAPIClient:
    """Client for communicating with the FastAPI agent server"""

    def __init__(self, base_url: str = "http://localhost:8002"):
        self.base_url = base_url.rstrip('/')
        print(self.base_url)

    def health_check(self) -> bool:
        """Check if the FastAPI server is healthy"""
        try:
            response = requests.get(f"{self.base_url}/health", timeout=5)
            return response.status_code == 200
        except:
            return False

    def submit_request(self, message: str, language: str = "en") -> Optional[str]:
        """Submit a chat request and return session ID"""
        try:
            data = {
                "message": message,
                "language": language
            }
            response = requests.post(f"{self.base_url}/chat-queue", json=data, timeout=10)
            if response.status_code == 200:
                result = response.json()
                return result.get("session_id")
            return None
        except Exception as e:
            print(f"Error submitting request: {e}")
            return None

    def upload_files(self, session_id: str, files: List[str]) -> bool:
        """Upload files for a session"""
        try:
            files_data = []
            for file_path in files:
                with open(file_path, 'rb') as f:
                    files_data.append(('files', (os.path.basename(file_path), f, 'application/octet-stream')))

            response = requests.post(
                f"{self.base_url}/upload/{session_id}",
                files=files_data,
                timeout=30
            )
            return response.status_code == 200
        except Exception as e:
            print(f"Error uploading files: {e}")
            return False

    def get_status(self, session_id: str) -> Optional[dict]:
        """Get status for a session"""
        try:
            response = requests.get(f"{self.base_url}/status/{session_id}", timeout=10)
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            print(f"Error getting status: {e}")
            return None

    def stop_task(self, session_id: str) -> bool:
        """Stop a running or queued task"""
        try:
            response = requests.post(f"{self.base_url}/stop/{session_id}", timeout=10)
            return response.status_code == 200
        except Exception as e:
            print(f"Error stopping task: {e}")
            return False

    def get_json_results(self, session_id: str) -> Optional[dict]:
        """Get structured JSON results for a completed session"""
        try:
            response = requests.get(f"{self.base_url}/results/{session_id}", timeout=10)
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            print(f"Error getting JSON results: {e}")
            return None

    def get_snapshots(self, session_id: str) -> Optional[dict]:
        """Get all periodic snapshots for a session"""
        try:
            response = requests.get(f"{self.base_url}/snapshots/{session_id}", timeout=10)
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            print(f"Error getting snapshots: {e}")
            return None

    def stream_progress(self, session_id: str, callback=None):
        """Stream progress updates using Server-Sent Events"""
        try:
            response = requests.get(f"{self.base_url}/stream/{session_id}", stream=True, timeout=30)
            for line in response.iter_lines():
                if line:
                    line = line.decode('utf-8')
                    if line.startswith('data: '):
                        data = json.loads(line[6:])
                        if callback:
                            callback(data)
                        if data.get("is_complete"):
                            break
        except Exception as e:
            print(f"Error streaming progress: {e}")

    def download_zip(self, session_id: str) -> Optional[str]:
        """Download zip file for a completed session"""
        try:
            response = requests.get(f"{self.base_url}/download/{session_id}", timeout=30)
            if response.status_code == 200:
                # Create temporary file for download
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                temp_file = tempfile.NamedTemporaryFile(
                    suffix='.zip',
                    prefix=f'session_{session_id[:8]}_{timestamp}_',
                    delete=False
                )
                temp_file.write(response.content)
                temp_file.close()
                return temp_file.name
            return None
        except Exception as e:
            print(f"Error downloading zip: {e}")
            return None

    def submit_and_wait(self, message: str, files: List[str] = None, language: str = "en", timeout: int = 1800) -> dict:
        """Submit request and wait for completion (non-streaming)"""
        # Submit request
        session_id = self.submit_request(message, language)
        if not session_id:
            return {"error": "Failed to submit request to server"}

        # Upload files if provided
        if files:
            upload_success = self.upload_files(session_id, files)
            if not upload_success:
                return {"error": "Failed to upload files to server"}

        # Poll for completion
        start_time = time.time()
        last_status = "queued"

        while time.time() - start_time < timeout:
            status_data = self.get_status(session_id)
            if not status_data:
                return {"error": "Failed to get status from server"}

            current_status = status_data.get("status", "unknown")

            # Update if status changed
            if current_status != last_status:
                last_status = current_status
                print(f"Status update: {current_status}")

            if status_data.get("is_complete"):
                if status_data.get("error"):
                    return {
                        "error": status_data["error"],
                        "session_id": session_id,
                        "status": current_status
                    }
                else:
                    return {
                        "success": True,
                        "session_id": session_id,
                        "final_report": status_data.get("final_report", "Processing completed successfully."),
                        "thinking_content": status_data.get("thinking_content", ""),
                        "session_path": status_data.get("session_path", ""),
                        "status": current_status
                    }

            # Show queue position if available
            if "queue_position" in status_data:
                queue_pos = status_data["queue_position"]
                wait_time = status_data.get("estimated_wait_time", 0)
                print(f"Queue position: {queue_pos}, estimated wait: {wait_time}s")

            time.sleep(2)  # Poll every 2 seconds

        return {"error": f"Request timed out after {timeout} seconds", "session_id": session_id}


async def stop_task_by_session_id(session_id: str, server_url: str):
    """Stop a task by session ID"""
    if not session_id.strip():
        return "## ❌ Error\n\nPlease enter a Session ID to stop the task."

    # Initialize client
    client = FastAPIClient(server_url)

    # Check server health
    if not client.health_check():
        return "## ❌ Server Error\n\nCannot connect to FastAPI server. Please ensure the server is running."

    try:
        # First check if the session exists
        status_data = client.get_status(session_id)
        if not status_data:
            return f"## ❌ Session Not Found\n\nSession ID '{session_id}' not found on server."

        # Check if task is already complete
        if status_data.get("is_complete", False):
            status = status_data.get("status", "unknown")
            return f"## ⚠️ Task Already Complete\n\nSession '{session_id}' has status: {status}.\nCannot stop a completed task."

        # Attempt to stop the task
        success = client.stop_task(session_id)
        if success:
            return f"""## ✅ Task Stopped Successfully

**Session ID:** {session_id}
**Status:** Cancelled by user
**Timestamp:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

The task has been successfully cancelled.
"""
        else:
            return f"""## ❌ Failed to Stop Task

**Session ID:** {session_id}
**Timestamp:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Failed to stop the task. It may have already completed or there was a server error.
"""

    except Exception as e:
        return f"""## ❌ Error Stopping Task

**Error:** {str(e)}
**Session ID:** {session_id}
**Timestamp:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""


async def get_json_results_by_session_id(session_id: str, server_url: str):
    """Get JSON results for a completed session"""
    if not session_id.strip():
        return (
            "## ❌ Error\n\nPlease enter a Session ID to get JSON results.",
            gr.update(visible=False)
        )

    # Initialize client
    client = FastAPIClient(server_url)

    # Check server health
    if not client.health_check():
        return (
            "## ❌ Server Error\n\nCannot connect to FastAPI server. Please ensure the server is running.",
            gr.update(visible=False)
        )

    try:
        # Get JSON results
        json_results = client.get_json_results(session_id)
        if not json_results:
            return (
                f"## ❌ No Results Available\n\nNo JSON results found for session '{session_id}'.\nThe session may not exist, be incomplete, or lack structured results.",
                gr.update(visible=False)
            )

        # Format results for display
        status = json_results.get("status", "unknown")
        timestamp = json_results.get("timestamp", "N/A")
        language = json_results.get("language", "N/A")
        query = json_results.get("query", "N/A")

        # Format file information
        files_info = json_results.get("files", {})
        images = files_info.get("images", [])

        files_display = f"""
**Files Generated:**
- Report (MD): `{os.path.basename(files_info.get('report_md', 'N/A'))}`
- Thinking Process: `{os.path.basename(files_info.get('thinking_process', 'N/A'))}`
- Session ZIP: `{os.path.basename(files_info.get('session_zip', 'N/A')) if files_info.get('session_zip') else 'N/A'}`
- Images: {len(images)} files
"""

        if images:
            files_display += "\n**Images:**\n"
            for img in images[:5]:  # Show first 5 images
                files_display += f"  - `{os.path.basename(img)}`\n"
            if len(images) > 5:
                files_display += f"  - ... and {len(images) - 5} more\n"

        # Content preview
        content = json_results.get("content", {})
        final_report = content.get("final_report", "")
        report_preview = final_report[:500] + "..." if len(final_report) > 500 else final_report

        result_display = f"""## 📊 JSON Results Retrieved

**Session Information:**
- **Session ID:** {session_id}
- **Status:** {status}
- **Language:** {language.upper()}
- **Timestamp:** {timestamp}

**Query:** {query[:200]}{'...' if len(query) > 200 else ''}

{files_display}

**Report Preview:**
```
{report_preview}
```

---

**Full JSON Result:** Available for download below.
"""

        # Create downloadable JSON file
        json_file = create_download_file(
            json.dumps(json_results, indent=2, ensure_ascii=False),
            f"results_{session_id[:8]}",
            "json"
        )

        return (
            result_display,
            gr.update(visible=True, value=json_file) if json_file else gr.update(visible=False)
        )

    except Exception as e:
        return (
            f"""## ❌ Error Getting Results

**Error:** {str(e)}
**Session ID:** {session_id}
**Timestamp:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
""",
            gr.update(visible=False)
        )


async def get_snapshots_by_session_id(session_id: str, server_url: str):
    """Get periodic snapshots for a session"""
    if not session_id.strip():
        return (
            "## ❌ Error\n\nPlease enter a Session ID to get snapshots.",
            gr.update(visible=False)
        )

    # Initialize client
    client = FastAPIClient(server_url)

    # Check server health
    if not client.health_check():
        return (
            "## ❌ Server Error\n\nCannot connect to FastAPI server. Please ensure the server is running.",
            gr.update(visible=False)
        )

    try:
        # Get snapshots
        snapshots_data = client.get_snapshots(session_id)
        if not snapshots_data:
            return (
                f"## ❌ No Snapshots Available\n\nNo snapshots found for session '{session_id}'.\nThe session may not exist or have no periodic snapshots.",
                gr.update(visible=False)
            )

        session_id = snapshots_data.get("session_id", "N/A")
        snapshot_count = snapshots_data.get("snapshot_count", 0)
        snapshots = snapshots_data.get("snapshots", [])

        if snapshot_count == 0:
            return (
                f"## 📊 No Snapshots Yet\n\nSession '{session_id}' exists but has no periodic snapshots yet.\nSnapshots are created every minute during processing.",
                gr.update(visible=False)
            )

        # Format snapshots display
        snapshots_display = f"""## 📊 Periodic Snapshots Retrieved

**Session ID:** {session_id}
**Total Snapshots:** {snapshot_count}
**Retrieved:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

"""

        for i, snapshot in enumerate(snapshots, 1):
            timestamp = snapshot.get("timestamp", "N/A")
            status = snapshot.get("status", "unknown")
            thinking_length = snapshot.get("content", {}).get("thinking_length", 0)
            image_count = len(snapshot.get("files", {}).get("images", []))

            # Parse timestamp for display
            try:
                dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                time_str = dt.strftime('%m/%d %H:%M:%S')
            except:
                time_str = timestamp

            snapshots_display += f"""### 📸 Snapshot {i}
- **Time:** {time_str}
- **Status:** {status}
- **Thinking Length:** {thinking_length:,} characters
- **Images Found:** {image_count}

"""

        snapshots_display += f"""
---

**Note:** Snapshots are automatically created every minute during processing.
They capture the current state including thinking process, status, and generated files.

**Full Snapshots Data:** Available for download below.
"""

        # Create downloadable snapshots file
        snapshots_file = create_download_file(
            json.dumps(snapshots_data, indent=2, ensure_ascii=False),
            f"snapshots_{session_id[:8]}",
            "json"
        )

        return (
            snapshots_display,
            gr.update(visible=True, value=snapshots_file) if snapshots_file else gr.update(visible=False)
        )

    except Exception as e:
        return (
            f"""## ❌ Error Getting Snapshots

**Error:** {str(e)}
**Session ID:** {session_id}
**Timestamp:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
""",
            gr.update(visible=False)
        )


def load_logo():
    """Load the logo image"""
    try:
        img = Image.open("dleader_logo.jpg")
        return img
    except:
        return None


def format_files_info(files):
    """Format uploaded files information"""
    if not files:
        return "No files uploaded"

    file_info = []
    for file in files:
        if file is None:
            continue
        filename = os.path.basename(file.name)
        try:
            file_size = os.path.getsize(file.name) / (1024 * 1024)  # Size in MB
            file_info.append(f"📁 **{filename}** ({file_size:.2f} MB)")
        except:
            file_info.append(f"📁 **{filename}**")

    return "**Uploaded Files:**\n\n" + "\n".join(file_info)


def create_download_file(content: str, prefix: str, extension: str) -> Optional[str]:
    """Create a temporary file for download"""
    try:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        temp_file = tempfile.NamedTemporaryFile(
            mode='w',
            suffix=f'.{extension}',
            prefix=f'{prefix}_{timestamp}_',
            delete=False,
            encoding='utf-8'
        )
        temp_file.write(content)
        temp_file.close()
        return temp_file.name
    except Exception:
        return None


async def process_request(message: str, files: List, server_url: str, language: str):
    """Process request using FastAPI backend - submit immediately and poll for results"""
    if not message.strip():
        return (
            "## ❌ Error\n\nPlease enter a request to process.",
            "## ❌ No Input\n\nPlease enter a request to process.",
            gr.update(visible=False),
            gr.update(visible=False),
            gr.update(value=load_history_display())
        )

    # Initialize client and history
    client = FastAPIClient(server_url)
    history = SessionHistory()

    # Check server health
    if not client.health_check():
        return (
            "## ❌ Server Error\n\nCannot connect to FastAPI server. Please ensure the server is running.",
            "## ❌ Server Error\n\nCannot connect to FastAPI server.",
            gr.update(visible=False),
            gr.update(visible=False),
            gr.update(value=load_history_display())
        )

    # Prepare file paths
    file_paths = []
    if files:
        for file in files:
            if file is not None:
                file_paths.append(file.name)

    # Submit request directly to FastAPI queue (non-blocking)
    try:
        session_id = client.submit_request(message, language)
        if not session_id:
            return (
                "## ❌ Submission Error\n\nFailed to submit request to server queue.",
                "## ❌ Submission Error\n\nFailed to submit request to server queue.",
                gr.update(visible=False),
                gr.update(visible=False),
                gr.update(value=load_history_display())
            )

        # Add to history
        history.add_session(session_id, message, language, len(file_paths))

        # Upload files if provided
        if file_paths:
            upload_success = client.upload_files(session_id, file_paths)
            if not upload_success:
                return (
                    "## ❌ Upload Error\n\nFailed to upload files to server.",
                    "## ❌ Upload Error\n\nFailed to upload files to server.",
                    gr.update(visible=False),
                    gr.update(visible=False),
                    gr.update(value=load_history_display())
                )

        # Return immediate confirmation - FastAPI will handle the queue
        status_display = f"""## 🚀 Request Submitted Successfully

**Status:** 📋 Queued for processing
**Session ID:** {session_id}
**Submitted:** {datetime.now().strftime('%H:%M:%S')}

Your request has been submitted to the FastAPI queue.
Processing will continue even if you close this page.
You can check status using Session ID: {session_id}
"""

        result_display = f"""## 📋 Request Submitted to Queue

**Session ID:** {session_id}
**Submitted:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**Language:** {language}

Your request has been added to the processing queue. The FastAPI server will handle the processing independently.

**Files uploaded:** {len(file_paths) if file_paths else 0}

**Request:** {message[:200]}{'...' if len(message) > 200 else ''}

---

### 🔄 Processing Status

The task is now queued for processing. You can:
1. Close this page safely - processing will continue
2. Check status using the Session ID above
3. Return later to retrieve results

Processing will be handled by the FastAPI server queue system.
"""

        return (
            result_display,
            status_display,
            gr.update(visible=False),
            gr.update(visible=False),
            gr.update(value=load_history_display())
        )

    except Exception as e:
        error_msg = f"""## ❌ System Error

**Error:** {str(e)}
**Timestamp:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Please check the server connection and try again.
"""
        return (
            error_msg,
            "## ❌ System Error\n\nError details displayed in the results panel →",
            gr.update(visible=False),
            gr.update(visible=False),
            gr.update(value=load_history_display())
        )


def load_history_display() -> str:
    """Load and format session history for display"""
    history = SessionHistory()
    sessions = history.get_history()

    if not sessions:
        return """## 📅 Session History

No sessions found. Start by submitting a request in the Submit Request tab.

**Instructions:**
1. Submit requests to see them appear here
2. Click on any session to check its status
3. Download files when tasks are completed
"""

    history_html = "## 📅 Session History\n\n"

    for session in sessions:
        status_emoji = {
            'queued': '📋',
            'processing': '🔄',
            'completed': '✅',
            'failed': '❌',
            'error': '❌',
            'cancelled': '🛑'
        }.get(session.get('status', 'unknown'), '❓')

        timestamp = session.get('timestamp', '')
        if timestamp:
            try:
                dt = datetime.fromisoformat(timestamp)
                time_str = dt.strftime('%m/%d %H:%M')
            except:
                time_str = timestamp[:16]
        else:
            time_str = 'Unknown'

        files_info = f" ({session.get('files_count', 0)} files)" if session.get('files_count', 0) > 0 else ""
        language_info = f" [{session.get('language', 'en').upper()}]"

        history_html += f"""**{status_emoji} {time_str}** `{session['session_id'][:12]}...`{language_info}{files_info}
> {session.get('query', 'No query')}

"""

    return history_html


def get_history_items() -> List[tuple]:
    """Get history items as list of tuples for dropdown/selection"""
    history = SessionHistory()
    sessions = history.get_history()

    if not sessions:
        return [("No sessions available", "")]

    items = []
    for session in sessions:
        status_emoji = {
            'queued': '📋',
            'processing': '🔄',
            'completed': '✅',
            'failed': '❌',
            'error': '❌',
            'cancelled': '🛑'
        }.get(session.get('status', 'unknown'), '❓')

        timestamp = session.get('timestamp', '')
        if timestamp:
            try:
                dt = datetime.fromisoformat(timestamp)
                time_str = dt.strftime('%m/%d %H:%M')
            except:
                time_str = timestamp[:16]
        else:
            time_str = 'Unknown'

        # Create display label
        label = f"{status_emoji} {time_str} - {session.get('query', 'No query')[:50]}..."
        items.append((label, session['session_id']))

    return items


async def handle_history_item_click(session_id: str, server_url: str):
    """Handle clicking on a history item - check its status"""
    if not session_id or session_id == "":
        return (
            "## 📅 History Selection\n\nSelect a session from the dropdown above to view its details.",
            gr.update(visible=False),
            gr.update(visible=False),
            gr.update(visible=False)
        )

    # Use the existing check_status function
    return await check_status(session_id, server_url)


async def check_status(session_id: str, server_url: str):
    """Check status of a submitted request"""
    if not session_id.strip():
        return (
            "## ❌ Error\n\nPlease enter a Session ID to check status.",
            gr.update(visible=False),
            gr.update(visible=False),
            gr.update(visible=False)
        )

    # Initialize client and history
    client = FastAPIClient(server_url)
    history = SessionHistory()

    # Check server health
    if not client.health_check():
        return (
            "## ❌ Server Error\n\nCannot connect to FastAPI server. Please ensure the server is running.",
            gr.update(visible=False),
            gr.update(visible=False),
            gr.update(visible=False)
        )

    try:
        status_data = client.get_status(session_id)
        if not status_data:
            return (
                f"## ❌ Session Not Found\n\nSession ID '{session_id}' not found on server.",
                gr.update(visible=False),
                gr.update(visible=False),
                gr.update(visible=False)
            )

        # Format status display
        current_status = status_data.get("status", "unknown")
        is_complete = status_data.get("is_complete", False)

        # Update history
        history.update_session_status(session_id, current_status, is_complete)

        if is_complete:
            if current_status == "cancelled":
                result_display = f"""## ✅ Processing Complete

{final_report}

---

**Session Information:**
- **Session ID:** {session_id}
- **Session Path:** {session_path}
- **Completed:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""

                # Create download files
                report_file = create_download_file(final_report, "report", "md")
                thinking_file = create_download_file(thinking_content, "thinking_process", "txt") if thinking_content else None
                zip_file = client.download_zip(session_id)

                return (
                    result_display,
                    gr.update(visible=True, value=report_file) if report_file else gr.update(visible=False),
                    gr.update(visible=True, value=thinking_file) if thinking_file else gr.update(visible=False),
                    gr.update(visible=True, value=zip_file) if zip_file else gr.update(visible=False)
                )
        else:
            # Still processing or queued
            queue_info = ""
            if "queue_position" in status_data:
                queue_pos = status_data["queue_position"]
                wait_time = status_data.get("estimated_wait_time", 0)
                queue_info = f"\n- **Queue Position:** {queue_pos}\n- **Estimated Wait:** {wait_time} seconds"

            result_display = f"""## 🔄 Processing Status

**Session ID:** {session_id}
**Status:** {current_status}
**Created:** {status_data.get('created_at', 'N/A')}
**Current Time:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
{queue_info}

Your request is {'being processed' if current_status == 'processing' else 'in queue'}.
Check back later for results.
"""

            return (
                result_display,
                gr.update(visible=False),
                gr.update(visible=False),
                gr.update(visible=False)
            )

    except Exception as e:
        error_msg = f"""## ❌ Status Check Error

**Error:** {str(e)}
**Session ID:** {session_id}
**Timestamp:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        return (
            error_msg,
            gr.update(visible=False),
            gr.update(visible=False),
            gr.update(visible=False)
        )


def create_interface(default_fastapi_url: str = "http://localhost:8002"):
    """Create the main Gradio interface"""

    with gr.Blocks(title="Agent FastAPI Interface", theme=gr.themes.Soft()) as demo:
        # Header section with logo and title
        with gr.Row():
            with gr.Column(scale=1, min_width=120):
                gr.Image(
                    value=load_logo(),
                    show_label=False,
                    show_download_button=False,
                    container=False,
                    height=100,
                    width=120,
                    interactive=False
                )
            with gr.Column(scale=5):
                gr.HTML("""
                <div style="display: flex; align-items: center; justify-content: center; height: 120px; background: #f8f9fa; color: #333; border: 2px solid #dee2e6; border-radius: 8px; margin: 10px; padding: 20px;">
                    <div style="text-align: center;">
                        <h1 style="margin: 0; font-size: 2.2em; color: #2c3e50; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; font-weight: 600;">KumiChem AI Agent</h1>
                        <p style="margin: 8px 0 0 0; font-size: 1.1em; color: #6c757d; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;">FastAPI Backend Integration</p>
                    </div>
                </div>
                """)

        # Server configuration section
        with gr.Row():
            with gr.Column():
                gr.Markdown("### ⚙️ Server Configuration")
                with gr.Row():
                    server_url = gr.Textbox(
                        label="FastAPI Server URL",
                        value=default_fastapi_url,
                        placeholder=default_fastapi_url
                    )
                    language_choice = gr.Dropdown(
                        label="Language",
                        choices=[("English", "en"), ("Japanese", "jp")],
                        value="en"
                    )

        # Main interface with tabs
        with gr.Tabs():
            # Submit Request Tab
            with gr.Tab("🚀 Submit Request"):
                with gr.Row(equal_height=True):
                    # Left Column - User Input and Controls
                    with gr.Column(scale=1):
                        gr.Markdown("## 📝 Input & Controls")

                        # File upload section
                        with gr.Group():
                            gr.Markdown("### 📁 Upload Files")
                            file_input = gr.File(
                                label="Upload Files",
                                file_count="multiple",
                                file_types=None,
                                height=100
                            )
                            file_status = gr.Markdown("No files uploaded")

                        # User input section
                        with gr.Group():
                            gr.Markdown("### 💬 Your Request")
                            user_input = gr.Textbox(
                                label="Describe what you want the agent to do",
                                placeholder="Enter your request here...\n\nExamples:\n• Analyze the uploaded data\n• Extract key information from documents\n• Perform calculations or analysis\n• Generate reports or summaries",
                                lines=5,
                                max_lines=10
                            )

                            with gr.Row():
                                submit_btn = gr.Button("🚀 Process", variant="primary", scale=2)
                                clear_btn = gr.Button("🗑️ Clear", variant="secondary", scale=1)

                        # Status section
                        with gr.Group():
                            gr.Markdown("### 📊 Status")
                            status_display = gr.Markdown(
                                """## 📊 Ready to Process

**Status:** 🟢 Waiting for input
**Server:** Not connected

Ready to process your request...
""",
                                height=150
                            )

                            with gr.Row():
                                download_report = gr.File(
                                    label="📥 Download Report",
                                    visible=False
                                )
                                download_thinking = gr.File(
                                    label="📥 Download Thinking Process",
                                    visible=False
                                )

                    # Right Column - Results Display
                    with gr.Column(scale=1):
                        gr.Markdown("## 📋 Results")

                        results_display = gr.Markdown(
                            """## 📋 Results Panel

Ready to display your results...

**Status:** 🟢 Waiting for processing
**Instructions:**
1. Upload files (optional)
2. Enter your request
3. Click "Process" to start
4. Results will appear here

Requests are submitted immediately to FastAPI queue.
You can safely close the page after submission.
""",
                            height=600
                        )

            # Check Status Tab
            with gr.Tab("🔍 Check Status"):
                with gr.Row():
                    with gr.Column(scale=1):
                        gr.Markdown("## 🔍 Check Request Status")

                        with gr.Group():
                            gr.Markdown("### 📋 Session ID")
                            session_id_input = gr.Textbox(
                                label="Enter Session ID",
                                placeholder="Paste your session ID here...",
                                lines=1
                            )

                            with gr.Row():
                                check_btn = gr.Button("🔍 Check Status", variant="primary", scale=2)
                                clear_status_btn = gr.Button("🗑️ Clear", variant="secondary", scale=1)

                    with gr.Column(scale=1):
                        gr.Markdown("## 📋 Status Results")

                        status_results = gr.Markdown(
                            """## 📋 Status Check

Enter a Session ID to check the status of your request.

**Instructions:**
1. Copy the Session ID from your submitted request
2. Paste it in the Session ID field
3. Click "Check Status"
4. Results will appear here

You can check status multiple times to monitor progress.
""",
                            height=400
                        )

                        with gr.Row():
                            status_download_report = gr.File(
                                label="📥 Download Report",
                                visible=False
                            )
                            status_download_thinking = gr.File(
                                label="📥 Download Thinking Process",
                                visible=False
                            )
                            status_download_zip = gr.File(
                                label="📥 Download Session Files",
                                visible=False
                            )

            # Snapshots Tab
            with gr.Tab("📸 View Snapshots"):
                with gr.Row():
                    with gr.Column(scale=1):
                        gr.Markdown("## 📸 View Periodic Snapshots")

                        with gr.Group():
                            gr.Markdown("### 📋 Session ID")
                            snapshots_session_id_input = gr.Textbox(
                                label="Enter Session ID for Snapshots",
                                placeholder="Paste your session ID here...",
                                lines=1
                            )

                            with gr.Row():
                                get_snapshots_btn = gr.Button("📸 Get Snapshots", variant="primary", scale=2)
                                clear_snapshots_btn = gr.Button("🗑️ Clear", variant="secondary", scale=1)

                    with gr.Column(scale=1):
                        gr.Markdown("## 📋 Snapshots Data")

                        snapshots_display = gr.Markdown(
                            """## 📸 View Periodic Snapshots

Enter a Session ID to view periodic snapshots taken during processing.

**Instructions:**
1. Copy the Session ID from your running or completed request
2. Paste it in the Session ID field
3. Click "Get Snapshots" to view progress snapshots
4. Download full snapshots data if needed

**Snapshots include:**
- Timestamp of each snapshot
- Current status and progress
- Thinking process length at each interval
- Number of images generated
- Complete session state data

**Note:** Snapshots are automatically created every 1 minute during processing.
""",
                            height=400
                        )

                        with gr.Row():
                            snapshots_download_file = gr.File(
                                label="📥 Download Snapshots Data",
                                visible=False
                            )

            # JSON Results Tab
            with gr.Tab("📊 Get JSON Results"):
                with gr.Row():
                    with gr.Column(scale=1):
                        gr.Markdown("## 📊 Get Structured Results")

                        with gr.Group():
                            gr.Markdown("### 📋 Session ID")
                            json_session_id_input = gr.Textbox(
                                label="Enter Session ID for JSON Results",
                                placeholder="Paste your session ID here...",
                                lines=1
                            )

                            with gr.Row():
                                get_json_btn = gr.Button("📊 Get JSON Results", variant="primary", scale=2)
                                clear_json_btn = gr.Button("🗑️ Clear", variant="secondary", scale=1)

                    with gr.Column(scale=1):
                        gr.Markdown("## 📋 JSON Results")

                        json_results_display = gr.Markdown(
                            """## 📊 Get JSON Results

Enter a Session ID to get structured JSON results for a completed task.

**Instructions:**
1. Copy the Session ID from your completed request
2. Paste it in the Session ID field
3. Click "Get JSON Results"
4. View structured data and download JSON file

**JSON includes:**
- Session metadata (ID, status, timestamp, language)
- File paths (report, thinking process, images, zip)
- Content (final report, thinking process, raw result)
- Error information (if any)
""",
                            height=400
                        )

                        with gr.Row():
                            json_download_file = gr.File(
                                label="📥 Download JSON Results",
                                visible=False
                            )

            # Stop Task Tab
            with gr.Tab("🛑 Stop Task"):
                with gr.Row():
                    with gr.Column(scale=1):
                        gr.Markdown("## 🛑 Stop Running Task")

                        with gr.Group():
                            gr.Markdown("### 📋 Session ID")
                            stop_session_id_input = gr.Textbox(
                                label="Enter Session ID to Stop",
                                placeholder="Paste your session ID here...",
                                lines=1
                            )

                            with gr.Row():
                                stop_task_btn = gr.Button("🛑 Stop Task", variant="primary", scale=2)
                                clear_stop_btn = gr.Button("🗑️ Clear", variant="secondary", scale=1)

                    with gr.Column(scale=1):
                        gr.Markdown("## 📋 Stop Results")

                        stop_results = gr.Markdown(
                            """## 🛑 Stop Task

Enter a Session ID to stop a running or queued task.

**Instructions:**
1. Copy the Session ID from your submitted request
2. Paste it in the Session ID field
3. Click "Stop Task"
4. Confirmation will appear here

**Note:** You can only stop tasks that are currently queued or processing.
Completed tasks cannot be stopped.
""",
                            height=400
                        )

            # History Tab
            with gr.Tab("📅 History"):
                with gr.Row():
                    with gr.Column(scale=1):
                        gr.Markdown("## 📅 Session History")

                        with gr.Group():
                            gr.Markdown("### 🔍 Select Session")

                            # Refresh history button
                            refresh_history_btn = gr.Button("🔄 Refresh History", variant="secondary")

                            # History selector dropdown
                            history_selector = gr.Dropdown(
                                label="Select a session to view details",
                                choices=get_history_items(),
                                value="",
                                interactive=True
                            )

                            # Button to load selected session
                            load_session_btn = gr.Button("📋 View Session Details", variant="primary")

                    with gr.Column(scale=1):
                        gr.Markdown("## 📋 Session Details")

                        history_results = gr.Markdown(
                            """## 📅 History Selection

Select a session from the dropdown above to view its details.

**Instructions:**
1. Use the refresh button to update the history list
2. Select a session from the dropdown
3. Click "View Session Details" to see status and results
4. Download files if the session is completed

This tab shows all your previous requests and their current status.
""",
                            height=400
                        )

                        with gr.Row():
                            history_download_report = gr.File(
                                label="📥 Download Report",
                                visible=False
                            )
                            history_download_thinking = gr.File(
                                label="📥 Download Thinking Process",
                                visible=False
                            )
                            history_download_zip = gr.File(
                                label="📥 Download Session Files",
                                visible=False
                            )

        # Event handlers
        def update_file_status(files):
            return format_files_info(files)

        def clear_interface():
            return (
                "",  # Clear user input
                """## 📊 Ready to Process

**Status:** 🟢 Waiting for input
**Server:** Not connected

Ready to process your request...
""",  # Reset status
                """## 📋 Results Panel

Ready to display your results...

**Status:** 🟢 Waiting for processing
**Instructions:**
1. Upload files (optional)
2. Enter your request
3. Click "Process" to start
4. Results will appear here

Requests are submitted immediately to FastAPI queue.
You can safely close the page after submission.
""",  # Reset results
                gr.update(visible=False),  # Hide download buttons
                gr.update(visible=False)
            )

        def clear_status_interface():
            return (
                "",  # Clear session ID input
                """## 📋 Status Check

Enter a Session ID to check the status of your request.

**Instructions:**
1. Copy the Session ID from your submitted request
2. Paste it in the Session ID field
3. Click "Check Status"
4. Results will appear here

You can check status multiple times to monitor progress.
""",  # Reset status results
                gr.update(visible=False),  # Hide download buttons
                gr.update(visible=False),
                gr.update(visible=False)  # Hide zip download button
            )

        def clear_stop_interface():
            return (
                "",  # Clear stop session ID input
                """## 🛑 Stop Task

Enter a Session ID to stop a running or queued task.

**Instructions:**
1. Copy the Session ID from your submitted request
2. Paste it in the Session ID field
3. Click "Stop Task"
4. Confirmation will appear here

**Note:** You can only stop tasks that are currently queued or processing.
Completed tasks cannot be stopped.
"""  # Reset stop results
            )

        def clear_json_interface():
            return (
                "",  # Clear JSON session ID input
                """## 📊 Get JSON Results

Enter a Session ID to get structured JSON results for a completed task.

**Instructions:**
1. Copy the Session ID from your completed request
2. Paste it in the Session ID field
3. Click "Get JSON Results"
4. View structured data and download JSON file

**JSON includes:**
- Session metadata (ID, status, timestamp, language)
- File paths (report, thinking process, images, zip)
- Content (final report, thinking process, raw result)
- Error information (if any)
""",  # Reset JSON results
                gr.update(visible=False)  # Hide download file
            )

        def clear_snapshots_interface():
            return (
                "",  # Clear snapshots session ID input
                """## 📸 View Periodic Snapshots

Enter a Session ID to view periodic snapshots taken during processing.

**Instructions:**
1. Copy the Session ID from your running or completed request
2. Paste it in the Session ID field
3. Click "Get Snapshots" to view progress snapshots
4. Download full snapshots data if needed

**Snapshots include:**
- Timestamp of each snapshot
- Current status and progress
- Thinking process length at each interval
- Number of images generated
- Complete session state data

**Note:** Snapshots are automatically created every 1 minute during processing.
""",  # Reset snapshots results
                gr.update(visible=False)  # Hide download file
            )

        # Wire up events
        file_input.change(
            fn=update_file_status,
            inputs=[file_input],
            outputs=[file_status]
        )

        submit_btn.click(
            fn=process_request,
            inputs=[user_input, file_input, server_url, language_choice],
            outputs=[results_display, status_display, download_report, download_thinking]
        )

        clear_btn.click(
            fn=clear_interface,
            outputs=[user_input, status_display, results_display, download_report, download_thinking]
        )

        # Allow Enter key to submit
        user_input.submit(
            fn=process_request,
            inputs=[user_input, file_input, server_url, language_choice],
            outputs=[results_display, status_display, download_report, download_thinking]
        )

        # Status checking events
        check_btn.click(
            fn=check_status,
            inputs=[session_id_input, server_url],
            outputs=[status_results, status_download_report, status_download_thinking, status_download_zip]
        )

        clear_status_btn.click(
            fn=clear_status_interface,
            outputs=[session_id_input, status_results, status_download_report, status_download_thinking, status_download_zip]
        )

        # Allow Enter key to check status
        session_id_input.submit(
            fn=check_status,
            inputs=[session_id_input, server_url],
            outputs=[status_results, status_download_report, status_download_thinking, status_download_zip]
        )

        # Stop task events
        stop_task_btn.click(
            fn=stop_task_by_session_id,
            inputs=[stop_session_id_input, server_url],
            outputs=[stop_results]
        )

        clear_stop_btn.click(
            fn=clear_stop_interface,
            outputs=[stop_session_id_input, stop_results]
        )

        # Allow Enter key to stop task
        stop_session_id_input.submit(
            fn=stop_task_by_session_id,
            inputs=[stop_session_id_input, server_url],
            outputs=[stop_results]
        )

        # JSON results events
        get_json_btn.click(
            fn=get_json_results_by_session_id,
            inputs=[json_session_id_input, server_url],
            outputs=[json_results_display, json_download_file]
        )

        clear_json_btn.click(
            fn=clear_json_interface,
            outputs=[json_session_id_input, json_results_display, json_download_file]
        )

        # Allow Enter key to get JSON results
        json_session_id_input.submit(
            fn=get_json_results_by_session_id,
            inputs=[json_session_id_input, server_url],
            outputs=[json_results_display, json_download_file]
        )

        # Snapshots events
        get_snapshots_btn.click(
            fn=get_snapshots_by_session_id,
            inputs=[snapshots_session_id_input, server_url],
            outputs=[snapshots_display, snapshots_download_file]
        )

        clear_snapshots_btn.click(
            fn=clear_snapshots_interface,
            outputs=[snapshots_session_id_input, snapshots_display, snapshots_download_file]
        )

        # Allow Enter key to get snapshots
        snapshots_session_id_input.submit(
            fn=get_snapshots_by_session_id,
            inputs=[snapshots_session_id_input, server_url],
            outputs=[snapshots_display, snapshots_download_file]
        )

        # History tab event handlers
        def refresh_history_choices():
            """Refresh the history dropdown choices"""
            return gr.update(choices=get_history_items(), value="")

        refresh_history_btn.click(
            fn=refresh_history_choices,
            outputs=[history_selector]
        )

        load_session_btn.click(
            fn=handle_history_item_click,
            inputs=[history_selector, server_url],
            outputs=[history_results, history_download_report, history_download_thinking, history_download_zip]
        )

        # Also allow direct selection to load session
        history_selector.change(
            fn=handle_history_item_click,
            inputs=[history_selector, server_url],
            outputs=[history_results, history_download_report, history_download_thinking, history_download_zip]
        )

    return demo


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Gradio Interface for FastAPI Agent Server")
    parser.add_argument("--server_port", type=int, default=7861, help="Port to run the Gradio server on (default: 7862)")
    parser.add_argument("--fastapi_url", type=str, default="http://localhost:8002", help="FastAPI server URL")
    args = parser.parse_args()

    print(f"Starting Gradio interface on port {args.server_port}")
    print(f"Configured to connect to FastAPI server at: {args.fastapi_url}")

    demo = create_interface(args.fastapi_url)
    demo.launch(
        server_name="0.0.0.0",
        server_port=args.server_port,
        share=True,
        debug=True
    )
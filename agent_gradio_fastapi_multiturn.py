"""
Multi-Turn Gradio Interface for FastAPI Agent Server

This interface provides a multi-turn conversation frontend that communicates with the FastAPI agent server:
- Submit initial requests to start new conversations
- Continue conversations with follow-up questions
- View complete conversation history with all turns
- Check status with merged history and snapshots view
- Stop tasks with history selection
- Context-aware multi-turn interactions
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


class FastAPIClient:
    """Client for communicating with the FastAPI agent server"""

    def __init__(self, base_url: str = "http://localhost:8001"):
        # Ensure URL has proper protocol
        if not base_url.startswith(('http://', 'https://')):
            base_url = f"http://{base_url}"
        self.base_url = base_url.rstrip('/')

    def health_check(self) -> bool:
        """Check if the FastAPI server is healthy"""
        try:
            print(f"Attempting to connect to: {self.base_url}/health")
            response = requests.get(f"{self.base_url}/health", timeout=5)
            print(f"Health check response: {response.status_code}")
            return response.status_code == 200
        except Exception as e:
            print(f"Health check failed: {e}")
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

    def get_all_sessions(self) -> List[dict]:
        """Get all sessions from server storage and active sessions"""
        all_sessions = []
        session_ids_seen = set()

        try:
            # First, get stored/completed sessions from /all-sessions
            print(f"Fetching stored sessions from: {self.base_url}/all-sessions")
            response = requests.get(f"{self.base_url}/all-sessions", timeout=10)
            if response.status_code == 200:
                data = response.json()
                stored_sessions = data.get("sessions", [])
                print(f"Retrieved {len(stored_sessions)} stored sessions")
                for session in stored_sessions:
                    session_id = session.get("session_id", "")
                    if session_id and session_id not in session_ids_seen:
                        all_sessions.append(session)
                        session_ids_seen.add(session_id)
            else:
                print(f"All-sessions endpoint returned {response.status_code}")

            # Then, get active sessions from /sessions
            print(f"Fetching active sessions from: {self.base_url}/sessions")
            response = requests.get(f"{self.base_url}/sessions", timeout=10)
            if response.status_code == 200:
                active_sessions = response.json()
                print(f"Retrieved {len(active_sessions)} active sessions")
                # Convert to expected format and merge
                for session in active_sessions:
                    session_id = session.get("session_id", "")
                    if session_id and session_id not in session_ids_seen:
                        formatted_session = {
                            "session_id": session_id,
                            "query": session.get("query", "No query available"),
                            "full_query": session.get("query", "No query available"),
                            "language": session.get("language", "en"),
                            "timestamp": session.get("created_at", ""),
                            "status": session.get("status", "unknown"),
                            "is_complete": session.get("status") in ["completed", "error", "cancelled"]
                        }
                        all_sessions.append(formatted_session)
                        session_ids_seen.add(session_id)
            else:
                print(f"Sessions endpoint returned {response.status_code}")

            print(f"Total merged sessions: {len(all_sessions)}")
            return all_sessions

        except Exception as e:
            print(f"Error getting all sessions: {e}")
            return []

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

    # Multi-Turn Methods
    def continue_session(self, session_id: str, message: str, language: str = "en") -> Optional[dict]:
        """Continue an existing multi-turn session with a new message"""
        try:
            data = {
                "session_id": session_id,
                "message": message,
                "language": language
            }
            response = requests.post(f"{self.base_url}/continue-session", json=data, timeout=30)
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            print(f"Error continuing session: {e}")
            return None

    def get_multiturn_session(self, session_id: str) -> Optional[dict]:
        """Get complete multi-turn session history"""
        try:
            response = requests.get(f"{self.base_url}/multiturn-session/{session_id}", timeout=10)
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            print(f"Error getting multi-turn session: {e}")
            return None

    def get_all_multiturn_sessions(self) -> List[dict]:
        """Get all multi-turn sessions"""
        try:
            response = requests.get(f"{self.base_url}/multiturn-sessions", timeout=10)
            if response.status_code == 200:
                data = response.json()
                return data.get("sessions", [])
            return []
        except Exception as e:
            print(f"Error getting multi-turn sessions: {e}")
            return []

    def get_turn_report(self, session_id: str, turn_number: int) -> Optional[dict]:
        """Get specific turn report from multi-turn session"""
        try:
            response = requests.get(f"{self.base_url}/turn-report/{session_id}/{turn_number}", timeout=10)
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            print(f"Error getting turn report: {e}")
            return None

    def get_session_context(self, session_id: str) -> Optional[dict]:
        """Get accumulated context for a multi-turn session"""
        try:
            response = requests.get(f"{self.base_url}/session-context/{session_id}", timeout=10)
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            print(f"Error getting session context: {e}")
            return None


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
    """Process request using FastAPI backend - submit immediately and return session ID"""
    if not message.strip():
        return (
            "## ❌ Error\n\nPlease enter a request to process.",
            "## ❌ No Input\n\nPlease enter a request to process."
        )

    # Initialize client
    client = FastAPIClient(server_url)

    # Check server health
    if not client.health_check():
        return (
            "## ❌ Server Error\n\nCannot connect to FastAPI server. Please ensure the server is running.",
            "## ❌ Server Error\n\nCannot connect to FastAPI server."
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
                "## ❌ Submission Error\n\nFailed to submit request to server queue."
            )

        # Upload files if provided
        if file_paths:
            upload_success = client.upload_files(session_id, file_paths)
            if not upload_success:
                return (
                    "## ❌ Upload Error\n\nFailed to upload files to server.",
                    "## ❌ Upload Error\n\nFailed to upload files to server."
                )

        # Return immediate confirmation - FastAPI will handle the queue
        status_display = f"""## 🚀 Request Submitted Successfully

**Status:** 📋 Queued for processing
**Session ID:** `{session_id}`
**Submitted:** {datetime.now().strftime('%H:%M:%S')}

Your request has been submitted to the FastAPI queue.
Processing will continue even if you close this page.
You can check status using Session ID: `{session_id}`"""

        result_display = f"""## 📋 Request Submitted to Queue

**Session ID:** `{session_id}`
**Submitted:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**Language:** {language.upper()}

Your request has been added to the processing queue. The FastAPI server will handle the processing independently.

**Files uploaded:** {len(file_paths) if file_paths else 0}

**Request:** {message[:200]}{'...' if len(message) > 200 else ''}

---

### 🔄 Processing Status

The task is now queued for processing. You can:
1. Close this page safely - processing will continue
2. Check status using the Session ID above
3. Return later to retrieve results

Processing will be handled by the FastAPI server queue system."""

        return (
            result_display,
            status_display
        )

    except Exception as e:
        error_msg = f"""## ❌ System Error

**Error:** {str(e)}
**Timestamp:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Please check the server connection and try again."""
        return (
            error_msg,
            "## ❌ System Error\n\nError details displayed in the results panel →"
        )


async def check_status_with_history(session_id: str, server_url: str):
    """Check status of a session with integrated history and snapshots"""
    if not session_id.strip():
        return (
            "## ❌ Error\n\nPlease enter a Session ID to check status.",
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
        # Get status data
        status_data = client.get_status(session_id)
        if not status_data:
            return (
                f"## ❌ Session Not Found\n\nSession ID '{session_id}' not found on server.",
                gr.update(visible=False)
            )

        # Get snapshots data
        snapshots_data = client.get_snapshots(session_id)

        # Format simplified status display
        current_status = status_data.get("status", "unknown")
        is_complete = status_data.get("is_complete", False)

        # Main status section
        status_emoji = {
            'queued': '📋',
            'processing': '🔄',
            'completed': '✅',
            'failed': '❌',
            'error': '❌',
            'cancelled': '🛑'
        }.get(current_status, '❓')

        result_display = f"""## {status_emoji} Session: {session_id[:8]}...

**Status:** {current_status.title()}
**Complete:** {'Yes' if is_complete else 'No'}
**Created:** {status_data.get('created_at', 'N/A')}"""

        # Add error information if available
        if status_data.get("error"):
            result_display += f"""
**Error:** {status_data['error']}"""

        # Add simplified snapshots with full text
        if snapshots_data:
            snapshots = snapshots_data.get("snapshots", [])
            if snapshots:
                result_display += f"""

## 📸 All Snapshots ({len(snapshots)} total) - Scroll Down for Full Content

*All snapshots are displayed below in chronological order. Scroll down to view complete content.*

"""
                for i, snapshot in enumerate(snapshots, 1):
                    snap_time = snapshot.get("timestamp", "N/A")
                    try:
                        dt = datetime.fromisoformat(snap_time.replace('Z', '+00:00'))
                        formatted_time = dt.strftime('%Y-%m-%d %H:%M:%S')
                    except:
                        formatted_time = snap_time

                    # Get thinking content
                    content = snapshot.get("content", {})
                    thinking_content = content.get("thinking_content", "")

                    # Add character count for transparency
                    char_count = len(thinking_content) if thinking_content else 0

                    result_display += f"""
---

### 📸 Snapshot #{i} - {formatted_time}
**Content Size:** {char_count:,} characters

```
{thinking_content if thinking_content else 'No thinking content available'}
```

"""
            else:
                result_display += """

## 📸 Snapshots

No snapshots available yet."""

        # Add completion download if completed
        if is_complete and current_status == "completed":
            # Get the final report for completed sessions
            results_data = client.get_json_results(session_id)
            if results_data and 'content' in results_data and 'final_report' in results_data['content']:
                final_report = results_data['content']['final_report']
                if final_report:
                    result_display += f"""

## 📋 Final Report

{final_report}

"""

            # Only show ZIP download for completed sessions
            zip_file = client.download_zip(session_id)

            return (
                result_display,
                gr.update(visible=True, value=zip_file) if zip_file else gr.update(visible=False)  # Show ZIP download
            )

        return (
            result_display,
            gr.update(visible=False)  # Hide ZIP download for incomplete sessions
        )

    except Exception as e:
        error_msg = f"""## ❌ Status Check Error

**Error:** {str(e)}
**Session ID:** {session_id}
**Timestamp:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""
        return (
            error_msg,
            gr.update(visible=False)
        )


def get_session_history(server_url: str) -> List[tuple]:
    """Get session history for dropdown selection"""
    try:
        client = FastAPIClient(server_url)
        if not client.health_check():
            return [("Server not available", "")]

        sessions = client.get_all_sessions()
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
                    dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    time_str = dt.strftime('%m/%d %H:%M')
                except:
                    time_str = timestamp[:16]
            else:
                time_str = 'Unknown'

            # Create display label
            label = f"{status_emoji} {time_str} - {session.get('query', 'No query')[:50]}..."
            items.append((label, session['session_id']))

        return items
    except Exception as e:
        print(f"Error getting session history: {e}")
        return [("Error loading history", "")]


async def stop_task_by_session_id(session_id: str, server_url: str):
    """Stop a task by session ID"""
    if not session_id or session_id.strip() == "":
        return "## ❌ Error\n\nPlease select a session to stop the task."

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

**Session ID:** `{session_id}`
**Status:** Cancelled by user
**Timestamp:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

The task has been successfully cancelled."""
        else:
            return f"""## ❌ Failed to Stop Task

**Session ID:** `{session_id}`
**Timestamp:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Failed to stop the task. It may have already completed or there was a server error."""

    except Exception as e:
        return f"""## ❌ Error Stopping Task

**Error:** {str(e)}
**Session ID:** `{session_id}`
**Timestamp:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""


def create_interface(default_fastapi_url: str = "http://localhost:8001"):
    """Create the simplified Gradio interface"""

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
                        <p style="margin: 8px 0 0 0; font-size: 1.1em; color: #6c757d; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;">Multi-Turn Conversation Interface</p>
                        <p style="margin: 4px 0 0 0; font-size: 0.9em; color: #28a745; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;">💬 Context-Aware Conversations</p>
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

Ready to process your request...""",
                                height=150
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
You can safely close the page after submission.""",
                            height=600
                        )

            # Check Status Tab
            with gr.Tab("🔍 Check Status"):
                with gr.Row():
                    with gr.Column(scale=1):
                        gr.Markdown("## 🔍 Check Request Status")

                        with gr.Group():
                            gr.Markdown("### 📋 Session Selection")

                            # Refresh session list button
                            refresh_status_history_btn = gr.Button("🔄 Refresh Session List", variant="secondary")

                            # Session selector dropdown
                            status_session_selector = gr.Dropdown(
                                label="Select a session to check status",
                                choices=get_session_history(default_fastapi_url),
                                value="",
                                interactive=True
                            )

                            with gr.Row():
                                check_btn = gr.Button("🔍 Check Status", variant="primary", scale=2)
                                clear_status_btn = gr.Button("🗑️ Clear", variant="secondary", scale=1)

                    with gr.Column(scale=1):
                        gr.Markdown("## 📋 Status Results")

                        status_results = gr.Markdown(
                            """## 📋 Status Check

Select a session from the dropdown to check status and view complete snapshots.

**Features:**
- Real-time status updates
- Complete snapshots view (no truncation)
- Full session history with scrollable window
- Download results when completed

**Instructions:**
1. Click "🔄 Refresh Session List" to load all sessions
2. Select a session from the dropdown (shows both active and completed sessions)
3. Click "🔍 Check Status"

All snapshots are displayed in full in a scrollable window without any character limits or truncation.""",
                            max_height="600px"
                        )

                        # Only show session ZIP download when completed
                        status_download_zip = gr.File(
                            label="📥 Download Session Files",
                            visible=False
                        )

            # Stop Task Tab
            with gr.Tab("🛑 Stop Task"):
                with gr.Row():
                    with gr.Column(scale=1):
                        gr.Markdown("## 🛑 Stop Running Task")

                        with gr.Group():
                            gr.Markdown("### 📋 Select Session")

                            # Refresh history button
                            refresh_stop_history_btn = gr.Button("🔄 Refresh Session List", variant="secondary")

                            # History selector dropdown
                            stop_session_selector = gr.Dropdown(
                                label="Select a session to stop",
                                choices=get_session_history(default_fastapi_url),
                                value="",
                                interactive=True
                            )

                            with gr.Row():
                                stop_task_btn = gr.Button("🛑 Stop Selected Task", variant="primary", scale=2)
                                clear_stop_btn = gr.Button("🗑️ Clear", variant="secondary", scale=1)

                    with gr.Column(scale=1):
                        gr.Markdown("## 📋 Stop Results")

                        stop_results = gr.Markdown(
                            """## 🛑 Stop Task

Select a session from the dropdown above to stop a running or queued task.

**Instructions:**
1. Click "Refresh Session List" to update the list
2. Select a session from the dropdown
3. Click "Stop Selected Task"
4. Confirmation will appear here

**Note:** You can only stop tasks that are currently queued or processing.
Completed tasks cannot be stopped.""",
                            height=400
                        )

            # Multi-Turn Conversation Tab
            with gr.Tab("💬 Multi-Turn Chat"):
                with gr.Row():
                    with gr.Column(scale=1):
                        gr.Markdown("## 💬 Continue Conversations")

                        with gr.Group():
                            gr.Markdown("### 🆕 Start New or Continue Existing")

                            # Session mode selector
                            session_mode = gr.Radio(
                                ["Start New Session", "Continue Existing Session"],
                                value="Start New Session",
                                label="Session Mode"
                            )

                            # Existing session selector (initially hidden)
                            refresh_multiturn_sessions_btn = gr.Button(
                                "🔄 Refresh Sessions",
                                variant="secondary",
                                visible=False
                            )

                            existing_session_selector = gr.Dropdown(
                                label="Select existing session to continue",
                                choices=[],
                                value="",
                                interactive=True,
                                visible=False
                            )

                            # New conversation inputs
                            new_conversation_group = gr.Group(visible=True)
                            with new_conversation_group:
                                multiturn_query = gr.Textbox(
                                    label="Your Question or Request",
                                    placeholder="What would you like me to help you with?",
                                    lines=3,
                                    max_lines=5
                                )

                                with gr.Row():
                                    multiturn_language = gr.Dropdown(
                                        choices=["en", "zh"],
                                        value="en",
                                        label="Language"
                                    )

                                with gr.Row():
                                    start_conversation_btn = gr.Button(
                                        "🚀 Start New Conversation",
                                        variant="primary",
                                        scale=3
                                    )
                                    clear_multiturn_btn = gr.Button(
                                        "🗑️ Clear",
                                        variant="secondary",
                                        scale=1
                                    )

                            # Continue conversation inputs (initially hidden)
                            continue_conversation_group = gr.Group(visible=False)
                            with continue_conversation_group:
                                continue_query = gr.Textbox(
                                    label="Follow-up Question or Request",
                                    placeholder="What else would you like to know or do?",
                                    lines=3,
                                    max_lines=5
                                )

                                with gr.Row():
                                    continue_conversation_btn = gr.Button(
                                        "💬 Continue Conversation",
                                        variant="primary",
                                        scale=3
                                    )
                                    clear_continue_btn = gr.Button(
                                        "🗑️ Clear",
                                        variant="secondary",
                                        scale=1
                                    )

                    with gr.Column(scale=2):
                        gr.Markdown("## 📋 Conversation History & Results")

                        # Progress indicator
                        multiturn_progress = gr.Markdown(
                            """## 💬 Multi-Turn Conversations

Choose to start a new conversation or continue an existing one from the left panel.

**Multi-Turn Features:**
- 🆕 Start new conversations with complex questions
- 💬 Continue conversations with follow-up questions
- 🧠 Context preservation across turns
- 📊 View complete conversation history
- 📁 Download all session files

**Instructions:**
1. Choose "Start New Session" or "Continue Existing Session"
2. For new sessions: Enter your question and click "Start New Conversation"
3. For continuing: Select a session, enter follow-up question, click "Continue Conversation"
4. Monitor progress and view results below""",
                            visible=True
                        )

                        # Conversation display
                        conversation_display = gr.Markdown(
                            "",
                            visible=False,
                            height=500
                        )

                        # Session info
                        multiturn_session_info = gr.Markdown(
                            "",
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

Ready to process your request...""",  # Reset status
                """## 📋 Results Panel

Ready to display your results...

**Status:** 🟢 Waiting for processing
**Instructions:**
1. Upload files (optional)
2. Enter your request
3. Click "Process" to start
4. Results will appear here

Requests are submitted immediately to FastAPI queue.
You can safely close the page after submission."""  # Reset results
            )

        def clear_status_interface():
            return (
                "",  # Clear dropdown selection
                """## 📋 Status Check

Select a session from the dropdown to check status and view complete snapshots.

**Features:**
- Real-time status updates
- Complete snapshots view (no truncation)
- Full session history
- Download results when completed

**Instructions:**
1. Click "🔄 Refresh Session List" to load all sessions
2. Select a session from the dropdown (shows both active and completed sessions)
3. Click "🔍 Check Status"

All snapshots are displayed in full without any character limits or truncation.""",  # Reset status results
                gr.update(visible=False)  # Hide download button
            )

        def clear_stop_interface():
            return (
                "",  # Clear selection
                """## 🛑 Stop Task

Select a session from the dropdown above to stop a running or queued task.

**Instructions:**
1. Click "Refresh Session List" to update the list
2. Select a session from the dropdown
3. Click "Stop Selected Task"
4. Confirmation will appear here

**Note:** You can only stop tasks that are currently queued or processing.
Completed tasks cannot be stopped."""  # Reset stop results
            )

        def refresh_stop_history():
            """Refresh the stop task session list"""
            return gr.update(choices=get_session_history(server_url.value), value="")

        def refresh_status_history():
            """Refresh the status check session list"""
            return gr.update(choices=get_session_history(server_url.value), value="")

        async def check_status_from_dropdown(selected_session_id, server_url_value):
            """Check status using dropdown selection"""
            if not selected_session_id:
                return await check_status_with_history("", server_url_value)
            return await check_status_with_history(selected_session_id, server_url_value)

        # Wire up events
        file_input.change(
            fn=update_file_status,
            inputs=[file_input],
            outputs=[file_status]
        )

        submit_btn.click(
            fn=process_request,
            inputs=[user_input, file_input, server_url, language_choice],
            outputs=[results_display, status_display]
        )

        clear_btn.click(
            fn=clear_interface,
            outputs=[user_input, status_display, results_display]
        )

        # Allow Enter key to submit
        user_input.submit(
            fn=process_request,
            inputs=[user_input, file_input, server_url, language_choice],
            outputs=[results_display, status_display]
        )

        # Status checking events
        # Refresh status session list
        refresh_status_history_btn.click(
            fn=refresh_status_history,
            outputs=[status_session_selector]
        )

        # Check status using dropdown selection
        check_btn.click(
            fn=check_status_from_dropdown,
            inputs=[status_session_selector, server_url],
            outputs=[status_results, status_download_zip]
        )

        clear_status_btn.click(
            fn=clear_status_interface,
            outputs=[status_session_selector, status_results, status_download_zip]
        )

        # Stop task events
        refresh_stop_history_btn.click(
            fn=refresh_stop_history,
            outputs=[stop_session_selector]
        )

        stop_task_btn.click(
            fn=stop_task_by_session_id,
            inputs=[stop_session_selector, server_url],
            outputs=[stop_results]
        )

        clear_stop_btn.click(
            fn=clear_stop_interface,
            outputs=[stop_session_selector, stop_results]
        )

        # Multi-turn conversation events
        def toggle_session_mode(mode):
            """Toggle between new session and continue session modes"""
            if mode == "Start New Session":
                return (
                    gr.update(visible=True),   # new_conversation_group
                    gr.update(visible=False),  # continue_conversation_group
                    gr.update(visible=False),  # refresh_multiturn_sessions_btn
                    gr.update(visible=False)   # existing_session_selector
                )
            else:  # Continue Existing Session
                return (
                    gr.update(visible=False),  # new_conversation_group
                    gr.update(visible=True),   # continue_conversation_group
                    gr.update(visible=True),   # refresh_multiturn_sessions_btn
                    gr.update(visible=True)    # existing_session_selector
                )

        def get_multiturn_sessions():
            """Get list of multi-turn sessions"""
            try:
                client = FastAPIClient(server_url.value)
                sessions_data = client.get_multiturn_sessions()
                if sessions_data and 'sessions' in sessions_data:
                    sessions = sessions_data['sessions']
                    choices = []
                    for session in sessions:
                        session_id = session['session_id']
                        status = session.get('session_status', 'unknown')
                        turns = session.get('total_turns', 0)
                        choices.append(f"{session_id} (Status: {status}, Turns: {turns})")
                    return choices
                return []
            except Exception as e:
                print(f"Error getting multiturn sessions: {e}")
                return []

        def refresh_multiturn_sessions():
            """Refresh the multi-turn sessions dropdown"""
            choices = get_multiturn_sessions()
            return gr.update(choices=choices, value="")

        def start_new_conversation(query, language, url):
            """Start a new multi-turn conversation"""
            if not query.strip():
                return (
                    gr.update(value="Please enter a question or request to start the conversation.", visible=True),
                    gr.update(visible=False),
                    gr.update(visible=False)
                )

            try:
                client = FastAPIClient(url)
                response = client.submit_request(query, [], language)

                if response and 'session_id' in response:
                    session_id = response['session_id']

                    # Show initial progress
                    progress_text = f"""## 🚀 New Conversation Started

**Session ID:** `{session_id}`
**Status:** Processing...
**Query:** {query}

Please wait while I process your request..."""

                    return (
                        gr.update(value=progress_text, visible=True),
                        gr.update(visible=False),
                        gr.update(visible=False)
                    )
                else:
                    return (
                        gr.update(value="❌ Failed to start conversation. Please try again.", visible=True),
                        gr.update(visible=False),
                        gr.update(visible=False)
                    )

            except Exception as e:
                return (
                    gr.update(value=f"❌ Error starting conversation: {str(e)}", visible=True),
                    gr.update(visible=False),
                    gr.update(visible=False)
                )

        def continue_existing_conversation(session_selection, query, url):
            """Continue an existing multi-turn conversation"""
            if not session_selection or not query.strip():
                return (
                    gr.update(value="Please select a session and enter a follow-up question.", visible=True),
                    gr.update(visible=False),
                    gr.update(visible=False)
                )

            try:
                # Extract session ID from selection
                session_id = session_selection.split(' ')[0]

                client = FastAPIClient(url)
                response = client.continue_session(session_id, query)

                if response and 'session_id' in response:
                    # Show progress
                    progress_text = f"""## 💬 Conversation Continued

**Session ID:** `{session_id}`
**Status:** Processing...
**Follow-up Query:** {query}

Please wait while I process your follow-up request..."""

                    return (
                        gr.update(value=progress_text, visible=True),
                        gr.update(visible=False),
                        gr.update(visible=False)
                    )
                else:
                    return (
                        gr.update(value="❌ Failed to continue conversation. Please try again.", visible=True),
                        gr.update(visible=False),
                        gr.update(visible=False)
                    )

            except Exception as e:
                return (
                    gr.update(value=f"❌ Error continuing conversation: {str(e)}", visible=True),
                    gr.update(visible=False),
                    gr.update(visible=False)
                )

        def clear_multiturn_interface():
            """Clear the multi-turn interface"""
            return (
                "",  # multiturn_query
                gr.update(value="", choices=get_multiturn_sessions()),  # existing_session_selector
                gr.update(value="## 💬 Multi-Turn Conversations\n\nChoose to start a new conversation or continue an existing one from the left panel.", visible=True),  # multiturn_progress
                gr.update(value="", visible=False),  # conversation_display
                gr.update(value="", visible=False)   # multiturn_session_info
            )

        def clear_continue_interface():
            """Clear the continue conversation interface"""
            return ""  # continue_query

        # Multi-turn event handlers
        session_mode.change(
            fn=toggle_session_mode,
            inputs=[session_mode],
            outputs=[new_conversation_group, continue_conversation_group, refresh_multiturn_sessions_btn, existing_session_selector]
        )

        refresh_multiturn_sessions_btn.click(
            fn=refresh_multiturn_sessions,
            outputs=[existing_session_selector]
        )

        start_conversation_btn.click(
            fn=start_new_conversation,
            inputs=[multiturn_query, multiturn_language, server_url],
            outputs=[multiturn_progress, conversation_display, multiturn_session_info]
        )

        continue_conversation_btn.click(
            fn=continue_existing_conversation,
            inputs=[existing_session_selector, continue_query, server_url],
            outputs=[multiturn_progress, conversation_display, multiturn_session_info]
        )

        clear_multiturn_btn.click(
            fn=clear_multiturn_interface,
            outputs=[multiturn_query, existing_session_selector, multiturn_progress, conversation_display, multiturn_session_info]
        )

        clear_continue_btn.click(
            fn=clear_continue_interface,
            outputs=[continue_query]
        )

        # Initialize session lists on load
        demo.load(
            fn=lambda url: (
                refresh_status_history(),
                refresh_stop_history()
            ),
            inputs=[server_url],
            outputs=[status_session_selector, stop_session_selector]
        )

    return demo


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Simplified Gradio Interface for FastAPI Agent Server")
    parser.add_argument("--server_port", type=int, default=7861, help="Port to run the Gradio server on (default: 7861)")
    parser.add_argument("--fastapi_url", type=str, default="http://localhost:8001", help="FastAPI server URL")
    args = parser.parse_args()

    print(f"Starting simplified Gradio interface on port {args.server_port}")
    print(f"Configured to connect to FastAPI server at: {args.fastapi_url}")

    demo = create_interface(args.fastapi_url)
    demo.launch(
        server_name="0.0.0.0",
        server_port=args.server_port,
        share=True,
        debug=True
    )
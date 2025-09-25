"""
Simplified Gradio Interface for FastAPI Agent Server

This is a simplified interface that provides basic multi-turn conversation functionality:
- Submit queries and view results
- Continue conversations with follow-up questions
- View conversation history
- Stop running tasks
- No user management, delete, or trash features
- All users default to: test_user_dleader
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

    def submit_request(self, message: str, language: str = "en", user_id: str = None, files: list = None) -> Optional[str]:
        """Submit a chat request with optional file uploads and return session ID"""
        try:
            if not user_id:
                print("Error: user_id is required for submit_request")
                return None

            data = {
                "message": message,
                "language": language,
                "user_id": user_id
            }

            # Prepare files for upload if provided
            files_data = None
            if files:
                files_data = []
                for file_path in files:
                    if file_path and os.path.exists(file_path):
                        filename = os.path.basename(file_path)
                        with open(file_path, 'rb') as f:
                            files_data.append(('files', (filename, f.read(), 'application/octet-stream')))

            print(f"Submitting request to /chat-queue with user_id={user_id}, files={len(files) if files else 0}")
            response = requests.post(f"{self.base_url}/chat-queue", data=data, files=files_data, timeout=30)

            if response.status_code == 200:
                result = response.json()
                print(f"Successfully submitted request, session_id: {result.get('session_id')}")
                return result.get("session_id")
            elif response.status_code == 422:
                print(f"Validation error (422): Missing required parameters. Response: {response.text}")
            else:
                print(f"Error {response.status_code}: {response.text}")
            return None
        except Exception as e:
            print(f"Error submitting request: {e}")
            return None


    def get_status(self, session_id: str, user_id: str) -> Optional[dict]:
        """Get status for a session"""
        try:
            response = requests.get(f"{self.base_url}/status/{session_id}",
                                  params={"user_id": user_id}, timeout=10)
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            print(f"Error getting status: {e}")
            return None

    def stop_task(self, session_id: str, user_id: str) -> bool:
        """Stop a running or queued task"""
        try:
            response = requests.post(f"{self.base_url}/stop/{session_id}",
                                   params={"user_id": user_id}, timeout=10)
            return response.status_code == 200
        except Exception as e:
            print(f"Error stopping task: {e}")
            return False

    def get_json_results(self, session_id: str, user_id: str) -> Optional[dict]:
        """Get structured JSON results for a completed session"""
        try:
            response = requests.get(f"{self.base_url}/results/{session_id}",
                                  params={"user_id": user_id}, timeout=10)
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            print(f"Error getting JSON results: {e}")
            return None

    def get_snapshots(self, session_id: str, user_id: str) -> Optional[dict]:
        """Get all periodic snapshots for a session"""
        try:
            response = requests.get(f"{self.base_url}/snapshots/{session_id}",
                                  params={"user_id": user_id}, timeout=10)
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            print(f"Error getting snapshots: {e}")
            return None

    def get_all_sessions(self, user_id: str = None) -> List[dict]:
        """Get all sessions from server storage and active sessions"""
        all_sessions = []
        session_ids_seen = set()

        try:
            # First, get stored/completed sessions from /all-sessions
            url = f"{self.base_url}/all-sessions"
            params = {}
            if user_id:
                params["user_id"] = user_id
            print(f"Fetching stored sessions from: {url} with params: {params}")
            response = requests.get(url, params=params, timeout=10)
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

            # Note: /all-sessions already includes both stored and active sessions with proper user filtering
            # No need to call /sessions separately to avoid security issues

            print(f"Total merged sessions: {len(all_sessions)}")
            return all_sessions

        except Exception as e:
            print(f"Error getting all sessions: {e}")
            return []

    def get_download_url(self, session_id: str, user_id: str) -> Optional[str]:
        """Get download URL for a completed session (API URL only - no local files)"""
        try:
            # Try to get direct download URL first (for cloud sessions)
            response = requests.get(f"{self.base_url}/download-urls/{session_id}",
                                  params={"user_id": user_id}, timeout=10)
            if response.status_code == 200:
                data = response.json()
                # Return the main session zip URL if available
                files = data.get("files", {})
                if "session_zip" in files and "presigned_url" in files["session_zip"]:
                    return files["session_zip"]["presigned_url"]
        except Exception as e:
            print(f"Error getting download URL: {e}")

        # Fallback to direct download endpoint URL (will redirect to S3 or serve local)
        return f"{self.base_url}/download/{session_id}?user_id={user_id}"

    def get_download_urls(self, session_id: str, user_id: str) -> Optional[dict]:
        """Get direct download URLs for cloud sessions (returns S3 presigned URLs)"""
        try:
            response = requests.get(f"{self.base_url}/download-urls/{session_id}",
                                  params={"user_id": user_id}, timeout=10)
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            print(f"Error getting download URLs: {e}")
            return None

    # Multi-Turn Methods
    def continue_session(self, session_id: str, message: str, language: str = "en", user_id: str = None, files: list = None) -> Optional[dict]:
        """Continue an existing multi-turn session with a new message and optional file uploads"""
        try:
            if not user_id:
                print("Error: user_id is required for continue_session")
                return None

            data = {
                "session_id": session_id,
                "message": message,
                "language": language,
                "user_id": user_id
            }

            # Prepare files for upload if provided
            files_data = None
            if files:
                files_data = []
                for file_path in files:
                    if file_path and os.path.exists(file_path):
                        filename = os.path.basename(file_path)
                        with open(file_path, 'rb') as f:
                            files_data.append(('files', (filename, f.read(), 'application/octet-stream')))

            print(f"Continuing session {session_id} with user_id={user_id}, files={len(files) if files else 0}")
            response = requests.post(f"{self.base_url}/continue-session", data=data, files=files_data, timeout=30)

            if response.status_code == 200:
                result = response.json()
                print(f"Successfully continued session {session_id}, turn: {result.get('turn_number')}")
                return result
            elif response.status_code == 422:
                print(f"Validation error (422): Missing required parameters. Response: {response.text}")
            elif response.status_code == 403:
                print(f"Access denied (403): User {user_id} cannot access session {session_id}")
            elif response.status_code == 404:
                print(f"Session not found (404): Session {session_id} does not exist")
            else:
                print(f"Error {response.status_code}: {response.text}")
            return None
        except Exception as e:
            print(f"Error continuing session: {e}")
            return None

    def get_multiturn_session(self, session_id: str, user_id: str) -> Optional[dict]:
        """Get complete multi-turn session history"""
        try:
            response = requests.get(f"{self.base_url}/multiturn-session/{session_id}",
                                  params={"user_id": user_id}, timeout=10)
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            print(f"Error getting multi-turn session: {e}")
            return None

    def get_all_multiturn_sessions(self, user_id: str = None) -> List[dict]:
        """Get all multi-turn sessions"""
        try:
            url = f"{self.base_url}/multiturn-sessions"
            params = {}
            if user_id:
                params["user_id"] = user_id
            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                return data.get("sessions", [])
            return []
        except Exception as e:
            print(f"Error getting multi-turn sessions: {e}")
            return []

    def get_turn_report(self, session_id: str, turn_number: int, user_id: str) -> Optional[dict]:
        """Get specific turn report from multi-turn session"""
        try:
            response = requests.get(f"{self.base_url}/turn-report/{session_id}/{turn_number}",
                                  params={"user_id": user_id}, timeout=10)
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            print(f"Error getting turn report: {e}")
            return None

    def get_session_context(self, session_id: str, user_id: str) -> Optional[dict]:
        """Get accumulated context for a multi-turn session"""
        try:
            response = requests.get(f"{self.base_url}/session-context/{session_id}",
                                  params={"user_id": user_id}, timeout=10)
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





async def check_status_with_history(session_id: str, server_url: str, user_id: str):
    """Check status of a session with integrated history and snapshots"""
    if not session_id.strip():
        return "## ❌ Error\n\nPlease enter a Session ID to check status.", gr.update(visible=False)

    # Initialize client
    client = FastAPIClient(server_url)

    # Check server health
    if not client.health_check():
        return "## ❌ Server Error\n\nCannot connect to FastAPI server. Please ensure the server is running.", gr.update(visible=False)

    try:
        # Get status data
        status_data = client.get_status(session_id, user_id)
        if not status_data:
            return f"## ❌ Session Not Found\n\nSession ID '{session_id}' not found on server.", gr.update(visible=False)

        # Get snapshots data
        snapshots_data = client.get_snapshots(session_id, user_id)

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
            results_data = client.get_json_results(session_id, user_id)
            if results_data and 'content' in results_data and 'final_report' in results_data['content']:
                final_report = results_data['content']['final_report']
                if final_report:
                    result_display += f"""

## 📋 Final Report

{final_report}

"""

            # For completed sessions, show S3 download links
            download_urls = client.get_download_urls(session_id, user_id)
            download_url = client.get_download_url(session_id, user_id)

            # Show S3 direct download links if available
            if download_urls and 'files' in download_urls:
                result_display += """

## 📥 Direct S3 Download Links

**Session Files - Click links to download directly from cloud storage:**

"""
                files = download_urls['files']
                for file_type, url_info in files.items():
                    if isinstance(url_info, dict) and 'presigned_url' in url_info:
                        url = url_info['presigned_url']
                        size = url_info.get('size', 'Unknown size')
                        result_display += f"""- **{file_type.replace('_', ' ').title()}**:
  - S3 URL: `{url}`
  - Size: {size}
  - [Direct Download Link]({url})

"""

                result_display += f"""*⏰ Links expire in {download_urls.get('expires_in', 'Unknown')} minutes*

"""

            # Show main session download S3 link
            if download_url:
                result_display += f"""

## 📦 Main Session Package

**Primary Download URL:**
```
{download_url}
```

**Direct Download Link**: [Download ZIP]({download_url})

*Copy the URL above to download directly, or click the link*
"""

            return result_display, gr.update(visible=False)

        # For non-completed sessions, hide download component
        return result_display, gr.update(visible=False)

    except Exception as e:
        error_msg = f"""## ❌ Status Check Error

**Error:** {str(e)}
**Session ID:** {session_id}
**Timestamp:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""
        return error_msg, gr.update(visible=False)


def get_session_history(server_url: str, user_id: str = "test_user_dleader") -> List[tuple]:
    """Get session history for dropdown selection"""
    # Always use default user in simplified version
    user_id = "test_user_dleader"
    try:
        client = FastAPIClient(server_url)
        if not client.health_check():
            return [("Server not available", "")]

        sessions = client.get_all_sessions(user_id=user_id)
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


async def stop_task_by_session_id(session_id: str, server_url: str, user_id: str):
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
        status_data = client.get_status(session_id, user_id)
        if not status_data:
            return f"## ❌ Session Not Found\n\nSession ID '{session_id}' not found on server."

        # Check if task is already complete
        if status_data.get("is_complete", False):
            status = status_data.get("status", "unknown")
            return f"## ⚠️ Task Already Complete\n\nSession '{session_id}' has status: {status}.\nCannot stop a completed task."

        # Attempt to stop the task
        success = client.stop_task(session_id, user_id)
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

    with gr.Blocks(title="Agent Interface (Simplified)", theme=gr.themes.Soft()) as demo:
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
                        <h1 style="margin: 0; font-size: 2.2em; color: #2c3e50; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; font-weight: 600;">AI Agent - Simplified</h1>
                        <p style="margin: 8px 0 0 0; font-size: 1.1em; color: #6c757d; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;">Basic Multi-Turn Interface</p>
                        <p style="margin: 4px 0 0 0; font-size: 0.9em; color: #007bff; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;">🚀 All users: test_user_dleader</p>
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
                    # Fixed user ID for simplified version
                    user_id_input = gr.State(value="test_user_dleader")

        # Main interface with tabs
        with gr.Tabs():

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
                                choices=[],  # Will be populated when user_id is provided
                                value="",
                                interactive=True,
                                allow_custom_value=True
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
- Direct download button when completed

**Instructions:**
1. Click "🔄 Refresh Session List" to load all sessions
2. Select a session from the dropdown (shows both active and completed sessions)
3. Click "🔍 Check Status"

For completed sessions, direct download URLs will appear.""",
                            max_height="600px"
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
                                choices=[],  # Will be populated when user_id is provided
                                value="",
                                interactive=True,
                                allow_custom_value=True
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
                                visible=False,
                                allow_custom_value=True
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

        def clear_status_interface():
            return (
                "",  # Clear dropdown selection
                """## 📋 Status Check

Select a session from the dropdown to check status and view complete snapshots.

**Features:**
- Real-time status updates
- Complete snapshots view (no truncation)
- Full session history with scrollable window
- Direct S3/API download URLs when completed

**Instructions:**
1. Click "🔄 Refresh Session List" to load all sessions
2. Select a session from the dropdown (shows both active and completed sessions)
3. Click "🔍 Check Status"

For completed sessions, direct download URLs will appear (S3 presigned URLs for cloud sessions, or API URLs for local sessions)."""  # Reset status results
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

        def refresh_stop_history(user_id):
            """Refresh the stop task session list"""
            return gr.update(choices=get_session_history(server_url.value, user_id), value="")

        def refresh_status_history(user_id):
            """Refresh the status check session list"""
            return gr.update(choices=get_session_history(server_url.value, user_id), value="")

        async def check_status_from_dropdown(selected_session_id, server_url_value, user_id):
            """Check status using dropdown selection"""
            if not selected_session_id:
                status_text, _ = await check_status_with_history("", server_url_value, user_id)
                return status_text
            status_text, _ = await check_status_with_history(selected_session_id, server_url_value, user_id)
            return status_text

        # Wire up events

        # Status checking events
        # Refresh status session list
        refresh_status_history_btn.click(
            fn=refresh_status_history,
            inputs=[user_id_input],
            outputs=[status_session_selector]
        )

        # Check status using dropdown selection
        check_btn.click(
            fn=check_status_from_dropdown,
            inputs=[status_session_selector, server_url, user_id_input],
            outputs=[status_results]
        )

        clear_status_btn.click(
            fn=clear_status_interface,
            outputs=[status_session_selector, status_results]
        )

        # Stop task events
        refresh_stop_history_btn.click(
            fn=refresh_stop_history,
            inputs=[user_id_input],
            outputs=[stop_session_selector]
        )

        stop_task_btn.click(
            fn=stop_task_by_session_id,
            inputs=[stop_session_selector, server_url, user_id_input],
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

        def get_multiturn_sessions(url, user_id=None):
            """Get list of multi-turn sessions"""
            try:
                client = FastAPIClient(url)
                sessions_data = client.get_all_multiturn_sessions(user_id)
                if sessions_data:
                    choices = []
                    for session in sessions_data:
                        session_id = session['session_id']
                        status = session.get('session_status', 'unknown')
                        turns = session.get('total_turns', 0)
                        first_query = session.get('first_query', 'No query')
                        # Create a readable display name
                        display_name = f"{session_id[:8]}... | {status} | {turns} turns | {first_query[:30]}..."
                        choices.append((display_name, session_id))
                    return choices
                return []
            except Exception as e:
                print(f"Error getting multiturn sessions: {e}")
                return []

        def refresh_multiturn_sessions(url, user_id):
            """Refresh the multi-turn sessions dropdown"""
            choices = get_multiturn_sessions(url, user_id)
            return gr.update(choices=choices, value="")

        def start_new_conversation(query, language, url, user_id):
            """Start a new multi-turn conversation"""
            if not query.strip():
                return (
                    gr.update(value="Please enter a question or request to start the conversation.", visible=True),
                    gr.update(visible=False),
                    gr.update(visible=False)
                )

            try:
                client = FastAPIClient(url)
                session_id = client.submit_request(query, language, user_id)

                if session_id:

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

        def continue_existing_conversation(session_selection, query, url, user_id):
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
                response = client.continue_session(session_id, query, language="en", user_id=user_id)

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
                gr.update(value="", choices=[]),  # existing_session_selector
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
            inputs=[server_url, user_id_input],
            outputs=[existing_session_selector]
        )

        start_conversation_btn.click(
            fn=start_new_conversation,
            inputs=[multiturn_query, multiturn_language, server_url, user_id_input],
            outputs=[multiturn_progress, conversation_display, multiturn_session_info]
        )

        continue_conversation_btn.click(
            fn=continue_existing_conversation,
            inputs=[existing_session_selector, continue_query, server_url, user_id_input],
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

        # Trash Management Tab
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
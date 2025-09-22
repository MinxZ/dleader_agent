"""
KumiChem AI Agent - Gradio Interface v3

A clean, modern Gradio interface for the FastAPI Agent Server.
Built from scratch to properly integrate with all FastAPI endpoints.

Features:
- Submit requests with file uploads to FastAPI queue
- Check status with integrated history and snapshots
- Stop tasks with session selection
- Download results and session files
"""

import argparse
import json
import os
import tempfile
import time
from datetime import datetime
from typing import List, Optional, Tuple, Dict, Any

import gradio as gr
import requests
from PIL import Image


class AgentAPIClient:
    """
    Client for communicating with the FastAPI Agent Server

    Provides methods for all available API endpoints:
    - Health check
    - Submit requests to queue
    - Upload files
    - Check status
    - Get snapshots
    - Get JSON results
    - Get all sessions
    - Stop tasks
    - Download session files
    """

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
        """Submit a chat request to the queue and return session ID"""
        try:
            data = {"message": message, "language": language}
            response = requests.post(f"{self.base_url}/chat-queue", json=data, timeout=10)
            if response.status_code == 200:
                result = response.json()
                return result.get("session_id")
            return None
        except Exception as e:
            print(f"Error submitting request: {e}")
            return None

    def upload_files(self, session_id: str, file_paths: List[str]) -> bool:
        """Upload files for a session"""
        try:
            files_data = []
            for file_path in file_paths:
                with open(file_path, 'rb') as f:
                    files_data.append(('files', (os.path.basename(file_path), f, 'application/octet-stream')))

            response = requests.post(f"{self.base_url}/upload/{session_id}", files=files_data, timeout=30)
            return response.status_code == 200
        except Exception as e:
            print(f"Error uploading files: {e}")
            return False

    def get_status(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get current status and progress for a session"""
        try:
            response = requests.get(f"{self.base_url}/status/{session_id}", timeout=10)
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            print(f"Error getting status: {e}")
            return None

    def get_snapshots(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get all periodic snapshots for a session"""
        try:
            response = requests.get(f"{self.base_url}/snapshots/{session_id}", timeout=10)
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            print(f"Error getting snapshots: {e}")
            return None

    def get_json_results(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get structured JSON results for a completed session"""
        try:
            response = requests.get(f"{self.base_url}/results/{session_id}", timeout=10)
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            print(f"Error getting JSON results: {e}")
            return None

    def get_all_sessions(self) -> List[Dict[str, Any]]:
        """Get all sessions from server storage"""
        try:
            print(f"Fetching sessions from: {self.base_url}/all-sessions")
            response = requests.get(f"{self.base_url}/all-sessions", timeout=10)
            if response.status_code == 200:
                data = response.json()
                sessions = data.get("sessions", [])
                print(f"Retrieved {len(sessions)} sessions from storage")
                return sessions
            else:
                print(f"All-sessions endpoint returned {response.status_code}, trying /sessions")
                # Fallback to /sessions endpoint for active sessions
                response = requests.get(f"{self.base_url}/sessions", timeout=10)
                if response.status_code == 200:
                    sessions = response.json()
                    # Convert to expected format
                    formatted_sessions = []
                    for session in sessions:
                        formatted_session = {
                            "session_id": session.get("session_id", ""),
                            "query": session.get("query", "No query available"),
                            "full_query": session.get("query", "No query available"),
                            "language": session.get("language", "en"),
                            "timestamp": session.get("created_at", ""),
                            "status": session.get("status", "unknown"),
                            "is_complete": session.get("status") in ["completed", "error", "cancelled"]
                        }
                        formatted_sessions.append(formatted_session)
                    print(f"Retrieved {len(formatted_sessions)} active sessions")
                    return formatted_sessions
            return []
        except Exception as e:
            print(f"Error getting all sessions: {e}")
            return []

    def stop_task(self, session_id: str) -> bool:
        """Stop a running or queued task"""
        try:
            response = requests.post(f"{self.base_url}/stop/{session_id}", timeout=10)
            return response.status_code == 200
        except Exception as e:
            print(f"Error stopping task: {e}")
            return False

    def download_session_zip(self, session_id: str) -> Optional[str]:
        """Download session zip file and return temporary file path"""
        try:
            response = requests.get(f"{self.base_url}/download/{session_id}", timeout=30)
            if response.status_code == 200:
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
            print(f"Error downloading session zip: {e}")
            return None


class UIHelpers:
    """Helper functions for UI components and data formatting"""

    @staticmethod
    def load_logo() -> Optional[Image.Image]:
        """Load the logo image if available"""
        try:
            return Image.open("dleader_logo.jpg")
        except:
            return None

    @staticmethod
    def format_file_info(files) -> str:
        """Format uploaded files information for display"""
        if not files:
            return "No files uploaded"

        file_info = []
        for file in files:
            if file is None:
                continue
            filename = os.path.basename(file.name)
            try:
                file_size = os.path.getsize(file.name) / (1024 * 1024)  # MB
                file_info.append(f"📁 **{filename}** ({file_size:.2f} MB)")
            except:
                file_info.append(f"📁 **{filename}**")

        return "**Uploaded Files:**\n\n" + "\n".join(file_info)

    @staticmethod
    def create_temp_file(content: str, prefix: str, extension: str) -> Optional[str]:
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

    @staticmethod
    def format_timestamp(timestamp_str: str) -> str:
        """Format timestamp for display"""
        try:
            dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            return dt.strftime('%m/%d %H:%M')
        except:
            return timestamp_str[:16] if timestamp_str else 'Unknown'

    @staticmethod
    def get_status_emoji(status: str) -> str:
        """Get emoji for status"""
        status_emojis = {
            'queued': '📋',
            'processing': '🔄',
            'completed': '✅',
            'failed': '❌',
            'error': '❌',
            'cancelled': '🛑'
        }
        return status_emojis.get(status, '❓')


class RequestHandler:
    """Handles all request processing and API interactions"""

    def __init__(self):
        self.client = None

    def set_client(self, server_url: str):
        """Set the API client with server URL"""
        self.client = AgentAPIClient(server_url)

    def submit_request(self, message: str, files: List, language: str) -> Tuple[str, str]:
        """Submit a new request to the FastAPI server"""
        if not message.strip():
            return (
                "## ❌ Error\n\nPlease enter a request to process.",
                "## ❌ No Input\n\nPlease enter a request."
            )

        if not self.client or not self.client.health_check():
            return (
                "## ❌ Server Error\n\nCannot connect to FastAPI server. Please ensure the server is running.",
                "## ❌ Server Error\n\nServer not available."
            )

        # Extract file paths
        file_paths = [file.name for file in files if file is not None]

        try:
            # Submit request to queue
            session_id = self.client.submit_request(message, language)
            if not session_id:
                return (
                    "## ❌ Submission Error\n\nFailed to submit request to server queue.",
                    "## ❌ Submission Error\n\nQueue submission failed."
                )

            # Upload files if any
            if file_paths:
                upload_success = self.client.upload_files(session_id, file_paths)
                if not upload_success:
                    return (
                        "## ❌ Upload Error\n\nFailed to upload files to server.",
                        "## ❌ Upload Error\n\nFile upload failed."
                    )

            # Return success confirmation
            current_time = datetime.now()
            status_display = f"""## 🚀 Request Submitted Successfully

**Status:** 📋 Queued for processing
**Session ID:** `{session_id}`
**Submitted:** {current_time.strftime('%H:%M:%S')}

Your request has been submitted to the FastAPI queue.
Processing will continue even if you close this page.
Use the Session ID above to check status."""

            result_display = f"""## 📋 Request Queued Successfully

**Session ID:** `{session_id}`
**Submitted:** {current_time.strftime('%Y-%m-%d %H:%M:%S')}
**Language:** {language.upper()}
**Files Uploaded:** {len(file_paths)}

**Request:** {message[:200]}{'...' if len(message) > 200 else ''}

---

### 🔄 Next Steps

1. **Copy the Session ID** above for status checking
2. **Switch to "Check Status" tab** to monitor progress
3. **Close this page safely** - processing continues on server
4. **Return later** to retrieve results

The FastAPI server will handle processing in the background."""

            return (result_display, status_display)

        except Exception as e:
            error_msg = f"""## ❌ System Error

**Error:** {str(e)}
**Timestamp:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Please check the server connection and try again."""
            return (error_msg, "## ❌ System Error\n\nSee details in results panel.")

    def check_status(self, session_id: str) -> Tuple[str, ...]:
        """Check comprehensive status of a session including snapshots and results"""
        if not session_id.strip():
            return (
                "## ❌ Error\n\nPlease enter a Session ID to check status.",
                gr.update(visible=False),
                gr.update(visible=False),
                gr.update(visible=False),
                gr.update(visible=False)
            )

        if not self.client or not self.client.health_check():
            return (
                "## ❌ Server Error\n\nCannot connect to FastAPI server.",
                gr.update(visible=False),
                gr.update(visible=False),
                gr.update(visible=False),
                gr.update(visible=False)
            )

        try:
            # Get main status data
            status_data = self.client.get_status(session_id)
            if not status_data:
                return (
                    f"## ❌ Session Not Found\n\nSession ID '{session_id}' not found on server.",
                    gr.update(visible=False),
                    gr.update(visible=False),
                    gr.update(visible=False),
                    gr.update(visible=False)
                )

            # Get additional data
            snapshots_data = self.client.get_snapshots(session_id)
            json_results = None
            if status_data.get("is_complete"):
                json_results = self.client.get_json_results(session_id)

            # Build comprehensive status display
            status = status_data.get("status", "unknown")
            is_complete = status_data.get("is_complete", False)
            status_emoji = UIHelpers.get_status_emoji(status)

            result_display = f"""## {status_emoji} Session Status: {status.title()}

**Session ID:** `{session_id}`
**Created:** {status_data.get('created_at', 'N/A')}
**Current Time:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**Status:** {status}
**Complete:** {'Yes' if is_complete else 'No'}"""

            # Add queue information
            if "queue_position" in status_data:
                queue_pos = status_data["queue_position"]
                wait_time = status_data.get("estimated_wait_time", 0)
                result_display += f"""

**Queue Position:** {queue_pos}
**Estimated Wait:** {wait_time} seconds"""

            # Add error information
            if status_data.get("error"):
                result_display += f"""

## ❌ Error Information
**Error:** {status_data['error']}"""

            # Add snapshots information
            if snapshots_data:
                snapshot_count = snapshots_data.get("snapshot_count", 0)
                result_display += f"""

## 📸 Snapshots Information
**Total Snapshots:** {snapshot_count}"""

                if snapshot_count > 0:
                    snapshots = snapshots_data.get("snapshots", [])
                    latest_snapshot = snapshots[-1] if snapshots else None
                    if latest_snapshot:
                        snap_time = latest_snapshot.get("timestamp", "N/A")
                        thinking_length = latest_snapshot.get("content", {}).get("thinking_length", 0)
                        image_count = len(latest_snapshot.get("files", {}).get("images", []))

                        formatted_time = UIHelpers.format_timestamp(snap_time)
                        result_display += f"""
**Latest Snapshot:** {formatted_time}
**Thinking Length:** {thinking_length:,} characters
**Images Generated:** {image_count}"""

            # Add completion details if completed
            download_files = [gr.update(visible=False)] * 4  # Default: hide all downloads

            if is_complete and status == "completed":
                final_report = status_data.get("final_report", "")
                thinking_content = status_data.get("thinking_content", "")
                session_path = status_data.get("session_path", "")

                result_display += f"""

## ✅ Completion Details
**Session Path:** {session_path}
**Final Report:** {'Available' if final_report else 'Not available'}
**Thinking Process:** {'Available' if thinking_content else 'Not available'}"""

                # Show JSON results summary
                if json_results:
                    files_info = json_results.get("files", {})
                    images = files_info.get("images", [])
                    result_display += f"""

## 📊 Results Summary
**Report File:** `{os.path.basename(files_info.get('report_md', 'N/A'))}`
**Thinking File:** `{os.path.basename(files_info.get('thinking_process', 'N/A'))}`
**Images Generated:** {len(images)} files
**Session ZIP:** {'Available' if files_info.get('session_zip') else 'Not available'}"""

                # Create download files
                report_file = UIHelpers.create_temp_file(final_report, "report", "md") if final_report else None
                thinking_file = UIHelpers.create_temp_file(thinking_content, "thinking_process", "txt") if thinking_content else None
                zip_file = self.client.download_session_zip(session_id)
                json_file = None
                if json_results:
                    json_file = UIHelpers.create_temp_file(
                        json.dumps(json_results, indent=2, ensure_ascii=False),
                        f"results_{session_id[:8]}",
                        "json"
                    )

                download_files = [
                    gr.update(visible=True, value=report_file) if report_file else gr.update(visible=False),
                    gr.update(visible=True, value=thinking_file) if thinking_file else gr.update(visible=False),
                    gr.update(visible=True, value=zip_file) if zip_file else gr.update(visible=False),
                    gr.update(visible=True, value=json_file) if json_file else gr.update(visible=False)
                ]

            return (result_display, *download_files)

        except Exception as e:
            error_msg = f"""## ❌ Status Check Error

**Error:** {str(e)}
**Session ID:** {session_id}
**Timestamp:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""
            return (
                error_msg,
                gr.update(visible=False),
                gr.update(visible=False),
                gr.update(visible=False),
                gr.update(visible=False)
            )

    def get_session_history(self) -> List[Tuple[str, str]]:
        """Get session history for dropdown selection"""
        try:
            if not self.client or not self.client.health_check():
                return [("Server not available", "")]

            sessions = self.client.get_all_sessions()
            if not sessions:
                return [("No sessions available", "")]

            items = []
            for session in sessions:
                status_emoji = UIHelpers.get_status_emoji(session.get('status', 'unknown'))
                time_str = UIHelpers.format_timestamp(session.get('timestamp', ''))
                query = session.get('query', 'No query')[:50] + "..."

                label = f"{status_emoji} {time_str} - {query}"
                items.append((label, session['session_id']))

            return items

        except Exception as e:
            print(f"Error getting session history: {e}")
            return [("Error loading history", "")]

    def stop_task(self, session_id: str) -> str:
        """Stop a task by session ID"""
        if not session_id or session_id.strip() == "":
            return "## ❌ Error\n\nPlease select a session to stop."

        if not self.client or not self.client.health_check():
            return "## ❌ Server Error\n\nCannot connect to FastAPI server."

        try:
            # Check if session exists
            status_data = self.client.get_status(session_id)
            if not status_data:
                return f"## ❌ Session Not Found\n\nSession ID '{session_id}' not found on server."

            # Check if task is already complete
            if status_data.get("is_complete", False):
                status = status_data.get("status", "unknown")
                return f"## ⚠️ Task Already Complete\n\nSession '{session_id}' has status: {status}.\nCannot stop a completed task."

            # Attempt to stop the task
            success = self.client.stop_task(session_id)
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


def create_interface(default_server_url: str = "http://localhost:8001") -> gr.Blocks:
    """Create the main Gradio interface"""

    # Initialize request handler
    request_handler = RequestHandler()

    with gr.Blocks(title="KumiChem AI Agent", theme=gr.themes.Soft()) as interface:

        # Header
        with gr.Row():
            with gr.Column(scale=1, min_width=120):
                gr.Image(
                    value=UIHelpers.load_logo(),
                    show_label=False,
                    show_download_button=False,
                    container=False,
                    height=100,
                    width=120,
                    interactive=False
                )
            with gr.Column(scale=5):
                gr.HTML("""
                <div style="display: flex; align-items: center; justify-content: center; height: 120px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; border-radius: 12px; margin: 10px; padding: 20px; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);">
                    <div style="text-align: center;">
                        <h1 style="margin: 0; font-size: 2.4em; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; font-weight: 600;">KumiChem AI Agent</h1>
                        <p style="margin: 8px 0 0 0; font-size: 1.2em; opacity: 0.9; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;">Advanced Chemical Analysis & Research Assistant</p>
                    </div>
                </div>
                """)

        # Server Configuration
        with gr.Row():
            with gr.Column():
                gr.Markdown("### ⚙️ Server Configuration")
                with gr.Row():
                    server_url_input = gr.Textbox(
                        label="FastAPI Server URL",
                        value=default_server_url,
                        placeholder="http://localhost:8001",
                        scale=3
                    )
                    language_select = gr.Dropdown(
                        label="Language",
                        choices=[("English", "en"), ("Japanese", "jp")],
                        value="en",
                        scale=1
                    )

        # Main Tabs
        with gr.Tabs():

            # Submit Request Tab
            with gr.Tab("🚀 Submit Request", id="submit"):
                with gr.Row(equal_height=True):

                    # Left Column - Input
                    with gr.Column(scale=1):
                        gr.Markdown("## 📝 Request Submission")

                        # File Upload
                        with gr.Group():
                            gr.Markdown("### 📁 File Upload")
                            file_upload = gr.File(
                                label="Upload Files (Optional)",
                                file_count="multiple",
                                height=120
                            )
                            file_info_display = gr.Markdown("No files uploaded")

                        # Message Input
                        with gr.Group():
                            gr.Markdown("### 💬 Your Request")
                            message_input = gr.Textbox(
                                label="Describe what you want the agent to do",
                                placeholder="Enter your request here...\n\nExamples:\n• Analyze molecular structures in uploaded files\n• Compare chemical compounds\n• Generate molecular visualizations\n• Perform property calculations",
                                lines=6,
                                max_lines=10
                            )

                        # Submit Controls
                        with gr.Row():
                            submit_button = gr.Button("🚀 Submit Request", variant="primary", scale=2)
                            clear_button = gr.Button("🗑️ Clear", variant="secondary", scale=1)

                        # Status Display
                        with gr.Group():
                            gr.Markdown("### 📊 Submission Status")
                            submission_status = gr.Markdown(
                                """## 📊 Ready to Submit

**Status:** 🟢 Waiting for input
**Server:** Not connected

Enter your request above and click Submit.""",
                                height=150
                            )

                    # Right Column - Results
                    with gr.Column(scale=1):
                        gr.Markdown("## 📋 Submission Results")

                        submission_results = gr.Markdown(
                            """## 📋 Results Panel

Results will appear here after submission.

**Instructions:**
1. Upload files (optional)
2. Enter your request description
3. Select language preference
4. Click "Submit Request"
5. Copy the Session ID for status checking

**Note:** Requests are processed asynchronously. You can safely close this page after submission.""",
                            height=600
                        )

            # Check Status Tab
            with gr.Tab("🔍 Check Status", id="status"):
                with gr.Row():

                    # Left Column - Input
                    with gr.Column(scale=1):
                        gr.Markdown("## 🔍 Status Inquiry")

                        with gr.Group():
                            gr.Markdown("### 📋 Session ID")
                            session_id_input = gr.Textbox(
                                label="Enter Session ID",
                                placeholder="Paste your session ID here...",
                                lines=1
                            )

                            with gr.Row():
                                check_status_button = gr.Button("🔍 Check Status", variant="primary", scale=2)
                                clear_status_button = gr.Button("🗑️ Clear", variant="secondary", scale=1)

                    # Right Column - Results
                    with gr.Column(scale=1):
                        gr.Markdown("## 📋 Status Information")

                        status_results = gr.Markdown(
                            """## 📋 Session Status

Enter a Session ID to check comprehensive status information.

**Features Available:**
- ⏱️ Real-time status updates
- 📸 Integrated snapshots view
- 📊 Progress monitoring
- 🗂️ Complete session history
- 📥 Download results when completed

**Instructions:**
1. Copy Session ID from submission
2. Paste it in the field above
3. Click "Check Status"
4. View detailed progress information""",
                            height=400
                        )

                        # Download Files
                        with gr.Row():
                            download_report = gr.File(label="📥 Download Report", visible=False)
                            download_thinking = gr.File(label="📥 Download Thinking Process", visible=False)

                        with gr.Row():
                            download_zip = gr.File(label="📥 Download Session ZIP", visible=False)
                            download_json = gr.File(label="📥 Download JSON Results", visible=False)

            # Stop Task Tab
            with gr.Tab("🛑 Stop Task", id="stop"):
                with gr.Row():

                    # Left Column - Selection
                    with gr.Column(scale=1):
                        gr.Markdown("## 🛑 Task Management")

                        with gr.Group():
                            gr.Markdown("### 📋 Session Selection")

                            refresh_sessions_button = gr.Button("🔄 Refresh Session List", variant="secondary")

                            session_dropdown = gr.Dropdown(
                                label="Select a session to stop",
                                choices=[("Loading...", "")],
                                value="",
                                interactive=True
                            )

                            with gr.Row():
                                stop_task_button = gr.Button("🛑 Stop Selected Task", variant="primary", scale=2)
                                clear_stop_button = gr.Button("🗑️ Clear Selection", variant="secondary", scale=1)

                    # Right Column - Results
                    with gr.Column(scale=1):
                        gr.Markdown("## 📋 Stop Results")

                        stop_results = gr.Markdown(
                            """## 🛑 Task Stopping

Select a session from the dropdown to stop a running or queued task.

**Instructions:**
1. Click "Refresh Session List" to load current sessions
2. Select a session from the dropdown menu
3. Click "Stop Selected Task" to cancel it
4. Confirmation will appear here

**Important Notes:**
- ✅ You can stop queued or processing tasks
- ❌ Completed tasks cannot be stopped
- 🔄 Use refresh to get the latest session list
- ⚠️ Stopping is immediate and cannot be undone""",
                            height=400
                        )

        # Event Handlers
        def update_file_info(files):
            return UIHelpers.format_file_info(files)

        def on_server_url_change(url):
            request_handler.set_client(url)
            return "Server URL updated"

        def clear_submit_form():
            return (
                "",  # Clear message
                """## 📊 Ready to Submit

**Status:** 🟢 Waiting for input
**Server:** Not connected

Enter your request above and click Submit.""",  # Reset status
                """## 📋 Results Panel

Results will appear here after submission.

**Instructions:**
1. Upload files (optional)
2. Enter your request description
3. Select language preference
4. Click "Submit Request"
5. Copy the Session ID for status checking

**Note:** Requests are processed asynchronously. You can safely close this page after submission."""  # Reset results
            )

        def clear_status_form():
            return (
                "",  # Clear session ID
                """## 📋 Session Status

Enter a Session ID to check comprehensive status information.

**Features Available:**
- ⏱️ Real-time status updates
- 📸 Integrated snapshots view
- 📊 Progress monitoring
- 🗂️ Complete session history
- 📥 Download results when completed

**Instructions:**
1. Copy Session ID from submission
2. Paste it in the field above
3. Click "Check Status"
4. View detailed progress information""",  # Reset status results
                gr.update(visible=False),  # Hide downloads
                gr.update(visible=False),
                gr.update(visible=False),
                gr.update(visible=False)
            )

        def clear_stop_form():
            return (
                "",  # Clear dropdown selection
                """## 🛑 Task Stopping

Select a session from the dropdown to stop a running or queued task.

**Instructions:**
1. Click "Refresh Session List" to load current sessions
2. Select a session from the dropdown menu
3. Click "Stop Selected Task" to cancel it
4. Confirmation will appear here

**Important Notes:**
- ✅ You can stop queued or processing tasks
- ❌ Completed tasks cannot be stopped
- 🔄 Use refresh to get the latest session list
- ⚠️ Stopping is immediate and cannot be undone"""  # Reset results
            )

        def refresh_session_list():
            return gr.update(choices=request_handler.get_session_history(), value="")

        # Wire up all events

        # Server URL change
        server_url_input.change(fn=on_server_url_change, inputs=[server_url_input])

        # File upload
        file_upload.change(fn=update_file_info, inputs=[file_upload], outputs=[file_info_display])

        # Submit request
        submit_button.click(
            fn=lambda msg, files, url, lang: request_handler.set_client(url) or request_handler.submit_request(msg, files, lang),
            inputs=[message_input, file_upload, server_url_input, language_select],
            outputs=[submission_results, submission_status]
        )

        # Clear submit form
        clear_button.click(
            fn=clear_submit_form,
            outputs=[message_input, submission_status, submission_results]
        )

        # Allow Enter to submit
        message_input.submit(
            fn=lambda msg, files, url, lang: request_handler.set_client(url) or request_handler.submit_request(msg, files, lang),
            inputs=[message_input, file_upload, server_url_input, language_select],
            outputs=[submission_results, submission_status]
        )

        # Check status
        check_status_button.click(
            fn=lambda sid, url: request_handler.set_client(url) or request_handler.check_status(sid),
            inputs=[session_id_input, server_url_input],
            outputs=[status_results, download_report, download_thinking, download_zip, download_json]
        )

        # Clear status form
        clear_status_button.click(
            fn=clear_status_form,
            outputs=[session_id_input, status_results, download_report, download_thinking, download_zip, download_json]
        )

        # Allow Enter to check status
        session_id_input.submit(
            fn=lambda sid, url: request_handler.set_client(url) or request_handler.check_status(sid),
            inputs=[session_id_input, server_url_input],
            outputs=[status_results, download_report, download_thinking, download_zip, download_json]
        )

        # Refresh sessions
        refresh_sessions_button.click(
            fn=lambda url: request_handler.set_client(url) or refresh_session_list(),
            inputs=[server_url_input],
            outputs=[session_dropdown]
        )

        # Stop task
        stop_task_button.click(
            fn=lambda sid, url: request_handler.set_client(url) or request_handler.stop_task(sid),
            inputs=[session_dropdown, server_url_input],
            outputs=[stop_results]
        )

        # Clear stop form
        clear_stop_button.click(
            fn=clear_stop_form,
            outputs=[session_dropdown, stop_results]
        )

        # Initialize session list on load
        interface.load(
            fn=lambda url: request_handler.set_client(url) or refresh_session_list(),
            inputs=[server_url_input],
            outputs=[session_dropdown]
        )

    return interface


def main():
    """Main function to run the Gradio interface"""
    parser = argparse.ArgumentParser(description="KumiChem AI Agent - Gradio Interface v3")
    parser.add_argument("--server_port", type=int, default=7861, help="Port for Gradio server (default: 7861)")
    parser.add_argument("--fastapi_url", type=str, default="http://localhost:8001", help="FastAPI server URL")
    parser.add_argument("--share", action="store_true", help="Create a public link")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")

    args = parser.parse_args()

    print("=" * 60)
    print("🧪 KumiChem AI Agent - Gradio Interface v3")
    print("=" * 60)
    print(f"🌐 Gradio server starting on port: {args.server_port}")
    print(f"🔗 FastAPI server URL: {args.fastapi_url}")
    print(f"🌍 Public sharing: {'Enabled' if args.share else 'Disabled'}")
    print(f"🐛 Debug mode: {'Enabled' if args.debug else 'Disabled'}")
    print("=" * 60)

    # Create and launch interface
    interface = create_interface(args.fastapi_url)

    interface.launch(
        server_name="0.0.0.0",
        server_port=args.server_port,
        share=args.share,
        debug=args.debug,
        show_error=True
    )


if __name__ == "__main__":
    main()
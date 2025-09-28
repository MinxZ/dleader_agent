"""
Simplified Multi-Turn Gradio Interface for FastAPI Agent Server

This is a simplified version with:
- No Community Sharing features
- Direct hard-delete instead of trash system
- All other core features retained
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

    def download_results(self, session_id: str, user_id: str) -> Optional[str]:
        """Download results for a session"""
        try:
            response = requests.get(f"{self.base_url}/download/{session_id}",
                                  params={"user_id": user_id}, timeout=30)
            if response.status_code == 200:
                # Save to temporary file
                with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as tmp_file:
                    tmp_file.write(response.content)
                    return tmp_file.name
            return None
        except Exception as e:
            print(f"Error downloading results: {e}")
            return None

    def hard_delete_session(self, session_id: str, user_id: str) -> bool:
        """Permanently delete a session (hard delete)"""
        try:
            response = requests.delete(
                f"{self.base_url}/hard-delete/{session_id}",
                params={"user_id": user_id, "confirm": "true"},
                timeout=10
            )
            return response.status_code == 200
        except Exception as e:
            print(f"Error deleting session: {e}")
            return False

    def get_all_sessions(self, user_id: str) -> List[dict]:
        """Get all sessions for a user"""
        try:
            response = requests.get(f"{self.base_url}/all-sessions",
                                  params={"user_id": user_id}, timeout=10)
            if response.status_code == 200:
                return response.json().get("sessions", [])
            return []
        except Exception as e:
            print(f"Error getting sessions: {e}")
            return []

    def get_snapshots(self, session_id: str, user_id: str) -> List[dict]:
        """Get snapshots for a session"""
        try:
            response = requests.get(f"{self.base_url}/snapshots/{session_id}",
                                  params={"user_id": user_id}, timeout=10)
            if response.status_code == 200:
                return response.json().get("snapshots", [])
            return []
        except Exception as e:
            print(f"Error getting snapshots: {e}")
            return []

    def continue_session(self, session_id: str, message: str, user_id: str, turn_number: int = None) -> Optional[str]:
        """Continue a multi-turn session"""
        try:
            data = {
                "session_id": session_id,
                "message": message,
                "user_id": user_id
            }
            if turn_number is not None:
                data["turn_number"] = str(turn_number)

            response = requests.post(f"{self.base_url}/continue-session", data=data, timeout=30)

            if response.status_code == 200:
                result = response.json()
                return result.get("turn_session_id") or result.get("session_id")
            else:
                print(f"Error continuing session: {response.status_code} - {response.text}")
            return None
        except Exception as e:
            print(f"Error continuing session: {e}")
            return None

    def get_multiturn_sessions(self, user_id: str) -> List[dict]:
        """Get all multi-turn sessions for a user"""
        try:
            response = requests.get(f"{self.base_url}/multiturn-sessions",
                                  params={"user_id": user_id}, timeout=10)
            if response.status_code == 200:
                return response.json().get("sessions", [])
            return []
        except Exception as e:
            print(f"Error getting multi-turn sessions: {e}")
            return []

    def get_multiturn_session_info(self, session_id: str, user_id: str) -> Optional[dict]:
        """Get information about a multi-turn session"""
        try:
            response = requests.get(f"{self.base_url}/multiturn-session/{session_id}",
                                  params={"user_id": user_id}, timeout=10)
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            print(f"Error getting multi-turn session info: {e}")
            return None

    def get_session_context(self, session_id: str, user_id: str) -> Optional[str]:
        """Get the accumulated context for a session"""
        try:
            response = requests.get(f"{self.base_url}/session-context/{session_id}",
                                  params={"user_id": user_id}, timeout=10)
            if response.status_code == 200:
                data = response.json()
                return data.get("accumulated_context", "")
            return None
        except Exception as e:
            print(f"Error getting session context: {e}")
            return None


def create_interface(server_url: str = "http://localhost:8001", user: str = "default_user"):
    """Create the simplified Gradio interface"""

    client = FastAPIClient(server_url)

    # Store user ID in state
    user_id = gr.State(value=user)
    server_url_state = gr.State(value=server_url)

    # Shared components
    current_session_id = gr.State(value=None)

    # Interface
    with gr.Blocks(title="dLeader Agent - Simplified", theme=gr.themes.Base()) as interface:
        gr.Markdown("# 🤖 dLeader Agent - Simplified Interface")
        gr.Markdown("*Multi-turn conversation interface with direct session management*")

        # Server Connection Status
        with gr.Row():
            with gr.Column(scale=3):
                server_url_input = gr.Textbox(
                    value=server_url,
                    label="FastAPI Server URL",
                    placeholder="http://localhost:8001",
                    interactive=True
                )
            with gr.Column(scale=2):
                user_input = gr.Textbox(
                    value=user,
                    label="User ID",
                    placeholder="Enter your user ID",
                    interactive=True
                )
            with gr.Column(scale=1):
                connect_btn = gr.Button("🔌 Connect", variant="primary")
                connection_status = gr.Markdown("🔴 Not Connected")

        # Main Tabs
        with gr.Tabs() as tabs:
            # Chat Tab
            with gr.Tab("💬 Chat"):
                with gr.Row():
                    with gr.Column(scale=2):
                        gr.Markdown("## 📝 New Request")
                        message_input = gr.Textbox(
                            label="Enter your message",
                            placeholder="Type your request here...",
                            lines=5,
                            interactive=True
                        )

                        # File upload section
                        with gr.Accordion("📎 File Upload (Optional)", open=False):
                            file_upload = gr.File(
                                label="Upload files",
                                file_types=["*"],
                                file_count="multiple",
                                interactive=True
                            )

                        language_select = gr.Radio(
                            choices=["en", "jp"],
                            value="en",
                            label="Language",
                            interactive=True
                        )

                        with gr.Row():
                            submit_btn = gr.Button("🚀 Submit", variant="primary", scale=2)
                            clear_btn = gr.Button("🗑️ Clear", variant="secondary", scale=1)

                        # Multi-turn section
                        gr.Markdown("## 🔄 Continue Conversation")

                        refresh_sessions_btn = gr.Button("🔄 Refresh Session List", variant="secondary")

                        session_dropdown = gr.Dropdown(
                            label="Select a session to continue",
                            choices=[],
                            value=None,
                            interactive=True,
                            info="Choose an existing session to continue the conversation"
                        )

                        continue_message_input = gr.Textbox(
                            label="Continue with:",
                            placeholder="Enter your follow-up message...",
                            lines=3,
                            interactive=True
                        )

                        continue_btn = gr.Button("➡️ Continue Session", variant="primary")

                    with gr.Column(scale=3):
                        gr.Markdown("## 📊 Results")
                        output_display = gr.Markdown("*Submit a request to see results here...*")

            # Status Tab
            with gr.Tab("📈 Status"):
                with gr.Row():
                    with gr.Column(scale=1):
                        gr.Markdown("## 🔍 Session Status")

                        refresh_status_sessions_btn = gr.Button("🔄 Refresh Sessions", variant="secondary")

                        status_session_selector = gr.Dropdown(
                            label="Select session to check",
                            choices=[],
                            value=None,
                            interactive=True
                        )

                        with gr.Row():
                            check_status_btn = gr.Button("📊 Check Status", variant="primary")
                            stop_btn = gr.Button("⏹️ Stop Task", variant="stop")
                            download_btn = gr.Button("📥 Download Results", variant="secondary")

                    with gr.Column(scale=2):
                        gr.Markdown("## 📋 Status Information")
                        status_display = gr.Markdown("*Select a session to view its status...*")

            # Session Management Tab (simplified with hard delete)
            with gr.Tab("🗂️ Sessions"):
                with gr.Row():
                    with gr.Column():
                        gr.Markdown("## 📚 Session Management")

                        refresh_manage_sessions_btn = gr.Button("🔄 Refresh Session List", variant="secondary")

                        manage_session_selector = gr.Dropdown(
                            label="Select session",
                            choices=[],
                            value=None,
                            interactive=True,
                            info="Select a session to view details or delete"
                        )

                        with gr.Row():
                            view_details_btn = gr.Button("👁️ View Details", variant="primary")
                            delete_btn = gr.Button("🗑️ Delete Permanently", variant="stop")

                        delete_confirmation = gr.Checkbox(
                            label="I understand this will permanently delete all session data",
                            value=False,
                            interactive=True
                        )

                with gr.Row():
                    with gr.Column():
                        gr.Markdown("## 📋 Session Details")
                        session_details_display = gr.Markdown("*Select a session to view details...*")

        # Event Handlers
        async def connect_to_server(url, user):
            """Connect to the FastAPI server"""
            client.base_url = url.rstrip('/')
            if client.health_check():
                return (
                    "🟢 Connected",
                    url,
                    user
                )
            else:
                return (
                    "🔴 Connection Failed - Check server URL",
                    url,
                    user
                )

        async def submit_request(message, files, language, server_url_value, user_id):
            """Submit a new request"""
            if not message:
                return "## ❌ Error\n\nPlease enter a message.", None

            # Process file uploads
            file_paths = []
            if files:
                for file in files:
                    if file and hasattr(file, 'name'):
                        file_paths.append(file.name)

            client.base_url = server_url_value
            session_id = client.submit_request(message, language, user_id, file_paths)

            if session_id:
                # Poll for results
                output = await poll_for_results(session_id, server_url_value, user_id)
                return output, session_id
            else:
                return "## ❌ Error\n\nFailed to submit request. Check server connection.", None

        async def poll_for_results(session_id, server_url_value, user_id, max_attempts=60):
            """Poll for task results with real-time updates"""
            client.base_url = server_url_value

            for attempt in range(max_attempts):
                status = client.get_status(session_id, user_id)
                if not status:
                    return "## ❌ Error\n\nFailed to get status."

                # Format current status
                output = f"## 📊 Session: {session_id}\n\n"
                output += f"**Status:** {status.get('status', 'Unknown')}\n\n"

                if status.get('status') == 'completed' or status.get('is_complete'):
                    output += "### ✅ Task Completed\n\n"

                    # Get snapshots
                    snapshots = client.get_snapshots(session_id, user_id)
                    if snapshots:
                        output += "### 📸 Snapshots:\n\n"
                        for i, snapshot in enumerate(snapshots, 1):
                            output += f"{i}. **{snapshot.get('name', 'Unnamed')}** - {snapshot.get('type', 'Unknown type')}\n"
                            if snapshot.get('url'):
                                output += f"   [View/Download]({snapshot['url']})\n"

                    # Get results if available
                    results_response = requests.get(
                        f"{server_url_value}/results/{session_id}",
                        params={"user_id": user_id}
                    )
                    if results_response.status_code == 200:
                        results = results_response.json()
                        if results.get('outputs'):
                            output += "\n### 📝 Outputs:\n\n"
                            for out in results['outputs']:
                                if out.get('type') == 'text':
                                    output += f"```\n{out.get('content', '')}\n```\n"

                    return output

                elif status.get('status') == 'failed':
                    output += f"### ❌ Task Failed\n\n**Error:** {status.get('error', 'Unknown error')}"
                    return output

                # Show progress
                output += f"**Progress:** Processing... (Attempt {attempt + 1}/{max_attempts})\n"

                # Get snapshots even while processing
                snapshots = client.get_snapshots(session_id, user_id)
                if snapshots:
                    output += f"\n### 📸 Current Snapshots ({len(snapshots)}):\n"
                    for snapshot in snapshots[-3:]:  # Show last 3 snapshots
                        output += f"- {snapshot.get('name', 'Unnamed')}\n"

                time.sleep(2)

            return "## ⏱️ Timeout\n\nTask is taking longer than expected. Check status tab."

        async def continue_session(session_id, message, server_url_value, user_id):
            """Continue a multi-turn session"""
            if not session_id:
                return "## ❌ Error\n\nPlease select a session to continue."
            if not message:
                return "## ❌ Error\n\nPlease enter a message."

            client.base_url = server_url_value

            # Get session info to determine turn number
            session_info = client.get_multiturn_session_info(session_id, user_id)
            if session_info:
                turn_number = len(session_info.get('turns', [])) + 1
            else:
                turn_number = 2

            # Submit continuation
            new_session_id = client.continue_session(session_id, message, user_id, turn_number)

            if new_session_id:
                # Poll for results
                output = await poll_for_results(new_session_id, server_url_value, user_id)

                # Add conversation history
                output += "\n\n---\n### 💬 Conversation History:\n\n"
                session_info = client.get_multiturn_session_info(session_id, user_id)
                if session_info and session_info.get('turns'):
                    for turn in session_info['turns']:
                        output += f"**Turn {turn['turn_number']}:** {turn.get('query', 'N/A')[:100]}...\n"

                return output
            else:
                return "## ❌ Error\n\nFailed to continue session."

        async def check_status(session_id, server_url_value, user_id):
            """Check status of a session"""
            if not session_id:
                return "## ❌ Error\n\nPlease select a session."

            client.base_url = server_url_value
            status = client.get_status(session_id, user_id)

            if status:
                output = f"## 📊 Session Status\n\n"
                output += f"**Session ID:** {session_id}\n\n"
                output += f"**Status:** {status.get('status', 'Unknown')}\n"
                output += f"**Complete:** {status.get('is_complete', False)}\n"
                output += f"**Created:** {status.get('created_at', 'Unknown')}\n"

                # Get snapshots
                snapshots = client.get_snapshots(session_id, user_id)
                if snapshots:
                    output += f"\n### 📸 Snapshots ({len(snapshots)}):\n\n"
                    for snapshot in snapshots:
                        output += f"- **{snapshot.get('name', 'Unnamed')}** ({snapshot.get('type', 'unknown')})\n"

                return output
            else:
                return "## ❌ Error\n\nFailed to get status."

        async def stop_task(session_id, server_url_value, user_id):
            """Stop a running task"""
            if not session_id:
                return "## ❌ Error\n\nPlease select a session to stop."

            client.base_url = server_url_value
            if client.stop_task(session_id, user_id):
                return "## ✅ Task Stopped\n\nThe task has been stopped successfully."
            else:
                return "## ❌ Error\n\nFailed to stop task. It may have already completed."

        async def download_results(session_id, server_url_value, user_id):
            """Download results for a session"""
            if not session_id:
                return "## ❌ Error\n\nPlease select a session to download."

            client.base_url = server_url_value
            file_path = client.download_results(session_id, user_id)

            if file_path:
                return f"## ✅ Download Ready\n\nResults saved to: {file_path}"
            else:
                return "## ❌ Error\n\nFailed to download results. Task may not be complete."

        async def delete_session(session_id, confirmed, server_url_value, user_id):
            """Permanently delete a session"""
            if not session_id:
                return "## ❌ Error\n\nPlease select a session to delete.", None

            if not confirmed:
                return "## ⚠️ Warning\n\nPlease check the confirmation box to delete.", None

            client.base_url = server_url_value
            if client.hard_delete_session(session_id, user_id):
                return "## ✅ Session Deleted\n\nThe session has been permanently deleted.", []
            else:
                return "## ❌ Error\n\nFailed to delete session.", None

        async def view_session_details(session_id, server_url_value, user_id):
            """View detailed information about a session"""
            if not session_id:
                return "## ❌ Error\n\nPlease select a session."

            client.base_url = server_url_value

            # Get session info
            session_info = client.get_multiturn_session_info(session_id, user_id)

            if session_info:
                output = f"## 📋 Session Details\n\n"
                output += f"**Session ID:** {session_id}\n"
                output += f"**Created:** {session_info.get('created_at', 'Unknown')}\n"
                output += f"**Language:** {session_info.get('language', 'Unknown')}\n\n"

                # Show turns
                turns = session_info.get('turns', [])
                if turns:
                    output += f"### 🔄 Conversation Turns ({len(turns)}):\n\n"
                    for turn in turns:
                        output += f"**Turn {turn['turn_number']}:**\n"
                        output += f"- Query: {turn.get('query', 'N/A')[:200]}...\n"
                        output += f"- Status: {turn.get('status', 'Unknown')}\n\n"

                # Get context
                context = client.get_session_context(session_id, user_id)
                if context:
                    output += "### 📝 Accumulated Context:\n\n"
                    output += f"```\n{context[:500]}...\n```\n" if len(context) > 500 else f"```\n{context}\n```\n"

                return output
            else:
                # Try regular session status
                return await check_status(session_id, server_url_value, user_id)

        def refresh_session_list(server_url_value, user_id):
            """Refresh the list of sessions"""
            client.base_url = server_url_value
            sessions = client.get_multiturn_sessions(user_id)

            if not sessions:
                sessions = client.get_all_sessions(user_id)

            choices = []
            for session in sessions:
                session_id = session.get('session_id', 'Unknown')
                created = session.get('created_at', 'Unknown')[:19] if session.get('created_at') else 'Unknown'
                query = session.get('query', 'No query')[:50]
                choices.append((f"{session_id[:8]}... | {created} | {query}", session_id))

            return gr.update(choices=choices, value=None)

        # Event connections
        connect_btn.click(
            fn=connect_to_server,
            inputs=[server_url_input, user_input],
            outputs=[connection_status, server_url_state, user_id]
        )

        submit_btn.click(
            fn=submit_request,
            inputs=[message_input, file_upload, language_select, server_url_state, user_id],
            outputs=[output_display, current_session_id]
        )

        clear_btn.click(
            fn=lambda: ("", None, None),
            outputs=[message_input, file_upload, output_display]
        )

        refresh_sessions_btn.click(
            fn=refresh_session_list,
            inputs=[server_url_state, user_id],
            outputs=[session_dropdown]
        )

        continue_btn.click(
            fn=continue_session,
            inputs=[session_dropdown, continue_message_input, server_url_state, user_id],
            outputs=[output_display]
        )

        refresh_status_sessions_btn.click(
            fn=refresh_session_list,
            inputs=[server_url_state, user_id],
            outputs=[status_session_selector]
        )

        check_status_btn.click(
            fn=check_status,
            inputs=[status_session_selector, server_url_state, user_id],
            outputs=[status_display]
        )

        stop_btn.click(
            fn=stop_task,
            inputs=[status_session_selector, server_url_state, user_id],
            outputs=[status_display]
        )

        download_btn.click(
            fn=download_results,
            inputs=[status_session_selector, server_url_state, user_id],
            outputs=[status_display]
        )

        refresh_manage_sessions_btn.click(
            fn=refresh_session_list,
            inputs=[server_url_state, user_id],
            outputs=[manage_session_selector]
        )

        view_details_btn.click(
            fn=view_session_details,
            inputs=[manage_session_selector, server_url_state, user_id],
            outputs=[session_details_display]
        )

        delete_btn.click(
            fn=delete_session,
            inputs=[manage_session_selector, delete_confirmation, server_url_state, user_id],
            outputs=[session_details_display, manage_session_selector]
        ).then(
            fn=lambda: False,
            outputs=[delete_confirmation]
        )

        # Initial connection
        interface.load(
            fn=connect_to_server,
            inputs=[server_url_input, user_input],
            outputs=[connection_status, server_url_state, user_id]
        )

    return interface


def main():
    """Main function to launch the interface"""
    parser = argparse.ArgumentParser(description="Simplified Gradio Interface for FastAPI Agent Server")
    parser.add_argument("--server", type=str, default="http://localhost:8001",
                      help="FastAPI server URL (default: http://localhost:8001)")
    parser.add_argument("--port", type=int, default=7860,
                      help="Port to run Gradio interface on (default: 7860)")
    parser.add_argument("--user", type=str, default="default_user",
                      help="Default user ID (default: default_user)")
    parser.add_argument("--share", action="store_true",
                      help="Create a public link")

    args = parser.parse_args()

    print(f"Connecting to FastAPI server at: {args.server}")
    print(f"Default user ID: {args.user}")

    # Create and launch interface
    interface = create_interface(server_url=args.server, user=args.user)

    interface.launch(
        server_name="0.0.0.0",
        server_port=args.port,
        share=args.share,
        show_error=True
    )


if __name__ == "__main__":
    main()
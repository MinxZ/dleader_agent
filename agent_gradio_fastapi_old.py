"""
Gradio Interface for FastAPI Agent Server

This interface provides a clean Gradio frontend that communicates with the FastAPI agent server:
- Submits requests to the FastAPI server's queue system
- Polls for status updates and results
- Displays results without streaming (as requested)
- Handles file uploads through the API
"""

import argparse
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

    def __init__(self, base_url: str = "http://localhost:8002"):
        self.base_url = base_url.rstrip('/')

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


def process_request(message: str, files: List, server_url: str, language: str):
    """Process request using FastAPI backend"""
    if not message.strip():
        return (
            "## ❌ Error\n\nPlease enter a request to process.",
            "## ❌ No Input\n\nPlease enter a request to process.",
            gr.update(visible=False),
            gr.update(visible=False)
        )

    # Initialize client
    client = FastAPIClient(server_url)

    # Check server health
    if not client.health_check():
        return (
            "## ❌ Server Error\n\nCannot connect to FastAPI server. Please ensure the server is running.",
            "## ❌ Server Error\n\nCannot connect to FastAPI server.",
            gr.update(visible=False),
            gr.update(visible=False)
        )

    # Prepare file paths
    file_paths = []
    if files:
        for file in files:
            if file is not None:
                file_paths.append(file.name)

    # Submit request and wait for completion
    try:
        result = client.submit_and_wait(message, file_paths, language)

        if result.get("error"):
            error_report = f"""## ❌ Processing Error

**Error:** {result['error']}

**Session ID:** {result.get('session_id', 'N/A')}
**Status:** {result.get('status', 'Unknown')}
**Timestamp:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
            return (
                error_report,
                "## ❌ Processing Failed\n\nError details displayed in the results panel →",
                gr.update(visible=False),
                gr.update(visible=False)
            )

        elif result.get("success"):
            # Format final report
            final_report = result.get("final_report", "Processing completed successfully.")
            thinking_content = result.get("thinking_content", "")
            session_id = result.get("session_id", "")
            session_path = result.get("session_path", "")

            # Create result display
            result_display = f"""## ✅ Processing Complete

{final_report}

---

**Session Information:**
- **Session ID:** {session_id}
- **Session Path:** {session_path}
- **Completed:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""

            status_display = f"""## ✅ Task Completed Successfully

**Status:** ✅ Completed
**Session ID:** {session_id}
**Completed:** {datetime.now().strftime('%H:%M:%S')}

Results are displayed in the results panel →
"""

            # Create download files
            report_file = create_download_file(final_report, "report", "md")
            thinking_file = create_download_file(thinking_content, "thinking_process", "txt") if thinking_content else None

            return (
                result_display,
                status_display,
                gr.update(visible=True, value=report_file) if report_file else gr.update(visible=False),
                gr.update(visible=True, value=thinking_file) if thinking_file else gr.update(visible=False)
            )

        else:
            return (
                "## ❌ Unknown Error\n\nReceived unexpected response from server.",
                "## ❌ Unknown Error\n\nReceived unexpected response from server.",
                gr.update(visible=False),
                gr.update(visible=False)
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
            gr.update(visible=False)
        )


def create_interface():
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
                        value="http://localhost:8002",
                        placeholder="http://localhost:8002"
                    )
                    language_choice = gr.Dropdown(
                        label="Language",
                        choices=[("English", "en"), ("Japanese", "jp")],
                        value="en"
                    )

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

The system will communicate with the FastAPI server and display results without streaming.
""",
                    height=600
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

The system will communicate with the FastAPI server and display results without streaming.
""",  # Reset results
                gr.update(visible=False),  # Hide download buttons
                gr.update(visible=False)
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

    return demo


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Gradio Interface for FastAPI Agent Server")
    parser.add_argument("--server_port", type=int, default=7862, help="Port to run the Gradio server on (default: 7862)")
    parser.add_argument("--fastapi_url", type=str, default="http://localhost:8002", help="FastAPI server URL")
    args = parser.parse_args()

    print(f"Starting Gradio interface on port {args.server_port}")
    print(f"Configured to connect to FastAPI server at: {args.fastapi_url}")

    demo = create_interface()
    demo.launch(
        server_name="0.0.0.0",
        server_port=args.server_port,
        share=True,
        debug=True
    )
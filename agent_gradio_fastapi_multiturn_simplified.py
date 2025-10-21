"""
Multi-Turn Gradio Interface for FastAPI Agent Server

This interface provides a multi-turn conversation frontend that communicates with the FastAPI agent server:
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
from io import BytesIO

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

    def get_json_results(self, session_id: str, user_id: str, turn_number: Optional[int] = None) -> Optional[dict]:
        """Get structured JSON results for a completed session, optionally for a specific turn"""
        try:
            params = {"user_id": user_id}
            if turn_number is not None:
                params["turn_number"] = turn_number
            response = requests.get(f"{self.base_url}/results/{session_id}",
                                  params=params, timeout=10)
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            print(f"Error getting JSON results: {e}")
            return None

    def get_snapshots(self, session_id: str, user_id: str, turn_number: Optional[int] = None) -> Optional[dict]:
        """Get all periodic snapshots for a session, optionally for a specific turn"""
        try:
            params = {"user_id": user_id}
            if turn_number is not None:
                params["turn_number"] = turn_number
            response = requests.get(f"{self.base_url}/snapshots/{session_id}",
                                  params=params, timeout=10)
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

    def get_all_multiturn_sessions(self, user_id: str = None, limit: int = 10, offset: int = 0) -> dict:
        """Get multi-turn sessions with pagination"""
        try:
            url = f"{self.base_url}/multiturn-sessions"
            params = {}
            if user_id:
                params["user_id"] = user_id
            params["limit"] = limit
            params["offset"] = offset
            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                return {
                    "sessions": data.get("sessions", []),
                    "total": data.get("total", 0),
                    "limit": data.get("limit", limit),
                    "offset": data.get("offset", offset)
                }
            return {"sessions": [], "total": 0, "limit": limit, "offset": offset}
        except Exception as e:
            print(f"Error getting multi-turn sessions: {e}")
            return {"sessions": [], "total": 0, "limit": limit, "offset": offset}

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
        img = Image.open("dleader_logo.png")
        return img
    except:
        return None


def download_images_from_urls(image_list: list) -> List[Image.Image]:
    """Download images from S3 URLs and return as PIL Images for Gradio display"""
    images = []
    if not image_list:
        return images

    for item in image_list:
        try:
            # Extract URL from the image item
            url = None
            if isinstance(item, dict):
                url = item.get('url') or item.get('presigned_url')
            elif isinstance(item, str) and item.startswith('http'):
                url = item

            if url:
                # Download image from URL
                response = requests.get(url, timeout=10)
                if response.status_code == 200:
                    img = Image.open(BytesIO(response.content))
                    images.append(img)
                    print(f"✓ Downloaded image from URL: {url[:50]}...")
        except Exception as e:
            print(f"Warning: Could not download image: {e}")
            continue

    return images


async def view_multiturn_session(session_selection: str, server_url: str, user_id: str):
    """View complete multi-turn session history, defaulting to show the last turn"""
    if not session_selection or not session_selection.strip():
        return (
            gr.update(value="## ❌ Error\n\nNo session selected. Please select a session first.", visible=True),
            gr.update(visible=False),
            gr.update(choices=[], value=None),
            gr.update(value=[], visible=False),
            ""
        )

    # Extract session ID from selection (format: "SESSION_ID... | status | turns | query...")
    # Or it might just be a plain session ID
    session_id = session_selection.split(' ')[0] if ' ' in session_selection else session_selection

    # Initialize client
    client = FastAPIClient(server_url)

    # Check server health
    if not client.health_check():
        return (
            gr.update(value="## ❌ Server Error\n\nCannot connect to FastAPI server.", visible=True),
            gr.update(visible=False),
            gr.update(choices=[], value=None),
            gr.update(value=[], visible=False),
            ""
        )

    try:
        # Extract total_turns from the selection label (from /multiturn-sessions list)
        # Format: "emoji time | X turns | query"
        total_turns = 1  # Default
        if '|' in session_selection and 'turns' in session_selection:
            parts = session_selection.split('|')
            if len(parts) >= 2:
                turns_part = parts[1].strip()  # "X turns"
                try:
                    total_turns = int(turns_part.split()[0])
                except:
                    total_turns = 1

        # Get the last turn data using /results (without turn_number to get latest)
        last_turn_data = client.get_json_results(session_id, user_id)

        if not last_turn_data:
            return (
                gr.update(value=f"## ❌ Session Not Found\n\nSession ID '{session_id}' not found.", visible=True),
                gr.update(visible=False),
                gr.update(choices=[], value=None),
                gr.update(value=[], visible=False),
                ""
            )

        # Extract info from last turn
        current_turn = last_turn_data.get('current_turn', total_turns)
        status = last_turn_data.get('status', 'unknown')
        timestamp = last_turn_data.get('timestamp', 'N/A')
        query = last_turn_data.get('query', 'No query')

        # Build turn selector choices based on total_turns from the list
        turn_choices = []
        if total_turns > 0:
            for i in range(1, total_turns + 1):
                turn_choices.append((f"Turn {i}", i))

        # Display session overview showing only the last turn
        result_display = f"""## 💬 Multi-Turn Session View

**Session ID:** `{session_id}`
**Total Turns:** {total_turns}
**Showing:** Turn {current_turn} (Latest)
**Status:** {status.title()}
**Timestamp:** {timestamp}

---

## 🔍 Turn {current_turn} (Latest)

**Query:** {query}

"""

        # Get content from last turn
        content = last_turn_data.get('content', {})
        final_report = content.get('final_report', '')

        if final_report:
            result_display += f"""**Final Report:**

{final_report}

---

"""

        # Get files from the last turn
        files = last_turn_data.get('files', {})

        # Show zip download URL after final report, before images
        session_zip_url = files.get('session_zip')
        if session_zip_url:
            result_display += f"""**📦 Download:**

[Download Complete Session (ZIP)]({session_zip_url})

---

"""

        # Get images from the last turn
        last_turn_images = []
        if 'images' in files and files['images']:
            print(f"Found {len(files['images'])} images in last turn")
            last_turn_images = download_images_from_urls(files['images'])
            result_display += f"\n**📸 {len(last_turn_images)} images from this turn**\n"

        result_display += f"\n\n💡 *Use the turn selector above to view other turns (1-{total_turns})*\n"

        # Return with images from last turn
        print(f"Returning {len(last_turn_images)} images for display")
        return (
            gr.update(value=result_display, visible=True),  # Make conversation_display visible
            gr.update(visible=True),  # Show turn_navigation_group
            gr.update(choices=turn_choices, value=current_turn if current_turn > 0 else None),
            gr.update(value=last_turn_images, visible=True if last_turn_images else False),
            session_id  # Store session_id in state
        )

    except Exception as e:
        import traceback
        traceback.print_exc()
        return (
            gr.update(value=f"## ❌ Error\n\n{str(e)}", visible=True),
            gr.update(visible=False),
            gr.update(choices=[], value=None),
            gr.update(value=[], visible=False),
            ""
        )


async def view_specific_turn(session_id: str, turn_number: int, server_url: str, user_id: str):
    """View specific turn details using /results endpoint with turn_number"""
    if not session_id or not session_id.strip():
        return gr.update(value="## ❌ Error\n\nNo session selected.", visible=True), gr.update(value=[], visible=False)

    if not turn_number:
        return gr.update(value="## ❌ Error\n\nPlease select a turn number.", visible=True), gr.update(value=[], visible=False)

    # Initialize client
    client = FastAPIClient(server_url)

    # Check server health
    if not client.health_check():
        return gr.update(value="## ❌ Server Error\n\nCannot connect to FastAPI server.", visible=True), gr.update(value=[], visible=False)

    try:
        # Step 1: Get turn-specific results from /results endpoint
        results_data = client.get_json_results(session_id, user_id, turn_number=turn_number)
        if not results_data:
            return gr.update(value=f"## ❌ Turn Not Found\n\nTurn {turn_number} not found for session {session_id}.", visible=True), gr.update(value=[], visible=False)

        # Extract turn info
        turn_num = results_data.get('turn_number', turn_number)
        current_turn = results_data.get('current_turn', 0)
        total_turns = results_data.get('total_turns', 0)
        status = results_data.get('status', 'unknown')
        timestamp = results_data.get('timestamp', 'N/A')
        query = results_data.get('query', 'No query')

        # Display turn details
        result_display = f"""## 🔍 Turn {turn_num} Details

**Session ID:** `{session_id}`
**Turn:** {turn_num}/{total_turns}
**Status:** {status.title()}
**Timestamp:** {timestamp}
**Query:** {query}

---

"""

        # Get content from /results
        content = results_data.get('content', {})
        final_report = content.get('final_report', '')

        # Show final report FIRST (if available and turn is completed)
        if final_report and status == 'completed':
            result_display += f"""## 📋 Final Report

{final_report}

---

"""

        # Get files from /results
        files = results_data.get('files', {})

        # Show zip download URL after final report, before images
        session_zip_url = files.get('session_zip')
        if session_zip_url and status == 'completed':
            result_display += f"""## 📦 Download Session

[**Download Complete Session (ZIP)**]({session_zip_url})

---

"""

        # Extract images from files (from /results)
        turn_images = []
        if files:
            result_display += "## 📁 Generated Files\n\n"
            for file_type, file_list in files.items():
                if isinstance(file_list, list) and file_list:
                    result_display += f"**{file_type.replace('_', ' ').title()}:**\n"
                    for file_item in file_list:
                        if isinstance(file_item, dict):
                            filename = file_item.get('filename', 'Unknown')
                            url = file_item.get('url', '')
                            if url:
                                result_display += f"- [{filename}]({url})\n"
                            else:
                                result_display += f"- {filename}\n"
                    result_display += "\n"

                    # Download images for gallery
                    if file_type == 'images':
                        print(f"Downloading {len(file_list)} images for turn {turn_num}...")
                        turn_images = download_images_from_urls(file_list)

        # Add note about images being displayed below
        if turn_images:
            result_display += f"\n**📸 {len(turn_images)} images from this turn (shown below)**\n\n"

        # Step 2: For completed turns, get thinking process from /snapshots separately
        if status == 'completed':
            snapshots_data = client.get_snapshots(session_id, user_id, turn_number=turn_number)
            if snapshots_data:
                # The API now returns 'thinking_process' as text directly
                thinking_process_text = snapshots_data.get('thinking_process')
                if thinking_process_text:
                    # Show FULL thinking process (NO TRUNCATION, PLAIN TEXT)
                    result_display += f"""

## 🧠 Thinking Process

{thinking_process_text}

---

"""

        # Return display and images
        print(f"Returning {len(turn_images)} images for turn {turn_number}")
        if turn_images:
            return gr.update(value=result_display, visible=True), gr.update(value=turn_images, visible=True)
        else:
            return gr.update(value=result_display, visible=True), gr.update(value=[], visible=False)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return gr.update(value=f"## ❌ Error\n\n{str(e)}", visible=True), gr.update(value=[], visible=False)





async def check_status_with_history(session_id: str, server_url: str, user_id: str):
    """Check status of a session and show report/images immediately

    Optimized flow for completed sessions:
    1. Call /results ONLY to get status, report, and images
    2. Show report and images immediately
    3. Thinking process loaded separately when user clicks that tab

    For in-progress sessions:
    - Shows status and current thinking process together
    """
    import time
    start_total = time.time()

    if not session_id.strip():
        return "## ❌ Error\n\nPlease enter a Session ID to check status.", gr.update(visible=False), gr.update(visible=False), None

    # Initialize client
    client = FastAPIClient(server_url)

    # Check server health
    if not client.health_check():
        return "## ❌ Server Error\n\nCannot connect to FastAPI server. Please ensure the server is running.", gr.update(visible=False), gr.update(visible=False), None

    try:
        # STEP 1: Get results data (contains everything: status, report, images)
        start_api = time.time()
        results_data = client.get_json_results(session_id, user_id)
        print(f"⏱️  [STATUS] get_json_results: {(time.time() - start_api) * 1000:.2f} ms")

        if not results_data:
            # Fallback to /status if /results fails (for in-progress sessions)
            start_api = time.time()
            status_data = client.get_status(session_id, user_id)
            print(f"⏱️  [STATUS] get_status (fallback): {(time.time() - start_api) * 1000:.2f} ms")
            if not status_data:
                return f"## ❌ Session Not Found\n\nSession ID '{session_id}' not found on server.", gr.update(visible=False), gr.update(visible=False), None

            # Use status data for in-progress sessions
            current_status = status_data.get("status", "unknown")
            is_complete = status_data.get("is_complete", False)
            current_turn = None
            total_turns = None
        else:
            # Extract status from results_data
            current_status = results_data.get("status", "completed")
            is_complete = True  # /results only works for completed sessions
            current_turn = results_data.get('current_turn')
            total_turns = results_data.get('total_turns')

        # Main status section
        status_emoji = {
            'queued': '📋',
            'processing': '🔄',
            'completed': '✅',
            'failed': '❌',
            'error': '❌',
            'cancelled': '🛑'
        }.get(current_status, '❓')

        turn_info = f"\n**Turn:** {current_turn}/{total_turns}" if current_turn and total_turns else ""

        result_display = f"""## {status_emoji} Session: {session_id[:8]}...

**Status:** {current_status.title()}
**Complete:** {'Yes' if is_complete else 'No'}{turn_info}"""

        # Add error information if available
        if results_data and results_data.get("error"):
            result_display += f"""
**Error:** {results_data['error']}"""

        # STEP 2: Show final report and images immediately (from /results data)
        status_images = []

        if is_complete and results_data:
            # Extract final report
            if 'content' in results_data and 'final_report' in results_data['content']:
                final_report = results_data['content']['final_report']
                if final_report:
                    # For old sessions stored in cloud, remove XML tags here as a fallback
                    import re
                    # Extract content from <solution> tags if present
                    if '<solution>' in final_report and '</solution>' in final_report:
                        start_idx = final_report.find('<solution>') + len('<solution>')
                        end_idx = final_report.find('</solution>')
                        final_report = final_report[:final_report.find('<solution>')] + final_report[start_idx:end_idx].strip() + final_report[end_idx + len('</solution>'):]

                    # Remove any remaining XML-like tags
                    final_report = re.sub(r'</?[a-zA-Z_][a-zA-Z0-9_]*(?:\s+[^>]*)?>', '', final_report)

                    # The API already includes "## ✅ Final Report" heading
                    result_display += f"""

{final_report}

"""

            # Show zip download URL after final report, before images
            if 'files' in results_data:
                files = results_data['files']
                session_zip_url = files.get('session_zip')
                if session_zip_url:
                    result_display += f"""## 📦 Download Session

[**Download Complete Session (ZIP)**]({session_zip_url})

---

"""

            # Extract and download images from /results (optimized)
            if 'files' in results_data:
                files = results_data['files']
                if 'images' in files and files['images']:
                    print(f"Found {len(files['images'])} images in /results")
                    start_images = time.time()
                    # Limit to first 10 images for faster rendering
                    image_urls = files['images'][:10] if len(files['images']) > 10 else files['images']
                    status_images = download_images_from_urls(image_urls)
                    print(f"⏱️  [STATUS] download_images: {(time.time() - start_images) * 1000:.2f} ms")
                    if len(files['images']) > 10:
                        print(f"⚠️  Showing first 10 of {len(files['images'])} images for performance")

            # Add image count info
            if status_images:
                result_display += f"\n\n**📸 {len(status_images)} images from latest turn shown below**\n\n"

            # Add note about thinking process in separate tab
            result_display += f"""

---

💡 **Tip:** Click the "🧠 Thinking Process" tab to view detailed agent reasoning steps.

"""

            # Return with images if available (NO snapshots call for completed sessions)
            backend_time = (time.time() - start_total) * 1000
            print(f"⏱️  [BACKEND] Total processing time: {backend_time:.2f} ms")
            print(f"⏱️  [GRADIO] About to return to Gradio (render time will be added by Gradio)")

            start_return = time.time()
            if status_images:
                result = (result_display, gr.update(visible=False), gr.update(value=status_images, visible=True), results_data)
            else:
                result = (result_display, gr.update(visible=False), gr.update(value=[], visible=False), results_data)

            print(f"⏱️  [RETURN] Preparing return objects: {(time.time() - start_return) * 1000:.2f} ms")
            return result

        # For non-completed sessions (in progress), show thinking process from /snapshots
        else:
            # For in-progress sessions, try to get images from /status if available
            if not results_data and 'progress_updates' in status_data:
                # Check if there are images in progress updates
                for update in status_data.get('progress_updates', []):
                    if update.get('type') == 'completion' and 'files' in update:
                        files = update['files']
                        if 'images' in files and files['images']:
                            print(f"Found {len(files['images'])} images in progress updates")
                            start_images = time.time()
                            status_images = download_images_from_urls(files['images'])
                            print(f"⏱️  [STATUS] download_images: {(time.time() - start_images) * 1000:.2f} ms")
                            break

            # Get current thinking process from /snapshots for in-progress sessions
            start_api = time.time()
            snapshots_data = client.get_snapshots(session_id, user_id)
            print(f"⏱️  [STATUS] get_snapshots (in-progress): {(time.time() - start_api) * 1000:.2f} ms")
            if snapshots_data:
                # The API now returns 'thinking_process' as text directly
                thinking_process_text = snapshots_data.get('thinking_process')
                if thinking_process_text:
                    # Show FULL thinking process (NO TRUNCATION, PLAIN TEXT)
                    result_display += f"""

## 🧠 Thinking Process (In Progress)

{thinking_process_text}

---

"""

        # For non-completed sessions, hide download component and images
        print(f"⏱️  [STATUS] TOTAL TIME: {(time.time() - start_total) * 1000:.2f} ms")
        if status_images:
            result_display += f"\n\n**📸 {len(status_images)} images from current turn shown below**\n\n"
            return result_display, gr.update(visible=False), gr.update(value=status_images, visible=True), results_data
        else:
            return result_display, gr.update(visible=False), gr.update(value=[], visible=False), results_data

    except Exception as e:
        import traceback
        traceback.print_exc()
        error_msg = f"""## ❌ Status Check Error

**Error:** {str(e)}
**Session ID:** {session_id}
**Timestamp:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""
        return error_msg, gr.update(visible=False), gr.update(visible=False), None


async def load_thinking_process(session_id: str, server_url: str, user_id: str):
    """Load thinking process/snapshots for a completed session - ONLY called when user clicks the tab

    This function is called separately when user clicks the "Thinking Process" tab
    to avoid slowing down the initial status check.
    """
    import time
    start_time = time.time()

    if not session_id or not session_id.strip():
        return "ℹ️ No Session Selected\n\nPlease check a session status first, then click this tab to view thinking process."

    # Initialize client
    client = FastAPIClient(server_url)

    # Check server health
    if not client.health_check():
        return "❌ Server Error\n\nCannot connect to FastAPI server. Please ensure the server is running."

    try:
        # Get snapshots for the session
        print(f"Loading thinking process for session: {session_id}")
        start_api = time.time()
        snapshots_data = client.get_snapshots(session_id, user_id)
        print(f"⏱️  [THINKING] get_snapshots: {(time.time() - start_api) * 1000:.2f} ms")

        if not snapshots_data:
            return f"❌ No Thinking Process Found\n\nNo thinking process data available for session {session_id[:8]}..."

        # Extract thinking_process text directly from the new API format
        thinking_process_text = snapshots_data.get('thinking_process')
        current_turn = snapshots_data.get('current_turn', 1)
        total_turns = snapshots_data.get('total_turns', 1)

        if not thinking_process_text:
            return f"ℹ️ No Thinking Process\n\nNo thinking process recorded for session {session_id[:8]}...\n\nTurn: {current_turn}/{total_turns}"

        # Build display with FULL thinking process text (NO TRUNCATION, PLAIN TEXT)
        result_display = f"""🧠 Thinking Process

Session: {session_id[:8]}...
Turn: {current_turn}/{total_turns}

{'='*80}

{thinking_process_text}

{'='*80}

"""

        total_time = (time.time() - start_time) * 1000
        print(f"⏱️  [THINKING] TOTAL TIME: {total_time:.2f} ms")
        print(f"⏱️  [THINKING] Thinking process length: {len(thinking_process_text)} characters")
        result_display += f"\n\nLoaded thinking process ({len(thinking_process_text):,} characters) in {total_time:.0f}ms"

        return result_display

    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"""❌ Error Loading Thinking Process

Error: {str(e)}
Session ID: {session_id}
Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""


def get_session_history(server_url: str, user_id: str = None) -> List[tuple]:
    """Get multi-turn session history for dropdown selection"""
    try:
        client = FastAPIClient(server_url)
        if not client.health_check():
            return [("Server not available", "")]

        # Use multiturn sessions instead of all sessions (default: latest 10)
        result = client.get_all_multiturn_sessions(user_id=user_id, limit=10, offset=0)
        sessions = result.get('sessions', [])

        if not sessions:
            return [("No sessions available", "")]

        items = []
        for session in sessions:
            # Status emoji based on session_status (not individual turn status)
            status_emoji = {
                'active': '🔄',
                'completed': '✅',
                'failed': '❌',
                'error': '❌',
                'cancelled': '🛑'
            }.get(session.get('session_status', 'unknown'), '❓')

            # Use last_updated or created_at timestamp
            timestamp = session.get('last_updated') or session.get('created_at', '')
            if timestamp:
                try:
                    dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    time_str = dt.strftime('%m/%d %H:%M')
                except:
                    time_str = timestamp[:16]
            else:
                time_str = 'Unknown'

            # Get session info
            session_id = session.get('session_id', '')
            session_name = session.get('session_name', '')
            total_turns = session.get('total_turns', 0)
            first_query = session.get('first_query', 'No query')

            # Create display label with session name or first query
            display_text = session_name if session_name else first_query[:40]
            label = f"{status_emoji} {time_str} | {total_turns} turns | {display_text}..."
            items.append((label, session_id))

        return items
    except Exception as e:
        print(f"Error getting session history: {e}")
        import traceback
        traceback.print_exc()
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
                gr.Markdown("### ⚙️ User Configuration")
                server_url = gr.State(value=default_fastapi_url)  # Hidden state variable
                current_session_id_state = gr.State(value="")  # Store current session ID for turn navigation
                user_id_input = gr.Dropdown(
                    label="User ID",
                    choices=["Test user", "Chen", "Yuan", "Zhang", "Tom"],
                    value="Test user",
                    allow_custom_value=True,
                    info="Select a user or type a custom ID"
                )

        # Main interface with tabs
        with gr.Tabs():

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
                            with gr.Row(visible=False) as session_controls_row:
                                refresh_multiturn_sessions_btn = gr.Button(
                                    "🔄 Refresh Sessions",
                                    variant="secondary",
                                    scale=2
                                )
                                load_more_sessions_btn = gr.Button(
                                    "⬇️ Load More",
                                    variant="secondary",
                                    scale=1
                                )

                            existing_session_selector = gr.Dropdown(
                                label="Select existing session to continue",
                                choices=[],
                                value="",
                                interactive=True,
                                visible=False,
                                allow_custom_value=True
                            )

                            # Session pagination info (hidden)
                            sessions_pagination_info = gr.Markdown(
                                "",
                                visible=False
                            )

                            # Hidden state for pagination
                            sessions_offset_state = gr.State(value=0)
                            sessions_total_state = gr.State(value=0)

                            # New conversation inputs
                            new_conversation_group = gr.Group(visible=True)
                            with new_conversation_group:
                                multiturn_query = gr.Textbox(
                                    label="Your Question or Request",
                                    placeholder="What would you like me to help you with?",
                                    lines=3,
                                    max_lines=5
                                )

                                multiturn_files = gr.File(
                                    label="Upload Files (optional)",
                                    file_count="multiple",
                                    type="filepath"
                                )

                                with gr.Row():
                                    multiturn_language = gr.Dropdown(
                                        choices=["en", "jp"],
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

                                continue_files = gr.File(
                                    label="Upload Files (optional)",
                                    file_count="multiple",
                                    type="filepath"
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

                        # View Session History button (always visible)
                        with gr.Row():
                            view_session_btn = gr.Button("📖 View Session History", variant="secondary", size="lg")

                        # Turn navigation controls (hidden until session is loaded)
                        with gr.Group(visible=False) as turn_navigation_group:
                            gr.Markdown("### 🔄 Navigate Between Turns")
                            with gr.Row():
                                turn_selector = gr.Dropdown(
                                    label="Select Turn",
                                    choices=[],
                                    value=None,
                                    interactive=True,
                                    scale=2
                                )
                                refresh_turn_btn = gr.Button("🔄 Refresh", variant="secondary", scale=1)

                        # Conversation display
                        conversation_display = gr.Markdown(
                            "",
                            visible=False,
                            height=500
                        )

                        # Image gallery for displaying images from turns
                        turn_images_gallery = gr.Gallery(
                            label="Turn Images",
                            visible=False,
                            columns=3,
                            height=400,
                            object_fit="contain"
                        )

                        # Session info
                        multiturn_session_info = gr.Markdown(
                            "",
                            visible=False
                        )

            # Check Status Tab
            with gr.Tab("🔍 Check Status"):
                with gr.Row():
                    with gr.Column(scale=1):
                        gr.Markdown("## 🔍 Check Request Status")

                        with gr.Group():
                            gr.Markdown("### 📋 Session Selection")

                            # Session controls
                            with gr.Row():
                                refresh_status_history_btn = gr.Button("🔄 Refresh", variant="secondary", scale=2)
                                load_more_status_btn = gr.Button("⬇️ Load More", variant="secondary", scale=1)

                            # Session selector dropdown
                            status_session_selector = gr.Dropdown(
                                label="Select a session to check status",
                                choices=[],  # Will be populated when user_id is provided
                                value="",
                                interactive=True,
                                allow_custom_value=True
                            )

                            # Pagination info
                            status_pagination_info = gr.Markdown("", visible=False)

                            # Hidden states for pagination
                            status_offset_state = gr.State(value=0)
                            status_total_state = gr.State(value=0)
                            current_status_session_id = gr.State(value="")  # Store selected session

                            with gr.Row():
                                check_btn = gr.Button("🔍 Check Status", variant="primary", scale=2)
                                clear_status_btn = gr.Button("🗑️ Clear", variant="secondary", scale=1)

                    with gr.Column(scale=1):
                        gr.Markdown("## 📋 Status Results")

                        # Turn selector (hidden until session is selected)
                        with gr.Group(visible=False) as status_turn_selector_group:
                            gr.Markdown("### 🔄 Select Turn")
                            status_turn_selector = gr.Dropdown(
                                label="View specific turn",
                                choices=[],
                                value=None,
                                interactive=True
                            )

                        # Tabs for status results and thinking process
                        with gr.Tabs() as status_tabs:
                            with gr.Tab("📋 Status & Report", id="status_report_tab"):
                                status_results = gr.Markdown(
                                    """## 📋 Status Check

Select a session from the dropdown to check status and view report.

**Features:**
- Real-time status updates
- Final report display
- Image gallery for completed sessions
- Turn selector to view different turns
- Separate thinking process tab (loads on demand)

**Instructions:**
1. Click "🔄 Refresh" to load latest 10 sessions
2. Click "⬇️ Load More" to load next 10 sessions
3. Select a session from the dropdown
4. Click "🔍 Check Status"
5. Use turn selector to view different turns
6. Click "🧠 Thinking Process" tab to view agent reasoning

For completed sessions, the final report and images will appear here.""",
                                    max_height="600px"
                                )

                                # Image gallery for status check
                                status_images_gallery = gr.Gallery(
                                    label="Session Images",
                                    visible=False,
                                    columns=3,
                                    height=400,
                                    object_fit="contain"
                                )

                            with gr.Tab("🧠 Thinking Process", id="thinking_tab"):
                                gr.Markdown("""### Agent Reasoning Steps

This tab shows the detailed thinking process and reasoning steps from the agent.

**Note:** This loads ONLY when you click this tab (to improve initial load speed).

Click "🔄 Load Thinking" after checking a session status to view the reasoning steps.""")

                                load_thinking_btn = gr.Button("🔄 Load Thinking Process", variant="primary")

                                thinking_display = gr.Textbox(
                                    value="No thinking process loaded yet.\n\nInstructions:\n1. First, check a session status in the '📋 Status & Report' tab\n2. Then click the '🔄 Load Thinking Process' button above\n\nThe thinking process will load on-demand to keep the interface fast.",
                                    label="🧠 Thinking Process",
                                    lines=20,
                                    max_lines=None,
                                    show_copy_button=True,
                                    interactive=False
                                )

            # Stop Task Tab
            with gr.Tab("🛑 Stop Task"):
                with gr.Row():
                    with gr.Column(scale=1):
                        gr.Markdown("## 🛑 Stop Running Task")

                        with gr.Group():
                            gr.Markdown("### 📋 Select Session")

                            # Session controls
                            with gr.Row():
                                refresh_stop_history_btn = gr.Button("🔄 Refresh", variant="secondary", scale=2)
                                load_more_stop_btn = gr.Button("⬇️ Load More", variant="secondary", scale=1)

                            # History selector dropdown
                            stop_session_selector = gr.Dropdown(
                                label="Select a session to stop",
                                choices=[],  # Will be populated when user_id is provided
                                value="",
                                interactive=True,
                                allow_custom_value=True
                            )

                            # Pagination info
                            stop_pagination_info = gr.Markdown("", visible=False)

                            # Hidden states for pagination
                            stop_offset_state = gr.State(value=0)
                            stop_total_state = gr.State(value=0)

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

        def refresh_stop_history(user_id, offset=0):
            """Refresh the stop task session list with pagination"""
            client = FastAPIClient(server_url.value)
            result = client.get_all_multiturn_sessions(user_id=user_id, limit=10, offset=offset)
            sessions = result.get('sessions', [])
            total = result.get('total', 0)

            items = []
            for session in sessions:
                status_emoji = {
                    'active': '🔄',
                    'completed': '✅',
                    'failed': '❌',
                    'error': '❌',
                    'cancelled': '🛑'
                }.get(session.get('session_status', 'unknown'), '❓')

                timestamp = session.get('last_updated') or session.get('created_at', '')
                if timestamp:
                    try:
                        dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                        time_str = dt.strftime('%m/%d %H:%M')
                    except:
                        time_str = timestamp[:16]
                else:
                    time_str = 'Unknown'

                session_id = session.get('session_id', '')
                session_name = session.get('session_name', '')
                total_turns = session.get('total_turns', 0)
                first_query = session.get('first_query', 'No query')

                display_text = session_name if session_name else first_query[:40]
                label = f"{status_emoji} {time_str} | {total_turns} turns | {display_text}..."
                items.append((label, session_id))

            showing_start = offset + 1 if total > 0 else 0
            showing_end = min(offset + 10, total)
            pagination_text = f"**Showing {showing_start}-{showing_end} of {total} sessions**"

            return (
                gr.update(choices=items, value=""),
                total,
                offset,
                gr.update(value=pagination_text, visible=True)
            )

        def refresh_status_history(user_id, offset=0):
            """Refresh the status check session list with pagination"""
            client = FastAPIClient(server_url.value)
            result = client.get_all_multiturn_sessions(user_id=user_id, limit=10, offset=offset)
            sessions = result.get('sessions', [])
            total = result.get('total', 0)

            items = []
            for session in sessions:
                status_emoji = {
                    'active': '🔄',
                    'completed': '✅',
                    'failed': '❌',
                    'error': '❌',
                    'cancelled': '🛑'
                }.get(session.get('session_status', 'unknown'), '❓')

                timestamp = session.get('last_updated') or session.get('created_at', '')
                if timestamp:
                    try:
                        dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                        time_str = dt.strftime('%m/%d %H:%M')
                    except:
                        time_str = timestamp[:16]
                else:
                    time_str = 'Unknown'

                session_id = session.get('session_id', '')
                session_name = session.get('session_name', '')
                total_turns = session.get('total_turns', 0)
                first_query = session.get('first_query', 'No query')

                display_text = session_name if session_name else first_query[:40]
                label = f"{status_emoji} {time_str} | {total_turns} turns | {display_text}..."
                items.append((label, session_id))

            showing_start = offset + 1 if total > 0 else 0
            showing_end = min(offset + 10, total)
            pagination_text = f"**Showing {showing_start}-{showing_end} of {total} sessions**"

            return (
                gr.update(choices=items, value=""),
                total,
                offset,
                gr.update(value=pagination_text, visible=True)
            )

        def load_more_status_sessions(user_id, current_offset, total):
            """Load next batch of sessions for status check"""
            new_offset = current_offset + 10
            if new_offset >= total:
                return (
                    gr.update(),
                    current_offset,
                    gr.update(value=f"**Showing all {total} sessions (end of list)**", visible=True)
                )
            return refresh_status_history(user_id, new_offset)

        def load_more_stop_sessions(user_id, current_offset, total):
            """Load next batch of sessions for stop task"""
            new_offset = current_offset + 10
            if new_offset >= total:
                return (
                    gr.update(),
                    current_offset,
                    current_offset,
                    gr.update(value=f"**Showing all {total} sessions (end of list)**", visible=True)
                )
            return refresh_stop_history(user_id, new_offset)

        async def check_status_from_dropdown(selected_session_id, server_url_value, user_id):
            """Check status using dropdown selection"""
            if not selected_session_id:
                status_text, _, images, _ = await check_status_with_history("", server_url_value, user_id)
                return (
                    status_text,
                    images,
                    gr.update(visible=False),
                    gr.update(choices=[], value=None),
                    selected_session_id
                )

            # Get status and results (results_data is returned to avoid duplicate API call)
            status_text, _, images, results_data = await check_status_with_history(selected_session_id, server_url_value, user_id)

            # Build turn choices based on current_turn and total_turns from results_data
            # (No need for duplicate /results call - reuse data from check_status_with_history)
            turn_choices = []
            if results_data and isinstance(results_data, dict):
                total_turns = results_data.get('total_turns', 0)
                current_turn = results_data.get('current_turn', 0)

                if total_turns and total_turns > 0:
                    turn_choices = [(f"Turn {i}", i) for i in range(1, total_turns + 1)]

            if turn_choices:
                return (
                    status_text,
                    images,
                    gr.update(visible=True),
                    gr.update(choices=turn_choices, value=current_turn if current_turn > 0 else None),
                    selected_session_id
                )
            else:
                return (
                    status_text,
                    images,
                    gr.update(visible=False),
                    gr.update(choices=[], value=None),
                    selected_session_id
                )

        async def view_status_turn(session_id, turn_number, server_url_value, user_id):
            """View specific turn for status check - uses /results then /snapshots separately"""
            if not session_id or not turn_number:
                return gr.update(), gr.update()

            # Initialize client
            client = FastAPIClient(server_url_value)

            # Step 1: Get turn-specific results first (/results endpoint)
            results_data = client.get_json_results(session_id, user_id, turn_number=turn_number)

            if not results_data:
                return gr.update(value=f"## ❌ Turn Not Found\n\nTurn {turn_number} not found.", visible=True), gr.update(visible=False)

            # Build display
            turn_num = results_data.get('turn_number', turn_number)
            total_turns = results_data.get('total_turns', 0)
            status = results_data.get('status', 'unknown')
            timestamp = results_data.get('timestamp', 'N/A')
            query = results_data.get('query', 'No query')

            result_display = f"""## 🔍 Turn {turn_num} Details

**Session ID:** `{session_id}`
**Turn:** {turn_num}/{total_turns}
**Status:** {status.title()}
**Timestamp:** {timestamp}
**Query:** {query}

---

"""

            # Get content from /results
            content = results_data.get('content', {})
            final_report = content.get('final_report', '')

            # Show final report FIRST (if available and turn is completed)
            if final_report and status == 'completed':
                result_display += f"""## 📋 Final Report

{final_report}

---

"""

            # Get files from /results
            files = results_data.get('files', {})

            # Show zip download URL after final report, before images
            session_zip_url = files.get('session_zip')
            if session_zip_url and status == 'completed':
                result_display += f"""## 📦 Download Session

[**Download Complete Session (ZIP)**]({session_zip_url})

---

"""

            # Get images from /results
            turn_images = []
            if 'images' in files and files['images']:
                print(f"Found {len(files['images'])} images for turn {turn_num}")
                turn_images = download_images_from_urls(files['images'])
                result_display += f"\n**📸 {len(turn_images)} images from this turn (shown below)**\n\n"

            # Add tip about thinking process tab
            if status == 'completed':
                result_display += f"""

---

💡 **Tip:** Click the "🧠 Thinking Process" tab and load thinking to view agent reasoning for this turn.

"""

            # NO snapshots call for completed turns - use the thinking process tab instead
            # Step 2: For IN-PROGRESS turns only, get thinking process from /snapshots
            if status != 'completed':
                snapshots_data = client.get_snapshots(session_id, user_id, turn_number=turn_number)
                if snapshots_data:
                    # The API now returns 'thinking_process' as text directly
                    thinking_process_text = snapshots_data.get('thinking_process')
                    if thinking_process_text:
                        # Show FULL thinking process (NO TRUNCATION, PLAIN TEXT)
                        result_display += f"""

## 🧠 Thinking Process (In Progress)

{thinking_process_text}

---

"""

            if turn_images:
                return gr.update(value=result_display, visible=True), gr.update(value=turn_images, visible=True)
            else:
                return gr.update(value=result_display, visible=True), gr.update(value=[], visible=False)

        # Wire up events

        # Status checking events
        # Refresh status session list
        refresh_status_history_btn.click(
            fn=refresh_status_history,
            inputs=[user_id_input, status_offset_state],
            outputs=[status_session_selector, status_total_state, status_offset_state, status_pagination_info]
        )

        # Load more sessions for status
        load_more_status_btn.click(
            fn=load_more_status_sessions,
            inputs=[user_id_input, status_offset_state, status_total_state],
            outputs=[status_session_selector, status_offset_state, status_pagination_info]
        )

        # Check status using dropdown selection
        check_btn.click(
            fn=check_status_from_dropdown,
            inputs=[status_session_selector, server_url, user_id_input],
            outputs=[status_results, status_images_gallery, status_turn_selector_group, status_turn_selector, current_status_session_id]
        )

        # Turn selector for status check
        status_turn_selector.change(
            fn=view_status_turn,
            inputs=[current_status_session_id, status_turn_selector, server_url, user_id_input],
            outputs=[status_results, status_images_gallery]
        )

        clear_status_btn.click(
            fn=clear_status_interface,
            outputs=[status_session_selector, status_results]
        )

        # Load thinking process button
        load_thinking_btn.click(
            fn=load_thinking_process,
            inputs=[current_status_session_id, server_url, user_id_input],
            outputs=[thinking_display]
        )

        # Stop task events
        refresh_stop_history_btn.click(
            fn=refresh_stop_history,
            inputs=[user_id_input, stop_offset_state],
            outputs=[stop_session_selector, stop_total_state, stop_offset_state, stop_pagination_info]
        )

        # Load more sessions for stop
        load_more_stop_btn.click(
            fn=load_more_stop_sessions,
            inputs=[user_id_input, stop_offset_state, stop_total_state],
            outputs=[stop_session_selector, stop_offset_state, stop_total_state, stop_pagination_info]
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
                    gr.update(visible=False),  # session_controls_row
                    gr.update(visible=False),  # existing_session_selector
                    gr.update(visible=False)   # sessions_pagination_info
                )
            else:  # Continue Existing Session
                return (
                    gr.update(visible=False),  # new_conversation_group
                    gr.update(visible=True),   # continue_conversation_group
                    gr.update(visible=True),   # session_controls_row
                    gr.update(visible=True),   # existing_session_selector
                    gr.update(visible=True)    # sessions_pagination_info
                )

        def get_multiturn_sessions(url, user_id=None, limit=10, offset=0):
            """Get list of multi-turn sessions with pagination"""
            try:
                client = FastAPIClient(url)
                result = client.get_all_multiturn_sessions(user_id, limit=limit, offset=offset)
                sessions_data = result.get("sessions", [])
                total = result.get("total", 0)

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
                    return choices, total
                return [], 0
            except Exception as e:
                print(f"Error getting multiturn sessions: {e}")
                return [], 0

        def get_all_multiturn_sessions(url, user_id=None):
            """Get all multi-turn sessions as dropdown choices for sharing"""
            choices, total = get_multiturn_sessions(url, user_id, limit=10, offset=0)
            return gr.update(choices=choices, value=""), total

        def refresh_multiturn_sessions(url, user_id, offset=0):
            """Refresh the multi-turn sessions dropdown with pagination"""
            choices, total = get_multiturn_sessions(url, user_id, limit=10, offset=offset)

            # Create pagination info text
            showing_start = offset + 1 if total > 0 else 0
            showing_end = min(offset + 10, total)
            pagination_text = f"**Showing {showing_start}-{showing_end} of {total} sessions**"

            return (
                gr.update(choices=choices, value=""),  # existing_session_selector
                total,  # sessions_total_state
                offset,  # sessions_offset_state
                gr.update(value=pagination_text, visible=True)  # sessions_pagination_info
            )

        def load_more_sessions(url, user_id, current_offset, total):
            """Load next batch of sessions"""
            new_offset = current_offset + 10
            if new_offset >= total:
                # Already at the end
                return (
                    gr.update(),  # existing_session_selector (no change)
                    current_offset,  # sessions_offset_state (no change)
                    gr.update(value=f"**Showing all {total} sessions (end of list)**", visible=True)
                )

            choices, total = get_multiturn_sessions(url, user_id, limit=10, offset=new_offset)

            # Create pagination info text
            showing_start = new_offset + 1
            showing_end = min(new_offset + 10, total)
            pagination_text = f"**Showing {showing_start}-{showing_end} of {total} sessions**"

            return (
                gr.update(choices=choices, value=""),  # existing_session_selector
                new_offset,  # sessions_offset_state
                gr.update(value=pagination_text, visible=True)  # sessions_pagination_info
            )

        def start_new_conversation(query, language, files, url, user_id):
            """Start a new multi-turn conversation"""
            if not query.strip():
                return (
                    gr.update(value="Please enter a question or request to start the conversation.", visible=True),
                    gr.update(visible=False),
                    gr.update(visible=False)
                )

            try:
                client = FastAPIClient(url)
                # Convert files to list of paths if provided
                file_paths = [f.name for f in files] if files else None
                session_id = client.submit_request(query, language, user_id, files=file_paths)

                if session_id:

                    # Show initial progress
                    files_info = f"\n**Files Uploaded:** {len(files)}" if files else ""
                    progress_text = f"""## 🚀 New Conversation Started

**Session ID:** `{session_id}`
**Status:** Processing...
**Query:** {query}{files_info}

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

        def continue_existing_conversation(session_selection, query, files, url, user_id):
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
                # Convert files to list of paths if provided
                file_paths = [f.name for f in files] if files else None
                response = client.continue_session(session_id, query, language="en", user_id=user_id, files=file_paths)

                if response and 'session_id' in response:
                    # Show progress
                    files_info = f"\n**Files Uploaded:** {len(files)}" if files else ""
                    progress_text = f"""## 💬 Conversation Continued

**Session ID:** `{session_id}`
**Status:** Processing...
**Follow-up Query:** {query}{files_info}

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
                None,  # multiturn_files
                gr.update(value="", choices=[]),  # existing_session_selector
                gr.update(value="## 💬 Multi-Turn Conversations\n\nChoose to start a new conversation or continue an existing one from the left panel.", visible=True),  # multiturn_progress
                gr.update(value="", visible=False),  # conversation_display
                gr.update(value="", visible=False)   # multiturn_session_info
            )

        def clear_continue_interface():
            """Clear the continue conversation interface"""
            return (
                "",  # continue_query
                None  # continue_files
            )  # continue_query

        # Multi-turn event handlers
        session_mode.change(
            fn=toggle_session_mode,
            inputs=[session_mode],
            outputs=[new_conversation_group, continue_conversation_group, session_controls_row, existing_session_selector, sessions_pagination_info]
        )

        refresh_multiturn_sessions_btn.click(
            fn=refresh_multiturn_sessions,
            inputs=[server_url, user_id_input, sessions_offset_state],
            outputs=[existing_session_selector, sessions_total_state, sessions_offset_state, sessions_pagination_info]
        )

        load_more_sessions_btn.click(
            fn=load_more_sessions,
            inputs=[server_url, user_id_input, sessions_offset_state, sessions_total_state],
            outputs=[existing_session_selector, sessions_offset_state, sessions_pagination_info]
        )

        start_conversation_btn.click(
            fn=start_new_conversation,
            inputs=[multiturn_query, multiturn_language, multiturn_files, server_url, user_id_input],
            outputs=[multiturn_progress, conversation_display, multiturn_session_info]
        )

        continue_conversation_btn.click(
            fn=continue_existing_conversation,
            inputs=[existing_session_selector, continue_query, continue_files, server_url, user_id_input],
            outputs=[multiturn_progress, conversation_display, multiturn_session_info]
        )

        clear_multiturn_btn.click(
            fn=clear_multiturn_interface,
            outputs=[multiturn_query, multiturn_files, existing_session_selector, multiturn_progress, conversation_display, multiturn_session_info]
        )

        clear_continue_btn.click(
            fn=clear_continue_interface,
            outputs=[continue_query, continue_files]
        )

        # Turn navigation event handlers
        view_session_btn.click(
            fn=view_multiturn_session,
            inputs=[existing_session_selector, server_url, user_id_input],
            outputs=[conversation_display, turn_navigation_group, turn_selector, turn_images_gallery, current_session_id_state]
        )

        turn_selector.change(
            fn=view_specific_turn,
            inputs=[current_session_id_state, turn_selector, server_url, user_id_input],
            outputs=[conversation_display, turn_images_gallery]
        )

        refresh_turn_btn.click(
            fn=view_multiturn_session,
            inputs=[current_session_id_state, server_url, user_id_input],
            outputs=[conversation_display, turn_navigation_group, turn_selector, turn_images_gallery, current_session_id_state]
        )

        # ========================================================================
        # MetaAgent Tab - HIDDEN (Still in Development)
        # ========================================================================
        # NOTE: MetaAgent functionality is commented out but preserved for future use
        # To re-enable, uncomment the code block below
        # ========================================================================
        """
        # MetaAgent Tab - Complex Multi-Step Tasks
        with gr.Tab("🧬 MetaAgent (Complex Tasks)"):
            gr.Markdown('''
            # 🧬 MetaAgent: Process Multiple Items in Parallel or Sequential Mode

            Perfect for tasks like:
            - "Analyze 1000 papers about X"
            - "Process 500 clinical records"
            - Any task requiring many files/items

            **Two Modes:**
            - **Parallel**: Fast, multiple workers simultaneously
            - **Sequential**: One batch at a time, full control, rate limiting support
            ''')

            with gr.Row():
                with gr.Column():
                    meta_query = gr.Textbox(
                        label="Complex Query with File List",
                        placeholder='''Example:
Analyze these papers:
[paper1.pdf, paper2.pdf, paper3.pdf, ..., paper100.pdf]

For each paper extract: title, authors, key findings''',
                        lines=8
                    )

                    meta_mode = gr.Radio(
                        label="Execution Mode",
                        choices=["parallel", "sequential"],
                        value="parallel",
                        info="Parallel: faster. Sequential: more control, rate limiting."
                    )

                    # Parallel settings
                    with gr.Group(visible=True) as meta_parallel_settings:
                        gr.Markdown("### ⚡ Parallel Mode Settings")
                        meta_workers = gr.Slider(1, 10, value=3, step=1, label="Max Workers")
                        meta_batch_size = gr.Slider(10, 200, value=50, step=10, label="Batch Size")

                    # Sequential settings
                    with gr.Group(visible=False) as meta_sequential_settings:
                        gr.Markdown("### 🔄 Sequential Mode Settings")
                        meta_items_per_batch = gr.Slider(5, 100, value=10, step=5, label="Items per Batch")
                        meta_pause = gr.Slider(0, 30, value=0, step=1, label="Pause Between Batches (s)")

                    meta_submit_btn = gr.Button("🚀 Submit Meta-Task", variant="primary")

                with gr.Column():
                    meta_session_output = gr.Textbox(label="Meta-Session ID", interactive=False)
                    meta_status_output = gr.Markdown("Ready to submit meta-task")

            gr.Markdown('''
            ### 📋 Supported File Formats:
            - List: `[file1.pdf, file2.pdf, ...]`
            - Keyword: `Files: paper1.pdf, paper2.pdf, ...`
            - Paths: `./data/file1.csv, /path/to/file2.txt`
            - URLs: `https://example.com/paper.pdf`

            The MetaAgent will automatically detect files and assign them to workers!
            ''')

            # Helper functions for MetaAgent
            def toggle_meta_mode(mode):
                if mode == "parallel":
                    return gr.update(visible=True), gr.update(visible=False)
                else:
                    return gr.update(visible=False), gr.update(visible=True)

            def submit_meta_task(query, mode, workers, batch_size, items_per_batch, pause, url, user_id):
                '''Submit a meta-task'''
                if not query.strip():
                    return "", "❌ Please enter a query"

                try:
                    request_data = {
                        "query": query,
                        "user_id": user_id,
                        "mode": mode
                    }

                    if mode == "parallel":
                        request_data["max_workers"] = int(workers)
                        request_data["max_batch_size"] = int(batch_size)
                    else:
                        request_data["items_per_batch"] = int(items_per_batch)
                        request_data["pause_between_batches"] = float(pause)

                    response = requests.post(
                        f"{url}/meta-task/submit",
                        json=request_data,
                        timeout=10
                    )

                    if response.status_code == 200:
                        data = response.json()
                        session_id = data["meta_session_id"]
                        message = data.get("message", "Submitted")

                        status_md = f'''## ✅ Meta-Task Submitted!

**Session ID:** `{session_id}`
**Mode:** {mode.upper()}
**Message:** {message}

**Next Steps:**
1. Use the session ID to check status: `/meta-task/{session_id}/status`
2. The task will be processed in the background
3. You can monitor progress via API or wait for completion

**Status Check:**
```bash
curl {url}/meta-task/{session_id}/status
```
'''
                        return session_id, status_md
                    else:
                        return "", f"❌ Error: {response.text}"

                except Exception as e:
                    return "", f"❌ Failed to submit: {str(e)}"

            # Wire up MetaAgent events
            meta_mode.change(
                fn=toggle_meta_mode,
                inputs=[meta_mode],
                outputs=[meta_parallel_settings, meta_sequential_settings]
            )

            meta_submit_btn.click(
                fn=submit_meta_task,
                inputs=[meta_query, meta_mode, meta_workers, meta_batch_size,
                       meta_items_per_batch, meta_pause, server_url, user_id_input],
                outputs=[meta_session_output, meta_status_output]
            )
        """
        # ========================================================================
        # End of MetaAgent Tab (Hidden)
        # ========================================================================

        # Delete Management Tab (Simplified - Hard Delete Only)
        with gr.Tab("🗑️ Delete Sessions"):
            with gr.Row():
                with gr.Column(scale=1):
                    gr.Markdown("## 🗑️ Session Deletion")

                    with gr.Group():
                        gr.Markdown("### Select Session to Delete")

                        # Session selector for deletion
                        refresh_sessions_for_delete_btn = gr.Button("🔄 Refresh Session List", variant="secondary")

                        session_to_delete_selector = gr.Dropdown(
                                label="Select session to permanently delete",
                                choices=[],
                                value="",
                                interactive=True,
                                allow_custom_value=True
                            )

                        # Confirmation checkbox
                        delete_confirmation = gr.Checkbox(
                            label="I understand this will permanently delete all session data (cannot be undone)",
                            value=False,
                            interactive=True
                        )

                        delete_btn = gr.Button("🗑️ Delete Permanently", variant="stop")

                with gr.Column(scale=1):
                    gr.Markdown("## 📋 Deletion Status")

                    delete_status = gr.Markdown(
                            """## 🗑️ Direct Deletion System

**Simplified One-Step Deletion:**
- Permanently deletes the session immediately
- Removes all data from S3, MongoDB, and local storage
- No recovery possible after deletion

**What Gets Deleted:**
- Session metadata and history
- All generated files and reports
- S3 stored objects
- MongoDB documents
- Local cache files

**Instructions:**
1. Click "Refresh Session List" to load sessions
2. Select the session you want to delete
3. Check the confirmation box
4. Click "Delete Permanently"

⚠️ **WARNING:** This action cannot be undone!
All session data will be permanently removed.""",
                            height=400
                        )

        # Delete management event handlers
        def refresh_sessions_for_delete(server_url_value, user_id):
            """Refresh sessions list for deletion"""
            return gr.update(choices=get_session_history(server_url.value, user_id), value="")

        async def hard_delete_session(session_id, confirmed, server_url_value, user_id):
            """Permanently delete a session using hard-delete"""
            if not session_id:
                return "## ❌ Error\n\nPlease select a session to delete."

            if not confirmed:
                return "## ⚠️ Warning\n\nPlease check the confirmation box to proceed with deletion."

            # Ensure URL has protocol
            if not server_url_value.startswith(('http://', 'https://')):
                server_url_value = f"http://{server_url_value}"

            try:
                response = requests.delete(f"{server_url_value}/hard-delete/{session_id}",
                                         params={"user_id": user_id, "confirm": "true"})
                if response.status_code == 200:
                    data = response.json()
                    deleted_items = data.get('deleted_items', {})
                    return f"""## ✅ Session Permanently Deleted

**Session ID:** `{session_id}`
**Deleted at:** {data.get('deleted_at', 'Unknown')}

**Deleted Items:**
- Local files: {len(deleted_items.get('local_files', []))}
- S3 objects: {len(deleted_items.get('s3_files', []))}
- MongoDB docs: {len(deleted_items.get('mongodb_docs', []))}

✅ All session data has been permanently removed."""
                else:
                    return f"""## ❌ Failed to Delete

**Session ID:** `{session_id}`
**Error:** {response.text}"""
            except Exception as e:
                return f"""## ❌ Error

**Error:** {str(e)}"""

        # Wire up delete events
        refresh_sessions_for_delete_btn.click(
            fn=refresh_sessions_for_delete,
            inputs=[server_url, user_id_input],
            outputs=[session_to_delete_selector]
        )

        delete_btn.click(
            fn=hard_delete_session,
            inputs=[session_to_delete_selector, delete_confirmation, server_url, user_id_input],
            outputs=[delete_status]
        ).then(
            fn=lambda: False,  # Reset confirmation checkbox
            outputs=[delete_confirmation]
        )



        # Initialize session lists on load
        # Removed auto-refresh on page load - let user manually refresh
        # demo.load(
        #     fn=lambda url, user_id: (
        #         refresh_status_history(user_id),
        #         refresh_stop_history(user_id)
        #     ),
        #     inputs=[server_url, user_id_input],
        #     outputs=[status_session_selector, stop_session_selector]
        # )

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

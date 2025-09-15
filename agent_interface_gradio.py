"""
Agent Interface with Live Thinking Display

This interface provides a clean layout with:
- Left side: User input and final report display
- Right side: Live executor showing planning and thinking process
- Download functionality for reports and thinking process
"""

import argparse
import os
import shutil
import sys
import tempfile
import threading
import time
import uuid
import zipfile
from contextlib import redirect_stdout
from datetime import datetime

import gradio as gr
import pandas as pd
from PIL import Image

# Add current directory to path for imports
sys.path.insert(0, os.getcwd())

from dleader_agent.agent.a1 import A1


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
    
    def get_all_sessions(self):
        """Get list of all existing chat sessions"""
        if not os.path.exists(self.sessions_dir):
            return []
        
        sessions = []
        for item in os.listdir(self.sessions_dir):
            session_path = os.path.join(self.sessions_dir, item)
            if os.path.isdir(session_path) and item.startswith("session_"):
                # Extract timestamp from session name
                try:
                    parts = item.split("_")
                    if len(parts) >= 3:
                        date_part = parts[1]
                        time_part = parts[2]
                        # Format: YYYYMMDD_HHMMSS
                        display_name = f"{date_part[:4]}-{date_part[4:6]}-{date_part[6:8]} {time_part[:2]}:{time_part[2:4]}:{time_part[4:6]}"
                        sessions.append((item, display_name, session_path))
                except:
                    sessions.append((item, item, session_path))
        
        # Sort by session name (newest first)
        sessions.sort(key=lambda x: x[0], reverse=True)
        return sessions
    
    def load_session_data(self, session_path):
        """Load data from an existing session"""
        if not os.path.exists(session_path):
            return None, None, None
        
        # Look for report, thinking, and query files
        report_content = None
        thinking_content = None
        session_files = []
        
        try:
            for file in os.listdir(session_path):
                file_path = os.path.join(session_path, file)
                if file.startswith("report_") and file.endswith(".md"):
                    with open(file_path, 'r', encoding='utf-8') as f:
                        report_content = f.read()
                elif file.startswith("thinking_process_") and file.endswith(".txt"):
                    with open(file_path, 'r', encoding='utf-8') as f:
                        thinking_content = f.read()
                elif not file.startswith("report_") and not file.startswith("thinking_process_") and not file.startswith("query_"):
                    # These are user uploaded files
                    session_files.append(file_path)
        except Exception as e:
            print(f"Error loading session data: {e}")
        
        return report_content, thinking_content, session_files
    
    def save_uploaded_files(self, uploaded_files, session_path):
        """Save uploaded files to session folder and return new paths"""
        if not uploaded_files:
            return []
        
        saved_files = []
        for file in uploaded_files:
            if file is None:
                continue
            original_name = os.path.basename(file.name)
            new_path = os.path.join(session_path, original_name)
            shutil.copy2(file.name, new_path)
            saved_files.append(new_path)
        
        return saved_files


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
    """Create an agent configured only for image analysis tasks."""
    
    # Initialize agent without downloading default data lake
    agent = A1(
        use_tool_retriever=True,
        download_data_lake=False, 
        llm='claude-sonnet-4-20250514'
    )
    
    return agent


def scan_for_new_files(current_path, start_time, exclude_folders=None):
    """Scan for files created after start_time, excluding specified folders"""
    if exclude_folders is None:
        exclude_folders = {'chat_sessions', '__pycache__', '.git', '.vscode', 'node_modules'}
    
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


def process_with_agent_streaming(message, uploaded_files):
    """Process user request with live streaming of agent's thinking"""
    if not message.strip():
        yield "😴 Please enter a message...", "", "", "", ""
        return
    
    try:
        # Record start time for file tracking

        # Create session folder for this chat
        session_manager = SessionManager()
        session_path, session_name = session_manager.create_session_folder()
        
        # Initialize agent
        yield f"🔄 **Initializing agent...** (Session: {session_name})", "", "", "", ""
        agent = create_agent()
        
        # Handle uploaded files
        session_file_paths = []
        if uploaded_files:
            yield f"📁 **Saving uploaded files to session folder...**", "", "", "", ""
            session_file_paths = session_manager.save_uploaded_files(uploaded_files, session_path)
            
            # Add files to agent's data lake with session paths
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
            
        yield f"🚀 **Starting processing...** (Files stored in: {session_path})", "", "", "", ""
        
        # Set up streaming capture
        stream_capture = StreamingCapture()
        
        # Container for results
        result_container = {"result": None, "error": None, "completed": False}
        accumulated_thinking = ""
        
        def run_agent():
            try:
                with redirect_stdout(stream_capture):
                    # Add session folder path to the message
                    enhanced_message = f"{message}\n\nNote: The uploaded files are stored in the folder: {session_path}. If saving file, also save in it, it is the working folder."
                    _, result = agent.go(enhanced_message)
                result_container["result"] = result
            except Exception as e:
                result_container["error"] = str(e)
            finally:
                result_container["completed"] = True
        
        # Start agent in background
        agent_thread = threading.Thread(target=run_agent)
        agent_thread.start()

        start_time = time.time()
        current_path = os.getcwd()
        print(current_path)
        chat_sessions_path = os.path.join(os.getcwd(), "chat_sessions")
        print(chat_sessions_path)
                
        # Monitor and stream updates
        last_content_length = 0
        while not result_container["completed"]:
            current_content = stream_capture.get_content()
            if len(current_content) > last_content_length:
                # New content available - show incremental update
                new_content = current_content[last_content_length:]
                accumulated_thinking += new_content
                
                # Format the live thinking display
                thinking_display = f"""## 🤖 Agent Executor (Live)
                
```
{accumulated_thinking}
```

**Status:** 🔄 Processing...
"""
# **Last Update:** {datetime.now().strftime('%H:%M:%S')}
                
                yield thinking_display, "", "", "", ""
                last_content_length = len(current_content)
            time.sleep(0.5)  # Update every 500ms
        
        # Wait for thread completion
        agent_thread.join()
        
        # Get final content
        final_content = stream_capture.get_content()
        if len(final_content) > last_content_length:
            new_content = final_content[last_content_length:]
            accumulated_thinking += new_content
        
        # Format final results
        if result_container["error"]:
            final_report = f"""## ❌ Final Report

```
{result_container['error']}
```
"""
            thinking_final = f"""## ❌ Agent Executor (Completed)

```
{accumulated_thinking}
```

**Status:** ❌ Error encountered
**Completed:** {datetime.now().strftime('%H:%M:%S')}
"""
        else:
            # Extract content between <solution> and </solution> tags
            raw_result = result_container['result'] or 'Processing completed successfully.'
            
            # Look for solution tags
            if '<solution>' in raw_result and '</solution>' in raw_result:
                start_idx = raw_result.find('<solution>') + len('<solution>')
                end_idx = raw_result.find('</solution>')
                solution_content = raw_result[start_idx:end_idx].strip()
            else:
                # If no solution tags found, use the full result
                solution_content = raw_result
            
            final_report = f"""## ✅ Final Report

{solution_content}
"""
            
            thinking_final = f"""## ✅ Agent Executor (Completed)

```
{accumulated_thinking}
```

**Status:** ✅ Completed successfully
**Finished:** {datetime.now().strftime('%H:%M:%S')}
"""
        
        # Scan for and move new files created during processing
        try:
            excude_paths = {'chat_sessions', '__pycache__', '.git', '.vscode', 'node_modules', chat_sessions_path}
            new_files = scan_for_new_files(current_path, start_time, excude_paths)
            
            # Filter out files that are already in chat_sessions folder
            filtered_files = [f for f in new_files if not f.startswith(chat_sessions_path)]
            
            if filtered_files:
                print(f"Found {len(filtered_files)} new files created during processing:")
                for file in filtered_files:
                    print(f"  - {file}")
                moved_files = move_files_to_session(filtered_files, session_path)
                print(f"Moved {len(moved_files)} files to session folder")
        except Exception as e:
            print(f"Error handling new files: {e}")
        
        # Save session files to chat_sessions folder
        try:
            # Save report file
            report_filename = f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
            report_path = os.path.join(session_path, report_filename)
            with open(report_path, 'w', encoding='utf-8') as f:
                f.write(final_report)
            
            # Save thinking process file
            thinking_filename = f"thinking_process_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            thinking_path = os.path.join(session_path, thinking_filename)
            with open(thinking_path, 'w', encoding='utf-8') as f:
                f.write(accumulated_thinking)
            
            # Save query/message for reference
            query_filename = f"query_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            query_path = os.path.join(session_path, query_filename)
            with open(query_path, 'w', encoding='utf-8') as f:
                f.write(f"Query: {message}\nTimestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                
        except Exception as e:
            print(f"Error saving session files: {e}")
        
        # Create downloadable files
        report_file = create_download_file(final_report, "report", "md")
        thinking_file = create_download_file(accumulated_thinking, "thinking_process", "txt")
        session_zip = create_session_zip(session_path)
        
        # Combine thinking and final report for Agent Executor display
        combined_executor_display = f"{thinking_final}\n\n---\n\n{final_report}"
        
        yield combined_executor_display, "## ✅ Processing Complete\n\nResults displayed in Agent Executor panel →", report_file, thinking_file, session_zip
        
    except Exception as e:
        error_display = f"""## ❌ Agent Executor (System Error)

```
System Error: {str(e)}
```

**Status:** ❌ System Error
**Timestamp:** {datetime.now().strftime('%H:%M:%S')}
"""
        yield error_display, "## ❌ System Error\n\nError details displayed in Agent Executor panel →", "", "", "", ""


def create_download_file(content, prefix, extension):
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


def create_session_zip(session_path):
    """Create a zip file containing all session content"""
    if not os.path.exists(session_path):
        return None
    
    try:
        session_name = os.path.basename(session_path)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # Create temporary zip file
        zip_file = tempfile.NamedTemporaryFile(
            suffix='.zip',
            prefix=f"{'_'.join(session_name.split('_')[:-1])}_",
            delete=False
        )
        zip_file.close()
        
        # Create zip archive
        with zipfile.ZipFile(zip_file.name, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # Walk through all files in session directory
            for root, dirs, files in os.walk(session_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    # Add file to zip with relative path
                    arcname = os.path.relpath(file_path, session_path)
                    zipf.write(file_path, arcname)
        
        return zip_file.name
    except Exception as e:
        print(f"Error creating session zip: {e}")
        return None


def format_files_info(files):
    """Format uploaded files information"""
    if not files:
        return "No files uploaded"
    
    file_info = []
    for file in files:
        filename = os.path.basename(file.name)
        file_size = os.path.getsize(file.name) / (1024 * 1024)  # Size in MB
        file_info.append(f"📁 **{filename}** ({file_size:.2f} MB)")
    
    return "**Uploaded Files:**\n\n" + "\n".join(file_info)


def load_logo():
    """Load the logo image"""
    try:
        img = Image.open("dleader_logo.jpg")
        return img
    except:
        return None

def create_interface():
    """Create the main Gradio interface"""
    
    with gr.Blocks(title="Agent Interface", theme=gr.themes.Soft()) as demo:
        # Header section with logo and title in blocks
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
                        <p style="margin: 8px 0 0 0; font-size: 1.1em; color: #6c757d; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;">Intelligent task processing with live thinking display</p>
                    </div>
                </div>
                """)
        
        with gr.Row(equal_height=True):
            # Left Column - User Input and Final Report
            with gr.Column(scale=1):
                gr.Markdown("## 📝 Input & Results")
                
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
                    gr.Markdown("### 💬 Your Request. Press 'Enter key' to go to next line.")
                    user_input = gr.Textbox(
                        label="Describe what you want the agent to do. Press 'Process' to start task.",
                        placeholder="Enter your request here...\n\nExamples:\n• Analyze the uploaded data\n• Extract key information from documents\n• Perform calculations or analysis\n• Generate reports or summaries",
                        lines=5,
                        max_lines=10
                    )
                    
                    with gr.Row():
                        submit_btn = gr.Button("🚀 Process", variant="primary", scale=2)
                        clear_btn = gr.Button("🗑️ Clear", variant="secondary", scale=1)
                
                # Status section (replaces Final Report)
                with gr.Group():
                    gr.Markdown("### 📊 Status & Results")
                    final_report = gr.Markdown(
                        """## 📊 Session Status

Ready to show your results...

**Status:** 🟢 Waiting for processing
**Ready to display results...**
""",
                        height=200
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
                        download_session_zip = gr.File(
                            label="📦 Download Complete Session",
                            visible=False
                        )
            
            # Right Column - Live Executor Display
            with gr.Column(scale=1):
                gr.Markdown("## 🧠 Agent Executor (scroll down to see more)")
                
                executor_display = gr.Markdown(
                    """## 🤖 Agent Executor
                    
Ready to process your request...

**Status:** 🟢 Idle
**Waiting for input...**
""",
                    height=600
                )
                
                # Status indicators
                with gr.Row():
                    gr.HTML("""
                    <div style="display: flex; align-items: center; justify-content: center; padding: 10px; background: #f0f0f0; border-radius: 5px;">
                        <span style="color: #28a745; font-weight: bold;">●</span>
                        <span style="margin-left: 10px;">System Ready</span>
                    </div>
                    """)
        
        # Event handlers
        def update_file_status(files):
            return format_files_info(files)
        
        
        def process_request(message, files):
            if not message.strip():
                return (
                    "## ❌ Agent Executor\n\n❌ Please enter a request", 
                    "## ❌ No Input\n\nPlease enter a request to process.",
                    gr.update(visible=False), 
                    gr.update(visible=False),
                    gr.update(visible=False)
                )
            
            # Stream the processing
            for executor, report, report_file, thinking_file, session_zip in process_with_agent_streaming(message, files):
                if report_file and thinking_file and session_zip:
                    yield (
                        executor, 
                        report,
                        gr.update(visible=True, value=report_file),
                        gr.update(visible=True, value=thinking_file),
                        gr.update(visible=True, value=session_zip)
                    )
                else:
                    yield (executor, report, gr.update(visible=False), gr.update(visible=False), gr.update(visible=False))
        
        def clear_interface():
            return (
                "",  # Clear user input
                """## 🤖 Agent Executor
                    
Ready to process your request...

**Status:** 🟢 Idle
**Waiting for input...**
""",  # Reset executor
                """## 📊 Session Status

Ready to show your results...

**Status:** 🟢 Waiting for processing
**Ready to display results...**
""",  # Reset status
                gr.update(visible=False),  # Hide download buttons
                gr.update(visible=False),
                gr.update(visible=False)  # Hide session zip
            )
        
        # Wire up events
        file_input.change(
            fn=update_file_status,
            inputs=[file_input],
            outputs=[file_status]
        )
        
        
        submit_btn.click(
            fn=process_request,
            inputs=[user_input, file_input],
            outputs=[executor_display, final_report, download_report, download_thinking, download_session_zip]
        )
        
        clear_btn.click(
            fn=clear_interface,
            outputs=[user_input, executor_display, final_report, download_report, download_thinking, download_session_zip]
        )
        
        # Allow Enter key to submit
        user_input.submit(
            fn=process_request,
            inputs=[user_input, file_input],
            outputs=[executor_display, final_report, download_report, download_thinking, download_session_zip]
        )
    
    return demo


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Agent Interface with Live Thinking Display")
    parser.add_argument("--server_port", type=int, default=7861, help="Port to run the server on (default: 7861)")
    args = parser.parse_args()
    
    demo = create_interface()
    demo.launch(
        server_name="0.0.0.0",
        server_port=args.server_port,
        share=True,
        debug=True
    )
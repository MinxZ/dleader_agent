"""
Utility functions for dleader_agent FastAPI server.

This module contains helper functions for agent processing, file management,
and session operations.
"""

import atexit
import glob
import io
import os
import shutil
import signal
import sys
import threading
import time
import zipfile
from contextlib import redirect_stdout
from multiprocessing import Queue as MPQueue
from typing import Optional, Dict, Any, List

import psutil

# Import dleader_agent components
from dleader_agent.agent.a1 import A1
from template_retriever import TemplateRetriever


def run_agent_in_process(message_queue: MPQueue, result_queue: MPQueue, enhanced_message: str, session_path: str, use_template: bool = True):
    """
    Run agent in a separate process for true termination capability
    This function runs in a separate process and communicates via queues

    Args:
        message_queue: Queue for receiving messages
        result_queue: Queue for sending results
        enhanced_message: The message/query to process
        session_path: Path to session directory
        use_template: Whether to use template matching (default: True)
    """
    import atexit
    import glob
    import io
    import os
    import shutil
    import sys
    import threading
    import time
    from contextlib import redirect_stdout

    import psutil

    # Record start time for file tracking
    process_start_time = time.time()

    # Track all child processes spawned by this process
    parent_process = psutil.Process()

    # Shared buffer for output capture
    output_buffer = io.StringIO()
    output_lock = threading.Lock()

    def cleanup_subprocesses():
        """Kill all child processes when parent terminates"""
        try:
            children = parent_process.children(recursive=True)
            for child in children:
                try:
                    print(f"Terminating subprocess PID {child.pid}")
                    child.terminate()
                except:
                    pass

            # Give them time to terminate gracefully
            _, alive = psutil.wait_procs(children, timeout=2)

            # Force kill any remaining
            for child in alive:
                try:
                    print(f"Force killing subprocess PID {child.pid}")
                    child.kill()
                except:
                    pass
        except:
            pass

    # Register cleanup function
    atexit.register(cleanup_subprocesses)

    # Also handle SIGTERM signal
    import signal
    def signal_handler(signum, frame):
        cleanup_subprocesses()
        sys.exit(0)

    signal.signal(signal.SIGTERM, signal_handler)

    def send_periodic_snapshots():
        """Send snapshots every 2 seconds while agent is running"""
        while not agent_complete.is_set():
            time.sleep(2)

            with output_lock:
                current_output = output_buffer.getvalue()

            # Send snapshot with current output
            result_queue.put({
                "type": "snapshot",
                "content": current_output,
                "timestamp": time.time()
            })

            # Also send as thinking update for real-time display
            if current_output:
                result_queue.put({
                    "type": "thinking_update",
                    "content": current_output
                })

    # Event to signal agent completion
    agent_complete = threading.Event()

    # Start snapshot thread
    snapshot_thread = threading.Thread(target=send_periodic_snapshots, daemon=True)
    snapshot_thread.start()

    try:
        with redirect_stdout(output_buffer):
            # Send status update
            result_queue.put({
                "type": "status",
                "content": "Agent starting in separate process with snapshot tracking..."
            })

            # Create agent
            # Import from api.utils (within same module, but in subprocess context)
            from dleader_agent.agent.a1 import A1

            def create_agent():
                """Create an agent configured for tasks"""
                agent = A1(
                    use_tool_retriever=True,
                    download_data_lake=False,
                    llm='claude-sonnet-4-5-20250929'
                )
                return agent

            agent = create_agent()

            # Send status
            result_queue.put({
                "type": "status",
                "content": "Agent initialized, processing message..."
            })

            # === TEMPLATE MATCHING & QUERY AUGMENTATION ===
            # Try to match the query to a workflow template (if enabled)
            base_message = enhanced_message
            template_info = {
                "matched": False,
                "title": None,
                "confidence": None,
                "reasoning": None,
                "modification": None
            }

            # use_template parameter is passed to this function
            # Check if template matching is enabled
            if use_template:
                try:
                    result_queue.put({
                        "type": "status",
                        "content": "Checking for relevant workflow templates..."
                    })

                    # Import TemplateRetriever in subprocess
                    from template_retriever import TemplateRetriever

                    # Initialize template retriever
                    try:
                        retriever = TemplateRetriever()
                    except Exception as e:
                        print(f"Warning: Could not initialize template retriever: {e}")
                        retriever = None

                    if retriever:
                        # Match query to templates
                        match_result = retriever.match_template(base_message)

                        if match_result.get("matched"):
                            template_title = match_result.get("template", {}).get("title", "Unknown")
                            confidence = match_result.get("confidence", "unknown")

                            # Store template info for later
                            template_info["matched"] = True
                            template_info["title"] = template_title
                            template_info["confidence"] = confidence
                            template_info["reasoning"] = match_result.get("reasoning", "")
                            template_info["modification"] = match_result.get("modification")

                            result_queue.put({
                                "type": "template_matched",
                                "content": f"Matched to template: {template_title} (confidence: {confidence})",
                                "template_title": template_title,
                                "confidence": confidence,
                                "reasoning": match_result.get("reasoning", "")
                            })

                            # Augment the query with template prompt
                            augmentation_result = retriever.augment_query_with_template(base_message, match_result)
                            enhanced_message = augmentation_result["augmented_query"]

                            print(f"✓ Template matched: {template_title} (confidence: {confidence})")
                            if augmentation_result.get("modification_applied"):
                                print(f"  Modification: {augmentation_result['modification_applied']}")
                        else:
                            print(f"✗ No template matched: {match_result.get('reasoning', 'Unknown reason')}")

                except Exception as e:
                    print(f"Warning: Template matching failed: {e}")
                    # Continue without template matching
            else:
                print("Template matching disabled by user")
                result_queue.put({
                    "type": "status",
                    "content": "Template matching disabled, proceeding with direct query..."
                })

            # === END TEMPLATE MATCHING ===

            # Add explicit file information to the message if not already included
            if session_path and os.path.exists(session_path):
                files_in_session = []
                for filename in os.listdir(session_path):
                    file_path = os.path.join(session_path, filename)
                    if os.path.isfile(file_path) and not filename.startswith('.'):
                        files_in_session.append(f"{filename} (Path: {file_path})")

                if files_in_session and "Available files" not in enhanced_message:
                    file_info = "\n\nAvailable files in your working directory:\n" + "\n".join([f"- {f}" for f in files_in_session])
                    enhanced_message = enhanced_message + file_info

            # Run agent (this blocks until complete)
            _, result = agent.go(enhanced_message)

            # Signal completion
            agent_complete.set()

            # Get final output
            with output_lock:
                final_output = output_buffer.getvalue()

            # Send final result with complete output and template info
            result_queue.put({
                "type": "result",
                "content": result,
                "output": final_output,
                "template_info": template_info
            })

            # Send final snapshot
            result_queue.put({
                "type": "final_snapshot",
                "content": final_output,
                "result": result,
                "timestamp": time.time(),
                "template_info": template_info
            })

    except Exception as e:
        import traceback
        agent_complete.set()

        with output_lock:
            error_output = output_buffer.getvalue()

        result_queue.put({
            "type": "error",
            "content": str(e),
            "traceback": traceback.format_exc(),
            "output": error_output
        })
    finally:
        # Move generated files to session folder before exiting process
        try:
            print(f"Process: Starting file collection for session path: {session_path}")
            print(f"Process: Session path exists: {os.path.exists(session_path)}")

            # Ensure session folder exists
            if not os.path.exists(session_path):
                os.makedirs(session_path, exist_ok=True)
                print(f"Process: Created session folder: {session_path}")

            # System files to never move
            system_files = {
                'requirements.txt', 'requirements_fastapi.txt', 'requirements-test.txt',
                'pytest.ini', 'README.md', 'CLOUD_STORAGE_README.md', 'TEST_SUMMARY.md',
                '.env', '.env.example', 'Dockerfile', 'docker-compose.yml', '.gitignore',
                'setup.py', 'setup.cfg', 'pyproject.toml', 'Makefile', 'dleader_logo.png'
            }

            # Application Python files to skip
            app_python_files = {
                'agent_fastapi_server_multiturn.py', 'agent_gradio_fastapi_multiturn.py',
                'cloud_storage_manager.py', 'unified_session_manager.py', 'a1.py',
                'agent_fastapi_server.py', 'agent_interface_gradio.py'
            }

            moved_count = 0
            image_count = 0

            # Scan for all files created during this process
            all_files = glob.glob("*") + glob.glob("*/*")
            print(f"Process: Scanning {len(all_files)} potential files")

            for file_path in all_files:
                # Skip directories and files in system folders
                if os.path.isdir(file_path):
                    continue

                # Skip files in system directories
                if any(file_path.startswith(d + '/') for d in ['chat_sessions', 'chat_zips',
                       'session_storage', 'multiturn_sessions', 'temp_uploads', 's3_mongodb']):
                    continue

                filename = os.path.basename(file_path)

                # Skip system files and app files
                if filename in system_files or filename in app_python_files:
                    continue

                # Skip test files
                if filename.startswith('test_') and filename.endswith('.py'):
                    continue

                # Skip compiled Python files
                if filename.endswith(('.pyc', '.pyo', '.pyd')):
                    continue

                # Check if file was created or modified after process started
                try:
                    file_mtime = os.path.getmtime(file_path)
                    file_ctime = os.path.getctime(file_path)
                    file_time = max(file_mtime, file_ctime)

                    if file_time >= process_start_time:
                        # Check file size (skip files > 500MB)
                        file_size = os.path.getsize(file_path)
                        file_size_mb = file_size / (1024 * 1024)

                        if file_size_mb > 500:
                            print(f"Process: Deleting large file {filename} ({file_size_mb:.1f}MB)")
                            os.remove(file_path)
                        else:
                            # Move file to session folder
                            dest_path = os.path.join(session_path, filename)

                            # Handle duplicate filenames
                            if os.path.exists(dest_path):
                                base, ext = os.path.splitext(filename)
                                counter = 1
                                while os.path.exists(dest_path):
                                    new_filename = f"{base}_{counter}{ext}"
                                    dest_path = os.path.join(session_path, new_filename)
                                    counter += 1

                            print(f"Process: Moving {file_path} -> {dest_path}")
                            shutil.move(file_path, dest_path)
                            moved_count += 1

                            # Count images
                            if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.bmp')):
                                image_count += 1
                                print(f"Process: This is an image file: {filename}")

                            print(f"Process: Successfully moved {filename} to session folder")

                except Exception as e:
                    print(f"Process: Error processing file {file_path}: {e}")
                    # Continue with other files even if one fails
                    pass

            if moved_count > 0:
                result_queue.put({
                    "type": "status",
                    "content": f"Process: Moved {moved_count} files to session ({image_count} images)"
                })
                print(f"Process: Successfully moved {moved_count} files ({image_count} images) to {session_path}")

        except Exception as e:
            print(f"Process: Error moving files: {e}")

        # Clean up any remaining subprocesses
        cleanup_subprocesses()

# Session and utility classes (reused from original files)


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
            total_size = 0
            max_zip_size = 500 * 1024 * 1024  # 500MB max zip size
            skipped_files = []

            # Walk through all files in session directory
            for root, dirs, files in os.walk(session_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    file_size = os.path.getsize(file_path)

                    # Skip individual files larger than 100MB
                    if file_size > 100 * 1024 * 1024:
                        skipped_files.append(f"{file} ({file_size / 1024 / 1024:.1f}MB)")
                        print(f"Skipping large file in zip: {file} ({file_size / 1024 / 1024:.1f}MB)")
                        continue

                    # Check total zip size limit
                    if total_size + file_size > max_zip_size:
                        skipped_files.append(f"{file} (would exceed 500MB zip limit)")
                        print(f"Skipping {file} - would exceed 500MB zip limit")
                        continue

                    # Add file to zip with relative path
                    arcname = os.path.relpath(file_path, session_path)
                    zipf.write(file_path, arcname)
                    total_size += file_size

            # Add a notice file if files were skipped
            if skipped_files:
                notice_content = "LARGE FILES EXCLUDED FROM ZIP:\n\n"
                notice_content += "\n".join(skipped_files)
                notice_content += "\n\nThese files were too large and excluded to keep download size manageable."
                zipf.writestr("SKIPPED_LARGE_FILES.txt", notice_content)

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
        llm='claude-sonnet-4-5-20250929'
    )
    return agent

# Global template retriever instance (initialized once, reused for all requests)
template_retriever = None



def get_template_retriever():
    """Get or create the global template retriever instance"""
    global template_retriever
    if template_retriever is None:
        try:
            template_retriever = TemplateRetriever()
            print("Initialized template retriever")
        except Exception as e:
            print(f"Warning: Could not initialize template retriever: {e}")
            template_retriever = None
    return template_retriever

# Custom CORS middleware to ensure headers are always present


def append_images_to_report(final_report: str, files_data: dict) -> str:
    """
    Append images and download links to the final report in Markdown format

    Args:
        final_report: The original final report content
        files_data: Dictionary containing file information with URLs

    Returns:
        Enhanced final report with images and download links appended
    """
    print(f"[APPEND] files_data type: {type(files_data)}, keys: {list(files_data.keys()) if isinstance(files_data, dict) else 'N/A'}")

    if not files_data or not isinstance(files_data, dict):
        return final_report

    additions = ""

    # Extract images from files_data
    images = files_data.get("images", [])
    if images:
        # Start building the images section
        images_section = "\n\n---\n\n## 📊 Generated Images\n\n"

        # Process each image
        image_count = 0
        for image_item in images:
            # Handle both dict and string formats
            if isinstance(image_item, dict):
                filename = image_item.get("filename", "image")
                url = image_item.get("url") or image_item.get("download_url")
                s3_key = image_item.get("s3_key")

                if url:
                    # Use the presigned URL (works with S3 URLs even without .png/.jpg extension)
                    image_count += 1
                    # Extract a cleaner name from filename or s3_key
                    display_name = filename.replace("_", " ").replace("-", " ").title()
                    images_section += f"### {display_name}\n\n"
                    images_section += f"![{display_name}]({url})\n\n"
            elif isinstance(image_item, str):
                # Handle string URL directly
                image_count += 1
                display_name = f"Image {image_count}"
                images_section += f"### {display_name}\n\n"
                images_section += f"![{display_name}]({image_item})\n\n"

        # Only append the section if we found images
        if image_count > 0:
            additions += images_section

    # Add download links section
    download_links = []

    # Check for session_zip or turn_zip
    for key in ["session_zip", "turn_zip"]:
        zip_info = files_data.get(key)
        if zip_info and isinstance(zip_info, dict):
            url = zip_info.get("url") or zip_info.get("download_url")
            filename = zip_info.get("filename", f"{key}.zip")
            if url:
                download_links.append({
                    "name": "Download All Files (ZIP)",
                    "url": url,
                    "icon": "📦"
                })
                break  # Only add one zip download link

    # Add other downloadable files if needed
    for key in ["report_md", "result_json"]:
        file_info = files_data.get(key)
        if file_info and isinstance(file_info, dict):
            url = file_info.get("url") or file_info.get("download_url")
            if url:
                name = "Final Report (Markdown)" if key == "report_md" else "Results (JSON)"
                icon = "📄" if key == "report_md" else "📋"
                download_links.append({
                    "name": name,
                    "url": url,
                    "icon": icon
                })

    # Build download links section
    if download_links:
        downloads_section = "\n\n---\n\n## 📥 Downloads\n\n"
        for link in download_links:
            downloads_section += f"- {link['icon']} **[{link['name']}]({link['url']})**\n"
        additions += downloads_section

    return final_report + additions




def generate_file_urls(files_data, session_id: str = None):
    """
    Helper function to convert file paths/S3 keys to accessible URLs

    IMPORTANT: Always returns S3 presigned URLs. If file is only available locally,
    it will be uploaded to S3 first before generating the URL.

    Args:
        files_data: Dictionary or list of file information (can be paths, dicts, or mixed)
        session_id: Optional session ID for generating download URLs

    Returns:
        Enhanced files_data with 'url' fields added (always S3 URLs)
    """
    from datetime import datetime, timedelta
    import os

    def process_file_item(file_item):
        """Process a single file item to add S3 URL"""
        # Handle string paths (convert to dict with URL)
        if isinstance(file_item, str):
            filename = file_item.split("/")[-1]
            file_path = file_item

            # Upload to S3 if file exists locally
            if os.path.exists(file_path) and session_id:
                try:
                    s3_key = f"sessions/{session_id}/files/{filename}"

                    # Check if file already exists in S3 first
                    try:
                        cloud_storage_manager.s3_client.head_object(
                            Bucket=cloud_storage_manager.bucket_name,
                            Key=s3_key
                        )
                        # File exists in S3, just generate presigned URL without uploading
                        url = cloud_storage_manager.generate_presigned_url(s3_key, expiry_seconds=7200)
                        print(f"✓ File {filename} already exists in S3, generated presigned URL")
                        return {
                            "path": file_path,
                            "filename": filename,
                            "s3_key": s3_key,
                            "url": url,
                            "expires_at": (datetime.now() + timedelta(hours=2)).isoformat()
                        }
                    except cloud_storage_manager.s3_client.exceptions.ClientError:
                        # File doesn't exist in S3, upload it
                        cloud_storage_manager.s3_client.upload_file(
                            file_path,
                            cloud_storage_manager.bucket_name,
                            s3_key
                        )
                        url = cloud_storage_manager.generate_presigned_url(s3_key, expiry_seconds=7200)
                        print(f"✓ Uploaded {filename} to S3 and generated presigned URL")
                        return {
                            "path": file_path,
                            "filename": filename,
                            "s3_key": s3_key,
                            "url": url,
                            "expires_at": (datetime.now() + timedelta(hours=2)).isoformat()
                        }
                except Exception as e:
                    print(f"Warning: Failed to upload {filename} to S3: {e}")

            return {
                "path": file_path,
                "filename": filename,
                "download_url": f"/download-file/{session_id}/{filename}" if session_id else None
            }

        if not isinstance(file_item, dict):
            return file_item

        result = file_item.copy()

        # If it has S3 key, generate presigned URL
        if "s3_key" in file_item:
            try:
                url = cloud_storage_manager.generate_presigned_url(
                    file_item["s3_key"],
                    expiry_seconds=7200  # 2 hours
                )
                result["url"] = url
                result["expires_at"] = (datetime.now() + timedelta(hours=2)).isoformat()
            except Exception as e:
                print(f"Warning: Failed to generate presigned URL for {file_item.get('filename', 'unknown')}: {e}")

        # If it only has a local path, upload to S3 and get URL
        elif "path" in file_item and session_id:
            filename = file_item.get("filename") or file_item["path"].split("/")[-1]
            file_path = file_item["path"]

            # Check if file exists locally
            if os.path.exists(file_path):
                try:
                    # Determine S3 key based on file type
                    file_ext = filename.split('.')[-1].lower()
                    if file_ext in ['png', 'jpg', 'jpeg', 'gif', 'svg', 'pdf']:
                        s3_key = f"sessions/{session_id}/images/{filename}"
                    else:
                        s3_key = f"sessions/{session_id}/files/{filename}"

                    # Check if file already exists in S3 first
                    try:
                        cloud_storage_manager.s3_client.head_object(
                            Bucket=cloud_storage_manager.bucket_name,
                            Key=s3_key
                        )
                        # File exists in S3, just generate presigned URL without uploading
                        url = cloud_storage_manager.generate_presigned_url(s3_key, expiry_seconds=7200)
                        result["s3_key"] = s3_key
                        result["url"] = url
                        result["expires_at"] = (datetime.now() + timedelta(hours=2)).isoformat()
                        print(f"✓ File {filename} already exists in S3, generated presigned URL")
                    except cloud_storage_manager.s3_client.exceptions.ClientError:
                        # File doesn't exist in S3, upload it
                        cloud_storage_manager.s3_client.upload_file(
                            file_path,
                            cloud_storage_manager.bucket_name,
                            s3_key
                        )
                        # Generate presigned URL
                        url = cloud_storage_manager.generate_presigned_url(s3_key, expiry_seconds=7200)
                        result["s3_key"] = s3_key
                        result["url"] = url
                        result["expires_at"] = (datetime.now() + timedelta(hours=2)).isoformat()
                        print(f"✓ Uploaded {filename} to S3 and generated presigned URL")
                    except Exception as upload_error:
                        # Upload failed, fall back to local download
                        result["download_url"] = f"/download-file/{session_id}/{filename}"
                        print(f"Warning: Failed to upload {filename} to S3: {upload_error}")
                except Exception as e:
                    print(f"Warning: Error uploading {filename} to S3: {e}")
                    # Fall back to local download URL
                    result["download_url"] = f"/download-file/{session_id}/{filename}"
            else:
                # File doesn't exist locally, provide download URL as fallback
                result["download_url"] = f"/download-file/{session_id}/{filename}"
                result["filename"] = filename

        return result

    # Handle different data structures
    if isinstance(files_data, list):
        return [process_file_item(item) for item in files_data]
    elif isinstance(files_data, dict):
        result = {}
        for key, value in files_data.items():
            if isinstance(value, list):
                result[key] = [process_file_item(item) for item in value]
            elif isinstance(value, dict):
                result[key] = process_file_item(value)
            elif isinstance(value, str):
                # Handle single string path
                result[key] = process_file_item(value)
            else:
                result[key] = value
        return result
    else:
        return files_data



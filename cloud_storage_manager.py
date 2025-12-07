"""
Cloud Storage Manager for Session Data
Hybrid approach using S3 for files and MongoDB for metadata
"""

import os
import json
import shutil
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from pathlib import Path

# Import your existing S3 and MongoDB utilities
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), 's3_mongodb'))

from s3_mongodb.s3_utils import (
    get_s3_client,
    upload_to_s3_and_get_link,
    upload_data_to_s3_and_get_link,
    create_bucket_if_not_exists
)
from s3_mongodb.func_mongodb import get_mongodb_collection, upsert_wrapper
from s3_mongodb.utiles import generate_unique_id

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class CloudStorageManager:
    """
    Manages session data storage using S3 for files and MongoDB for metadata
    """

    def __init__(self):
        # S3 Configuration
        self.aws_access_key = os.getenv("AWS_ACCESS_KEY_ID_SELF")
        self.aws_secret_key = os.getenv("AWS_SECRET_ACCESS_KEY_SELF")
        self.aws_region = os.getenv("AWS_REGION_SELF", "us-east-1")
        self.bucket_name = os.getenv("SESSION_STORAGE_BUCKET", "dleader-agent-sessions")

        # MongoDB Configuration
        self.mongodb_uri = os.getenv("MONGODB_URI")
        self.database_name = os.getenv("SESSION_DB_NAME", "dleader_agent")
        self.sessions_collection = "sessions"
        self.multiturn_collection = "multiturn_sessions"

        # MongoDB connection cache to avoid reconnecting on every request
        self._mongodb_sessions_cache = None
        self._mongodb_multiturn_cache = None
        self._mongodb_connection_failed = False

        # Initialize clients
        self.s3_client = None
        self.init_clients()

    def init_clients(self):
        """Initialize S3 and MongoDB clients"""
        try:
            # Initialize S3 client
            self.s3_client = get_s3_client(
                self.aws_access_key,
                self.aws_secret_key,
                self.aws_region
            )

            # Create bucket if it doesn't exist
            create_bucket_if_not_exists(self.s3_client, self.bucket_name, self.aws_region)

            logger.info("Cloud storage clients initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize cloud storage clients: {e}")
            raise

    def _get_cached_mongodb_collection(self, collection_name: str):
        """Get cached MongoDB collection or create new connection if needed

        Args:
            collection_name: Name of collection ('sessions' or 'multiturn_sessions')

        Returns:
            MongoDB collection object or None if connection failed
        """
        if self._mongodb_connection_failed:
            return None

        # Check which cache to use
        if collection_name == self.sessions_collection:
            if self._mongodb_sessions_cache is not None:
                return self._mongodb_sessions_cache
        elif collection_name == self.multiturn_collection:
            if self._mongodb_multiturn_cache is not None:
                return self._mongodb_multiturn_cache

        # Create new connection
        try:
            collection = get_mongodb_collection(self.database_name, collection_name)
            if collection is None:
                self._mongodb_connection_failed = True
                return None

            # Cache the collection
            if collection_name == self.sessions_collection:
                self._mongodb_sessions_cache = collection
                logger.info(f"[MongoDB CloudStorage] Connection established and cached for {collection_name}")
            elif collection_name == self.multiturn_collection:
                self._mongodb_multiturn_cache = collection
                logger.info(f"[MongoDB CloudStorage] Connection established and cached for {collection_name}")

            return collection
        except Exception as e:
            logger.error(f"[MongoDB CloudStorage] Connection failed for {collection_name}: {e}")
            self._mongodb_connection_failed = True
            return None

    async def upload_session_to_cloud(self, session_id: str, session_data: Dict) -> Dict[str, Any]:
        """
        Upload complete session data to cloud storage

        Args:
            session_id: Session identifier
            session_data: Complete session data including local paths

        Returns:
            Dict with upload results and cloud URLs
        """
        try:
            logger.info(f"Starting cloud upload for session {session_id}")

            # Extract local paths from session data
            local_session_path = session_data.get("session_path")
            if not local_session_path or not os.path.exists(local_session_path):
                raise Exception(f"Local session path not found: {local_session_path}")

            # Extract turn_start_time for filtering images in multi-turn sessions
            turn_start_time = session_data.get("turn_start_time")

            # Upload files to S3 and get keys
            s3_files = await self._upload_session_files_to_s3(session_id, local_session_path, turn_start_time=turn_start_time)

            # Prepare metadata for MongoDB
            session_metadata = self._prepare_session_metadata(session_id, session_data, s3_files)

            # Save metadata to MongoDB
            mongodb_result = await self._save_session_metadata(session_metadata)

            # Clean up local files after successful upload
            await self._cleanup_local_files(local_session_path)

            result = {
                "session_id": session_id,
                "status": "success",
                "s3_files": s3_files,
                "mongodb_id": mongodb_result.get("_id"),
                "uploaded_at": datetime.now().isoformat()
            }

            logger.info(f"Successfully uploaded session {session_id} to cloud")
            return result

        except Exception as e:
            logger.error(f"Failed to upload session {session_id} to cloud: {e}")
            return {
                "session_id": session_id,
                "status": "error",
                "error": str(e)
            }

    async def _upload_session_files_to_s3(self, session_id: str, local_session_path: str, turn_start_time: float = None) -> Dict[str, str]:
        """Upload all session files to S3 and return S3 keys (not URLs)

        Args:
            session_id: Session identifier
            local_session_path: Path to local session directory
            turn_start_time: For multi-turn sessions, only upload images created after this timestamp
        """
        s3_files = {}
        session_path = Path(local_session_path)

        # Define file patterns to upload with categories
        file_patterns = {
            "report_md": "report_*.md",
            "report_pdf": "report_*.pdf",
            "thinking_process": "thinking_process_*.txt",
            "query_file": "query_*.txt",
            "result_json": "result_*.json",
            "session_zip": "*.zip",
            "snapshots": "snapshot_*.json"
        }

        # Handle standard file patterns
        for file_type, pattern in file_patterns.items():
            files = list(session_path.glob(pattern))

            # For multi-turn sessions, upload ALL files, not just the latest
            # This ensures each turn's files are available in S3
            if file_type == "snapshots" or len(files) > 1:
                # Handle multiple files (snapshots or multi-turn session files)
                file_list = []
                for file_path in files:
                    if file_path.exists():
                        try:
                            s3_key = f"sessions/{session_id}/{file_type}/{file_path.name}"
                            # Upload file to S3 without getting URL
                            self.s3_client.upload_file(str(file_path), self.bucket_name, s3_key)
                            file_list.append({
                                "filename": file_path.name,
                                "s3_key": s3_key,
                                "file_size": file_path.stat().st_size,
                                "uploaded_at": datetime.now().isoformat()
                            })
                            logger.info(f"Uploaded {file_type} file to S3: {file_path.name}")
                        except FileNotFoundError as e:
                            logger.warning(f"File not found for {file_type}: {file_path} - {e}")
                        except Exception as e:
                            logger.warning(f"Failed to upload {file_type} file {file_path.name}: {e}")

                if file_list:
                    # For backward compatibility, if there's only one file, store as dict
                    # Otherwise, store as list
                    if len(file_list) == 1 and file_type != "snapshots":
                        s3_files[file_type] = file_list[0]
                    else:
                        s3_files[file_type] = file_list

            elif files:
                # Single file - upload as before (for backward compatibility)
                file_path = files[0]
                if file_path.exists():
                    try:
                        s3_key = f"sessions/{session_id}/{file_type}/{file_path.name}"
                        # Upload file to S3 without getting URL
                        self.s3_client.upload_file(str(file_path), self.bucket_name, s3_key)
                        s3_files[file_type] = {
                            "filename": file_path.name,
                            "s3_key": s3_key,
                            "file_size": file_path.stat().st_size,
                            "uploaded_at": datetime.now().isoformat()
                        }
                        logger.info(f"Uploaded {file_type} file to S3: {file_path.name}")
                    except FileNotFoundError as e:
                        logger.warning(f"File not found for {file_type}: {file_path} - {e}")
                    except Exception as e:
                        logger.warning(f"Failed to upload {file_type} file {file_path.name}: {e}")
                else:
                    logger.warning(f"File for {file_type} no longer exists: {file_path}")

        # Categorize and upload all other files
        image_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.svg', '.webp'}
        data_extensions = {'.csv', '.xlsx', '.xls', '.tsv'}

        images = []
        data_files = []
        other_files = []

        # Process all files in the session directory
        if session_path.exists():
            for file_path in session_path.glob("*"):
                if file_path.is_file() and not any(file_path.match(pattern) for pattern in file_patterns.values()):
                    # Check if file still exists (handle race conditions)
                    if not file_path.exists():
                        logger.warning(f"File {file_path} no longer exists, skipping")
                        continue

                    file_ext = file_path.suffix.lower()

                    # Determine file category and S3 path
                    if file_ext in image_extensions:
                        # For multi-turn sessions, only include images created during this turn
                        if turn_start_time is not None:
                            file_mtime = file_path.stat().st_mtime
                            if file_mtime < turn_start_time:
                                logger.info(f"Skipping image {file_path.name} - created before turn start")
                                continue  # Skip images from previous turns
                        s3_key = f"sessions/{session_id}/images/{file_path.name}"
                        category = "images"
                        target_list = images
                    elif file_ext in data_extensions:
                        s3_key = f"sessions/{session_id}/data/{file_path.name}"
                        category = "data"
                        target_list = data_files
                    else:
                        s3_key = f"sessions/{session_id}/additional/{file_path.name}"
                        category = "additional"
                        target_list = other_files

                    try:
                        # Check if file already exists in S3 to avoid duplicate uploads
                        # Files already uploaded in continue-session have keys like: sessions/{session_id}/turn{n}_{filename}
                        turn_based_key = None
                        for turn_num in range(1, 20):  # Check up to 20 turns
                            potential_key = f"sessions/{session_id}/turn{turn_num}_{file_path.name}"
                            try:
                                self.s3_client.head_object(Bucket=self.bucket_name, Key=potential_key)
                                turn_based_key = potential_key
                                logger.info(f"File {file_path.name} already exists in S3 as {potential_key}, skipping upload")
                                break
                            except:
                                continue

                        if turn_based_key:
                            # File already exists, just add to metadata
                            target_list.append({
                                "filename": file_path.name,
                                "s3_key": turn_based_key,  # Use existing S3 key
                                "file_size": file_path.stat().st_size if file_path.exists() else 0,
                                "uploaded_at": datetime.now().isoformat(),
                                "skipped_duplicate": True
                            })
                        else:
                            # Upload file to S3
                            self.s3_client.upload_file(str(file_path), self.bucket_name, s3_key)

                            # Add to appropriate list
                            target_list.append({
                                "filename": file_path.name,
                                "s3_key": s3_key,
                                "file_size": file_path.stat().st_size,
                                "uploaded_at": datetime.now().isoformat()
                            })

                    except FileNotFoundError as e:
                        logger.warning(f"File not found during upload {file_path.name}: {e}")
                        continue
                    except Exception as e:
                        logger.warning(f"Failed to upload {file_path.name}: {e}")
                        continue
        else:
            logger.warning(f"Session directory {session_path} does not exist, skipping individual file upload")

        # Add categorized files to s3_files
        if images:
            s3_files["images"] = images
        if data_files:
            s3_files["data_files"] = data_files
        if other_files:
            s3_files["additional_files"] = other_files

        return s3_files

    def _prepare_session_metadata(self, session_id: str, session_data: Dict, s3_files: Dict) -> Dict:
        """Prepare session metadata for MongoDB storage"""

        # Extract thinking process and report from json_result if available
        thinking_content = ""
        report_content = ""
        if session_data.get("json_result"):
            json_result = session_data["json_result"]
            if isinstance(json_result, dict):
                content = json_result.get("content", {})
                if isinstance(content, dict):
                    thinking_content = content.get("thinking_content", "")
                    report_content = content.get("final_report", "")

        # Extract key information from session_data
        metadata = {
            "_id": session_id,
            "session_id": session_id,
            "status": session_data.get("status", "unknown"),
            "is_complete": session_data.get("is_complete", False),
            "is_cancelled": session_data.get("is_cancelled", False),
            "error": session_data.get("error"),
            "created_at": session_data.get("created_at"),
            "query": session_data.get("query") or session_data.get("message", ""),
            "language": session_data.get("language", "en"),
            "user_id": session_data.get("user_id"),
            "uploaded_to_cloud_at": datetime.now().isoformat(),

            # S3 file keys and metadata - includes all files (images, data, etc.)
            "s3_files": s3_files,

            # Store thinking process and report content
            "thinking_process": thinking_content,
            "final_report": report_content,

            # Progress summary (keep only key progress info)
            "progress_summary": {
                "total_updates": len(session_data.get("all_progress_updates", [])),
                "snapshot_count": len(session_data.get("periodic_snapshots", [])),
                "final_status": session_data.get("status")
            },

            # Result summary
            "result_summary": {
                "has_result": bool(session_data.get("result")),
                "json_result_keys": list(session_data.get("json_result", {}).keys()) if session_data.get("json_result") else [],
                "image_count": len(s3_files.get("images", [])),
                "data_file_count": len(s3_files.get("data_files", [])),
                "additional_file_count": len(s3_files.get("additional_files", []))
            }
        }

        # Add multi-turn specific metadata if applicable
        if hasattr(session_data, 'original_session_id') and session_data.original_session_id:
            metadata["multiturn_info"] = {
                "original_session_id": session_data.original_session_id,
                "turn_number": getattr(session_data, 'turn_number', 0),
                "is_multiturn": True
            }

        return metadata

    async def _save_session_metadata(self, metadata: Dict) -> Dict:
        """Save session metadata to MongoDB"""
        try:
            event = {
                "database_name": self.database_name,
                "collection_name": self.sessions_collection,
                "items": [metadata],
                "id_field": "_id"
            }

            result = upsert_wrapper(event)

            if result.get("statusCode") == 200:
                logger.info(f"Session metadata saved to MongoDB: {metadata['session_id']}")
                return metadata
            else:
                raise Exception(f"MongoDB upsert failed: {result}")

        except Exception as e:
            logger.error(f"Failed to save session metadata: {e}")
            raise

    async def _cleanup_local_files(self, local_session_path: str):
        """Clean up local session files after successful cloud upload"""
        try:
            if os.path.exists(local_session_path):
                shutil.rmtree(local_session_path)
                logger.info(f"Cleaned up local session files: {local_session_path}")
        except Exception as e:
            logger.error(f"Failed to cleanup local files {local_session_path}: {e}")

    async def retrieve_session_from_cloud(self, session_id: str) -> Optional[Dict]:
        """Retrieve session metadata from MongoDB using cached connection"""
        import time
        start_time = time.time()

        try:
            # Use cached MongoDB connection instead of creating new one
            conn_start = time.time()
            collection = self._get_cached_mongodb_collection(self.sessions_collection)
            print(f"[PERF retrieve_session_from_cloud] Get cached connection: {(time.time() - conn_start) * 1000:.2f} ms")

            if collection is None:
                print(f"[PERF retrieve_session_from_cloud] ERROR: Collection is None")
                return None

            query_start = time.time()
            session_doc = collection.find_one({"_id": session_id})
            print(f"[PERF retrieve_session_from_cloud] MongoDB query: {(time.time() - query_start) * 1000:.2f} ms")
            print(f"[PERF retrieve_session_from_cloud] Total: {(time.time() - start_time) * 1000:.2f} ms")

            return session_doc

        except Exception as e:
            print(f"[PERF retrieve_session_from_cloud] ERROR: {e}")
            logger.error(f"Failed to retrieve session {session_id} from cloud: {e}")
            return None

    async def update_session_metadata(self, session_id: str, updates: Dict) -> bool:
        """Update session metadata in MongoDB using cached connection"""
        try:
            # Use cached MongoDB connection
            collection = self._get_cached_mongodb_collection(self.sessions_collection)
            if collection is None:
                return False

            collection.update_one(
                {"_id": session_id},
                {"$set": updates}
            )
            logger.info(f"Updated session metadata for {session_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to update session metadata {session_id}: {e}")
            return False

    async def delete_session_from_s3(self, session_id: str) -> List[str]:
        """Delete all session files from S3"""
        deleted_files = []
        try:
            # List all objects with session prefix
            prefix = f"sessions/{session_id}/"

            paginator = self.s3_client.get_paginator('list_objects_v2')
            page_iterator = paginator.paginate(
                Bucket=self.bucket_name,
                Prefix=prefix
            )

            objects_to_delete = []
            for page in page_iterator:
                if 'Contents' in page:
                    for obj in page['Contents']:
                        objects_to_delete.append({'Key': obj['Key']})
                        deleted_files.append(obj['Key'])

            # Delete objects in batches
            if objects_to_delete:
                # S3 allows deletion of up to 1000 objects at a time
                batch_size = 1000
                for i in range(0, len(objects_to_delete), batch_size):
                    batch = objects_to_delete[i:i + batch_size]
                    self.s3_client.delete_objects(
                        Bucket=self.bucket_name,
                        Delete={'Objects': batch}
                    )

                logger.info(f"Deleted {len(deleted_files)} S3 objects for session {session_id}")

        except Exception as e:
            logger.error(f"Failed to delete S3 objects for session {session_id}: {e}")

        return deleted_files

    async def delete_session_from_mongodb(self, session_id: str) -> List[str]:
        """Delete session documents from MongoDB"""
        deleted_docs = []
        try:
            # Delete from 'sessions' collection
            collection = get_mongodb_collection(self.database_name, self.sessions_collection)
            if collection is not None:
                # Delete main session document
                result = collection.delete_one({"_id": session_id})
                if result.deleted_count > 0:
                    deleted_docs.append(f"sessions:{session_id}")

                # Also delete any turn-specific documents
                turn_result = collection.delete_many({"_id": {"$regex": f"^{session_id}_turn_"}})
                if turn_result.deleted_count > 0:
                    deleted_docs.append(f"sessions_turns:{turn_result.deleted_count}")

            # Also delete from 'multiturn_sessions' collection (use cached connection)
            multiturn_collection = self._get_cached_mongodb_collection(self.multiturn_collection)
            if multiturn_collection is not None:
                # Try deleting by session_id field
                multiturn_result = multiturn_collection.delete_one({"session_id": session_id})
                if multiturn_result.deleted_count > 0:
                    deleted_docs.append(f"multiturn_sessions:{session_id}")
                else:
                    # Also try deleting by _id in case it's stored that way
                    multiturn_id_result = multiturn_collection.delete_one({"_id": session_id})
                    if multiturn_id_result.deleted_count > 0:
                        deleted_docs.append(f"multiturn_sessions_by_id:{session_id}")

            logger.info(f"Deleted MongoDB documents for session {session_id}: {deleted_docs}")

        except Exception as e:
            logger.error(f"Failed to delete MongoDB documents for session {session_id}: {e}")

        return deleted_docs

    async def list_cloud_sessions(self, limit: int = 100, status_filter: str = None, user_id: str = None) -> List[Dict]:
        """List sessions stored in cloud with optional filtering using cached connection"""
        try:
            # Use cached MongoDB connection
            collection = self._get_cached_mongodb_collection(self.sessions_collection)
            if collection is None:
                return []

            # Build query
            query = {}
            if status_filter:
                query["status"] = status_filter
            if user_id:
                query["user_id"] = user_id

            # Get sessions sorted by creation date (newest first)
            sessions = list(collection.find(query).sort("created_at", -1).limit(limit))

            return sessions

        except Exception as e:
            logger.error(f"Failed to list cloud sessions: {e}")
            return []

    async def download_turn_files_from_s3(self, session_id: str, session_path: str) -> Dict[str, str]:
        """
        Download USER-UPLOADED files from previous turns in a multi-turn session from S3
        Excludes system-generated files (query, report, thinking_process, result, snapshot)

        Args:
            session_id: The multi-turn session ID
            session_path: Local path where files should be downloaded

        Returns:
            Dictionary mapping filenames to local paths
        """
        downloaded_files = {}

        # System-generated file patterns to EXCLUDE from download
        system_file_patterns = [
            'query_*.txt',
            'report_*.md',
            'thinking_process_*.txt',
            'result_*.json',
            'snapshot_*.json',
            '*.zip'
        ]

        def is_system_file(filename):
            """Check if filename matches system-generated patterns"""
            import fnmatch
            for pattern in system_file_patterns:
                if fnmatch.fnmatch(filename, pattern):
                    return True
            return False

        try:
            # Ensure session directory exists
            os.makedirs(session_path, exist_ok=True)

            # For multi-turn sessions, we need to check multiple prefixes:
            # - sessions/{session_id}/ (Turn 1)
            # - sessions/{session_id}_turn_2/ (Turn 2)
            # - sessions/{session_id}_turn_3/ (Turn 3), etc.
            prefixes_to_check = [f"sessions/{session_id}/"]

            # Also check for turn-specific paths (up to 10 turns)
            for turn_num in range(2, 11):
                prefixes_to_check.append(f"sessions/{session_id}_turn_{turn_num}/")

            paginator = self.s3_client.get_paginator('list_objects_v2')

            for prefix in prefixes_to_check:
                page_iterator = paginator.paginate(
                    Bucket=self.bucket_name,
                    Prefix=prefix
                )

                for page in page_iterator:
                    if 'Contents' in page:
                        for obj in page['Contents']:
                            s3_key = obj['Key']

                            # Skip system-generated file directories
                            if any(x in s3_key for x in ['/report_md/', '/thinking_process/', '/query_file/',
                                                         '/result_json/', '/snapshots/', '/session_zip/']):
                                logger.debug(f"Skipping system file: {s3_key}")
                                continue

                            # Extract filename from S3 key
                            # Keys are like: sessions/{session_id}/turn{n}_{filename}
                            # or sessions/{session_id}/images/{filename}
                            filename_parts = s3_key.split('/')[-1]  # Get last part

                            # Remove turn prefix if present (e.g., "turn1_file.txt" -> "file.txt")
                            if filename_parts.startswith('turn'):
                                # Find the underscore after turn number
                                underscore_pos = filename_parts.find('_')
                                if underscore_pos > 0:
                                    filename = filename_parts[underscore_pos + 1:]
                                else:
                                    filename = filename_parts
                            else:
                                filename = filename_parts

                            # Skip system-generated files
                            if is_system_file(filename):
                                logger.debug(f"Skipping system-generated file: {filename}")
                                continue

                            # Skip if file already exists locally
                            local_path = os.path.join(session_path, filename)
                            if os.path.exists(local_path):
                                logger.info(f"File {filename} already exists locally, skipping download")
                                downloaded_files[filename] = local_path
                                continue

                            # Download file from S3
                            try:
                                self.s3_client.download_file(
                                    self.bucket_name,
                                    s3_key,
                                    local_path
                                )
                                downloaded_files[filename] = local_path
                                logger.info(f"Downloaded user file {filename} from S3 (key: {s3_key})")
                            except Exception as e:
                                logger.error(f"Failed to download {s3_key} from S3: {e}")

            logger.info(f"Downloaded {len(downloaded_files)} user files from S3 for session {session_id}")

        except Exception as e:
            logger.error(f"Error downloading files from S3 for session {session_id}: {e}")

        return downloaded_files

    def generate_presigned_url(self, s3_key: str, expiry_seconds: int = 7200) -> str:
        """Generate a presigned URL for an S3 object (2 hours default)"""
        try:
            from s3_mongodb.s3_utils import get_s3_link
            url = get_s3_link(self.s3_client, self.bucket_name, s3_key, expiry_seconds)
            return url
        except Exception as e:
            logger.error(f"Failed to generate presigned URL for {s3_key}: {e}")
            raise

    def download_file_content(self, s3_key: str) -> Optional[bytes]:
        """Download file content from S3 as bytes"""
        try:
            response = self.s3_client.get_object(Bucket=self.bucket_name, Key=s3_key)
            content = response['Body'].read()
            logger.info(f"Downloaded {len(content)} bytes from S3 key: {s3_key}")
            return content
        except Exception as e:
            logger.error(f"Failed to download content from S3 key {s3_key}: {e}")
            return None

    async def upload_file(self, local_path: str, s3_key: str) -> bool:
        """Upload a single file to S3

        Args:
            local_path: Local file path to upload
            s3_key: S3 object key (path in bucket)

        Returns:
            True if successful, False otherwise
        """
        try:
            if not self.s3_client:
                logger.warning("S3 client not initialized, skipping upload")
                return False

            self.s3_client.upload_file(str(local_path), self.bucket_name, s3_key)
            logger.info(f"Uploaded {local_path} to S3: {s3_key}")
            return True
        except Exception as e:
            logger.error(f"Failed to upload {local_path} to S3: {e}")
            return False

    async def get_session_download_urls(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get fresh download URLs for all session's S3 files including images"""
        try:
            # Get session metadata from MongoDB
            session_data = await self.retrieve_session_from_cloud(session_id)
            if not session_data:
                return None

            s3_files = session_data.get("s3_files", {})
            if not s3_files:
                return None

            # Generate fresh URLs for all files
            download_urls = {
                "session_id": session_id,
                "thinking_process": session_data.get("thinking_process", ""),
                "final_report": session_data.get("final_report", ""),
                "files": {}
            }

            for file_type, file_info in s3_files.items():
                if file_type in ["snapshots", "images", "data_files", "additional_files"]:
                    # Handle multiple files (lists)
                    file_urls = []
                    if isinstance(file_info, list):
                        for file_item in file_info:
                            if isinstance(file_item, dict) and "s3_key" in file_item:
                                url = self.generate_presigned_url(file_item["s3_key"])
                                file_urls.append({
                                    "filename": file_item["filename"],
                                    "url": url,
                                    "s3_key": file_item["s3_key"],
                                    "file_size": file_item.get("file_size", 0),
                                    "expires_at": (datetime.now() + timedelta(hours=2)).isoformat()
                                })
                    if file_urls:
                        download_urls["files"][file_type] = file_urls

                elif isinstance(file_info, dict) and "s3_key" in file_info:
                    # Handle single file
                    url = self.generate_presigned_url(file_info["s3_key"])
                    download_urls["files"][file_type] = {
                        "filename": file_info["filename"],
                        "url": url,
                        "s3_key": file_info["s3_key"],
                        "file_size": file_info.get("file_size", 0),
                        "expires_at": (datetime.now() + timedelta(hours=2)).isoformat()
                    }

            # Add session_zip with presigned_url for backward compatibility with Gradio
            if "session_zip" in download_urls["files"]:
                # session_zip already exists in S3, add presigned_url alias for Gradio compatibility
                download_urls["files"]["session_zip"]["presigned_url"] = download_urls["files"]["session_zip"]["url"]
            else:
                # session_zip doesn't exist in S3 - provide /download endpoint as fallback
                # Note: This will be a redirect URL, not a presigned S3 URL
                download_urls["files"]["session_zip"] = {
                    "filename": f"session_{session_id[:8]}.zip",
                    "url": f"/download/{session_id}",  # Placeholder - will be replaced by caller with proper server URL
                    "presigned_url": f"/download/{session_id}",  # For Gradio compatibility
                    "s3_key": None,
                    "file_size": 0,
                    "expires_at": (datetime.now() + timedelta(hours=2)).isoformat(),
                    "note": "ZIP will be generated on-demand from S3 files"
                }

            return download_urls

        except Exception as e:
            logger.error(f"Failed to generate download URLs for session {session_id}: {e}")
            return None

    async def upload_multiturn_session(self, multiturn_session_data: Dict) -> Dict[str, Any]:
        """Upload multi-turn session data to cloud"""
        try:
            session_id = multiturn_session_data.get("session_id")
            logger.info(f"Uploading multi-turn session {session_id} to cloud")

            # Prepare multi-turn metadata
            metadata = {
                "_id": session_id,
                "session_id": session_id,
                "session_name": multiturn_session_data.get("session_name", ""),
                "created_at": multiturn_session_data.get("created_at"),
                "last_updated": multiturn_session_data.get("last_updated"),
                "total_turns": multiturn_session_data.get("total_turns", 0),
                "language": multiturn_session_data.get("language", "en"),
                "session_status": multiturn_session_data.get("session_status", "active"),
                "first_query": multiturn_session_data.get("first_query", ""),
                "latest_query": multiturn_session_data.get("latest_query", ""),
                "user_id": multiturn_session_data.get("user_id"),
                "turns": multiturn_session_data.get("turns", []),
                # Sharing metadata
                "is_shared": multiturn_session_data.get("is_shared", False),
                "shared_at": multiturn_session_data.get("shared_at"),
                "uploaded_to_cloud_at": datetime.now().isoformat()
            }

            # Save to MongoDB multiturn collection
            event = {
                "database_name": self.database_name,
                "collection_name": self.multiturn_collection,
                "items": [metadata],
                "id_field": "_id"
            }

            result = upsert_wrapper(event)

            if result.get("statusCode") == 200:
                logger.info(f"Multi-turn session {session_id} uploaded to cloud successfully")
                return {
                    "session_id": session_id,
                    "status": "success",
                    "mongodb_id": session_id
                }
            else:
                raise Exception(f"MongoDB upsert failed: {result}")

        except Exception as e:
            logger.error(f"Failed to upload multi-turn session: {e}")
            return {
                "session_id": multiturn_session_data.get("session_id"),
                "status": "error",
                "error": str(e)
            }

    # ============= COMMUNITY SHARING METHODS =============

    async def store_shared_session(self, shared_data: Dict) -> Dict[str, Any]:
        """Store a shared session in the community collection"""
        try:
            session_id = shared_data.get("session_id")
            logger.info(f"Storing shared session {session_id} to community collection")

            # Add metadata fields
            shared_data["_id"] = session_id
            shared_data["indexed_at"] = datetime.now().isoformat()

            # Store in community_sessions collection
            event = {
                "database_name": self.database_name,
                "collection_name": "community_sessions",
                "items": [shared_data],
                "id_field": "_id"
            }

            result = upsert_wrapper(event)

            if result.get("statusCode") == 200:
                logger.info(f"Shared session {session_id} stored successfully")
                return {"success": True, "session_id": session_id}
            else:
                raise Exception(f"Failed to store shared session: {result}")

        except Exception as e:
            logger.error(f"Failed to store shared session {session_id}: {e}")
            raise

    async def remove_shared_session(self, session_id: str) -> Dict[str, Any]:
        """Remove a session from the community collection"""
        try:
            logger.info(f"Removing shared session {session_id} from community collection")

            collection = get_mongodb_collection(self.database_name, "community_sessions")
            if collection is not None:
                result = collection.delete_one({"session_id": session_id})
                if result.deleted_count > 0:
                    logger.info(f"Shared session {session_id} removed successfully")
                    return {"success": True, "session_id": session_id}

            return {"success": False, "message": "Session not found"}

        except Exception as e:
            logger.error(f"Failed to remove shared session {session_id}: {e}")
            raise

    async def search_shared_sessions(self, tags: List[str] = None, search_query: str = None,
                                    visibility: str = "community", limit: int = 50,
                                    offset: int = 0) -> Dict[str, Any]:
        """Search for shared sessions based on tags and query"""
        try:
            collection = get_mongodb_collection(self.database_name, "community_sessions")
            if collection is None:
                return {"sessions": [], "total": 0}

            # Build query
            query = {"visibility": visibility}

            if tags:
                query["tags"] = {"$in": tags}

            if search_query:
                # Search in title, description, and first/last query
                query["$or"] = [
                    {"title": {"$regex": search_query, "$options": "i"}},
                    {"description": {"$regex": search_query, "$options": "i"}},
                    {"first_query": {"$regex": search_query, "$options": "i"}},
                    {"last_query": {"$regex": search_query, "$options": "i"}}
                ]

            # Count total matching documents
            total = collection.count_documents(query)

            # Get paginated results
            sessions = list(collection.find(query)
                          .sort("shared_at", -1)
                          .skip(offset)
                          .limit(limit))

            # Clean up MongoDB _id field
            for session in sessions:
                if "_id" in session:
                    session["_id"] = str(session["_id"])

            return {
                "sessions": sessions,
                "total": total
            }

        except Exception as e:
            logger.error(f"Failed to search shared sessions: {e}")
            return {"sessions": [], "total": 0}

    async def get_shared_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific shared session"""
        try:
            collection = get_mongodb_collection(self.database_name, "community_sessions")
            if collection is None:
                return None

            session = collection.find_one({"session_id": session_id})
            if session:
                if "_id" in session:
                    session["_id"] = str(session["_id"])
                return session

            return None

        except Exception as e:
            logger.error(f"Failed to get shared session {session_id}: {e}")
            return None

    async def get_popular_tags(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get popular tags from shared sessions"""
        try:
            collection = get_mongodb_collection(self.database_name, "community_sessions")
            if collection is None:
                return []

            # Aggregate to get tag counts
            pipeline = [
                {"$match": {"visibility": {"$ne": "private"}}},
                {"$unwind": "$tags"},
                {"$group": {"_id": "$tags", "count": {"$sum": 1}}},
                {"$sort": {"count": -1}},
                {"$limit": limit},
                {"$project": {"tag": "$_id", "count": 1, "_id": 0}}
            ]

            result = list(collection.aggregate(pipeline))
            return result

        except Exception as e:
            logger.error(f"Failed to get popular tags: {e}")
            return []

# Global instance
cloud_storage_manager = CloudStorageManager()
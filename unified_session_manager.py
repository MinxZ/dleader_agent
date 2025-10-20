"""
Unified Session Manager
Provides a single interface for accessing sessions from both local storage and cloud storage
The API interface remains simple and doesn't need to know about storage locations
"""

import asyncio
import os
import json
from datetime import datetime
from typing import Dict, List, Optional, Any, Union
from cloud_storage_manager import cloud_storage_manager

class UnifiedSessionManager:
    """
    Manages sessions across local and cloud storage with intelligent routing

    Task State Handling:
    - ONGOING: Active sessions (in queue or processing) - Always local
    - PENDING: Queued sessions waiting to start - Always local
    - COMPLETED: Finished sessions - Can be local or cloud
    """

    def __init__(self, queue_manager):
        self.queue_manager = queue_manager
        self.cloud_manager = cloud_storage_manager

    async def get_all_sessions(self, include_cloud: bool = True, user_id: str = None) -> List[Dict[str, Any]]:
        """
        Get all sessions from both local and cloud storage
        Returns unified list with storage location abstracted
        """
        all_sessions = []
        session_ids_seen = set()

        # 1. Get ONGOING/PENDING sessions (always local/active) - filter by user_id
        active_sessions = self._get_active_sessions(user_id=user_id)
        for session in active_sessions:
            session_id = session.get("session_id", "")
            if session_id and session_id not in session_ids_seen:
                all_sessions.append(session)
                session_ids_seen.add(session_id)

        # 2. Get locally stored sessions (completed but not yet uploaded) - filter by user_id
        local_stored_sessions = self._get_local_stored_sessions(user_id=user_id)
        for session in local_stored_sessions:
            session_id = session.get("session_id", "")
            if session_id and session_id not in session_ids_seen:
                # Add storage location metadata (internal use)
                session["_storage_location"] = "local"
                all_sessions.append(session)
                session_ids_seen.add(session_id)

        # 3. Get cloud sessions (completed and uploaded) if requested - already filtered by user_id
        if include_cloud:
            try:
                cloud_sessions = await self.cloud_manager.list_cloud_sessions(limit=1000, user_id=user_id)
                for session in cloud_sessions:
                    session_id = session.get("session_id", "")
                    if session_id and session_id not in session_ids_seen:
                        # Add storage location metadata (internal use)
                        session["_storage_location"] = "cloud"
                        # Convert cloud format to unified format
                        unified_session = self._convert_cloud_to_unified_format(session)
                        all_sessions.append(unified_session)
                        session_ids_seen.add(session_id)
            except Exception as e:
                print(f"Warning: Could not fetch cloud sessions: {e}")

        # No need for additional filtering since we already filtered at the source

        # Sort by creation date (newest first)
        def get_sort_key(session):
            timestamp = session.get('timestamp') or session.get('created_at') or ''
            # Handle datetime objects
            if hasattr(timestamp, 'isoformat'):
                timestamp = timestamp.isoformat()
            return timestamp

        all_sessions.sort(key=get_sort_key, reverse=True)

        return all_sessions

    async def get_session_by_id(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a specific session by ID from any storage location
        Returns unified format regardless of storage location
        """

        # 1. Check active sessions first (ongoing/pending)
        if session_id in self.queue_manager.active_sessions:
            user_request = self.queue_manager.active_sessions[session_id]
            return self._convert_active_session_to_unified(user_request)

        # 2. Check local storage (recently completed)
        local_session = self.queue_manager._load_session_from_storage(session_id)
        if local_session:
            local_session["_storage_location"] = "local"
            return local_session

        # 3. Check cloud storage (uploaded completed sessions)
        try:
            cloud_session = await self.cloud_manager.retrieve_session_from_cloud(session_id)
            if cloud_session:
                cloud_session["_storage_location"] = "cloud"
                return self._convert_cloud_to_unified_format(cloud_session)
        except Exception as e:
            print(f"Warning: Could not fetch session {session_id} from cloud: {e}")

        return None

    async def get_session_status(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Get session status with intelligent routing based on session state
        """

        # 1. For ongoing/pending sessions, get real-time status
        if session_id in self.queue_manager.active_sessions:
            return self.queue_manager.get_session_progress(session_id)

        # 2. For completed sessions, get from appropriate storage
        session_data = await self.get_session_by_id(session_id)
        if not session_data:
            return None

        # Convert to status format
        return {
            "session_id": session_id,
            "status": session_data.get("status", "unknown"),
            "is_complete": session_data.get("is_complete", True),
            "is_cancelled": session_data.get("is_cancelled", False),
            "error": session_data.get("error"),
            "created_at": session_data.get("created_at", session_data.get("timestamp")),
            "storage_location": session_data.get("_storage_location", "unknown"),
            "progress_updates": session_data.get("all_progress_updates", []),
            "json_result": session_data.get("json_result", {}),
            "periodic_snapshots": session_data.get("periodic_snapshots", []),
            "user_id": session_data.get("user_id")  # Include user_id for security checks
        }

    async def get_session_files(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Get session files/download info with intelligent routing
        """
        session_data = await self.get_session_by_id(session_id)
        if not session_data:
            return None

        storage_location = session_data.get("_storage_location", "unknown")

        if storage_location == "cloud":
            # Cloud sessions: return S3 keys for on-demand URL generation
            return {
                "session_id": session_id,
                "storage_type": "cloud",
                "s3_files": session_data.get("s3_files", {}),
                "download_method": "s3_keys"
            }
        elif storage_location == "local":
            # Local sessions: return local file paths (for zip download)
            # First check if a zip file already exists
            import glob
            existing_zips = glob.glob(f"chat_zips/*{session_id[:8]}*.zip")
            if existing_zips:
                # For multi-turn sessions, use the most recent zip
                # Sort by modification time to get the latest zip (contains most turns)
                existing_zips.sort(key=lambda x: os.path.getmtime(x), reverse=True)
                zip_path = existing_zips[0]  # Use the most recent zip
                print(f"Selected zip for session {session_id[:8]}: {os.path.basename(zip_path)} (most recent of {len(existing_zips)} files)")
                return {
                    "session_id": session_id,
                    "storage_type": "local",
                    "zip_path": zip_path,
                    "download_method": "local_zip"
                }

            # No existing zip, try to find session folder
            session_path = session_data.get("session_path")

            # Fallback to trying to find it if not stored
            if not session_path or not os.path.exists(session_path):
                # Try to find by pattern
                patterns = [
                    f"chat_sessions/*{session_id[:8]}*",
                    f"chat_sessions/multiturn_*{session_id[:8]}*",
                    f"chat_sessions/session_*{session_id[:8]}*"
                ]
                for pattern in patterns:
                    matches = glob.glob(pattern)
                    if matches:
                        session_path = matches[0]
                        break

            if session_path and os.path.exists(session_path):
                # Try to create zip if it doesn't exist
                try:
                    from agent_fastapi_server_multiturn import create_session_zip
                    zip_path = create_session_zip(session_path, save_to_chat_zips=True)
                    return {
                        "session_id": session_id,
                        "storage_type": "local",
                        "zip_path": zip_path,
                        "download_method": "local_zip"
                    }
                except Exception as e:
                    print(f"Error creating zip for local session {session_id}: {e}")
                    return {
                        "session_id": session_id,
                        "storage_type": "local",
                        "download_method": "none",
                        "message": "Error creating download file"
                    }
        else:
            # Check if session is actually completed
            if session_data.get("is_complete", False):
                # First check if a zip file already exists
                import glob
                existing_zips = glob.glob(f"chat_zips/*{session_id[:8]}*.zip")
                if existing_zips:
                    # Use the existing zip file
                    zip_path = existing_zips[0]  # Use the first matching zip
                    return {
                        "session_id": session_id,
                        "storage_type": "active_completed",
                        "zip_path": zip_path,
                        "download_method": "local_zip"
                    }

                # No existing zip, try to create one from session folder
                session_path = session_data.get("session_path")
                if not session_path:
                    # Try to find session folder by ID or name patterns
                    possible_paths = [
                        os.path.join("chat_sessions", f"session_*{session_id[:8]}*"),
                        os.path.join("chat_sessions", f"multiturn_*{session_id[:8]}*"),
                    ]
                    for pattern in possible_paths:
                        matches = glob.glob(pattern)
                        if matches:
                            session_path = matches[0]
                            break

                if session_path and os.path.exists(session_path):
                    try:
                        from agent_fastapi_server_multiturn import create_session_zip
                        zip_path = create_session_zip(session_path, save_to_chat_zips=True)
                        return {
                            "session_id": session_id,
                            "storage_type": "active_completed",
                            "zip_path": zip_path,
                            "download_method": "local_zip"
                        }
                    except Exception as e:
                        print(f"Error creating zip for completed active session {session_id}: {e}")

            # Active session - files not ready yet
            return {
                "session_id": session_id,
                "storage_type": "active",
                "message": "Session is still active, files not ready for download",
                "download_method": "none"
            }

        return None

    def _get_active_sessions(self, user_id: str = None) -> List[Dict[str, Any]]:
        """Get all active (ongoing/pending) sessions, optionally filtered by user_id"""
        active_sessions = []

        for session_id, user_request in self.queue_manager.active_sessions.items():
            # Filter by user_id if provided
            if user_id and getattr(user_request, 'user_id', None) != user_id:
                continue

            session_data = self._convert_active_session_to_unified(user_request)
            active_sessions.append(session_data)

        return active_sessions

    def _get_local_stored_sessions(self, user_id: str = None) -> List[Dict[str, Any]]:
        """Get all locally stored (completed but not uploaded) sessions, optionally filtered by user_id"""
        stored_sessions = []

        # Get stored sessions from queue manager
        try:
            all_stored = self.queue_manager.get_all_stored_sessions()
            for session in all_stored:
                # Skip if session is also active (shouldn't happen but be safe)
                if session.get("session_id") not in self.queue_manager.active_sessions:
                    # Filter by user_id if provided
                    if user_id and session.get('user_id') != user_id:
                        continue
                    stored_sessions.append(session)
        except:
            # Fallback: scan session_storage directory
            session_storage_dir = "session_storage"
            if os.path.exists(session_storage_dir):
                for filename in os.listdir(session_storage_dir):
                    if filename.endswith('.json'):
                        try:
                            session_id = filename.replace('.json', '')
                            if session_id not in self.queue_manager.active_sessions:
                                session_path = os.path.join(session_storage_dir, filename)
                                with open(session_path, 'r') as f:
                                    session_data = json.load(f)
                                    # Filter by user_id if provided
                                    if user_id and session_data.get('user_id') != user_id:
                                        continue
                                    stored_sessions.append(session_data)
                        except Exception as e:
                            print(f"Error loading stored session {filename}: {e}")

        return stored_sessions

    def _convert_active_session_to_unified(self, user_request) -> Dict[str, Any]:
        """Convert active session object to unified format"""

        # Determine status based on session state
        if user_request.is_complete:
            status = "completed" if not user_request.error else "error"
        elif user_request.is_cancelled:
            status = "cancelled"
        elif hasattr(user_request, 'is_processing') and user_request.is_processing:
            status = "processing"
        else:
            status = "queued"

        return {
            "session_id": user_request.session_id,
            "status": status,
            "is_complete": user_request.is_complete,
            "is_cancelled": user_request.is_cancelled,
            "error": user_request.error,
            "query": user_request.message,
            "full_query": user_request.message,
            "language": user_request.language,
            "timestamp": user_request.created_at.isoformat(),
            "created_at": user_request.created_at.isoformat(),
            "user_id": getattr(user_request, 'user_id', None),
            "_storage_location": "active",
            "progress_updates": getattr(user_request, 'all_progress_updates', []),
            "json_result": getattr(user_request, 'json_result', {}),
            "periodic_snapshots": getattr(user_request, 'periodic_snapshots', [])
        }

    def _convert_cloud_to_unified_format(self, cloud_session: Dict) -> Dict[str, Any]:
        """Convert cloud session format to unified format"""
        return {
            "session_id": cloud_session.get("session_id"),
            "status": cloud_session.get("status", "completed"),
            "is_complete": cloud_session.get("is_complete", True),
            "is_cancelled": cloud_session.get("is_cancelled", False),
            "error": cloud_session.get("error"),
            "query": cloud_session.get("query", ""),
            "full_query": cloud_session.get("query", ""),
            "language": cloud_session.get("language", "en"),
            "timestamp": cloud_session.get("created_at"),
            "created_at": cloud_session.get("created_at"),
            "user_id": cloud_session.get("user_id"),  # Preserve user_id for filtering
            "_storage_location": "cloud",
            # Cloud sessions have summarized data, not full progress
            "progress_summary": cloud_session.get("progress_summary", {}),
            "result_summary": cloud_session.get("result_summary", {}),
            "s3_files": cloud_session.get("s3_files", {}),
            "uploaded_to_cloud_at": cloud_session.get("uploaded_to_cloud_at")
        }

    async def get_multiturn_sessions(self, include_cloud: bool = True, user_id: str = None) -> List[Dict[str, Any]]:
        """Get all multi-turn sessions from MongoDB only"""
        all_sessions = []
        session_ids_seen = set()

        # 1. Get in-memory active multi-turn sessions (currently being processed)
        for session_id, session in self.queue_manager.multiturn_sessions.items():
            session_data = {
                "session_id": session_id,
                "session_name": getattr(session, 'session_name', ""),
                "created_at": session.created_at,
                "last_updated": session.last_updated,
                "total_turns": session.total_turns,
                "language": session.language,
                "session_status": session.session_status,
                "first_query": session.first_query,
                "latest_query": session.latest_query,
                "user_id": getattr(session, 'user_id', None),
                # Sharing metadata
                "is_shared": getattr(session, 'is_shared', False),
                "shared_at": getattr(session, 'shared_at', None),
                "_storage_location": "memory"
            }
            all_sessions.append(session_data)
            session_ids_seen.add(session_id)

        # 2. Get multi-turn sessions from MongoDB (all persisted sessions)
        if include_cloud:
            try:
                # Get from MongoDB multiturn collection
                from s3_mongodb.func_mongodb import get_mongodb_collection
                import os
                collection = get_mongodb_collection(
                    os.getenv("SESSION_DB_NAME", "dleader_agent"),
                    "multiturn_sessions"
                )
                if collection is not None:
                    # Build query for multiturn sessions
                    query = {}
                    if user_id:
                        query["user_id"] = user_id
                    mongodb_sessions = list(collection.find(query).sort("created_at", -1).limit(1000))
                    for session in mongodb_sessions:
                        session_id = session.get("session_id")
                        if session_id and session_id not in session_ids_seen:
                            # Extract only necessary metadata (exclude heavy content like turns data)
                            session_metadata = {
                                "session_id": session_id,
                                "session_name": session.get("session_name", ""),
                                "user_id": session.get("user_id"),
                                "total_turns": session.get("total_turns", 0),
                                "created_at": session.get("created_at"),
                                "last_updated": session.get("last_updated"),
                                "language": session.get("language", "en"),
                                "session_status": session.get("session_status", "active"),
                                "first_query": session.get("first_query", ""),
                                "latest_query": session.get("latest_query", ""),
                                "is_shared": session.get("is_shared", False),
                                "shared_at": session.get("shared_at"),
                                "_storage_location": "mongodb"
                            }
                            all_sessions.append(session_metadata)
                            session_ids_seen.add(session_id)
            except Exception as e:
                print(f"Warning: Could not fetch MongoDB multi-turn sessions: {e}")

        # Filter by user_id if provided
        if user_id:
            filtered_sessions = []
            for session in all_sessions:
                session_user_id = session.get("user_id")
                if session_user_id == user_id:
                    filtered_sessions.append(session)
            all_sessions = filtered_sessions

        # Sort by last_updated (newest first)
        all_sessions.sort(key=lambda x: x.get('last_updated', x.get('created_at', '')), reverse=True)

        return all_sessions

    async def get_multiturn_session_by_id(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific multi-turn session by ID from any storage location"""

        # 1. Check in-memory first (currently active)
        if session_id in self.queue_manager.multiturn_sessions:
            session = self.queue_manager.multiturn_sessions[session_id]
            return {
                "session_id": session_id,
                "session_name": getattr(session, 'session_name', ""),
                "created_at": session.created_at,
                "last_updated": session.last_updated,
                "total_turns": session.total_turns,
                "language": session.language,
                "session_status": session.session_status,
                "first_query": session.first_query,
                "latest_query": session.latest_query,
                "user_id": getattr(session, 'user_id', None),
                "is_shared": getattr(session, 'is_shared', False),
                "shared_at": getattr(session, 'shared_at', None),
                "_storage_location": "memory",
                "_session_object": session  # Include the actual object for updates
            }

        # 2. Check local storage
        multiturn_file = os.path.join(self.queue_manager.multiturn_storage_dir, f"{session_id}.json")
        if os.path.exists(multiturn_file):
            try:
                with open(multiturn_file, 'r', encoding='utf-8') as f:
                    session_data = json.load(f)
                    session_data["_storage_location"] = "local"
                    return session_data
            except Exception as e:
                print(f"Error loading multiturn session from local storage: {e}")

        # 3. Check MongoDB (primary storage)
        try:
            from s3_mongodb.func_mongodb import get_mongodb_collection
            collection = get_mongodb_collection(
                os.getenv("SESSION_DB_NAME", "dleader_agent"),
                "multiturn_sessions"
            )
            if collection is not None:
                session_data = collection.find_one({"session_id": session_id})
                if session_data:
                    session_data["_storage_location"] = "mongodb"
                    return session_data
        except Exception as e:
            print(f"Error loading multiturn session from MongoDB: {e}")

        return None

    async def update_multiturn_session(self, session_id: str, updates: Dict[str, Any], user_id: str = None) -> bool:
        """Update a multi-turn session in all storage locations"""

        # Get the session first
        session = await self.get_multiturn_session_by_id(session_id)
        if not session:
            return False

        # Verify user ownership if user_id is provided
        if user_id and session.get("user_id") != user_id:
            raise PermissionError("Access denied: Session belongs to different user")

        storage_location = session.get("_storage_location")

        # Update timestamp
        updates["last_updated"] = datetime.now().isoformat()

        # 1. Update in-memory if it exists there
        if storage_location == "memory":
            session_obj = session.get("_session_object")
            if session_obj:
                for key, value in updates.items():
                    setattr(session_obj, key, value)
                # Save to local storage
                self.queue_manager._save_multiturn_session(session_obj)

        # 2. Update local file if it exists
        multiturn_file = os.path.join(self.queue_manager.multiturn_storage_dir, f"{session_id}.json")
        if os.path.exists(multiturn_file):
            try:
                with open(multiturn_file, 'r', encoding='utf-8') as f:
                    session_data = json.load(f)
                session_data.update(updates)
                with open(multiturn_file, 'w', encoding='utf-8') as f:
                    json.dump(session_data, f, indent=2, ensure_ascii=False)
            except Exception as e:
                print(f"Warning: Could not update local multiturn session file: {e}")

        # 3. Always update MongoDB (primary storage)
        try:
            from s3_mongodb.func_mongodb import get_mongodb_collection
            collection = get_mongodb_collection(
                os.getenv("SESSION_DB_NAME", "dleader_agent"),
                "multiturn_sessions"
            )
            if collection is not None:
                result = collection.update_one(
                    {"session_id": session_id},
                    {"$set": updates}
                )
                return result.modified_count > 0 or result.matched_count > 0
        except Exception as e:
            print(f"Error updating multiturn session in MongoDB: {e}")
            return False

        return True


# Global instance to be used by FastAPI endpoints
unified_session_manager = None

def get_unified_session_manager(queue_manager):
    """Get or create unified session manager instance"""
    global unified_session_manager
    if unified_session_manager is None:
        unified_session_manager = UnifiedSessionManager(queue_manager)
    return unified_session_manager
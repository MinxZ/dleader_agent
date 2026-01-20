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
        # Cache MongoDB connection to avoid 1.5s overhead on every request
        self._mongodb_collection_cache = None
        self._mongodb_connection_failed = False

    def _get_cached_mongodb_collection(self):
        """Get cached MongoDB collection or create new connection if needed"""
        # If connection previously failed, don't try again
        if self._mongodb_connection_failed:
            return None

        # Return cached connection if available
        if self._mongodb_collection_cache is not None:
            return self._mongodb_collection_cache

        # Create new connection and cache it
        try:
            from s3_mongodb.func_mongodb import get_mongodb_collection
            import os

            self._mongodb_collection_cache = get_mongodb_collection(
                os.getenv("SESSION_DB_NAME", "dleader_agent"), "multiturn_sessions"
            )
            print(f"[MongoDB] Connection established and cached")
            return self._mongodb_collection_cache
        except Exception as e:
            print(f"[MongoDB] Connection failed: {e}")
            self._mongodb_connection_failed = True
            return None

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
            timestamp = session.get("timestamp") or session.get("created_at") or ""
            # Handle datetime objects
            if hasattr(timestamp, "isoformat"):
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

        # 4. Check multiturn_sessions collection
        try:
            from s3_mongodb.func_mongodb import get_mongodb_collection
            import os

            multiturn_collection = get_mongodb_collection(
                os.getenv("SESSION_DB_NAME", "dleader_agent"), "multiturn_sessions"
            )
            if multiturn_collection is not None:
                # Try both session_id field and _id field
                multiturn_session = multiturn_collection.find_one({"session_id": session_id})
                if not multiturn_session:
                    multiturn_session = multiturn_collection.find_one({"_id": session_id})
                if multiturn_session:
                    multiturn_session["_storage_location"] = "mongodb_multiturn"
                    return multiturn_session
        except Exception as e:
            print(f"Warning: Could not fetch session {session_id} from multiturn collection: {e}")

        return None

    async def get_session_status(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Get session status with intelligent routing based on session state
        """

        # Parse turn-specific session IDs (e.g., "session_id_turn_2")
        base_session_id = session_id
        if "_turn_" in session_id:
            parts = session_id.rsplit("_turn_", 1)
            if len(parts) == 2 and parts[1].isdigit():
                base_session_id = parts[0]

        # 1. For ongoing/pending sessions, get real-time status
        # Check session_id first (handles turn-specific IDs)
        if session_id in self.queue_manager.active_sessions:
            return self.queue_manager.get_session_progress(session_id)
        # Then check base_session_id
        if base_session_id in self.queue_manager.active_sessions:
            return self.queue_manager.get_session_progress(base_session_id)
        # For multi-turn sessions, check if current turn is active
        multiturn_session = self.queue_manager.multiturn_sessions.get(base_session_id)
        if multiturn_session:
            current_turn = multiturn_session.current_turn
            if current_turn:
                turn_specific_id = f"{base_session_id}_turn_{current_turn}"
                if turn_specific_id in self.queue_manager.active_sessions:
                    return self.queue_manager.get_session_progress(turn_specific_id)

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
            "user_id": session_data.get("user_id"),  # Include user_id for security checks
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
                "download_method": "s3_keys",
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
                print(
                    f"Selected zip for session {session_id[:8]}: {os.path.basename(zip_path)} (most recent of {len(existing_zips)} files)"
                )
                return {
                    "session_id": session_id,
                    "storage_type": "local",
                    "zip_path": zip_path,
                    "download_method": "local_zip",
                }

            # No existing zip, try to find session folder
            session_path = session_data.get("session_path")

            # Fallback to trying to find it if not stored
            if not session_path or not os.path.exists(session_path):
                # Try to find by pattern
                patterns = [
                    f"chat_sessions/*{session_id[:8]}*",
                    f"chat_sessions/multiturn_*{session_id[:8]}*",
                    f"chat_sessions/session_*{session_id[:8]}*",
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
                        "download_method": "local_zip",
                    }
                except Exception as e:
                    print(f"Error creating zip for local session {session_id}: {e}")
                    return {
                        "session_id": session_id,
                        "storage_type": "local",
                        "download_method": "none",
                        "message": "Error creating download file",
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
                        "download_method": "local_zip",
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
                            "download_method": "local_zip",
                        }
                    except Exception as e:
                        print(f"Error creating zip for completed active session {session_id}: {e}")

            # Active session - files not ready yet
            return {
                "session_id": session_id,
                "storage_type": "active",
                "message": "Session is still active, files not ready for download",
                "download_method": "none",
            }

        return None

    def _get_active_sessions(self, user_id: str = None) -> List[Dict[str, Any]]:
        """Get all active (ongoing/pending) sessions, optionally filtered by user_id"""
        active_sessions = []

        for session_id, user_request in self.queue_manager.active_sessions.items():
            # Filter by user_id if provided
            if user_id and getattr(user_request, "user_id", None) != user_id:
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
                    if user_id and session.get("user_id") != user_id:
                        continue
                    stored_sessions.append(session)
        except:
            # Fallback: scan session_storage directory
            session_storage_dir = "session_storage"
            if os.path.exists(session_storage_dir):
                for filename in os.listdir(session_storage_dir):
                    if filename.endswith(".json"):
                        try:
                            session_id = filename.replace(".json", "")
                            if session_id not in self.queue_manager.active_sessions:
                                session_path = os.path.join(session_storage_dir, filename)
                                with open(session_path, "r") as f:
                                    session_data = json.load(f)
                                    # Filter by user_id if provided
                                    if user_id and session_data.get("user_id") != user_id:
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
        elif hasattr(user_request, "is_processing") and user_request.is_processing:
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
            "user_id": getattr(user_request, "user_id", None),
            "_storage_location": "active",
            "progress_updates": getattr(user_request, "all_progress_updates", []),
            "json_result": getattr(user_request, "json_result", {}),
            "periodic_snapshots": getattr(user_request, "periodic_snapshots", []),
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
            "uploaded_to_cloud_at": cloud_session.get("uploaded_to_cloud_at"),
        }

    async def get_multiturn_sessions(
        self, include_cloud: bool = True, user_id: str = None, limit: int = 10, offset: int = 0
    ) -> Dict[str, Any]:
        """Get multi-turn sessions from MongoDB with pagination

        Args:
            include_cloud: Whether to include cloud storage sessions
            user_id: Filter by user ID
            limit: Number of sessions to return (default: 10)
            offset: Number of sessions to skip (default: 0)

        Returns:
            Dict containing sessions list and total count
        """
        import time

        start_time = time.time()

        all_sessions = []
        session_ids_seen = set()
        in_memory_session_ids = set()

        # 1. Get in-memory active multi-turn sessions (currently being processed)
        # Filter by user_id upfront and collect session IDs
        step1_start = time.time()
        for session_id, session in self.queue_manager.multiturn_sessions.items():
            # Filter by user_id if provided
            session_user_id = getattr(session, "user_id", None)
            if user_id and session_user_id != user_id:
                continue

            in_memory_session_ids.add(session_id)

            # Determine current_status by checking active UserRequests
            # Check for any active turn in this session
            current_status = None
            current_turn = getattr(session, "current_turn", None)
            if current_turn:
                # Check for turn-specific session ID first
                turn_session_id = f"{session_id}_turn_{current_turn}"
                if turn_session_id in self.queue_manager.active_sessions:
                    user_request = self.queue_manager.active_sessions[turn_session_id]
                    current_status = user_request.status
                elif session_id in self.queue_manager.active_sessions:
                    user_request = self.queue_manager.active_sessions[session_id]
                    current_status = user_request.status

            # Fallback to session_status if no active UserRequest found
            if not current_status:
                # Map session_status to current_status
                if session.session_status == "active":
                    current_status = "completed"  # Active but not processing means idle
                elif session.session_status == "completed":
                    current_status = "completed"
                elif session.session_status == "error":
                    current_status = "error"
                else:
                    current_status = session.session_status

            session_data = {
                "session_id": session_id,
                "session_name": getattr(session, "session_name", ""),
                "created_at": session.created_at,
                "last_updated": session.last_updated,
                "total_turns": session.total_turns,
                "language": session.language,
                "session_status": session.session_status,
                "current_status": current_status,  # Rich status (queued, processing, completed, cancelled, error)
                "first_query": session.first_query,
                "latest_query": session.latest_query,
                "user_id": session_user_id,
                # Timing metadata
                "last_turn_started_at": getattr(session, "last_turn_started_at", None),
                "last_turn_finished_at": getattr(session, "last_turn_finished_at", None),
                # Sharing metadata
                "is_shared": getattr(session, "is_shared", False),
                "shared_at": getattr(session, "shared_at", None),
                "_storage_location": "memory",  # Will update if also in MongoDB
            }
            all_sessions.append(session_data)
            session_ids_seen.add(session_id)

        print(
            f"[PERF] Step 1 (in-memory): {(time.time() - step1_start) * 1000:.2f} ms - Found {len(all_sessions)} sessions"
        )

        # Get MongoDB collection from cache (fast!) or establish connection (slow, but only first time)
        step_mongo_connect = time.time()
        mongodb_collection = None
        was_cached = False
        if include_cloud:
            # Check if connection is already cached before getting it
            was_cached = self._mongodb_collection_cache is not None
            mongodb_collection = self._get_cached_mongodb_collection()
        connection_time = (time.time() - step_mongo_connect) * 1000
        if mongodb_collection is not None:
            cache_status = "CACHED ✅" if was_cached else "NEW CONNECTION (will be cached)"
            print(f"[PERF] MongoDB connection: {connection_time:.2f} ms ({cache_status})")
        else:
            print(f"[PERF] MongoDB connection: FAILED or SKIPPED")

        # 2. Efficiently check which in-memory sessions are also in MongoDB (batch query)
        step2_start = time.time()
        if mongodb_collection is not None and in_memory_session_ids:
            try:
                # Only check for the specific in-memory session IDs (much faster)
                mongodb_in_memory_sessions = set(
                    [
                        doc["session_id"]
                        for doc in mongodb_collection.find(
                            {"session_id": {"$in": list(in_memory_session_ids)}}, {"session_id": 1}
                        )
                    ]
                )
                # Update storage location for sessions that are both in memory and MongoDB
                for session_data in all_sessions:
                    if session_data["session_id"] in mongodb_in_memory_sessions:
                        is_complete = session_data["session_status"] == "completed"
                        if is_complete:
                            session_data["_storage_location"] = "mongodb"
            except Exception as e:
                print(f"Warning: Could not check MongoDB for in-memory sessions: {e}")

        print(f"[PERF] Step 2 (check in-memory in MongoDB): {(time.time() - step2_start) * 1000:.2f} ms")

        # 3. Get total count from MongoDB (fast - just count, no data fetch)
        step3_start = time.time()
        total_mongodb_sessions = 0
        if mongodb_collection is not None:
            try:
                query = {}
                if user_id:
                    query["user_id"] = user_id
                # Only add $nin if there are sessions to exclude (empty $nin can slow down queries)
                if session_ids_seen:
                    query["session_id"] = {"$nin": list(session_ids_seen)}

                print(f"[PERF] Count query: {query}")

                # Always do the count to return accurate total
                try:
                    total_mongodb_sessions = mongodb_collection.count_documents(
                        query,
                        hint="user_id_last_updated",  # Force use of our index
                    )
                except:
                    # If hint fails, fall back to regular count
                    total_mongodb_sessions = mongodb_collection.count_documents(query)
            except Exception as e:
                print(f"Warning: Could not count MongoDB sessions: {e}")

        print(
            f"[PERF] Step 3 (count MongoDB): {(time.time() - step3_start) * 1000:.2f} ms - Total: {total_mongodb_sessions}"
        )

        # 4. Calculate total and determine how many MongoDB sessions to fetch
        total_count = len(all_sessions) + total_mongodb_sessions

        # Sort in-memory sessions by last_updated
        all_sessions.sort(key=lambda x: x.get("last_updated", x.get("created_at", "")), reverse=True)

        # Determine if we need MongoDB sessions for this page
        in_memory_count = len(all_sessions)
        need_mongodb_sessions = False
        mongodb_offset = 0
        mongodb_limit = 0

        if offset < in_memory_count:
            # Page starts within in-memory sessions
            paginated_sessions = all_sessions[offset : offset + limit]
            remaining_slots = limit - len(paginated_sessions)
            if remaining_slots > 0:
                # Need to fill remaining slots from MongoDB
                need_mongodb_sessions = True
                mongodb_offset = 0
                mongodb_limit = remaining_slots
        else:
            # Page is entirely from MongoDB
            need_mongodb_sessions = True
            mongodb_offset = offset - in_memory_count
            mongodb_limit = limit
            paginated_sessions = []

        # 5. Fetch only the needed MongoDB sessions with server-side sorting and pagination
        step5_start = time.time()
        if include_cloud and need_mongodb_sessions and mongodb_collection is not None:
            try:
                query = {}
                if user_id:
                    query["user_id"] = user_id
                # Only add $nin if there are sessions to exclude (empty $nin can slow down queries)
                if session_ids_seen:
                    query["session_id"] = {"$nin": list(session_ids_seen)}

                # Use MongoDB's server-side sort, skip, and limit (MUCH faster!)
                mongodb_sessions = list(
                    mongodb_collection.find(
                        query,
                        {
                            "session_id": 1,
                            "session_name": 1,
                            "user_id": 1,
                            "total_turns": 1,
                            "created_at": 1,
                            "last_updated": 1,
                            "language": 1,
                            "session_status": 1,
                            "first_query": 1,
                            "latest_query": 1,
                            "last_turn_started_at": 1,
                            "last_turn_finished_at": 1,
                            "is_shared": 1,
                            "shared_at": 1,
                        },
                    )
                    .sort("last_updated", -1)  # Sort by last_updated descending
                    .skip(mongodb_offset)
                    .limit(mongodb_limit)
                )

                for session in mongodb_sessions:
                    # Determine current_status from session_status for MongoDB sessions
                    session_status = session.get("session_status", "active")
                    if session_status == "error":
                        current_status = "error"
                    elif session_status == "cancelled":
                        current_status = "cancelled"
                    else:
                        # For MongoDB sessions, they're archived so completed
                        current_status = "completed"

                    session_metadata = {
                        "session_id": session.get("session_id"),
                        "session_name": session.get("session_name", ""),
                        "user_id": session.get("user_id"),
                        "total_turns": session.get("total_turns", 0),
                        "created_at": session.get("created_at"),
                        "last_updated": session.get("last_updated"),
                        "language": session.get("language", "en"),
                        "session_status": session_status,
                        "current_status": current_status,  # Rich status (completed, error, cancelled)
                        "first_query": session.get("first_query", ""),
                        "latest_query": session.get("latest_query", ""),
                        "last_turn_started_at": session.get("last_turn_started_at"),
                        "last_turn_finished_at": session.get("last_turn_finished_at"),
                        "is_shared": session.get("is_shared", False),
                        "shared_at": session.get("shared_at"),
                        "_storage_location": "mongodb",
                    }
                    paginated_sessions.append(session_metadata)
            except Exception as e:
                print(f"Warning: Could not fetch MongoDB multi-turn sessions: {e}")

        print(f"[PERF] Step 5 (fetch MongoDB): {(time.time() - step5_start) * 1000:.2f} ms")
        print(f"[PERF] TOTAL TIME: {(time.time() - start_time) * 1000:.2f} ms")

        return {"sessions": paginated_sessions, "total": total_count, "limit": limit, "offset": offset}

    async def get_multiturn_session_by_id(
        self, session_id: str, include_turns: bool = True
    ) -> Optional[Dict[str, Any]]:
        """Get a specific multi-turn session by ID from any storage location

        Args:
            session_id: The session ID to fetch
            include_turns: If False, excludes the 'turns' array to improve performance (default: True)
        """
        import os
        import json
        import time

        func_start = time.time()

        # 1. Check in-memory first (currently active)
        step_start = time.time()
        if session_id in self.queue_manager.multiturn_sessions:
            session = self.queue_manager.multiturn_sessions[session_id]
            result = {
                "session_id": session_id,
                "session_name": getattr(session, "session_name", ""),
                "created_at": session.created_at,
                "last_updated": session.last_updated,
                "total_turns": session.total_turns,
                "current_turn": session.current_turn,
                "language": session.language,
                "session_status": session.session_status,
                "first_query": session.first_query,
                "latest_query": session.latest_query,
                "user_id": getattr(session, "user_id", None),
                "last_turn_started_at": getattr(session, "last_turn_started_at", None),
                "last_turn_finished_at": getattr(session, "last_turn_finished_at", None),
                "is_shared": getattr(session, "is_shared", False),
                "shared_at": getattr(session, "shared_at", None),
                "_storage_location": "memory",
                "_session_object": session,  # Include the actual object for updates
            }

            # Extract turns if requested
            if include_turns and hasattr(session, "turns"):
                result["turns"] = []
                for turn in session.turns:
                    turn_dict = {
                        "turn_number": turn.turn_number,
                        "turn_type": turn.turn_type,
                        "query": turn.query,
                        "final_report": turn.final_report,
                        "timestamp": turn.timestamp,
                        "status": turn.status,
                        "files": turn.files if hasattr(turn, "files") else {},
                        "response_content": turn.response_content if hasattr(turn, "response_content") else None,
                    }
                    result["turns"].append(turn_dict)

                # DEBUG: Log file references from in-memory session
                print(f"[DEBUG LOAD FROM MEMORY] Session {session_id} has {len(result['turns'])} turns:")
                for t in result["turns"]:
                    turn_num = t.get("turn_number")
                    files = t.get("files", {}) or {}
                    tp_file = (
                        files.get("thinking_process", {}).get("filename", "NONE")
                        if isinstance(files.get("thinking_process"), dict)
                        else "NONE"
                    )
                    report_file = (
                        files.get("final_report", {}).get("filename", "NONE")
                        if isinstance(files.get("final_report"), dict)
                        else "NONE"
                    )
                    print(f"[DEBUG LOAD FROM MEMORY]   Turn {turn_num}: TP={tp_file}, Report={report_file}")

            return result
        print(
            f"[PERF get_multiturn_session_by_id] Step 1 (in-memory check): {(time.time() - step_start) * 1000:.2f} ms - NOT FOUND"
        )

        # 2. Check MongoDB (primary storage) - use cached connection
        step_start = time.time()
        try:
            get_conn_start = time.time()
            mongodb_collection = self._get_cached_mongodb_collection()
            print(
                f"[PERF get_multiturn_session_by_id] Step 2a (get MongoDB connection): {(time.time() - get_conn_start) * 1000:.2f} ms"
            )

            if mongodb_collection is not None:
                query_start = time.time()

                # Use projection to exclude large 'turns' array if not needed
                if not include_turns:
                    # Only include the fields we need (turns will be automatically excluded)
                    projection = {
                        "session_id": 1,
                        "session_name": 1,
                        "user_id": 1,
                        "total_turns": 1,
                        "current_turn": 1,
                        "created_at": 1,
                        "last_updated": 1,
                        "language": 1,
                        "session_status": 1,
                        "first_query": 1,
                        "latest_query": 1,
                        "is_shared": 1,
                        "shared_at": 1,
                        # Note: 'turns' is automatically excluded when not listed
                    }
                    session_data = mongodb_collection.find_one({"session_id": session_id}, projection)
                    print(
                        f"[PERF get_multiturn_session_by_id] Step 2b (MongoDB find_one query WITH PROJECTION): {(time.time() - query_start) * 1000:.2f} ms"
                    )
                else:
                    session_data = mongodb_collection.find_one({"session_id": session_id})
                    print(
                        f"[PERF get_multiturn_session_by_id] Step 2b (MongoDB find_one query FULL): {(time.time() - query_start) * 1000:.2f} ms"
                    )

                if session_data:
                    session_data["_storage_location"] = "mongodb"

                    # DEBUG: Log file references from MongoDB
                    if "turns" in session_data and isinstance(session_data["turns"], list):
                        print(f"[DEBUG LOAD FROM MONGODB] Session {session_id} has {len(session_data['turns'])} turns:")
                        for t in session_data["turns"]:
                            turn_num = t.get("turn_number")
                            files = t.get("files", {}) or {}
                            tp_file = (
                                files.get("thinking_process", {}).get("filename", "NONE")
                                if isinstance(files.get("thinking_process"), dict)
                                else "NONE"
                            )
                            report_file = (
                                files.get("final_report", {}).get("filename", "NONE")
                                if isinstance(files.get("final_report"), dict)
                                else "NONE"
                            )
                            print(f"[DEBUG LOAD FROM MONGODB]   Turn {turn_num}: TP={tp_file}, Report={report_file}")

                    print(
                        f"[PERF get_multiturn_session_by_id] Step 2 (MongoDB total): {(time.time() - step_start) * 1000:.2f} ms - FOUND"
                    )
                    print(
                        f"[PERF get_multiturn_session_by_id] TOTAL FUNCTION TIME: {(time.time() - func_start) * 1000:.2f} ms"
                    )
                    return session_data
                else:
                    print(
                        f"[PERF get_multiturn_session_by_id] Step 2 (MongoDB total): {(time.time() - step_start) * 1000:.2f} ms - NOT FOUND"
                    )
        except Exception as e:
            print(f"Error loading multiturn session from MongoDB: {e}")
        print(
            f"[PERF get_multiturn_session_by_id] Step 2 (MongoDB): {(time.time() - step_start) * 1000:.2f} ms - NOT FOUND"
        )

        # 3. Fallback to local storage (may be stale, but better than nothing)
        step_start = time.time()
        multiturn_file = os.path.join(self.queue_manager.multiturn_storage_dir, f"{session_id}.json")
        if os.path.exists(multiturn_file):
            try:
                with open(multiturn_file, "r", encoding="utf-8") as f:
                    session_data = json.load(f)
                    session_data["_storage_location"] = "local"
                    print(
                        f"[PERF get_multiturn_session_by_id] Step 3 (local storage fallback): {(time.time() - step_start) * 1000:.2f} ms - FOUND"
                    )
                    print(
                        f"[PERF get_multiturn_session_by_id] TOTAL FUNCTION TIME: {(time.time() - func_start) * 1000:.2f} ms"
                    )
                    return session_data
            except Exception as e:
                print(f"Error loading multiturn session from local storage: {e}")
        print(
            f"[PERF get_multiturn_session_by_id] Step 3 (local storage fallback): {(time.time() - step_start) * 1000:.2f} ms - NOT FOUND"
        )

        print(
            f"[PERF get_multiturn_session_by_id] TOTAL FUNCTION TIME: {(time.time() - func_start) * 1000:.2f} ms - SESSION NOT FOUND ANYWHERE"
        )
        return None

    async def update_multiturn_session(self, session_id: str, updates: Dict[str, Any], user_id: str = None) -> bool:
        """Update a multi-turn session in all storage locations (optimized with parallel updates)"""
        import asyncio
        import time

        start = time.time()

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

        # Define update tasks for parallel execution
        update_tasks = []

        # 1. Update in-memory if it exists there
        async def update_memory():
            start_mem = time.time()
            if storage_location == "memory":
                session_obj = session.get("_session_object")
                if session_obj:
                    for key, value in updates.items():
                        setattr(session_obj, key, value)
                    # Save to local storage (synchronous, but fast)
                    await asyncio.to_thread(self.queue_manager._save_multiturn_session, session_obj)
            print(f"  ⏱️  [UPDATE] Memory update: {(time.time() - start_mem) * 1000:.2f} ms")

        # 2. Update local file if it exists
        async def update_local_file():
            start_file = time.time()
            multiturn_file = os.path.join(self.queue_manager.multiturn_storage_dir, f"{session_id}.json")
            if os.path.exists(multiturn_file):
                try:
                    # Use asyncio.to_thread to run blocking I/O in thread pool
                    def _update_file():
                        with open(multiturn_file, "r", encoding="utf-8") as f:
                            session_data = json.load(f)
                        session_data.update(updates)
                        with open(multiturn_file, "w", encoding="utf-8") as f:
                            json.dump(session_data, f, indent=2, ensure_ascii=False)

                    await asyncio.to_thread(_update_file)
                except Exception as e:
                    print(f"Warning: Could not update local multiturn session file: {e}")
            print(f"  ⏱️  [UPDATE] File update: {(time.time() - start_file) * 1000:.2f} ms")

        # 3. Always update MongoDB (primary storage)
        async def update_mongodb():
            start_mongo = time.time()
            try:
                from s3_mongodb.func_mongodb import get_mongodb_collection

                # Use asyncio.to_thread for MongoDB operation
                def _update_mongo():
                    collection = get_mongodb_collection(
                        os.getenv("SESSION_DB_NAME", "dleader_agent"), "multiturn_sessions"
                    )
                    if collection is not None:
                        result = collection.update_one({"session_id": session_id}, {"$set": updates})
                        return result.modified_count > 0 or result.matched_count > 0
                    return False

                result = await asyncio.to_thread(_update_mongo)
                print(f"  ⏱️  [UPDATE] MongoDB update: {(time.time() - start_mongo) * 1000:.2f} ms")
                return result
            except Exception as e:
                print(f"Error updating multiturn session in MongoDB: {e}")
                return False

        # Execute all updates in parallel
        results = await asyncio.gather(update_memory(), update_local_file(), update_mongodb(), return_exceptions=True)

        # Check if MongoDB update succeeded (it's the last result)
        mongodb_result = results[2] if len(results) > 2 and not isinstance(results[2], Exception) else False

        total_time = (time.time() - start) * 1000
        print(f"  ⏱️  [UPDATE] Total parallel update: {total_time:.2f} ms")

        return mongodb_result if isinstance(mongodb_result, bool) else True


# Global instance to be used by FastAPI endpoints
unified_session_manager = None


def get_unified_session_manager(queue_manager):
    """Get or create unified session manager instance"""
    global unified_session_manager
    if unified_session_manager is None:
        unified_session_manager = UnifiedSessionManager(queue_manager)
    return unified_session_manager

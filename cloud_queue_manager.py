"""
Cloud-First Queue Manager for Distributed Instances
Synchronizes all session state to MongoDB in real-time
"""

import os
import json
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from s3_mongodb.func_mongodb import get_mongodb_collection, upsert_wrapper
from cloud_storage_manager import cloud_storage_manager
import logging

logger = logging.getLogger(__name__)

class CloudQueueManager:
    """
    Manages session state in cloud (MongoDB) for distributed instances
    All state changes are immediately synced to MongoDB
    """

    def __init__(self, instance_id: str = None):
        self.mongodb_uri = os.getenv("MONGODB_URI")
        self.database_name = os.getenv("SESSION_DB_NAME", "dleader_agent")
        self.active_sessions_collection = "active_sessions"
        self.queue_collection = "session_queue"

        # Instance identifier for distributed setup
        self.instance_id = instance_id or os.getenv("INSTANCE_ID", f"instance_{os.getpid()}")

        # Local cache for performance (still use in-memory for active processing)
        self.local_cache = {}

        # Heartbeat interval (seconds)
        self.heartbeat_interval = 30

        logger.info(f"CloudQueueManager initialized for instance: {self.instance_id}")

    async def create_session(self, session_data: Dict[str, Any]) -> str:
        """
        Create a new session in cloud storage
        Returns session_id
        """
        session_id = session_data.get("session_id")

        # Add cloud metadata
        cloud_session = {
            "_id": session_id,
            "session_id": session_id,
            "instance_id": self.instance_id,
            "status": "queued",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "heartbeat_at": datetime.now().isoformat(),
            **session_data
        }

        # Save to MongoDB immediately
        event = {
            "database_name": self.database_name,
            "collection_name": self.active_sessions_collection,
            "items": [cloud_session],
            "id_field": "_id"
        }

        result = upsert_wrapper(event)
        if result.get("statusCode") != 200:
            raise Exception(f"Failed to create session in MongoDB: {result}")

        # Cache locally
        self.local_cache[session_id] = cloud_session

        logger.info(f"Created session {session_id} in cloud")
        return session_id

    async def update_session_status(self, session_id: str, status: str, **kwargs) -> bool:
        """
        Update session status in cloud
        kwargs can include: progress, error, result, etc.
        """
        try:
            updates = {
                "status": status,
                "updated_at": datetime.now().isoformat(),
                "heartbeat_at": datetime.now().isoformat(),
                "instance_id": self.instance_id,
                **kwargs
            }

            # Update MongoDB
            collection = get_mongodb_collection(self.database_name, self.active_sessions_collection)
            if collection is None:
                return False

            collection.update_one(
                {"_id": session_id},
                {"$set": updates}
            )

            # Update local cache
            if session_id in self.local_cache:
                self.local_cache[session_id].update(updates)

            logger.debug(f"Updated session {session_id} status to {status}")
            return True

        except Exception as e:
            logger.error(f"Failed to update session {session_id}: {e}")
            return False

    async def add_progress_update(self, session_id: str, progress_data: Dict) -> bool:
        """
        Add a progress update to session (append to array)
        """
        try:
            progress_entry = {
                **progress_data,
                "timestamp": datetime.now().isoformat()
            }

            # Append to MongoDB array
            collection = get_mongodb_collection(self.database_name, self.active_sessions_collection)
            if collection is None:
                return False

            collection.update_one(
                {"_id": session_id},
                {
                    "$push": {"progress_updates": progress_entry},
                    "$set": {
                        "updated_at": datetime.now().isoformat(),
                        "heartbeat_at": datetime.now().isoformat()
                    }
                }
            )

            return True

        except Exception as e:
            logger.error(f"Failed to add progress update for {session_id}: {e}")
            return False

    async def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Get session from cloud (with local cache fallback)
        """
        # Check local cache first
        if session_id in self.local_cache:
            return self.local_cache[session_id]

        # Fetch from MongoDB
        try:
            collection = get_mongodb_collection(self.database_name, self.active_sessions_collection)
            if collection is None:
                return None

            session = collection.find_one({"_id": session_id})
            if session:
                # Cache locally
                self.local_cache[session_id] = session
                return session

            return None

        except Exception as e:
            logger.error(f"Failed to get session {session_id}: {e}")
            return None

    async def list_active_sessions(self, instance_id: str = None, status: str = None) -> List[Dict[str, Any]]:
        """
        List active sessions (optionally filtered by instance or status)
        """
        try:
            collection = get_mongodb_collection(self.database_name, self.active_sessions_collection)
            if collection is None:
                return []

            # Build query
            query = {}
            if instance_id:
                query["instance_id"] = instance_id
            if status:
                query["status"] = status

            # Get sessions
            sessions = list(collection.find(query).sort("created_at", -1))
            return sessions

        except Exception as e:
            logger.error(f"Failed to list active sessions: {e}")
            return []

    async def complete_session(self, session_id: str, result_data: Dict[str, Any]) -> bool:
        """
        Mark session as complete and move to permanent storage
        """
        try:
            # Update final status
            await self.update_session_status(
                session_id,
                status="completed",
                is_complete=True,
                completed_at=datetime.now().isoformat(),
                **result_data
            )

            # Get full session data
            session = await self.get_session(session_id)
            if not session:
                return False

            # Upload to permanent storage (MongoDB sessions collection + S3)
            await cloud_storage_manager.upload_session_to_cloud(session_id, session)

            # Remove from active_sessions collection after successful upload
            collection = get_mongodb_collection(self.database_name, self.active_sessions_collection)
            if collection:
                collection.delete_one({"_id": session_id})

            # Remove from local cache
            self.local_cache.pop(session_id, None)

            logger.info(f"Completed and archived session {session_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to complete session {session_id}: {e}")
            return False

    async def heartbeat(self, session_id: str) -> bool:
        """
        Update heartbeat for session (indicates instance is still alive)
        """
        try:
            collection = get_mongodb_collection(self.database_name, self.active_sessions_collection)
            if collection is None:
                return False

            collection.update_one(
                {"_id": session_id},
                {"$set": {"heartbeat_at": datetime.now().isoformat()}}
            )
            return True

        except Exception as e:
            logger.error(f"Failed to update heartbeat for {session_id}: {e}")
            return False

    async def cleanup_stale_sessions(self, timeout_minutes: int = 60):
        """
        Cleanup sessions with stale heartbeats (dead instances)
        Should be run periodically
        """
        try:
            collection = get_mongodb_collection(self.database_name, self.active_sessions_collection)
            if collection is None:
                return

            # Find sessions with heartbeat older than timeout
            cutoff_time = datetime.now() - timedelta(minutes=timeout_minutes)
            cutoff_iso = cutoff_time.isoformat()

            stale_sessions = collection.find({
                "heartbeat_at": {"$lt": cutoff_iso},
                "status": {"$in": ["processing", "queued"]}
            })

            for session in stale_sessions:
                session_id = session.get("session_id")
                logger.warning(f"Cleaning up stale session {session_id} from instance {session.get('instance_id')}")

                # Mark as failed due to timeout
                await self.update_session_status(
                    session_id,
                    status="error",
                    is_complete=True,
                    error="Session timeout - instance may have crashed",
                    completed_at=datetime.now().isoformat()
                )

                # Move to permanent storage
                await cloud_storage_manager.upload_session_to_cloud(session_id, session)

                # Remove from active_sessions
                collection.delete_one({"_id": session_id})

        except Exception as e:
            logger.error(f"Failed to cleanup stale sessions: {e}")

    async def claim_queued_session(self) -> Optional[Dict[str, Any]]:
        """
        Claim a queued session for processing (for distributed work stealing)
        Returns session data if claimed, None if no sessions available
        """
        try:
            collection = get_mongodb_collection(self.database_name, self.active_sessions_collection)
            if collection is None:
                return None

            # Find and update in one atomic operation
            session = collection.find_one_and_update(
                {"status": "queued"},
                {
                    "$set": {
                        "status": "processing",
                        "instance_id": self.instance_id,
                        "processing_started_at": datetime.now().isoformat(),
                        "heartbeat_at": datetime.now().isoformat()
                    }
                },
                sort=[("created_at", 1)],  # FIFO
                return_document=True
            )

            if session:
                session_id = session.get("session_id")
                logger.info(f"Claimed session {session_id} for processing")
                # Cache locally
                self.local_cache[session_id] = session
                return session

            return None

        except Exception as e:
            logger.error(f"Failed to claim queued session: {e}")
            return None


# Global instance
cloud_queue_manager = None

def get_cloud_queue_manager(instance_id: str = None):
    """Get or create cloud queue manager instance"""
    global cloud_queue_manager
    if cloud_queue_manager is None:
        cloud_queue_manager = CloudQueueManager(instance_id)
    return cloud_queue_manager

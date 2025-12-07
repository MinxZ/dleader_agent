"""
Users route handlers for dleader_agent API.
"""

import logging
import os
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

logger = logging.getLogger(__name__)

from api import queue_manager
from api.models import (
    ConversationTurn,
    Language,
    MultiTurnSession,
    RenameMultiSessionRequest,
    ShareSessionRequest,
    Template,
    TemplateListRequest,
    TemplateResponse,
)
from api.utils import (
    create_session_zip,
    generate_file_urls,
    get_template_retriever,
)
from cloud_storage_manager import cloud_storage_manager
from unified_session_manager import UnifiedSessionManager

router = APIRouter(tags=["users"])


@router.get("/user/{user_id}/name")
async def get_user_name(user_id: str):
    """
    Get username for a given user_id.
    Returns the user_id as the default name if no custom name is set.

    Args:
        user_id: The user identifier

    Returns:
        JSON with username (defaults to user_id if not set)
    """
    if not user_id or user_id.strip() == "":
        raise HTTPException(status_code=400, detail="user_id is required and cannot be empty")

    try:
        # Import MongoDB functions
        from s3_mongodb.func_mongodb import get_mongodb_collection

        # Get users collection
        users_collection = get_mongodb_collection(
            os.getenv("SESSION_DB_NAME", "dleader_agent"),
            "users"
        )

        if users_collection is None:
            # If MongoDB is not available, return user_id as default
            return {
                "user_id": user_id,
                "username": user_id,
                "source": "default"
            }

        # Find user in MongoDB
        user_doc = users_collection.find_one({"_id": user_id})

        if user_doc and "username" in user_doc:
            return {
                "user_id": user_id,
                "username": user_doc["username"],
                "source": "mongodb"
            }
        else:
            # No custom name set, return user_id as default
            return {
                "user_id": user_id,
                "username": user_id,
                "source": "default"
            }

    except Exception as e:
        logger.error(f"Error retrieving username for {user_id}: {e}")
        # On error, return user_id as fallback
        return {
            "user_id": user_id,
            "username": user_id,
            "source": "error_fallback"
        }



@router.put("/user/{user_id}/name")
async def update_user_name(user_id: str, request: Request):
    """
    Update username for a given user_id.

    Args:
        user_id: The user identifier
        request: Request body containing {"username": "new_name"}

    Returns:
        JSON with updated username
    """
    if not user_id or user_id.strip() == "":
        raise HTTPException(status_code=400, detail="user_id is required and cannot be empty")

    try:
        # Parse request body
        body = await request.json()
        new_username = body.get("username", "").strip()

        if not new_username:
            raise HTTPException(status_code=400, detail="username is required and cannot be empty")

        # Import MongoDB functions
        from s3_mongodb.func_mongodb import get_mongodb_collection

        # Get users collection
        users_collection = get_mongodb_collection(
            os.getenv("SESSION_DB_NAME", "dleader_agent"),
            "users"
        )

        if users_collection is None:
            raise HTTPException(status_code=503, detail="Database unavailable")

        # Upsert user document with new username
        result = users_collection.update_one(
            {"_id": user_id},
            {
                "$set": {
                    "username": new_username,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                },
                "$setOnInsert": {
                    "created_at": datetime.now(timezone.utc).isoformat()
                }
            },
            upsert=True
        )

        return {
            "user_id": user_id,
            "username": new_username,
            "updated": result.modified_count > 0,
            "created": result.upserted_id is not None,
            "message": "Username updated successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating username for {user_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Error updating username: {str(e)}")

# ============= TRASH SYSTEM ENDPOINTS =============
# Most trash management endpoints have been moved to trash_api.py
# Only hard-delete remains here as it's a direct operation

# Import and include the trash router





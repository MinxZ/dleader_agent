"""
Templates route handlers for dleader_agent API.
"""

from typing import List, Optional

import os
import sys
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

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

router = APIRouter(tags=["templates"])


@router.post("/upload-template")
async def upload_template(request: TemplateListRequest):
    """Upload workflow templates to MongoDB"""
    try:
        from s3_mongodb.func_mongodb import (get_mongodb_collection,
                                             upsert_wrapper)

        # Get MongoDB collection
        collection = get_mongodb_collection(
            os.getenv("SESSION_DB_NAME", "dleader_agent"),
            "workflow_templates"
        )

        if collection is None:
            raise HTTPException(status_code=503, detail="MongoDB connection not available")

        # Prepare templates for MongoDB
        templates_to_upload = []
        for template in request.templates:
            template_data = template.dict()
            # Use title as _id for easy upsert
            template_data["_id"] = template.title
            template_data["uploaded_at"] = datetime.now().isoformat()
            templates_to_upload.append(template_data)

        # Upsert templates to MongoDB
        event = {
            "database_name": os.getenv("SESSION_DB_NAME", "dleader_agent"),
            "collection_name": "workflow_templates",
            "items": templates_to_upload,
            "id_field": "_id"
        }

        result = upsert_wrapper(event)

        if result.get("statusCode") != 200:
            raise Exception(f"MongoDB upsert failed: {result}")

        # Also save to local as backup
        templates_dir = os.path.join(os.getcwd(), "templates")
        os.makedirs(templates_dir, exist_ok=True)
        templates_file = os.path.join(templates_dir, "workflow_templates.json")
        templates_data = {"templates": [template.dict() for template in request.templates]}
        with open(templates_file, 'w', encoding='utf-8') as f:
            json.dump(templates_data, f, ensure_ascii=False, indent=2)

        return TemplateResponse(
            success=True,
            message="Templates uploaded successfully to MongoDB",
            total_templates=len(request.templates)
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error uploading templates: {e}")
        raise HTTPException(status_code=500, detail=f"Error uploading templates: {str(e)}")



@router.get("/templates")
async def get_templates():
    """Get all workflow templates from MongoDB"""
    try:
        from s3_mongodb.func_mongodb import get_mongodb_collection

        # Try to get from MongoDB first
        collection = get_mongodb_collection(
            os.getenv("SESSION_DB_NAME", "dleader_agent"),
            "workflow_templates"
        )

        if collection is not None:
            templates = list(collection.find({}).sort("title", 1))
            # Remove MongoDB _id field from response
            for template in templates:
                if "_id" in template:
                    template.pop("_id", None)
                if "uploaded_at" in template:
                    template.pop("uploaded_at", None)

            return {
                "templates": templates,
                "total": len(templates),
                "source": "mongodb"
            }

        # Fallback to local file if MongoDB not available
        templates_file = os.path.join(os.getcwd(), "templates", "workflow_templates.json")
        if not os.path.exists(templates_file):
            return {"templates": [], "total": 0, "source": "none"}

        with open(templates_file, 'r', encoding='utf-8') as f:
            templates_data = json.load(f)

        return {
            "templates": templates_data.get("templates", []),
            "total": len(templates_data.get("templates", [])),
            "source": "local_backup"
        }

    except Exception as e:
        print(f"Error retrieving templates: {e}")
        raise HTTPException(status_code=500, detail=f"Error retrieving templates: {str(e)}")





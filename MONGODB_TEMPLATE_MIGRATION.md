# Template Storage Migration: Local Files → MongoDB

## Overview
This document describes the migration of workflow template storage from local files to MongoDB cloud storage to ensure data persistence in ECS deployments.

## Problem Statement

### Local Storage Issues on ECS
- ❌ **Ephemeral Containers**: ECS containers are stateless and can be terminated/restarted at any time
- ❌ **Data Loss**: Local files are lost when containers restart or redeploy
- ❌ **Isolation**: Each container instance has its own file system
- ❌ **Inconsistency**: Different containers may have different template versions
- ❌ **No Sharing**: Cannot share templates across multiple container instances

### Impact
When running on ECS, any templates uploaded via `/upload-template` would be lost on the next deployment or container restart, requiring manual re-upload.

## Solution: MongoDB Cloud Storage

### Architecture
```
┌─────────────────┐
│  React Client   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐      ┌──────────────────┐
│  ECS Container  │◄────►│  MongoDB Atlas   │
│  (FastAPI)      │      │  (Cloud Storage) │
└─────────────────┘      └──────────────────┘
         │                        │
         ▼                        │
┌─────────────────┐              │
│  Local Backup   │◄─────────────┘
│  (Fallback)     │
└─────────────────┘
```

### Benefits
✅ **Persistence**: Templates survive container restarts and redeployments
✅ **Consistency**: All ECS instances read from the same MongoDB collection
✅ **Scalability**: Supports auto-scaling with multiple containers
✅ **Reliability**: MongoDB Atlas provides automatic backups and replication
✅ **Performance**: Indexed queries on template title
✅ **Centralized**: Single source of truth for all templates

## Implementation Changes

### 1. Upload Template Endpoint

**Before** (Local Storage):
```python
@app.post("/upload-template")
async def upload_template(request: TemplateListRequest):
    # Save to local file only
    with open(templates_file, 'w') as f:
        json.dump(templates_data, f)
    return {"success": True}
```

**After** (MongoDB + Backup):
```python
@app.post("/upload-template")
async def upload_template(request: TemplateListRequest):
    # Save to MongoDB (primary)
    collection = get_mongodb_collection("dleader_agent", "workflow_templates")
    event = {
        "database_name": "dleader_agent",
        "collection_name": "workflow_templates",
        "items": templates_to_upload,
        "id_field": "_id"
    }
    result = upsert_wrapper(event)

    # Also save to local as backup
    with open(templates_file, 'w') as f:
        json.dump(templates_data, f)

    return {"success": True, "message": "Templates uploaded to MongoDB"}
```

### 2. Get Templates Endpoint

**Before** (Local Only):
```python
@app.get("/templates")
async def get_templates():
    # Read from local file
    with open(templates_file, 'r') as f:
        templates_data = json.load(f)
    return {"templates": templates_data}
```

**After** (MongoDB with Fallback):
```python
@app.get("/templates")
async def get_templates():
    # Try MongoDB first
    collection = get_mongodb_collection("dleader_agent", "workflow_templates")
    if collection:
        templates = list(collection.find({}).sort("title", 1))
        return {"templates": templates, "source": "mongodb"}

    # Fallback to local file if MongoDB unavailable
    if os.path.exists(templates_file):
        with open(templates_file, 'r') as f:
            templates_data = json.load(f)
        return {"templates": templates_data, "source": "local_backup"}

    return {"templates": [], "source": "none"}
```

## MongoDB Schema

### Collection: `workflow_templates`

```json
{
  "_id": "QSPR Workflow",           // Template title (unique)
  "title": "QSPR Workflow",
  "running_time": "~15 min",
  "tools": 13,
  "description": "Quantitative Structure-Property Relationship...",
  "prompt": "Optional detailed prompt...",
  "uploaded_at": "2025-10-12T10:00:00Z"
}
```

### Indexes
- Primary key: `_id` (template title) - automatic unique index
- Optional: Text index on `description` for future search functionality

## Deployment Workflow

### Initial Deployment
1. Deploy FastAPI server to ECS
2. Upload templates via POST `/upload-template`
3. Templates saved to MongoDB + local backup
4. All containers can now access templates from MongoDB

### Container Restart/Redeploy
1. New container starts up
2. GET `/templates` retrieves from MongoDB
3. No data loss, no manual intervention needed

### Auto-Scaling
1. ECS launches additional containers
2. All containers read from same MongoDB collection
3. Consistent template data across all instances

### Disaster Recovery
1. MongoDB unavailable temporarily
2. Containers fall back to local backup file
3. When MongoDB recovers, normal operation resumes

## Migration Steps

### For Existing Deployments

1. **Backup existing templates**:
   ```bash
   curl http://localhost:8001/templates > templates_backup.json
   ```

2. **Update FastAPI code** (already done in this commit)

3. **Deploy updated container** to ECS

4. **Re-upload templates** to populate MongoDB:
   ```bash
   curl -X POST http://server:8001/upload-template \
     -H "Content-Type: application/json" \
     -d @templates_backup.json
   ```

5. **Verify** templates are in MongoDB:
   ```bash
   curl http://server:8001/templates
   # Should return "source": "mongodb"
   ```

## Testing

### Test Script
Run `python test_template_upload.py` to verify:
1. Templates upload successfully to MongoDB
2. Templates retrieved from MongoDB (not local)
3. Source field indicates "mongodb"

### Manual Testing
```bash
# Upload templates
curl -X POST http://localhost:8001/upload-template \
  -H "Content-Type: application/json" \
  -d @templates/workflow_templates.json

# Verify storage location
curl http://localhost:8001/templates | jq '.source'
# Should output: "mongodb"
```

## Configuration

### Environment Variables
- `SESSION_DB_NAME`: MongoDB database name (default: "dleader_agent")
- MongoDB connection configured via existing s3_mongodb module

### Files Modified
1. `agent_fastapi_server_multiturn.py` (Lines 3282-3383)
   - POST `/upload-template` - MongoDB storage
   - GET `/templates` - MongoDB retrieval with fallback

2. `test_template_upload.py`
   - Updated to verify MongoDB storage

3. Documentation updated:
   - `COMPLETE_API_DOCUMENTATION.md`
   - `TEMPLATE_API_IMPLEMENTATION.md`

## Rollback Plan

If MongoDB storage causes issues:

1. **Immediate**: Templates still work from local backup
2. **Fallback**: GET endpoint automatically uses local file if MongoDB fails
3. **Revert**: Restore previous code version (local-only storage)

## Monitoring

Check template data source:
```bash
curl http://server:8001/templates | jq '.source'
```

Expected responses:
- `"mongodb"` ✅ - Normal operation
- `"local_backup"` ⚠️ - MongoDB unavailable (check connection)
- `"none"` ❌ - No templates found (need to upload)

## Best Practices

1. **Upload once**: After deployment, upload templates once to MongoDB
2. **Idempotent uploads**: Safe to re-upload (uses upsert, no duplicates)
3. **Monitor source**: Check that `source: "mongodb"` in production
4. **Backup locally**: Keep local backup in repo for disaster recovery
5. **Version control**: Track template changes in git

## Summary

✅ **Before**: Templates stored locally, lost on container restart
✅ **After**: Templates stored in MongoDB, persist forever
✅ **ECS-Ready**: Supports ephemeral containers and auto-scaling
✅ **Resilient**: Local backup for failover scenarios
✅ **Zero-Downtime**: Existing containers continue using local files until migration

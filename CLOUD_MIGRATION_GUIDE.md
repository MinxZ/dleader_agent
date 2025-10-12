# Cloud-First Architecture Migration Guide

## Overview

This guide explains how to migrate the dleader_agent system from local file storage to a fully cloud-based architecture that supports multiple distributed instances.

## Architecture Changes

### Before (Local-First)
- **Session State**: Stored in memory (`active_sessions` dict), persisted to local `session_storage/` folder
- **Files**: Uploaded to local `chat_sessions/` folder, zipped locally
- **Progress**: Tracked in memory, saved to local JSON files
- **Problem**: Cannot share state across multiple server instances

### After (Cloud-First)
- **Session State**: Stored in MongoDB `active_sessions` collection with real-time sync
- **Files**: Uploaded directly to S3, no local storage needed
- **Progress**: Streamed to MongoDB, accessible from any instance
- **Benefit**: Multiple instances can share work and state seamlessly

## Components

### 1. CloudQueueManager (`cloud_queue_manager.py`)
Manages distributed session state in MongoDB

**Key Features:**
- Real-time state synchronization to MongoDB
- Heartbeat mechanism for instance health monitoring
- Atomic session claiming for distributed work stealing
- Automatic cleanup of stale sessions from dead instances

**Usage:**
```python
from cloud_queue_manager import get_cloud_queue_manager

# Initialize with unique instance ID
cloud_queue = get_cloud_queue_manager(instance_id="server-1")

# Create session
session_id = await cloud_queue.create_session({
    "session_id": "abc123",
    "message": "User query",
    "user_id": "user123"
})

# Update status (syncs to MongoDB immediately)
await cloud_queue.update_session_status(session_id, "processing")

# Add progress updates
await cloud_queue.add_progress_update(session_id, {
    "type": "status",
    "message": "Processing step 1..."
})

# Complete session (moves to permanent storage)
await cloud_queue.complete_session(session_id, {
    "result": "Final output",
    "thinking_process": "...",
    "final_report": "..."
})
```

### 2. MongoDB Collections

#### `active_sessions` (Temporary)
Stores sessions currently being processed

**Schema:**
```json
{
  "_id": "session_id",
  "session_id": "abc123",
  "instance_id": "server-1",
  "status": "processing",  // queued, processing, completed, error, cancelled
  "user_id": "user123",
  "message": "User query",
  "created_at": "2025-10-02T10:00:00Z",
  "updated_at": "2025-10-02T10:05:00Z",
  "heartbeat_at": "2025-10-02T10:05:30Z",
  "progress_updates": [
    {"type": "status", "message": "...", "timestamp": "..."}
  ],
  "uploaded_files": ["file1.csv", "file2.png"]
}
```

#### `sessions` (Permanent)
Stores completed sessions with S3 file references

**Schema:**
```json
{
  "_id": "session_id",
  "session_id": "abc123",
  "user_id": "user123",
  "status": "completed",
  "created_at": "2025-10-02T10:00:00Z",
  "completed_at": "2025-10-02T10:10:00Z",
  "thinking_process": "Full thinking content...",
  "final_report": "Final report markdown...",
  "s3_files": {
    "report_md": {
      "filename": "report_abc123.md",
      "s3_key": "sessions/abc123/report_md/report_abc123.md",
      "file_size": 1024
    },
    "images": [
      {
        "filename": "plot1.png",
        "s3_key": "sessions/abc123/images/plot1.png",
        "file_size": 50000
      }
    ]
  }
}
```

## Integration Steps

### Step 1: Install Dependencies

Ensure these environment variables are set:
```bash
# MongoDB
MONGODB_URI=mongodb+srv://username:password@cluster.mongodb.net/
SESSION_DB_NAME=dleader_agent

# S3
AWS_ACCESS_KEY_ID_SELF=your_access_key
AWS_SECRET_ACCESS_KEY_SELF=your_secret_key
AWS_REGION_SELF=us-east-1
SESSION_STORAGE_BUCKET=dleader-agent-sessions

# Instance ID (unique per server)
INSTANCE_ID=server-1
```

### Step 2: Update QueueManager

Replace local storage operations with cloud operations:

```python
# OLD - Local storage
def _save_session_to_storage(self, user_request):
    session_file = os.path.join(self.sessions_storage_dir, f"{session_id}.json")
    with open(session_file, 'w') as f:
        json.dump(session_data, f)

# NEW - Cloud storage
async def _save_session_to_cloud(self, user_request):
    await cloud_queue_manager.update_session_status(
        user_request.session_id,
        user_request.status,
        result=user_request.result,
        error=user_request.error
    )
```

### Step 3: Update Progress Tracking

Stream progress to MongoDB instead of in-memory queue:

```python
# OLD - In-memory queue
user_request.progress_queue.put({"type": "status", "message": "Processing..."})

# NEW - Cloud sync
await cloud_queue_manager.add_progress_update(
    user_request.session_id,
    {"type": "status", "message": "Processing..."}
)
```

### Step 4: Update File Uploads

Upload files directly to S3 (already implemented):

```python
# Files are already being uploaded to S3 in the upload endpoint
s3_object_name = f"sessions/{session_id}/turn{turn_number}_{filename}"
cloud_storage_manager.s3_client.upload_file(
    local_path,
    cloud_storage_manager.bucket_name,
    s3_object_name
)
```

### Step 5: Update Endpoints

Endpoints should now ALWAYS use `unified_session_manager` (already updated):

```python
# All endpoints now use:
unified_manager = get_unified_session_manager(queue_manager)
session_data = await unified_manager.get_session_by_id(session_id)
```

## Distributed Instance Setup

### Single Instance (Current)
No changes needed. Works as before with cloud backup.

### Multiple Instances (New)

**Instance 1:**
```bash
INSTANCE_ID=server-1 python agent_fastapi_server_multiturn.py --port 8001
```

**Instance 2:**
```bash
INSTANCE_ID=server-2 python agent_fastapi_server_multiturn.py --port 8002
```

**Load Balancer:**
```nginx
upstream dleader_backend {
    server server-1:8001;
    server server-2:8002;
}

server {
    location / {
        proxy_pass http://dleader_backend;
        proxy_set_header Host $host;
    }
}
```

### Work Distribution

Two modes supported:

#### Mode 1: Sticky Sessions (Recommended)
- Load balancer routes user to same instance
- Session state synced to MongoDB for failover
- If instance dies, another can pick up from MongoDB

#### Mode 2: Work Stealing (Advanced)
- Any instance can claim queued work
- Enable with `claim_queued_session()` method
- Best for high-availability scenarios

```python
# In worker thread
async def process_queue():
    while True:
        # Try to claim work from shared queue
        session = await cloud_queue_manager.claim_queued_session()
        if session:
            await process_session(session)
        else:
            await asyncio.sleep(5)
```

## Monitoring & Maintenance

### Health Checks

Each instance should run periodic heartbeat:

```python
async def heartbeat_loop():
    while True:
        for session_id in active_sessions:
            await cloud_queue_manager.heartbeat(session_id)
        await asyncio.sleep(30)
```

### Cleanup Stale Sessions

Run cleanup task periodically:

```python
# In scheduler (every 10 minutes)
await cloud_queue_manager.cleanup_stale_sessions(timeout_minutes=60)
```

### Monitoring Queries

**Active sessions by instance:**
```python
sessions = await cloud_queue_manager.list_active_sessions(instance_id="server-1")
```

**Stuck sessions:**
```python
# Find sessions with old heartbeats
db.active_sessions.find({
    "heartbeat_at": {"$lt": ISODate("2025-10-02T09:00:00Z")},
    "status": "processing"
})
```

## Migration Checklist

- [ ] Environment variables configured (MongoDB URI, S3 credentials, INSTANCE_ID)
- [ ] MongoDB collections created (`active_sessions`, `sessions`, `multiturn_sessions`)
- [ ] S3 bucket created with proper permissions
- [ ] `cloud_queue_manager.py` integrated into `agent_fastapi_server_multiturn.py`
- [ ] Progress tracking updated to use MongoDB
- [ ] Session creation updated to create MongoDB record
- [ ] Session completion updated to move from active → permanent storage
- [ ] Heartbeat mechanism implemented
- [ ] Stale session cleanup scheduled
- [ ] Load balancer configured (if using multiple instances)
- [ ] Monitoring dashboard set up

## Rollback Plan

If issues occur, you can temporarily disable cloud sync:

```python
USE_CLOUD_STORAGE = os.getenv("USE_CLOUD_STORAGE", "true").lower() == "true"

if USE_CLOUD_STORAGE:
    await cloud_queue_manager.update_session_status(...)
else:
    # Fall back to local storage
    self._save_session_to_storage(...)
```

## Performance Considerations

### MongoDB Indexes

Create indexes for better query performance:

```javascript
// Active sessions
db.active_sessions.createIndex({"status": 1, "created_at": 1})
db.active_sessions.createIndex({"instance_id": 1})
db.active_sessions.createIndex({"heartbeat_at": 1})
db.active_sessions.createIndex({"user_id": 1})

// Permanent sessions
db.sessions.createIndex({"user_id": 1, "created_at": -1})
db.sessions.createIndex({"status": 1})
```

### Caching Strategy

- Keep active sessions in local cache for fast access
- Update MongoDB asynchronously (don't block main thread)
- Fetch from MongoDB only when local cache misses

### S3 Performance

- Use multipart upload for large files
- Enable S3 Transfer Acceleration for faster uploads
- Use CloudFront CDN for download URLs

## Testing

Test distributed setup locally with Docker Compose:

```yaml
version: '3.8'
services:
  server1:
    build: .
    environment:
      - INSTANCE_ID=server-1
      - MONGODB_URI=${MONGODB_URI}
    ports:
      - "8001:8001"

  server2:
    build: .
    environment:
      - INSTANCE_ID=server-2
      - MONGODB_URI=${MONGODB_URI}
    ports:
      - "8002:8001"

  nginx:
    image: nginx
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
    ports:
      - "80:80"
    depends_on:
      - server1
      - server2
```

## Conclusion

This migration enables:
- ✅ Horizontal scaling with multiple instances
- ✅ Automatic failover if instance crashes
- ✅ Shared session state across servers
- ✅ No local file dependencies
- ✅ Real-time progress tracking
- ✅ Cloud-native architecture

The system remains backward compatible - single instances work without any code changes.

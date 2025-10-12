# DLeader Agent FastAPI Project Documentation

## Project Overview

This is a FastAPI-based multi-turn chat and code execution system with cloud storage integration and comprehensive trash management.

## Quick Start for Developers

### 1. Start the FastAPI Server
```bash
# Default with auto-reload
python agent_fastapi_server_multiturn.py

# Production mode without reload
python agent_fastapi_server_multiturn.py --no-reload

# Custom host/port
python agent_fastapi_server_multiturn.py --host 0.0.0.0 --port 8001
```

### 2. Start the Gradio Interface
```bash
python agent_gradio_fastapi_multiturn.py
```
Access at: http://localhost:7860

### 3. Run Tests
```bash
# Run all tests
python run_trash_tests.py

# Run specific tests
python test_trash_fastapi.py
python test_trash_gradio.py
python test_trash_integration.py
```

## Key Files and Their Purpose

### Core Application Files
- **`agent_fastapi_server_multiturn.py`** (3024 lines)
  - Main FastAPI server with all API endpoints
  - Queue management system
  - Process pool for code execution
  - Trash system endpoints (lines 2603-2889)

- **`agent_gradio_fastapi_multiturn.py`** (1340+ lines)
  - Gradio web interface
  - Trash Management tab (lines 1102-1340)
  - Multi-turn chat interface
  - File upload/download handling

- **`unified_session_manager.py`**
  - Centralized session management
  - File operations and zip creation
  - Trash metadata handling
  - Multi-turn session support

- **`cloud_storage_manager.py`**
  - S3 integration for file storage
  - MongoDB integration for metadata
  - Batch deletion operations
  - Presigned URL generation

### Test Files
- **`test_trash_fastapi.py`** - Unit tests for FastAPI trash endpoints
- **`test_trash_gradio.py`** - Unit tests for Gradio interface
- **`test_trash_integration.py`** - Integration tests with live server
- **`run_trash_tests.py`** - Comprehensive test runner

### Documentation Files
- **`API_DOCUMENTATION.md`** - Complete API reference with examples
- **`CLAUDE_CODE_GUIDE.md`** - Instructions for Claude Code
- **`TRASH_SYSTEM_STATUS.md`** - Trash system implementation details
- **`PROJECT_DOCUMENTATION.md`** - This file

## Environment Configuration

Create a `.env` file:
```bash
# Server Settings
FASTAPI_HOST=0.0.0.0
FASTAPI_PORT=8001
GRADIO_PORT=7860

# Cloud Storage (Optional)
USE_CLOUD_STORAGE=true
AWS_ACCESS_KEY_ID=your_key
AWS_SECRET_ACCESS_KEY=your_secret
AWS_REGION=us-west-2
S3_BUCKET_NAME=your-bucket

# MongoDB (Optional)
MONGODB_URI=mongodb://localhost:27017
MONGODB_DB_NAME=agent_sessions

# File Limits
MAX_FILE_SIZE_MB=100
AUTO_DELETE_LARGE_FILES_MB=500
```

## API Endpoints Summary

### Core Endpoints
- `GET /health` - Server health check
- `POST /chat-queue` - Submit code/chat request
- `GET /status/{session_id}` - Check session status
- `POST /stop/{session_id}` - Stop running session
- `GET /results/{session_id}` - Get execution results
- `GET /snapshots/{session_id}` - Get intermediate snapshots
- `GET /download/{session_id}` - Download session files

### Multi-turn Endpoints
- `POST /continue-session` - Continue multi-turn chat
- `GET /multiturn-session/{session_id}` - Get multi-turn info
- `GET /turn-report/{session_id}/{turn_number}` - Get specific turn

### Trash System Endpoints
- `POST /trash/{session_id}` - Move to trash
- `GET /trash` - List trash sessions
- `POST /restore/{session_id}` - Restore from trash
- `DELETE /permanent-delete/{session_id}` - Permanently delete
- `POST /empty-trash` - Empty all trash

## Testing Guide

### Unit Test Coverage
```bash
# FastAPI Tests (6 tests)
- Move to trash
- Get trash sessions
- Restore from trash
- Permanent deletion
- Empty trash
- Security/access control

# Gradio Tests (6 tests)
- Refresh trash list
- Restore session
- Permanent delete
- Empty all trash
- Error handling
- UI interaction flow
```

### Integration Test Flow
1. Create test session
2. Move to trash
3. Verify in trash
4. Restore from trash (optional)
5. Permanently delete
6. Verify deletion

### Quick API Test Script
```python
import requests

BASE_URL = "http://localhost:8001"
USER_ID = "test_user"

# 1. Health check
r = requests.get(f"{BASE_URL}/health")
print("Health:", r.json())

# 2. Submit request
r = requests.post(f"{BASE_URL}/chat-queue",
    data={"message": "print('Hello')", "user_id": USER_ID, "language": "en"})
session_id = r.json()["session_id"]

# 3. Move to trash
r = requests.post(f"{BASE_URL}/trash/{session_id}?user_id={USER_ID}")

# 4. List trash
r = requests.get(f"{BASE_URL}/trash?user_id={USER_ID}")
print("Trash count:", r.json()["count"])

# 5. Delete permanently
r = requests.delete(f"{BASE_URL}/permanent-delete/{session_id}?user_id={USER_ID}&confirm=true")
```

## Common Development Tasks

### Adding a New API Endpoint
1. Add route in `agent_fastapi_server_multiturn.py`
2. Update `API_DOCUMENTATION.md`
3. Add unit test in appropriate test file
4. Update Gradio interface if needed

### Modifying Trash System
1. Core logic: `agent_fastapi_server_multiturn.py` (lines 2603-2889)
2. UI: `agent_gradio_fastapi_multiturn.py` (lines 1102-1340)
3. Session handling: `unified_session_manager.py`
4. Cloud deletion: `cloud_storage_manager.py`

### Debugging Tips
```bash
# Check server is running
curl http://localhost:8001/health

# View server logs
tail -f uvicorn.log

# Check specific endpoint
curl http://localhost:8001/openapi.json | jq '.paths | keys[]'

# Monitor file system
watch -n 1 'ls -la session_storage/ | tail -5'
```

## Troubleshooting

### Issue: Trash endpoints return 404
**Solution:** Server needs restart after code changes
```bash
# Server auto-reloads by default now
# If not, manually restart:
pkill -f agent_fastapi_server_multiturn
python agent_fastapi_server_multiturn.py
```

### Issue: Integration tests fail
**Solution:** Ensure server is running
```bash
# Start server first
python agent_fastapi_server_multiturn.py

# Then run tests
python test_trash_integration.py
```

### Issue: Permission denied errors
**Solution:** Check user_id consistency
```python
# All requests must use same user_id
user_id = "consistent_user_id"
```

## Performance Notes

- Sessions >500MB are auto-flagged for cleanup
- Queue processes requests sequentially
- Multi-turn sessions preserve context
- S3 uploads are async for performance
- MongoDB operations use connection pooling

## Security Considerations

- All endpoints validate user ownership
- Permanent deletion requires explicit confirmation
- No cross-user access allowed
- File uploads validated for size/type
- Sensitive data not logged

## Recent Changes (Latest)

1. **Auto-reload by default** - Server now auto-reloads on code changes
2. **Fixed trash endpoints** - Corrected indentation issue (were inside health_check)
3. **S3 URL display** - Shows presigned URLs directly in UI
4. **Multi-turn download fix** - Correctly handles `_turn_N` session IDs
5. **Comprehensive trash system** - Two-step deletion with full resource cleanup

## For Claude Code

When working on this project:
1. Always check if server is running: `curl http://localhost:8001/health`
2. Run tests after changes: `python run_trash_tests.py`
3. Server auto-reloads, but verify with health check
4. Use `API_DOCUMENTATION.md` for endpoint reference
5. Check `CLAUDE_CODE_GUIDE.md` for specific instructions

## Contact & Support

- Check `API_DOCUMENTATION.md` for detailed endpoint docs
- Review test files for usage examples
- Server issues: Check if running on correct port
- Trash system: See `TRASH_SYSTEM_STATUS.md`
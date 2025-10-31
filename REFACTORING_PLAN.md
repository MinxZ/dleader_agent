# FastAPI Server Refactoring Plan

## Current State
- **File**: `agent_fastapi_server_multiturn.py`
- **Size**: 4,701 lines
- **Issues**: Too large, hard to maintain, difficult to test individual components

## Proposed Structure

```
dleader_agent_demo/
├── agent_fastapi_server_multiturn.py  (MAIN - reduced to ~300 lines)
├── api/
│   ├── __init__.py
│   ├── models.py  ✅ CREATED (220 lines)
│   ├── managers.py  (QueueManager + SessionManager, ~1670 lines)
│   ├── utils.py  (utility functions, ~400 lines)
│   └── routes/
│       ├── __init__.py
│       ├── chat.py  (chat-queue, continue-session, ~300 lines)
│       ├── sessions.py  (status, results, snapshots, ~600 lines)
│       ├── multiturn.py  (multiturn-session, multiturn-sessions, ~200 lines)
│       ├── files.py  (download, download-file, download-urls, ~300 lines)
│       ├── sharing.py  (share-session, unshare-session, shared-sessions, ~200 lines)
│       ├── templates.py  (upload-template, get templates, ~150 lines)
│       ├── users.py  (user operations, ~100 lines)
│       └── admin.py  (hard-delete, health, ~100 lines)
```

## Files to Create

### 1. ✅ `api/models.py` - COMPLETED
**Lines**: ~220
**Content**:
- All Pydantic models (ChatRequest, ChatResponse, etc.)
- Data classes (UserRequest)
- Enums (Language)
- Helper functions (now_jst)

**Status**: ✅ Created

### 2. `api/managers.py`
**Lines**: ~1670
**Content**:
- `QueueManager` class (lines 246-1915)
- `SessionManager` class (lines 2250-2279)
- `StreamingCapture` class (lines 2280-2295)

**Key Functionality**:
- Queue management for multi-user requests
- Session lifecycle management
- Multi-turn session handling
- Template matching
- Cloud storage integration

### 3. `api/utils.py`
**Lines**: ~400
**Content**:
- `run_agent_in_process()` (lines 1916-2249)
- `scan_for_new_files()` (lines 2297-2321)
- `move_files_to_session()` (lines 2323-2349)
- `create_session_zip()` (lines 2351-2419)
- `create_agent()` (lines 2421-2431)
- `get_template_retriever()` (lines 2433-2444)
- `generate_file_urls()` (lines 2974-3104)

### 4. `api/routes/chat.py`
**Lines**: ~300
**Endpoints**:
- `POST /chat-queue` - Start new chat session
- `POST /continue-session` - Continue multi-turn conversation

### 5. `api/routes/sessions.py`
**Lines**: ~600
**Endpoints**:
- `GET /progress/{session_id}` - Get progress (deprecated)
- `GET /status/{session_id}` - Get session status
- `GET /results/{session_id}` - Get session results
- `POST /stop/{session_id}` - Stop running task
- `GET /snapshots/{session_id}` - Get thinking snapshots
- `GET /all-sessions` - Get all sessions

### 6. `api/routes/multiturn.py`
**Lines**: ~200
**Endpoints**:
- `GET /multiturn-session/{session_id}` - Get full conversation history
- `GET /multiturn-sessions` - Get all multiturn sessions (with pagination)
- `GET /turn-report/{session_id}/{turn_number}` - Get specific turn
- `GET /session-context/{session_id}` - Get session context
- `POST /rename-multisession` - Rename session

### 7. `api/routes/files.py`
**Lines**: ~300
**Endpoints**:
- `GET /download/{session_id}` - Download session ZIP
- `GET /download-file/{session_id}/{filename:path}` - Download individual file
- `GET /download-urls/{session_id}` - Get presigned URLs

### 8. `api/routes/sharing.py`
**Lines**: ~200
**Endpoints**:
- `POST /share-session` - Share a session publicly
- `POST /unshare-session` - Unshare a session
- `GET /shared-sessions` - Get all shared sessions

### 9. `api/routes/templates.py`
**Lines**: ~150
**Endpoints**:
- `POST /upload-template` - Upload workflow templates
- `GET /templates` - Get available templates

### 10. `api/routes/users.py`
**Lines**: ~100
**Endpoints**:
- `GET /user/{user_id}/name` - Get user name
- `PUT /user/{user_id}/name` - Update user name

### 11. `api/routes/admin.py`
**Lines**: ~100
**Endpoints**:
- `DELETE /hard-delete/{session_id}` - Hard delete session
- `GET /health` - Health check

### 12. `agent_fastapi_server_multiturn.py` - MAIN FILE (Refactored)
**Lines**: ~300 (reduced from 4701!)
**Content**:
```python
# Imports
from fastapi import FastAPI
from api.models import *
from api.managers import queue_manager, session_manager
from api.routes import (
    chat, sessions, multiturn, files,
    sharing, templates, users, admin
)

# App initialization
app = FastAPI(title="dleader_agent API")

# CORS middleware
app.add_middleware(CORSMiddleware, ...)

# Include routers
app.include_router(chat.router)
app.include_router(sessions.router)
app.include_router(multiturn.router)
app.include_router(files.router)
app.include_router(sharing.router)
app.include_router(templates.router)
app.include_router(users.router)
app.include_router(admin.router)

# Server startup
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)
```

## Benefits

### 1. **Maintainability**
- Each file has a single responsibility
- Easier to find and fix bugs
- Clearer code organization

### 2. **Testability**
- Can test individual modules in isolation
- Mock dependencies more easily
- Faster test execution

### 3. **Scalability**
- Add new endpoints without touching main file
- Team members can work on different routes simultaneously
- Easier to add features

### 4. **Performance**
- Faster IDE loading and navigation
- Better code completion
- Reduced memory usage

### 5. **Code Reuse**
- Utility functions can be imported anywhere
- Managers can be used in multiple routes
- Models are centralized

## Migration Steps

### Phase 1: Create Structure (Current)
1. ✅ Create `api/` directory
2. ✅ Create `api/__init__.py`
3. ✅ Create `api/models.py` with all Pydantic models
4. Create `api/managers.py` with QueueManager and SessionManager
5. Create `api/utils.py` with utility functions

### Phase 2: Split Routes
1. Create `api/routes/` directory
2. Create route files (chat, sessions, multiturn, etc.)
3. Move endpoint functions to appropriate route files
4. Update imports in each route file

### Phase 3: Refactor Main File
1. Update `agent_fastapi_server_multiturn.py` to import from modules
2. Replace code with imports
3. Set up FastAPI router includes
4. Test all endpoints

### Phase 4: Testing & Validation
1. Run existing tests
2. Test each endpoint manually
3. Verify no regressions
4. Update documentation

## Estimated Time
- **Phase 1**: 30 minutes
- **Phase 2**: 2 hours
- **Phase 3**: 1 hour
- **Phase 4**: 1 hour
- **Total**: ~4.5 hours

## Next Steps

Would you like me to:
1. ✅ Continue with Phase 1 (create managers.py and utils.py)?
2. Move to Phase 2 (split routes)?
3. Do the full refactoring in one go?
4. Create a migration script to automate the process?

## Notes
- All existing functionality will be preserved
- No breaking changes to the API
- Backward compatible
- Can be done incrementally without downtime

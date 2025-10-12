# Claude Code Guide for DLeader Agent Project

## Quick Reference for Claude Code

This guide helps Claude Code quickly understand and work with the DLeader Agent project.

## Project Context

**What is this?** A FastAPI server + Gradio UI for multi-turn chat, code execution, and file management with cloud storage integration.

**Key Features:**
- Queue-based async processing
- Multi-turn conversations with context
- S3/MongoDB cloud storage
- Two-step trash system (soft delete → permanent delete)
- Real-time execution snapshots

## Essential Commands

### 1. Check Server Status
```bash
# Is server running?
curl http://localhost:8001/health

# Check which process
ps aux | grep agent_fastapi_server_multiturn
```

### 2. Start/Restart Server
```bash
# Start with auto-reload (default)
python agent_fastapi_server_multiturn.py

# Kill and restart if needed
pkill -f agent_fastapi_server_multiturn
python agent_fastapi_server_multiturn.py
```

### 3. Run Tests
```bash
# Run all tests
python run_trash_tests.py

# Run specific test suite
python test_trash_fastapi.py
python test_trash_integration.py
```

### 4. Quick API Test
```bash
# Test trash endpoint
curl "http://localhost:8001/trash?user_id=test_user"

# Submit a test request
curl -X POST http://localhost:8001/chat-queue \
  -F "message=print('test')" \
  -F "user_id=test" \
  -F "language=en"
```

## File Structure Map

```
Key Files to Know:
├── agent_fastapi_server_multiturn.py    # Main server (3024 lines)
│   └── Trash endpoints: lines 2603-2889
├── agent_gradio_fastapi_multiturn.py    # Web UI (1340+ lines)
│   └── Trash UI: lines 1102-1340
├── unified_session_manager.py           # Session management
├── cloud_storage_manager.py             # S3/MongoDB operations
└── tests/
    ├── run_trash_tests.py               # Run this to test everything
    └── test_trash_integration.py        # Live server tests
```

## Common Tasks

### Task: Fix an API Endpoint

1. **Locate the endpoint:**
```bash
grep -n "@app.post\|@app.get\|@app.delete" agent_fastapi_server_multiturn.py
```

2. **Edit the endpoint:**
```python
# Endpoints are in agent_fastapi_server_multiturn.py
# Trash system: lines 2603-2889
# Multi-turn: lines 2400-2600
```

3. **Test the change:**
```bash
# Server auto-reloads, just test:
curl http://localhost:8001/your-endpoint
```

### Task: Add a New Endpoint

1. **Add to FastAPI server:**
```python
# In agent_fastapi_server_multiturn.py
@app.post("/new-endpoint")
async def new_endpoint(user_id: str):
    return {"status": "success"}
```

2. **Document it:**
```markdown
# Add to API_DOCUMENTATION.md
### New Endpoint
**Endpoint:** `POST /new-endpoint`
...
```

3. **Add tests:**
```python
# In test file
def test_new_endpoint():
    response = requests.post(...)
    assert response.status_code == 200
```

### Task: Fix Trash System Issues

**Key files:**
- Server endpoints: `agent_fastapi_server_multiturn.py:2603-2889`
- UI components: `agent_gradio_fastapi_multiturn.py:1102-1340`
- Session logic: `unified_session_manager.py`
- Cloud deletion: `cloud_storage_manager.py`

**Common issues:**
```python
# Issue: Session not found in trash
# Check: is_trashed flag in session data
cat session_storage/{session_id}.json | jq '.is_trashed'

# Issue: Restore fails
# Check: unified_manager.get_session_by_id() loading

# Issue: Delete fails
# Check: user_id matches, confirm=true parameter
```

### Task: Debug Multi-turn Sessions

```python
# Session IDs have _turn_N suffix
base_id = "abc-123"
turn_2_id = "abc-123_turn_2"

# Extract base ID:
if "_turn_" in session_id:
    base_id = session_id.split("_turn_")[0]
```

## Important Patterns

### 1. User Authentication Pattern
```python
# All endpoints validate user ownership
session_data = get_session_by_id(session_id)
if session_data.get("user_id") != user_id:
    raise HTTPException(403, "Access denied")
```

### 2. Two-Step Deletion Pattern
```python
# Step 1: Soft delete (move to trash)
session_data["is_trashed"] = True
session_data["trashed_at"] = datetime.now().isoformat()

# Step 2: Permanent delete (requires confirm=true)
if not confirm:
    raise HTTPException(400, "Confirmation required")
# Delete from local, S3, MongoDB
```

### 3. Auto-reload Pattern
```python
# Server auto-reloads on file changes
# No need to restart manually
# Just save file and test
```

## Quick Debugging

### Check Logs
```bash
# FastAPI logs
tail -f uvicorn.log

# Check errors
grep -i error *.log

# Python syntax check
python -m py_compile agent_fastapi_server_multiturn.py
```

### Common Fixes

1. **404 on endpoints:**
   - Check indentation (must be module level, not inside function)
   - Verify server reloaded: `curl http://localhost:8001/health`

2. **422 Validation Error:**
   - Check parameter names and types
   - Form data vs JSON body
   - Required vs optional parameters

3. **500 Server Error:**
   - Check imports
   - Verify file paths exist
   - Check MongoDB/S3 connectivity

## Testing Checklist

Before committing changes:

```bash
# 1. Syntax check
python -m py_compile agent_fastapi_server_multiturn.py

# 2. Server starts
python agent_fastapi_server_multiturn.py
# Ctrl+C after confirmed

# 3. Run tests
python run_trash_tests.py

# 4. Integration test
python test_trash_integration.py

# 5. Check specific endpoint
curl http://localhost:8001/your-endpoint
```

## Environment Variables

Key ones to know:
```bash
# In .env file
FASTAPI_PORT=8001
USE_CLOUD_STORAGE=true
S3_BUCKET_NAME=your-bucket
MONGODB_URI=mongodb://localhost:27017
AUTO_DELETE_LARGE_FILES_MB=500
```

## API Response Patterns

### Success Response
```json
{
  "status": "success",
  "data": {...},
  "message": "Operation completed"
}
```

### Error Response
```json
{
  "detail": "Error message here"
}
```

### Validation Error (422)
```json
{
  "detail": [
    {
      "loc": ["body", "field_name"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

## Recent Issues & Fixes

1. **Trash endpoints were 404** → Fixed indentation (were inside health_check function)
2. **Multi-turn downloads failed** → Fixed by extracting base session ID
3. **Wrong zip for turn 2** → Fixed by sorting zips by modification time
4. **S3 URLs not showing** → Changed to display presigned URLs directly

## Tips for Claude Code

1. **Always verify server is running before testing**
2. **Use auto-reload - it's enabled by default**
3. **Check API_DOCUMENTATION.md for endpoint details**
4. **Run tests after making changes**
5. **Look for existing patterns before implementing new features**
6. **User data isolation is critical - always check user_id**
7. **Permanent deletion needs explicit confirmation**

## Need More Info?

- **API Details:** See `API_DOCUMENTATION.md`
- **Project Setup:** See `PROJECT_DOCUMENTATION.md`
- **Trash System:** See `TRASH_SYSTEM_STATUS.md`
- **Test Examples:** Check `test_*.py` files

## Quick Test Script

Save as `quick_test.py`:
```python
#!/usr/bin/env python3
import requests

BASE = "http://localhost:8001"
USER = "test_user"

# Check health
r = requests.get(f"{BASE}/health")
print("✅ Server healthy" if r.status_code == 200 else "❌ Server down")

# Test trash
r = requests.get(f"{BASE}/trash?user_id={USER}")
print(f"✅ Trash works: {r.json()['count']} items" if r.status_code == 200 else "❌ Trash failed")

# Submit test
r = requests.post(f"{BASE}/chat-queue",
    data={"message": "print(1)", "user_id": USER, "language": "en"})
if r.status_code == 200:
    print(f"✅ Submit works: {r.json()['session_id']}")
else:
    print(f"❌ Submit failed: {r.status_code}")
```

Run with: `python quick_test.py`

---

**Remember:** This project auto-reloads on changes. Just save and test!
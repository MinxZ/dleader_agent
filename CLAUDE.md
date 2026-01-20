# CLAUDE.md

## Important: API Documentation

**When modifying any API endpoint**, always update the API documentation:
- **File:** `~/react_interface_demo/COMPLETE_API_DOCUMENTATION.md`
- Update response schemas, add new fields, document new endpoints
- Add entry to "Recent Updates" section at top of file

## Commands

```bash
# Environment
conda activate dleader_agent_e1
pip install dleader_agent --upgrade

# Run server
python agent_fastapi_server_multiturn.py --host 0.0.0.0 --port 8001

# Code quality
ruff check . && ruff format .
```

## API Endpoints (localhost:8001)

**Note:** All endpoints except `/health` require `user_id` parameter.

**Important:** When using curl with multiline messages, use single quotes for the message value.

### Start Chat
```bash
# Simple query
curl -X POST 'http://localhost:8001/chat-queue' \
  -F 'message=Your query' -F 'user_id=DLeader' -F 'language=en'

# With template matching disabled
curl -X POST 'http://localhost:8001/chat-queue' \
  -F 'message=Your query' -F 'user_id=DLeader' -F 'language=en' -F 'use_template=false'

# Note: For queries with special characters like newlines, encode them properly:
# - Use literal \n (backslash-n) in the message string
# - Avoid HTML tags like <br> in queries as they may interfere with processing
```

### Check Status
```bash
curl 'http://localhost:8001/status/{session_id}?user_id=DLeader'
```

### Get Snapshots (Thinking Process)
```bash
curl 'http://localhost:8001/snapshots/{session_id}?user_id=DLeader'
# With execute blocks: &include_execute=true
# Specific turn: &turn_number=2
```

### Get Results
```bash
curl 'http://localhost:8001/results/{session_id}?user_id=DLeader'
```

### Continue Session
```bash
curl -X POST 'http://localhost:8001/continue-session' \
  -F 'session_id={session_id}' -F 'message=Follow-up' -F 'user_id=DLeader'
```

### Stop Task
```bash
curl -X POST 'http://localhost:8001/stop/{session_id}?user_id=DLeader'
```

### Share Session
```bash
curl -X POST 'http://localhost:8001/share-session' \
  -H 'Content-Type: application/json' \
  -d '{"session_id": "{session_id}", "user_id": "DLeader"}'
```

### Other Endpoints
```bash
# Get shared sessions
curl 'http://localhost:8001/shared-sessions?user_id=DLeader&limit=10'

# Get session history
curl 'http://localhost:8001/multiturn-session/{session_id}?user_id=DLeader'

# Get all sessions
curl 'http://localhost:8001/multiturn-sessions?user_id=DLeader&limit=10'

# Get templates
curl 'http://localhost:8001/templates?user_id=DLeader'

# Upload templates
python test_template_upload.py

# Delete session
curl -X DELETE 'http://localhost:8001/hard-delete/{session_id}?user_id=DLeader&confirm=true'

# Download ZIP
curl 'http://localhost:8001/download/{session_id}?user_id=DLeader' -o session.zip
```

## Debugging Notes

**Important:** Local session files are automatically cleaned up. To check query content/results:
- Use `/snapshots/{session_id}` endpoint for thinking process
- Use `/results/{session_id}` endpoint for final results
- Do NOT rely on local file paths as they may be deleted

## Polling Flow
1. `POST /chat-queue` → get `session_id`
2. Poll `GET /status/{session_id}` every 5s
3. Poll `GET /snapshots/{session_id}` for thinking process
4. When `is_complete: true` → `GET /results/{session_id}`

## Multi-Turn Sessions
- Original: `abc123`
- Turns: `abc123_turn_2`, `abc123_turn_3`
- Use `turn_session_id` from `/continue-session` response for status polling

## Status Values
| Status | Description |
|--------|-------------|
| `queued` | Waiting in queue |
| `processing` | Currently running |
| `completed` | Finished successfully |
| `error` | Failed with error |
| `cancelled` | Stopped by user |
| `interrupted` | Server restart during processing |

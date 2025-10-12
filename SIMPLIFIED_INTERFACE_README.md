# Simplified Gradio Interface

## Overview

A streamlined version of the Gradio interface with:
- ✅ Basic multi-turn conversation functionality
- ✅ No user management required
- ✅ No delete or trash features
- ✅ Fixed user ID: `test_user_dleader`
- ✅ Simpler, cleaner interface

## Quick Start

### Start the Simplified Interface
```bash
python agent_gradio_simple.py
```

The interface will be available at: **http://localhost:7861**

### Start with Custom Settings
```bash
# Custom port
python agent_gradio_simple.py --server_port 7862

# Custom FastAPI server
python agent_gradio_simple.py --fastapi_url http://192.168.1.100:8001
```

## Features Comparison

| Feature | Original Interface | Simplified Interface |
|---------|-------------------|---------------------|
| **User Selection** | Dropdown with multiple users | Fixed: test_user_dleader |
| **Trash Management** | Full trash system with restore | ❌ Removed |
| **Delete Sessions** | Available | ❌ Removed |
| **User ID Display** | Visible and editable | Hidden (fixed) |
| **Multi-turn Chat** | ✅ Available | ✅ Available |
| **Status Check** | ✅ Available | ✅ Available |
| **Stop Tasks** | ✅ Available | ✅ Available |
| **File Uploads** | ✅ Available | ✅ Available |
| **Language Selection** | ✅ Available | ✅ Available |
| **Default Port** | 7860 | 7861 |

## What Was Removed

1. **User ID Selection**
   - No dropdown selector
   - All sessions use `test_user_dleader`
   - No user switching capability

2. **Trash Tab**
   - No trash management interface
   - No restore functionality
   - No permanent delete options

3. **Delete Functions**
   - No session deletion from UI
   - No "Move to Trash" buttons
   - No "Empty Trash" functionality

## How It Works

### Fixed User ID
All operations automatically use `test_user_dleader`:
```python
# Hardcoded in the interface
user_id_input = gr.State(value="test_user_dleader")
```

### API Calls
All API requests include the fixed user:
```python
# Example: Submit query
POST /chat-queue
  message: "your query"
  user_id: "test_user_dleader"  # Always this value
  language: "en"
```

## Interface Layout

```
┌─────────────────────────────────────┐
│     AI Agent - Simplified          │
│   Basic Multi-Turn Interface        │
│  🚀 All users: test_user_dleader    │
└─────────────────────────────────────┘

Tabs:
1. 💬 Multi-Turn Chat - Submit and continue conversations
2. 📊 Check Status - View session status and results
3. 🛑 Stop Session - Stop running tasks

Server Settings:
- FastAPI Server URL: [http://localhost:8001]
- Language: [English ▼]
```

## Use Cases

Perfect for:
- 🎓 Educational environments
- 🧪 Testing and demos
- 👤 Single-user deployments
- 🏢 Internal tools without user management
- 🚀 Quick prototyping

Not suitable for:
- Multi-user production environments
- Applications requiring user isolation
- Systems needing audit trails per user
- Deployments requiring session management

## Testing

Run the test suite:
```bash
python test_simple_interface.py
```

Expected output:
```
✅ Basic Functionality - PASSED
✅ User Management - PASSED
✅ Multi-Turn - PASSED
```

## Files

- **`agent_gradio_simple.py`** - The simplified interface (1100 lines)
- **`test_simple_interface.py`** - Test script
- **`SIMPLIFIED_INTERFACE_README.md`** - This documentation

## Deployment Notes

### Running Both Interfaces
You can run both the original and simplified interfaces simultaneously:

```bash
# Terminal 1: Original interface
python agent_gradio_fastapi_multiturn.py  # Port 7860

# Terminal 2: Simplified interface
python agent_gradio_simple.py  # Port 7861
```

### Security Considerations
- All users share the same user ID
- No user isolation or access control
- Sessions are visible to anyone with access
- Suitable only for trusted environments

### Performance
- Lighter weight than full interface
- Faster loading time
- Reduced memory usage
- Fewer API calls

## Reverting to Full Interface

If you need user management features back:
```bash
python agent_gradio_fastapi_multiturn.py
```

The full interface includes:
- User ID selection
- Trash management
- Session deletion
- Per-user isolation

## Troubleshooting

### Port Already in Use
```bash
# Change port
python agent_gradio_simple.py --server_port 7862
```

### Server Connection Issues
```bash
# Verify server is running
curl http://localhost:8001/health

# Use different server URL
python agent_gradio_simple.py --fastapi_url http://your-server:8001
```

### Sessions Not Appearing
All sessions are under `test_user_dleader`. Check:
```bash
curl "http://localhost:8001/all-sessions?user_id=test_user_dleader"
```

## Summary

The simplified interface provides a cleaner, easier-to-use experience for single-user or demonstration scenarios. It removes complexity while maintaining core functionality for code execution and multi-turn conversations.
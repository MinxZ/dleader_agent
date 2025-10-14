# Sharing Status in Session Lists

## Overview
This document describes how to identify shared vs. unshared sessions in the multi-turn session list API responses.

## Problem
The user asked: "How do we know if a session is shared or unshared when getting all sessions?"

## Solution
The multi-turn session list now includes complete sharing metadata for each session.

## API Endpoint

### GET /multiturn-sessions

**Purpose**: Get all multi-turn sessions with sharing status

**Query Parameters**:
- `user_id` (optional): Filter sessions by user

**Response Format**:
```json
{
  "sessions": [
    {
      "session_id": "abc123",
      "session_name": "QSPR Analysis Project",
      "user_id": "test_user_dleader",
      "total_turns": 3,
      "created_at": "2024-01-01T10:00:00Z",
      "last_updated": "2024-01-01T12:00:00Z",
      "language": "en",
      "session_status": "completed",
      "first_query": "Analyze this dataset...",
      "latest_query": "Generate final report...",

      // Sharing Status Fields
      "is_shared": true,
      "shared_at": "2024-01-01T13:00:00Z",
      "share_tags": ["genomics", "QSPR"],
      "share_title": "QSPR Workflow Example",
      "share_description": "Demonstrates QSPR analysis",
      "share_visibility": "community"
    }
  ]
}
```

## Sharing Status Fields

### Core Field: `is_shared`
**Type**: `boolean`
**Purpose**: Primary indicator of sharing status
**Values**:
- `true` - Session is publicly shared
- `false` - Session is private

### Additional Sharing Fields

1. **`shared_at`**
   - **Type**: `string` (ISO timestamp) or `null`
   - **Purpose**: When the session was shared
   - **Example**: `"2024-01-01T13:00:00Z"`

2. **`share_tags`**
   - **Type**: `array` of strings
   - **Purpose**: Categorization tags for discovery
   - **Example**: `["genomics", "QSPR", "drug-discovery"]`

3. **`share_title`**
   - **Type**: `string` or `null`
   - **Purpose**: Public-facing title (may differ from session_name)
   - **Example**: `"QSPR Workflow Example"`

4. **`share_description`**
   - **Type**: `string` or `null`
   - **Purpose**: Public description of what the session demonstrates
   - **Example**: `"Demonstrates QSPR analysis on chemical compounds"`

5. **`share_visibility`**
   - **Type**: `string`
   - **Purpose**: Visibility level
   - **Values**:
     - `"private"` - Not shared (default)
     - `"public"` - Publicly accessible
     - `"community"` - Shared with community

## Usage Examples

### Check if Session is Shared
```javascript
const isShared = session.is_shared;

if (isShared) {
  console.log(`Session "${session.session_name}" is shared publicly`);
  console.log(`Shared on: ${session.shared_at}`);
  console.log(`Tags: ${session.share_tags.join(', ')}`);
} else {
  console.log(`Session "${session.session_name}" is private`);
}
```

### Display Share Status Icon
```javascript
function getShareIcon(session) {
  if (!session.is_shared) {
    return '🔒'; // Private
  }

  switch (session.share_visibility) {
    case 'community':
      return '👥'; // Community shared
    case 'public':
      return '🌍'; // Public
    default:
      return '🔓'; // Shared (generic)
  }
}
```

### Filter Shared Sessions
```javascript
const sharedSessions = sessions.filter(s => s.is_shared === true);
const privateSessions = sessions.filter(s => s.is_shared === false);
```

### Group by Sharing Status
```javascript
const sessionsByStatus = {
  shared: sessions.filter(s => s.is_shared),
  private: sessions.filter(s => !s.is_shared)
};
```

## Implementation Details

### Backend Changes

1. **unified_session_manager.py** (Lines 388-393)
   - Added sharing metadata to local session response
   - Fields: `is_shared`, `shared_at`, `share_tags`, `share_title`, `share_description`, `share_visibility`

2. **cloud_storage_manager.py** (Lines 663-668)
   - Updated MongoDB upload to include sharing metadata
   - Ensures cloud storage preserves sharing status

3. **MultiTurnSession Model** (agent_fastapi_server_multiturn.py:126-132)
   - Model already had sharing fields defined
   - Now properly exposed in API responses

### Data Flow

```
┌─────────────────────────┐
│  MultiTurnSession       │
│  (In-Memory Model)      │
│  - is_shared: true      │
│  - share_tags: [...]    │
└───────────┬─────────────┘
            │
            ├─→ Local Storage (JSON)
            │   multiturn_sessions/abc123.json
            │
            ├─→ MongoDB Upload
            │   Collection: multiturn_sessions
            │   Document includes sharing fields
            │
            └─→ API Response
                GET /multiturn-sessions
                Returns sharing fields
```

### Storage Locations

1. **Local Storage**: `multiturn_sessions/{session_id}.json`
   - Contains full MultiTurnSession data including sharing fields

2. **MongoDB**: `dleader_agent.multiturn_sessions` collection
   - Document includes all sharing metadata
   - Persists across ECS container restarts

## Use Cases

### 1. Session List UI
Show sharing status badge/icon next to each session:
```
📊 QSPR Analysis Project         👥 Community
🧬 Gene Expression Study         🔒 Private
💊 Drug Discovery Workflow       🌍 Public
```

### 2. Share/Unshare Toggle
```javascript
async function toggleShare(sessionId, currentlyShared) {
  if (currentlyShared) {
    await fetch(`/unshare-session`, {
      method: 'POST',
      body: JSON.stringify({ session_id: sessionId, user_id })
    });
  } else {
    await fetch(`/share-session`, {
      method: 'POST',
      body: JSON.stringify({
        session_id: sessionId,
        user_id,
        title: "My Analysis",
        tags: ["genomics"]
      })
    });
  }

  // Refresh session list
  const updated = await fetch(`/multiturn-sessions?user_id=${userId}`);
}
```

### 3. Filter/Sort by Sharing Status
```javascript
// Show only shared sessions
<button onClick={() => setFilter('shared')}>
  Shared ({sessions.filter(s => s.is_shared).length})
</button>

// Show only private sessions
<button onClick={() => setFilter('private')}>
  Private ({sessions.filter(s => !s.is_shared).length})
</button>
```

### 4. Share Analytics
```javascript
const shareStats = {
  total: sessions.length,
  shared: sessions.filter(s => s.is_shared).length,
  private: sessions.filter(s => !s.is_shared).length,
  communityShared: sessions.filter(s => s.share_visibility === 'community').length
};
```

## Default Values

When a session is **not shared**, the fields have these default values:
```json
{
  "is_shared": false,
  "shared_at": null,
  "share_tags": [],
  "share_title": null,
  "share_description": null,
  "share_visibility": "private"
}
```

## Migration Notes

### For Existing Sessions
- Old sessions without sharing fields will default to:
  - `is_shared: false`
  - All other fields: `null` or empty arrays
- No data migration needed
- Fields populated when session is first shared

### Backward Compatibility
- All sharing fields use safe defaults via `getattr()`
- Existing code that doesn't check sharing status continues to work
- New code can safely check `is_shared` field

## Testing

### Verify Sharing Status in Response
```bash
# Get all sessions
curl "http://localhost:8001/multiturn-sessions?user_id=test_user_dleader" | jq '.sessions[] | {session_id, is_shared, share_visibility}'

# Expected output:
# {
#   "session_id": "abc123",
#   "is_shared": true,
#   "share_visibility": "community"
# }
# {
#   "session_id": "def456",
#   "is_shared": false,
#   "share_visibility": "private"
# }
```

### Test Sharing Workflow
```bash
# 1. Get initial status
curl "http://localhost:8001/multiturn-sessions?user_id=test_user" | jq '.sessions[0].is_shared'
# Output: false

# 2. Share the session
curl -X POST "http://localhost:8001/share-session" \
  -H "Content-Type: application/json" \
  -d '{"session_id": "abc123", "user_id": "test_user", "tags": ["test"]}'

# 3. Verify shared status
curl "http://localhost:8001/multiturn-sessions?user_id=test_user" | jq '.sessions[0].is_shared'
# Output: true
```

## Summary

✅ **Question**: How do we know if a session is shared?
✅ **Answer**: Check the `is_shared` field in the session object

**Quick Reference**:
```javascript
// Check if shared
if (session.is_shared === true) {
  // Session is shared
}

// Get sharing details
const {
  shared_at,        // When shared
  share_tags,       // Tags for discovery
  share_title,      // Public title
  share_visibility  // private/public/community
} = session;
```

All multi-turn sessions now include complete sharing metadata in the response, making it easy to display sharing status in the UI and filter/sort sessions accordingly.

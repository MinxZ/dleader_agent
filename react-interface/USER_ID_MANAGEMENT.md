# User ID Management in React Interface

## Overview
The React interface uses a persistent user ID system to maintain session history across browser refreshes and visits.

## How It Works

### 1. User ID Generation
```javascript
const [userId] = useState(() => {
  const storedUserId = localStorage.getItem('dleader_user_id');
  if (storedUserId) {
    return storedUserId;  // Use existing ID
  }
  const newUserId = `user_${uuidv4()}`;
  localStorage.setItem('dleader_user_id', newUserId);  // Store for future use
  return newUserId;
});
```

### 2. User ID Format
- Pattern: `user_{uuid}`
- Example: `user_a1b2c3d4-e5f6-7890-abcd-ef1234567890`
- Stored in browser's localStorage
- Persists across browser sessions

### 3. Session Ownership
- All sessions are tied to the user ID
- Only sessions belonging to the current user ID are displayed in the sidebar
- Users cannot access sessions from other user IDs

## User Interface Features

### Display User ID
- Shows abbreviated user ID in the sidebar header
- Format: "User ID: user_a1b2c3d4..."
- Provides visual confirmation of current user identity

### Reset User ID
- "Reset" button in sidebar header
- Confirmation dialog to prevent accidental resets
- Clears localStorage and reloads the page
- Generates a new user ID
- Previous sessions become inaccessible

## Session History Management

### Loading Sessions
```javascript
const loadSessions = async () => {
  const allSessions = await apiClient.current.getAllSessions(userId);
  setSessions(allSessions.reverse());
};
```
- Called on app initialization
- Fetches all sessions for the current user ID
- Displays in reverse chronological order (newest first)

### Session Persistence
- Sessions are stored on the server with user ID association
- Persist across browser refreshes
- Available from any browser with the same user ID

## API Integration

All API calls include the user ID:

```javascript
// Start new session
apiClient.submitRequest(message, 'en', userId, files);

// Continue session
apiClient.continueSession(sessionId, message, 'en', userId, files);

// Get status
apiClient.getStatus(sessionId, userId);

// Get session history
apiClient.getSessionHistory(sessionId, userId);
```

## Privacy & Security

### Isolation
- Each user ID has completely isolated sessions
- No cross-user data access
- Server validates user ownership on every request

### Local Storage
- User ID stored in browser's localStorage
- Clearing browser data will reset the user ID
- Different browsers will have different user IDs

### Session Protection
- Server returns 403 Forbidden if user tries to access another user's session
- All endpoints validate user ownership

## Use Cases

### Single User Mode
- Default behavior
- One persistent user ID per browser
- All sessions accessible across visits

### Multi-User Mode (Same Device)
- Use "Reset" button to switch users
- Each user gets their own session history
- No data sharing between users

### Testing/Development
- Reset user ID to start fresh
- Useful for testing clean state
- Can simulate multiple users

## Troubleshooting

### Lost Session History
**Problem:** Sessions disappeared after browser update/clear
**Solution:** User ID was reset. Previous sessions still exist on server but are inaccessible with new ID.

### Sessions Not Loading
**Problem:** Sidebar shows no sessions despite previous activity
**Solution:** Check if user ID matches. May have been reset accidentally.

### Access Denied Errors
**Problem:** Getting 403 errors when accessing sessions
**Solution:** User ID doesn't match session owner. Ensure consistent user ID.

## Best Practices

1. **Don't Share User IDs**: Each user should have their unique ID
2. **Backup Important Sessions**: Download session ZIPs for important analyses
3. **Clear Sessions Periodically**: Delete old sessions to keep sidebar clean
4. **Document User ID**: For important work, note your user ID for reference

## Technical Details

### localStorage Key
- Key: `dleader_user_id`
- Value: User ID string
- Persistence: Until manually cleared or reset

### Session ID Format for Multi-turn
- First turn: `session_abc123`
- Second turn: `session_abc123_turn_2`
- Third turn: `session_abc123_turn_3`
- Each turn tracked separately but linked to main session

### Cleanup
To completely reset:
1. Click "Reset" button in UI, or
2. Run in browser console: `localStorage.removeItem('dleader_user_id')`
3. Refresh the page
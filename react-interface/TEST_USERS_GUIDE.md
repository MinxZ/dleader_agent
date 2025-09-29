# Test Users Guide

## Overview
The React interface provides a user selector with predefined test users for easier testing and development, similar to the Gradio interface.

## Default User
- **`test_user_dleader`** - Default test user (same as Gradio simple interface)
- Automatically set on first load
- Consistent with backend testing expectations

## Predefined Test Users

### Available Users:
1. **Test User (Default)** - `test_user_dleader`
   - Primary test user for development
   - Has sample session data pre-configured
   - Used in automated tests

2. **DLeader Test** - `dleader_test`
   - Alternative test account
   - For testing multi-user scenarios

3. **Alice** - `user_alice`
   - Sample user for demos
   - Clean session history

4. **Bob** - `user_bob`
   - Sample user for demos
   - Clean session history

5. **Custom User ID**
   - Enter any custom user ID
   - Useful for specific testing scenarios

6. **Generate New Random User**
   - Creates a new UUID-based user
   - Format: `user_{uuid}`
   - For testing fresh user experiences

## How to Use

### Switching Users:
1. Click "Switch User ▼" button in sidebar
2. Select from dropdown list
3. Sessions automatically reload for new user
4. Current user shown as "User: [id]"

### User Persistence:
- Selected user saved in localStorage
- Persists across browser refreshes
- Each user has isolated session history

### Custom User ID:
1. Select "Custom User ID" from dropdown
2. Enter desired user ID in prompt
3. Can be any string (e.g., email, username)

## Features

### User Selector UI:
```
┌─────────────────────────┐
│ User: test_user_dleader │
│ [Switch User ▼]         │
├─────────────────────────┤
│ Select User:            │
│ • Test User (Default) ✓ │
│ • DLeader Test          │
│ • Alice                 │
│ • Bob                   │
│ • Custom User ID        │
│ ─────────────────────── │
│ [Generate New Random]   │
└─────────────────────────┘
```

### Visual Indicators:
- ✓ checkmark shows current active user
- Blue highlight on active selection
- Dropdown closes on selection or outside click

## Testing Scenarios

### Single User Testing:
- Use default `test_user_dleader`
- All sessions persist across refreshes
- Ideal for feature development

### Multi-User Testing:
- Switch between Alice and Bob
- Test session isolation
- Verify user-specific data

### Fresh User Testing:
- Generate new random user
- Start with clean slate
- Test first-time user experience

### Integration Testing:
- Use `test_user_dleader` to match backend
- Consistent with Gradio interface
- Works with existing test data

## API Integration

All API calls include the selected user ID:

```javascript
// Sessions loaded for current user
GET /all-sessions?user_id=test_user_dleader

// New chat started with user ID
POST /chat-queue
{
  user_id: "test_user_dleader",
  message: "...",
  ...
}

// Status checks include user ID
GET /status/{session_id}?user_id=test_user_dleader
```

## Session Management

### Per-User Sessions:
- Each user has separate session history
- No cross-user data access
- Sessions persist on server

### Switching Impact:
- Clears current chat
- Reloads session list
- Resets UI state
- Maintains localStorage

## Best Practices

### For Development:
1. Use `test_user_dleader` as primary test user
2. Create test data under this user
3. Switch to other users for multi-user testing

### For Demos:
1. Use Alice/Bob for clean demos
2. Generate new user for fresh start
3. Custom ID for specific scenarios

### For Testing:
1. `test_user_dleader` for integration tests
2. Random users for isolation testing
3. Multiple users for concurrency testing

## Troubleshooting

### Sessions Not Showing:
- Verify correct user selected
- Check localStorage has user_id
- Ensure server has sessions for user

### Can't Switch Users:
- Clear browser cache if stuck
- Check console for errors
- Manually clear localStorage

### User ID Reset:
```javascript
// In browser console:
localStorage.removeItem('dleader_user_id');
location.reload();
```

## Comparison with Gradio

| Feature | React Interface | Gradio Simple |
|---------|----------------|---------------|
| Default User | `test_user_dleader` | `test_user_dleader` |
| User Selection | Dropdown with presets | Fixed user |
| Custom Users | Yes, via selector | No |
| Random Users | Yes, generator button | No |
| Multi-User | Yes, easy switching | No |
| Persistence | localStorage | Session only |

## Security Notes

- User IDs are not authenticated
- Anyone can access any user ID
- For testing/development only
- Production should implement proper auth

## Quick Start

1. App loads with `test_user_dleader`
2. Start chatting immediately
3. Switch users via dropdown as needed
4. Sessions persist per user
5. Use same user across sessions
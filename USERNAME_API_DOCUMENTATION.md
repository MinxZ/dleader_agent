# Username Management API Documentation

## Overview

The username management system provides isolated user profile management through MongoDB. Each user can have a custom username associated with their `user_id`. By default, the username equals the `user_id` until explicitly changed.

## Database Schema

**Collection:** `users` (in the database specified by `SESSION_DB_NAME` environment variable, defaults to `dleader_agent`)

**Document Structure:**
```json
{
  "_id": "user_id_string",
  "username": "Display Name",
  "created_at": "2025-10-20T12:00:00.000000+00:00",
  "updated_at": "2025-10-20T12:30:00.000000+00:00"
}
```

## API Endpoints

### 1. Get Username

**Endpoint:** `GET /user/{user_id}/name`

**Description:** Retrieve the username for a given user_id. Returns the user_id as the default name if no custom name has been set.

**Parameters:**
- `user_id` (path parameter, required): The user identifier

**Response Format:**
```json
{
  "user_id": "test_user_123",
  "username": "Alice Johnson",
  "source": "mongodb"
}
```

**Response Fields:**
- `user_id`: The requested user identifier
- `username`: The display name (defaults to user_id if not set)
- `source`: Where the username came from
  - `"mongodb"`: Retrieved from database (custom name set)
  - `"default"`: No custom name set, using user_id as default
  - `"error_fallback"`: Error occurred, falling back to user_id

**Example Request:**
```bash
curl http://localhost:8001/user/test_user_123/name
```

**Example Response (custom name set):**
```json
{
  "user_id": "test_user_123",
  "username": "Alice Johnson",
  "source": "mongodb"
}
```

**Example Response (default name):**
```json
{
  "user_id": "new_user_456",
  "username": "new_user_456",
  "source": "default"
}
```

**Error Responses:**
- `400 Bad Request`: user_id is empty or missing
  ```json
  {
    "detail": "user_id is required and cannot be empty"
  }
  ```

---

### 2. Update Username

**Endpoint:** `PUT /user/{user_id}/name`

**Description:** Update or set the username for a given user_id. Creates a new user document if one doesn't exist (upsert operation).

**Parameters:**
- `user_id` (path parameter, required): The user identifier

**Request Body:**
```json
{
  "username": "New Display Name"
}
```

**Request Body Fields:**
- `username` (required): The new username to set (cannot be empty)

**Response Format:**
```json
{
  "user_id": "test_user_123",
  "username": "Alice Johnson",
  "updated": true,
  "created": false,
  "message": "Username updated successfully"
}
```

**Response Fields:**
- `user_id`: The user identifier
- `username`: The newly set username
- `updated`: `true` if an existing document was modified, `false` if newly created
- `created`: `true` if a new user document was created, `false` if updating existing
- `message`: Success message

**Example Request:**
```bash
curl -X PUT http://localhost:8001/user/test_user_123/name \
  -H "Content-Type: application/json" \
  -d '{"username": "Dr. Alice Johnson"}'
```

**Example Response (updating existing):**
```json
{
  "user_id": "test_user_123",
  "username": "Dr. Alice Johnson",
  "updated": true,
  "created": false,
  "message": "Username updated successfully"
}
```

**Example Response (creating new):**
```json
{
  "user_id": "brand_new_user",
  "username": "John Doe",
  "updated": false,
  "created": true,
  "message": "Username updated successfully"
}
```

**Error Responses:**
- `400 Bad Request`: user_id is empty or missing
  ```json
  {
    "detail": "user_id is required and cannot be empty"
  }
  ```
- `400 Bad Request`: username is empty or missing
  ```json
  {
    "detail": "username is required and cannot be empty"
  }
  ```
- `503 Service Unavailable`: MongoDB connection failed
  ```json
  {
    "detail": "Database unavailable"
  }
  ```
- `500 Internal Server Error`: Other errors
  ```json
  {
    "detail": "Error updating username: <error details>"
  }
  ```

---

## Usage Examples

### Python with requests

```python
import requests

BASE_URL = "http://localhost:8001"
user_id = "alice_123"

# Get username
response = requests.get(f"{BASE_URL}/user/{user_id}/name")
print(response.json())
# Output: {"user_id": "alice_123", "username": "alice_123", "source": "default"}

# Set username
response = requests.put(
    f"{BASE_URL}/user/{user_id}/name",
    json={"username": "Alice Cooper"}
)
print(response.json())
# Output: {"user_id": "alice_123", "username": "Alice Cooper", "updated": false, "created": true, ...}

# Get updated username
response = requests.get(f"{BASE_URL}/user/{user_id}/name")
print(response.json())
# Output: {"user_id": "alice_123", "username": "Alice Cooper", "source": "mongodb"}
```

### JavaScript with fetch

```javascript
const BASE_URL = "http://localhost:8001";
const userId = "alice_123";

// Get username
const getUsername = async (userId) => {
  const response = await fetch(`${BASE_URL}/user/${userId}/name`);
  const data = await response.json();
  console.log(data);
  return data;
};

// Update username
const updateUsername = async (userId, newName) => {
  const response = await fetch(`${BASE_URL}/user/${userId}/name`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ username: newName })
  });
  const data = await response.json();
  console.log(data);
  return data;
};

// Usage
await getUsername(userId);
await updateUsername(userId, "Alice Cooper");
await getUsername(userId);
```

### cURL

```bash
# Get username
curl http://localhost:8001/user/alice_123/name

# Update username
curl -X PUT http://localhost:8001/user/alice_123/name \
  -H "Content-Type: application/json" \
  -d '{"username": "Alice Cooper"}'

# Get updated username
curl http://localhost:8001/user/alice_123/name
```

---

## Implementation Details

### Isolation
The username system is completely isolated from other user data:
- Stored in a separate `users` collection
- No dependencies on session data
- Independent of authentication/authorization (for now)

### Default Behavior
- When a user_id has no custom username set, the GET endpoint returns the user_id itself as the username
- This ensures every user always has a displayable name
- No need to explicitly "initialize" users before use

### Data Persistence
- Usernames are stored in MongoDB with timestamps
- Uses upsert operations to create or update user documents atomically
- `created_at` is set only on first creation
- `updated_at` is updated on every change

### Error Handling
- Graceful degradation: If MongoDB is unavailable on GET, returns user_id as default
- Validation: Empty user_ids and usernames are rejected with 400 errors
- Logging: All errors are logged for debugging

### MongoDB Indexes
For better performance with large user bases, consider adding an index:

```javascript
db.users.createIndex({ "username": 1 })  // For searching by username (optional)
db.users.createIndex({ "updated_at": -1 })  // For sorting by last update
```

---

## Testing

A test script is provided at `test_username_api.py`:

```bash
# Make sure the server is running first
python agent_fastapi_server_multiturn.py

# In another terminal, run the test
python test_username_api.py
```

The test script will:
1. Get the default username (should be user_id)
2. Update the username to a custom value
3. Verify the update was persisted
4. Update again and verify
5. Test with multiple users

---

## Environment Variables

- `SESSION_DB_NAME`: MongoDB database name (default: `"dleader_agent"`)
- `MONGODB_URI`: MongoDB connection string (required)

Example `.env`:
```
MONGODB_URI=mongodb://localhost:27017/
SESSION_DB_NAME=dleader_agent
```

---

## Security Considerations

**Current Implementation:**
- No authentication/authorization required
- Any client can read/write any user's name
- Suitable for trusted environments or development

**Future Enhancements:**
- Add API key authentication
- Implement user ownership verification
- Add rate limiting to prevent abuse
- Validate username format (length, allowed characters)

---

## Roadmap

Potential future features:
- User profiles with additional fields (email, avatar, bio)
- Username uniqueness constraints
- Username history/audit trail
- Bulk user operations
- Search users by username
- User metadata (join date, last seen, etc.)

# Username API - Quick Start Guide

## TL;DR

Two simple endpoints to manage usernames:

```bash
# Get username (defaults to user_id if not set)
GET /user/{user_id}/name

# Set username
PUT /user/{user_id}/name
Body: {"username": "Your Name"}
```

---

## Quick Examples

### 1. Get Username

```bash
curl http://localhost:8001/user/alice_123/name
```

**Response:**
```json
{
  "user_id": "alice_123",
  "username": "alice_123",
  "source": "default"
}
```

### 2. Set Username

```bash
curl -X PUT http://localhost:8001/user/alice_123/name \
  -H "Content-Type: application/json" \
  -d '{"username": "Alice Cooper"}'
```

**Response:**
```json
{
  "user_id": "alice_123",
  "username": "Alice Cooper",
  "updated": false,
  "created": true,
  "message": "Username updated successfully"
}
```

### 3. Get Updated Username

```bash
curl http://localhost:8001/user/alice_123/name
```

**Response:**
```json
{
  "user_id": "alice_123",
  "username": "Alice Cooper",
  "source": "mongodb"
}
```

---

## Python Example

```python
import requests

BASE_URL = "http://localhost:8001"

# Get username
resp = requests.get(f"{BASE_URL}/user/alice_123/name")
print(resp.json()["username"])  # "alice_123" (default)

# Set username
requests.put(
    f"{BASE_URL}/user/alice_123/name",
    json={"username": "Alice Cooper"}
)

# Get updated username
resp = requests.get(f"{BASE_URL}/user/alice_123/name")
print(resp.json()["username"])  # "Alice Cooper"
```

---

## JavaScript Example

```javascript
const BASE_URL = "http://localhost:8001";

// Get username
let resp = await fetch(`${BASE_URL}/user/alice_123/name`);
let data = await resp.json();
console.log(data.username);  // "alice_123" (default)

// Set username
await fetch(`${BASE_URL}/user/alice_123/name`, {
  method: 'PUT',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ username: "Alice Cooper" })
});

// Get updated username
resp = await fetch(`${BASE_URL}/user/alice_123/name`);
data = await resp.json();
console.log(data.username);  // "Alice Cooper"
```

---

## Testing

```bash
# Start server
python agent_fastapi_server_multiturn.py

# Run tests (in another terminal)
python test_username_api.py
```

---

## Key Points

✅ **Isolated System**: Username is independent of sessions/auth
✅ **Default Behavior**: Username defaults to user_id if not set
✅ **Automatic Creation**: PUT creates user if doesn't exist (upsert)
✅ **MongoDB Storage**: Stored in `users` collection
✅ **Error Handling**: Gracefully handles DB unavailability

---

## MongoDB Storage

**Database:** `dleader_agent` (or value of `SESSION_DB_NAME` env var)
**Collection:** `users`

**Document Structure:**
```json
{
  "_id": "user_id",
  "username": "Display Name",
  "created_at": "2025-10-20T12:00:00+00:00",
  "updated_at": "2025-10-20T12:30:00+00:00"
}
```

---

## Common Use Cases

### Use Case 1: Display user-friendly names in UI
```python
user_id = get_current_user_id()
response = requests.get(f"{BASE_URL}/user/{user_id}/name")
display_name = response.json()["username"]
print(f"Welcome, {display_name}!")
```

### Use Case 2: User profile settings
```python
def update_profile(user_id, new_name):
    response = requests.put(
        f"{BASE_URL}/user/{user_id}/name",
        json={"username": new_name}
    )
    return response.json()["username"]
```

### Use Case 3: List users with names
```python
user_ids = ["alice_123", "bob_456", "charlie_789"]
for uid in user_ids:
    resp = requests.get(f"{BASE_URL}/user/{uid}/name")
    name = resp.json()["username"]
    print(f"{uid}: {name}")
```

---

For complete documentation, see `USERNAME_API_DOCUMENTATION.md`

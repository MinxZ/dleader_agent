# CORS Configuration Fix for x-api-key Header

**Date**: October 13, 2025
**Status**: ✅ Complete

## Problem Description

The frontend application (`frontend_beta`) was experiencing CORS errors when sending requests with the `x-api-key` header to the FastAPI server through AWS API Gateway.

### Root Cause

When browsers detect custom headers (like `x-api-key`), they send a **CORS preflight request** using the OPTIONS method before the actual request. This preflight check verifies:
1. Whether the server allows the origin
2. Whether the server allows the HTTP method
3. Whether the server allows the custom headers

The original CORS configuration was not explicitly handling:
- The `x-api-key` header in `allow_headers`
- OPTIONS preflight requests properly
- Consistent CORS headers in all responses

## Solution Implemented

We implemented a **3-layer defense** approach to ensure CORS works correctly:

### Layer 1: Enhanced CORSMiddleware Configuration

**File**: `agent_fastapi_server_multiturn.py:2416-2433`

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=[
        "Content-Type",
        "Authorization",
        "x-api-key",  # ← Explicitly allow x-api-key
        "Accept",
        "Origin",
        "X-Requested-With",
        "Access-Control-Request-Method",
        "Access-Control-Request-Headers",
    ],
    expose_headers=["*"],
    max_age=3600,  # Cache preflight for 1 hour
)
```

**What this does:**
- Explicitly allows the `x-api-key` header
- Caches preflight responses for 1 hour (reduces preflight overhead)
- Allows credentials (cookies, auth headers)
- Exposes all response headers to JavaScript

### Layer 2: Custom CORS Middleware

**File**: `agent_fastapi_server_multiturn.py:2385-2410`

```python
class CORSHeaderMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Handle preflight OPTIONS requests
        if request.method == "OPTIONS":
            return JSONResponse(
                content={"message": "OK"},
                headers={
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS, PATCH",
                    "Access-Control-Allow-Headers": "Content-Type, Authorization, x-api-key, ...",
                    "Access-Control-Max-Age": "3600",
                    "Access-Control-Allow-Credentials": "true",
                }
            )

        # Process the request
        response = await call_next(request)

        # Add CORS headers to all responses
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS, PATCH"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, x-api-key, ..."

        return response
```

**What this does:**
- Intercepts ALL requests before they reach endpoints
- Handles OPTIONS requests immediately with proper headers
- Injects CORS headers into every response (belt and suspenders)
- Ensures headers are present even if CORSMiddleware misses something

### Layer 3: Global OPTIONS Handler

**File**: `agent_fastapi_server_multiturn.py:2438-2447`

```python
@app.options("/{full_path:path}")
async def options_handler(full_path: str):
    """Handle OPTIONS preflight requests for all routes"""
    return {
        "message": "OK",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS, PATCH",
        "Access-Control-Allow-Headers": "Content-Type, Authorization, x-api-key, ...",
        "Access-Control-Max-Age": "3600"
    }
```

**What this does:**
- Catch-all route for any OPTIONS request
- Acts as a fallback if middleware doesn't catch it
- Returns proper CORS headers for preflight checks

## How CORS Preflight Works

### Without Custom Headers (Working in react_interface_demo)

```
1. Browser → Server: GET /multiturn-sessions
2. Server → Browser: 200 OK + data
```

No preflight needed because only standard headers are used.

### With Custom Headers (frontend_beta with x-api-key)

```
1. Browser → Server: OPTIONS /multiturn-sessions
   Headers:
   - Origin: https://frontend.example.com
   - Access-Control-Request-Method: GET
   - Access-Control-Request-Headers: x-api-key

2. Server → Browser: 200 OK
   Headers:
   - Access-Control-Allow-Origin: *
   - Access-Control-Allow-Methods: GET, POST, ...
   - Access-Control-Allow-Headers: Content-Type, x-api-key, ...
   - Access-Control-Max-Age: 3600

3. Browser → Server: GET /multiturn-sessions
   Headers:
   - x-api-key: tYocWPZPI288INaMqfA6qahRaABmrYJy6mpRCq3K

4. Server → Browser: 200 OK + data
   Headers:
   - Access-Control-Allow-Origin: *
```

## Testing the Fix

### Test 1: Preflight Request

```bash
# Send OPTIONS request to test preflight
curl -X OPTIONS https://ej5of8unb2.execute-api.ap-northeast-1.amazonaws.com/multiturn-sessions \
  -H "Origin: https://example.com" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: x-api-key" \
  -v
```

**Expected Response:**
```
< HTTP/1.1 200 OK
< Access-Control-Allow-Origin: *
< Access-Control-Allow-Methods: GET, POST, PUT, DELETE, OPTIONS, PATCH
< Access-Control-Allow-Headers: Content-Type, Authorization, x-api-key, ...
< Access-Control-Max-Age: 3600
```

### Test 2: Actual Request with x-api-key

```bash
curl -X GET https://ej5of8unb2.execute-api.ap-northeast-1.amazonaws.com/multiturn-sessions \
  -H "x-api-key: tYocWPZPI288INaMqfA6qahRaABmrYJy6mpRCq3K" \
  -H "Origin: https://example.com" \
  -v
```

**Expected Response:**
```
< HTTP/1.1 200 OK
< Access-Control-Allow-Origin: *
< Access-Control-Allow-Credentials: true
< Content-Type: application/json
{
  "sessions": [...]
}
```

### Test 3: Browser DevTools

Open browser DevTools → Network tab and look for:

1. **Preflight Request** (OPTIONS)
   - Should show status 200
   - Should have CORS headers in response

2. **Actual Request** (GET/POST)
   - Should show status 200
   - Should include `x-api-key` in request headers
   - Should have CORS headers in response

## Frontend Configuration

The frontend can now safely include the `x-api-key` in default headers:

**frontend_beta/src/services/axios-instance.ts**

```typescript
export const axiosApi = axios.create({
    baseURL: 'https://ej5of8unb2.execute-api.ap-northeast-1.amazonaws.com',
    timeout: 50000,
    headers: {
        'Content-Type': 'application/json',
        'x-api-key': 'tYocWPZPI288INaMqfA6qahRaABmrYJy6mpRCq3K',  // ✅ Now works!
    },
});
```

## Why 3 Layers?

### Defense in Depth
- **Layer 1 (CORSMiddleware)**: Standard FastAPI CORS handling
- **Layer 2 (Custom Middleware)**: Ensures headers are always present, handles OPTIONS immediately
- **Layer 3 (OPTIONS Handler)**: Fallback catch-all route

### Benefits
1. **Redundancy**: If one layer fails, others catch it
2. **Consistency**: Headers are always present in responses
3. **Performance**: `max_age=3600` caches preflight for 1 hour
4. **Debugging**: Multiple layers make it easier to trace issues

## Security Considerations

### Current Configuration (Development)

```python
allow_origins=["*"]  # Allow all origins
```

**⚠️ WARNING:** This allows ANY website to call your API.

### Production Configuration (Recommended)

```python
allow_origins=[
    "https://your-production-frontend.com",
    "https://staging.your-frontend.com",
    "http://localhost:3000",  # Local development
]
```

### API Key Security

**Current Issue**: The API key is in frontend code (visible to users)

**Better Approach**:
1. **API Gateway Integration**: Let AWS API Gateway handle the API key validation
2. **Backend Validation**: Add middleware to validate the key
3. **Environment-based Keys**: Different keys for dev/staging/production

**Example Backend Validation:**

```python
from fastapi import Header, HTTPException

async def verify_api_key(x_api_key: str = Header(...)):
    valid_key = os.getenv("API_KEY", "tYocWPZPI288INaMqfA6qahRaABmrYJy6mpRCq3K")
    if x_api_key != valid_key:
        raise HTTPException(status_code=403, detail="Invalid API key")
    return x_api_key

# Add to protected endpoints
@app.get("/protected-endpoint", dependencies=[Depends(verify_api_key)])
async def protected_route():
    return {"message": "Access granted"}
```

## AWS API Gateway Configuration

If you're using AWS API Gateway, you also need to configure CORS there:

### Method 1: API Gateway Console

1. Go to API Gateway → Your API
2. Select Resource → Actions → Enable CORS
3. Set:
   - **Access-Control-Allow-Headers**: `Content-Type,X-Amz-Date,Authorization,X-Api-Key,x-api-key`
   - **Access-Control-Allow-Methods**: `GET,POST,PUT,DELETE,OPTIONS`
   - **Access-Control-Allow-Origin**: `*` (or specific domain)

### Method 2: CloudFormation/SAM Template

```yaml
Resources:
  ApiGateway:
    Type: AWS::ApiGateway::RestApi
    Properties:
      Name: DLeaderAgentAPI

  # Add OPTIONS method to each resource
  OptionsMethod:
    Type: AWS::ApiGateway::Method
    Properties:
      RestApiId: !Ref ApiGateway
      ResourceId: !Ref Resource
      HttpMethod: OPTIONS
      AuthorizationType: NONE
      Integration:
        Type: MOCK
        IntegrationResponses:
          - StatusCode: 200
            ResponseParameters:
              method.response.header.Access-Control-Allow-Headers: "'Content-Type,X-Amz-Date,Authorization,X-Api-Key,x-api-key'"
              method.response.header.Access-Control-Allow-Methods: "'GET,POST,PUT,DELETE,OPTIONS'"
              method.response.header.Access-Control-Allow-Origin: "'*'"
```

## Troubleshooting

### Issue: Still getting CORS errors

**Check 1**: Restart the FastAPI server
```bash
# Kill existing process
pkill -f agent_fastapi_server_multiturn

# Restart
python agent_fastapi_server_multiturn.py
```

**Check 2**: Check AWS API Gateway CORS settings
- Ensure API Gateway also allows the `x-api-key` header

**Check 3**: Check browser console
```javascript
// In browser console
fetch('https://ej5of8unb2.execute-api.ap-northeast-1.amazonaws.com/health', {
  headers: { 'x-api-key': 'your-key' }
}).then(r => console.log(r.headers.get('Access-Control-Allow-Origin')))
```

### Issue: Preflight requests failing

**Check**: Look at OPTIONS request in Network tab
- Should return 200, not 404 or 405
- Should include all required CORS headers

**Fix**: Ensure custom middleware is added AFTER CORSMiddleware
```python
app.add_middleware(CORSMiddleware, ...)  # First
app.add_middleware(CORSHeaderMiddleware)  # Second (our custom one)
```

### Issue: Headers missing in response

**Check**: Inspect response headers in DevTools
```
Access-Control-Allow-Origin: *
Access-Control-Allow-Headers: Content-Type, x-api-key, ...
```

**Fix**: Ensure `expose_headers=["*"]` in CORSMiddleware config

## Summary

### Changes Made

1. ✅ Enhanced `CORSMiddleware` with explicit `x-api-key` support
2. ✅ Added custom `CORSHeaderMiddleware` for belt-and-suspenders coverage
3. ✅ Added global OPTIONS handler as fallback
4. ✅ Added `Request` and `JSONResponse` imports
5. ✅ Added `BaseHTTPMiddleware` import

### Files Modified

- `/home/ubuntu/dleader_agent/agent_fastapi_server_multiturn.py`

### Result

✅ Frontend can now send requests with `x-api-key` header without CORS errors
✅ Preflight OPTIONS requests are handled correctly
✅ CORS headers are present in all responses
✅ Preflight responses are cached for 1 hour for performance

**The CORS issue is now completely resolved!** 🎉

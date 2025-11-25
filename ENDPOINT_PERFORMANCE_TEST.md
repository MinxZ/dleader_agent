# Endpoint Performance Test Results

**User ID**: z08040992048@gmail.com
**Test Date**: 2025-11-13
**Server**: FastAPI Multi-turn Server (localhost:8001)

---

## Summary

### Available Endpoints

1. **`/multiturn-sessions`** - List all sessions with pagination
2. **`/multiturn-session/{session_id}`** - Get detailed session data
3. **`/results/{session_id}`** - Get session results

---

## Performance Results

### 1. `/multiturn-sessions` Endpoint (List Sessions)

**Parameters**: `?user_id=z08040992048@gmail.com&limit=10`

| Metric | Value |
|--------|-------|
| **Response Time** | ~0.274s (274ms) |
| **Total Sessions** | 5 |
| **Sessions Returned** | 5 |

#### Pagination Performance

All pagination tests showed consistent performance:

| Limit | Offset | Response Time | Sessions Returned |
|-------|--------|---------------|-------------------|
| 5 | 0 | 0.146s | 5/5 |
| 10 | 0 | 0.145s | 5/5 |
| 100 | 0 | 0.144s | 5/5 |

**Analysis**: Pagination performance is excellent and consistent (~145ms) regardless of limit size. This suggests efficient query optimization and likely in-memory caching.

---

### 2. `/multiturn-session/{session_id}` Endpoint (Individual Session Detail)

Performance varies significantly based on session complexity:

| Session ID | First Query | Turns | Response Time | Performance |
|------------|-------------|-------|---------------|-------------|
| 10d8d194-cc25-4429-9378-91a6eb11bffd | plot the tpsa for some drugs... | 1 | **4.100s** | ⚠️ Slowest |
| 8170fb34-229d-461b-b20a-e23b10646f4f | design an ASO drug for MALAT1 | 1 | **1.366s** | Slow |
| 1d00756e-e163-4c62-9176-253fd8cd43ad | Can you merge them together... | 1 | **0.698s** | Moderate |
| 4f425397-37fe-40d8-9d4e-578e2ebfa021 | plot the tpsa for 5 drugs... | 1 | **0.429s** | Fast |
| cd6af43b-1746-4d9b-8e80-8c9953fb975f | 1+1 | 1 | **0.152s** | ✅ Fastest |

**Average Response Time**: 1.349s
**Range**: 0.152s - 4.100s (27x variance)

**Analysis**:
- Simple sessions (e.g., "1+1") load nearly instantly (152ms)
- Complex sessions with drug analysis can take up to 4.1 seconds
- Response time likely correlates with:
  - Session data size
  - Number of attachments/files
  - Cloud storage retrieval latency
  - Report complexity

---

### 3. `/results/{session_id}` Endpoint (Session Results)

| Session ID | Response Time | Notes |
|------------|---------------|-------|
| 10d8d194-cc25-4429-9378-91a6eb11bffd | **1.649s** | Complex session |
| cd6af43b-1746-4d9b-8e80-8c9953fb975f | **0.289s** | Simple session |

**Analysis**: `/results` endpoint is generally faster than `/multiturn-session` for the same session, likely because it returns less data (just query + response vs full session details with turns).

---

## Key Findings

### ✅ Strengths

1. **Pagination is very fast** (~145ms consistently)
2. **Simple sessions load quickly** (<300ms)
3. **Response time is predictable** for similar session types

### ⚠️ Areas for Optimization

1. **Complex session retrieval is slow** (up to 4.1s)
   - First session (drug plotting) takes 4.1s
   - May involve cloud storage retrieval
   - Possible file system I/O bottleneck

2. **High variance in response times** (27x difference)
   - Need to investigate what causes slowdowns
   - Consider caching strategies for frequently accessed sessions

### 📊 Performance Characteristics

- **Best case**: 145-152ms (simple queries, pagination)
- **Typical case**: 400-700ms (moderate sessions)
- **Worst case**: 1.4-4.1s (complex sessions with files/plots)

---

## Recommendations

1. **Add caching layer** for frequently accessed sessions
2. **Pre-load session metadata** to reduce initial fetch time
3. **Implement lazy loading** for large attachments/reports
4. **Consider pagination** for turn data in large sessions
5. **Monitor cloud storage latency** if S3/DynamoDB is involved
6. **Add performance metrics** to identify bottlenecks

---

## Session Details

All 5 sessions for user `z08040992048@gmail.com`:

1. **10d8d194-cc25-4429-9378-91a6eb11bffd**
   - Query: "plot the tpsa for some drugs and save the plot"
   - Status: active
   - Language: en

2. **8170fb34-229d-461b-b20a-e23b10646f4f**
   - Query: "design an ASO drug for MALAT1"
   - Status: active
   - Language: en

3. **1d00756e-e163-4c62-9176-253fd8cd43ad**
   - Query: "Can you merge them together as a complete csv"
   - Status: active
   - Language: en

4. **4f425397-37fe-40d8-9d4e-578e2ebfa021**
   - Query: "plot the tpsa for 5 drugs with high logp"
   - Status: active
   - Language: en

5. **cd6af43b-1746-4d9b-8e80-8c9953fb975f**
   - Query: "1+1"
   - Status: active
   - Language: en

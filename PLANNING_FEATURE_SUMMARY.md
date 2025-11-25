# Planning Mode Feature Summary

## Overview

Add a planning/clarification phase before execution where the agent:
1. Asks clarifying questions (2-4 focused questions)
2. Builds understanding of user requirements
3. **Automatically suggests execution when ready** ✅
4. Provides clear execution plan (3-5 steps)

## Key Design Decision: Same Model for Planning

**✅ Use Claude Sonnet 4 for both planning and execution**

### Why?
- **Critical quality**: Planning quality directly impacts execution success
- **Complex domain**: Biomedical analysis requires strong reasoning to understand requirements
- **Cost-effective**: 2-3 planning turns (~$0.03-0.06) << 1 failed execution ($2-5)
- **Better outcomes**: High-quality model generates accurate execution plans
- **ROI**: 50-100x return by getting requirements right the first time

### Differences: Planning vs Execution

| Aspect | Planning | Execution |
|--------|----------|-----------|
| Model | Claude Sonnet 4 | Claude Sonnet 4 |
| Tools | **None** | **Full access (50+ tools)** |
| Timeout | 90 seconds | 600 seconds |
| Duration | 2-5 seconds | 2-10 minutes |
| Cost/turn | ~$0.01-0.02 | ~$1-3 |
| Purpose | Clarify & plan | Execute & analyze |

**Key difference:** Tools disabled, not model quality!

## Implementation Approach

### Separate Endpoint (Recommended) ✅

**New endpoint:** `/plan-session`
**Existing endpoints:** `/chat-queue`, `/continue-session` (unchanged)

**Benefits:**
- Clear separation of concerns
- Easy to understand for frontend
- User can skip planning if desired
- Backward compatible

## How It Works

### 1. Agent Signals Readiness

The planning agent includes a special marker when ready:

```
Response: "Great! Here's my execution plan:
1. Load gene expression data
2. Normalize and preprocess
3. Apply hierarchical clustering
4. Generate heatmap visualization

I have enough information to proceed! [READY_FOR_EXECUTION]"
```

Backend detects `[READY_FOR_EXECUTION]` and sets `ready_for_execution: true`

### 2. Frontend Adapts UI

**When NOT ready:**
```
┌────────────────────────────┐
│ 🤔 Planning Mode           │
│ Ask more questions...      │
│ [Send Message]             │
└────────────────────────────┘
```

**When READY:**
```
┌─────────────────────────────────┐
│ 🤔 Planning Mode  ✅ Ready       │
│ Here's my plan: 1... 2... 3...  │
│ ┌───────────────────────────┐   │
│ │  🚀 Start Execution       │   │ ← Prominent
│ └───────────────────────────┘   │
│ [Continue Planning Instead]     │ ← Subtle
└─────────────────────────────────┘
```

### 3. Execution Starts with Full Context

When user clicks "Start Execution":
- Uses `/continue-session` endpoint (existing)
- Agent receives ALL planning turns in context
- Execution proceeds with clear requirements

## Complete Flow Example

```bash
# Turn 1: Start planning (vague)
POST /plan-session
  → "I want to analyze some data"
  → Agent: "What type? What's your goal?"
  → ready_for_execution: false

# Turn 2: More details
POST /plan-session (same session)
  → "Gene expression, I want clustering"
  → Agent: "How many samples? Which method?"
  → ready_for_execution: false

# Turn 3: Final details
POST /plan-session (same session)
  → "20 samples, hierarchical clustering"
  → Agent: "Perfect! Here's my plan: 1... 2... 3... ✅"
  → ready_for_execution: true  ← UI shows green button

# Turn 4: Execution (user clicks button)
POST /continue-session (same session)
  → "Proceed with analysis"
  → Agent executes with FULL context from turns 1-3
  → Uses tools, generates results
```

## Session Storage

All turns (planning + execution) in one session:

```json
{
  "session_id": "abc123",
  "turns": [
    {
      "turn_number": 1,
      "turn_type": "planning",
      "ready_for_execution": false,
      "model_used": "claude-sonnet-4",
      "tools_used": []
    },
    {
      "turn_number": 2,
      "turn_type": "planning",
      "ready_for_execution": false,
      "model_used": "claude-sonnet-4",
      "tools_used": []
    },
    {
      "turn_number": 3,
      "turn_type": "planning",
      "ready_for_execution": true,  // ← ✅
      "model_used": "claude-sonnet-4",
      "tools_used": []
    },
    {
      "turn_number": 4,
      "turn_type": "execution",  // ← Switched
      "model_used": "claude-sonnet-4",
      "tools_used": ["load_csv", "cluster", "plot"]
    }
  ]
}
```

## API Changes

### New Endpoint

```
POST /plan-session
  - session_id (optional): None for new, ID for continue
  - message: User's message
  - language: en/jp
  - user_id: Required
  - files: Optional

Response:
  {
    "session_id": "abc123",
    "turn_session_id": "abc123_turn_1",
    "turn_number": 1,
    "turn_type": "planning",
    "status": "queued"
  }
```

### Enhanced Response

```
GET /results/{turn_session_id}?user_id=...

Response (for planning turns):
  {
    "turn_type": "planning",
    "ready_for_execution": true,  // ← NEW FIELD
    "content": {
      "final_report": "Here's my plan..."
    }
  }
```

## Benefits

1. **Better Query Quality** - Users refine before execution
2. **Same Model Quality** - Claude Sonnet 4 understands complex requirements
3. **Cost Efficiency** - Avoid expensive failed executions
4. **Time Efficiency** - Planning: 2-5s, Execution: 2-10min
5. **Smart Guidance** - Agent decides when ready
6. **Clear Plans** - Users see what will happen
7. **Better Success Rate** - Clear requirements → better outcomes
8. **Flexible** - Users can skip planning
9. **Backward Compatible** - Existing endpoints unchanged

## Implementation Files

1. **`PLANNING_ENDPOINT_IMPLEMENTATION.md`** - Complete technical guide
2. **`PLANNING_FLOW_DIAGRAM.md`** - Visual flows and examples
3. **`PLANNING_FEATURE_SUMMARY.md`** (this file) - Executive summary

## Next Steps

To implement:

1. Add `TurnType` enum (`planning`, `execution`)
2. Create `create_planning_agent()` function (Sonnet 4, no tools)
3. Add `/plan-session` endpoint
4. Update agent runner to detect `[READY_FOR_EXECUTION]`
5. Store `ready_for_execution` flag in turn data
6. Update frontend to show readiness UI

## Questions?

- Should we make planning the default entry point?
- Should we limit max planning turns (e.g., 5)?
- Should we auto-transition after certain signals?
- How to handle users who want to skip planning entirely?

---

**Ready to implement?** See `PLANNING_ENDPOINT_IMPLEMENTATION.md` for detailed code.

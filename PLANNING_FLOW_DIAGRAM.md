# Planning to Execution Flow Diagram

## Why Use the Same Model for Planning?

**Decision:** Planning uses **Claude Sonnet 4** (same as execution), not a cheaper model.

### Reasoning:
1. **Planning quality is critical** - Poor planning → poor execution
2. **Complex biomedical domain** - Requires strong reasoning to understand requirements
3. **Cost-benefit analysis**:
   - 2-3 planning turns with Sonnet 4: ~$0.03-0.06
   - 1 failed execution due to poor planning: $2-5
   - ROI: 50-100x savings by getting it right the first time
4. **Better execution plans** - High-quality model generates detailed, accurate execution plans
5. **Time savings** - Planning takes 2-5 seconds (no tools), execution takes 2-10 minutes (with tools)

### Key Differences: Planning vs Execution

| Aspect | Planning Mode | Execution Mode |
|--------|--------------|----------------|
| **Model** | Claude Sonnet 4 | Claude Sonnet 4 |
| **Tools** | None (disabled) | Full access (50+ tools) |
| **Timeout** | 90 seconds | 600 seconds |
| **Duration** | 2-5 seconds | 2-10 minutes |
| **Cost per turn** | ~$0.01-0.02 | ~$1-3 |
| **Purpose** | Clarify & plan | Execute & analyze |
| **Output** | Questions + plan | Results + files |

## Visual Flow with Readiness Detection

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         USER STARTS NEW TASK                             │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │
                                ▼
                    ┌───────────────────────┐
                    │  POST /plan-session   │
                    │  (session_id = None)  │
                    └───────────┬───────────┘
                                │
                                ▼
┌───────────────────────────────────────────────────────────────────────────┐
│                          PLANNING PHASE                                   │
│                                                                           │
│  ┌─────────────────────────────────────────────────────────────┐        │
│  │  Turn 1 (Planning)                                          │        │
│  │  ┌───────────────────────────────────────────────────────┐ │        │
│  │  │ Agent: "What type of data? What's your goal?"        │ │        │
│  │  │ ready_for_execution: false                           │ │        │
│  │  └───────────────────────────────────────────────────────┘ │        │
│  │                                                             │        │
│  │  User provides more details → POST /plan-session           │        │
│  └─────────────────────────────────────────────────────────────┘        │
│                                │                                         │
│                                ▼                                         │
│  ┌─────────────────────────────────────────────────────────────┐        │
│  │  Turn 2 (Planning)                                          │        │
│  │  ┌───────────────────────────────────────────────────────┐ │        │
│  │  │ Agent: "Perfect! Just one more question..."          │ │        │
│  │  │ ready_for_execution: false                           │ │        │
│  │  └───────────────────────────────────────────────────────┘ │        │
│  │                                                             │        │
│  │  User provides final details → POST /plan-session          │        │
│  └─────────────────────────────────────────────────────────────┘        │
│                                │                                         │
│                                ▼                                         │
│  ┌─────────────────────────────────────────────────────────────┐        │
│  │  Turn 3 (Planning)                                          │        │
│  │  ┌───────────────────────────────────────────────────────┐ │        │
│  │  │ Agent: "Great! Here's my execution plan:             │ │        │
│  │  │  1. Load data                                        │ │        │
│  │  │  2. Preprocess                                       │ │        │
│  │  │  3. Cluster                                          │ │        │
│  │  │  4. Visualize                                        │ │        │
│  │  │                                                       │ │        │
│  │  │ I have enough information to proceed! ✅             │ │        │
│  │  │ ready_for_execution: true                            │ │        │
│  │  └───────────────────────────────────────────────────────┘ │        │
│  └─────────────────────────────────────────────────────────────┘        │
│                                                                           │
└───────────────────────────────┬───────────────────────────────────────────┘
                                │
                                │ UI shows: [🚀 START EXECUTION] button
                                │ User clicks it
                                │
                                ▼
                    ┌───────────────────────┐
                    │ POST /continue-session │
                    │ (session_id = abc123) │
                    └───────────┬───────────┘
                                │
                                ▼
┌───────────────────────────────────────────────────────────────────────────┐
│                        EXECUTION PHASE                                    │
│                                                                           │
│  ┌─────────────────────────────────────────────────────────────┐        │
│  │  Turn 4 (Execution)                                         │        │
│  │  ┌───────────────────────────────────────────────────────┐ │        │
│  │  │ 🔧 Loading gene expression data...                   │ │        │
│  │  │ 🔧 Normalizing expression values...                  │ │        │
│  │  │ 🔧 Performing hierarchical clustering...             │ │        │
│  │  │ 📊 Generating heatmap visualization...               │ │        │
│  │  │                                                       │ │        │
│  │  │ ✅ Analysis complete!                                │ │        │
│  │  │ turn_type: execution                                 │ │        │
│  │  │ tools_used: [load_csv, normalize, cluster, plot]    │ │        │
│  │  └───────────────────────────────────────────────────────┘ │        │
│  └─────────────────────────────────────────────────────────────┘        │
│                                                                           │
└───────────────────────────────────────────────────────────────────────────┘
```

## State Transitions

```
                    ┌──────────────────┐
                    │   Planning Mode   │
                    │  (NOT READY)      │
                    │                   │
                    │ - Ask questions   │
                    │ - Gather info     │
                    │ - Build context   │
                    └─────────┬─────────┘
                              │
                              │ Agent detects
                              │ sufficient info
                              │
                              ▼
                    ┌──────────────────┐
                    │   Planning Mode   │
                    │   (READY ✅)      │
                    │                   │
                    │ - Show plan       │
                    │ - Signal ready    │
                    │ - Wait for user   │
                    └─────────┬─────────┘
                              │
                              │ User confirms
                              │
                              ▼
                    ┌──────────────────┐
                    │  Execution Mode   │
                    │                   │
                    │ - Run tools       │
                    │ - Generate output │
                    │ - Complete task   │
                    └──────────────────┘
```

## Decision Logic

### Agent's Internal Decision: When to Signal Ready?

```python
def should_signal_ready_for_execution(conversation_history):
    """
    Agent evaluates if it has enough information to proceed

    Returns: bool (whether to include [READY_FOR_EXECUTION] signal)
    """

    # Agent checks (via system prompt guidance):
    checklist = {
        "data_type_known": False,       # CSV, Excel, database, etc.
        "analysis_goal_clear": False,   # What are they trying to achieve?
        "expected_outputs_defined": False,  # What do they want to see?
        "constraints_understood": False # Any specific requirements?
    }

    # If 3+ criteria met, signal readiness
    if sum(checklist.values()) >= 3:
        return True

    return False
```

### Frontend's Decision: What to Show?

```javascript
function determineUI(planningResult) {
  if (planningResult.ready_for_execution) {
    return {
      primaryAction: "START_EXECUTION",
      buttonText: "🚀 Start Execution",
      buttonColor: "green",
      buttonSize: "large",
      secondaryAction: "CONTINUE_PLANNING",
      secondaryText: "Continue Planning Instead",
      badge: "✅ Ready for Execution"
    };
  } else {
    return {
      primaryAction: "CONTINUE_PLANNING",
      inputPlaceholder: "Continue refining your request...",
      badge: "🤔 Planning Mode"
    };
  }
}
```

## Session Storage Structure

```json
{
  "session_id": "abc123",
  "user_id": "test_user",
  "session_name": "Gene Expression Analysis",
  "current_turn": 4,
  "total_turns": 4,
  "turns": [
    {
      "turn_number": 1,
      "turn_type": "planning",
      "turn_session_id": "abc123_turn_1",
      "query": "I want to analyze gene expression data",
      "response": "I'd be happy to help! Could you tell me:\n1. What format is your data...",
      "ready_for_execution": false,
      "model_used": "claude-sonnet-4",
      "tools_used": [],
      "timestamp": "2025-01-10T10:00:00Z",
      "status": "completed",
      "duration": 2.8
    },
    {
      "turn_number": 2,
      "turn_type": "planning",
      "turn_session_id": "abc123_turn_2",
      "query": "It's CSV with gene names and expression values...",
      "response": "Perfect! Just one more question:\n- How many samples...",
      "ready_for_execution": false,
      "model_used": "claude-sonnet-4",
      "tools_used": [],
      "timestamp": "2025-01-10T10:02:00Z",
      "status": "completed",
      "duration": 3.1
    },
    {
      "turn_number": 3,
      "turn_type": "planning",
      "turn_session_id": "abc123_turn_3",
      "query": "20 samples, 4 conditions, hierarchical clustering",
      "response": "Great! Here's my execution plan:\n1. Load CSV\n2. Normalize\n...",
      "ready_for_execution": true,  // ← ✅ READY!
      "model_used": "claude-sonnet-4",
      "tools_used": [],
      "timestamp": "2025-01-10T10:04:00Z",
      "status": "completed"
    },
    {
      "turn_number": 4,
      "turn_type": "execution",  // ← Changed to execution
      "turn_session_id": "abc123_turn_4",
      "query": "Please proceed with the analysis",
      "response": "## Gene Expression Analysis Report\n...",
      "ready_for_execution": null,  // Not applicable for execution turns
      "model_used": "claude-sonnet-4",
      "tools_used": ["load_csv", "normalize_data", "hierarchical_cluster", "plot_heatmap"],
      "timestamp": "2025-01-10T10:06:00Z",
      "status": "completed",
      "files": {
        "images": ["heatmap.png", "dendrogram.png"],
        "data_files": ["clustered_data.csv"]
      }
    }
  ]
}
```

## API Response Comparison

### Planning Turn (NOT Ready)
```json
GET /results/abc123_turn_1?user_id=test_user

{
  "session_id": "abc123",
  "turn_session_id": "abc123_turn_1",
  "turn_number": 1,
  "turn_type": "planning",
  "ready_for_execution": false,  // ← Key field
  "status": "completed",
  "content": {
    "final_report": "I'd be happy to help! Could you tell me..."
  }
}
```

### Planning Turn (READY)
```json
GET /results/abc123_turn_3?user_id=test_user

{
  "session_id": "abc123",
  "turn_session_id": "abc123_turn_3",
  "turn_number": 3,
  "turn_type": "planning",
  "ready_for_execution": true,  // ← ✅ READY!
  "status": "completed",
  "content": {
    "final_report": "Great! Here's my execution plan:\n1. Load...\n2. Preprocess...\nI have enough information to proceed!"
  }
}
```

### Execution Turn
```json
GET /results/abc123_turn_4?user_id=test_user

{
  "session_id": "abc123",
  "turn_session_id": "abc123_turn_4",
  "turn_number": 4,
  "turn_type": "execution",
  "ready_for_execution": null,  // Not applicable
  "status": "completed",
  "content": {
    "final_report": "## Analysis Complete\n..."
  },
  "files": {
    "images": [...],
    "data_files": [...]
  }
}
```

## Benefits of This Approach

1. **Guided Experience**: Agent guides users from vague to specific
2. **Clear Transition**: Visual feedback when ready to execute
3. **User Control**: User can always continue planning or start execution
4. **Context Preserved**: All planning turns inform execution
5. **Cost Efficient**: Planning uses cheap Haiku model
6. **Time Efficient**: Planning responses in 2-5 seconds vs 2-5 minutes for execution
7. **Better Outcomes**: Execution starts with clear, well-defined requirements

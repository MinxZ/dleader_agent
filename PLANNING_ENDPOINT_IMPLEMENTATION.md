# Planning Endpoint Implementation Guide

## Overview
Add a lightweight planning/clarification endpoint to help users refine their queries before full agent execution.

## Architecture Decision: Separate Endpoint (Recommended)

### Why Separate Endpoint?
1. **Clear separation** - Users know when they're planning vs executing
2. **Performance optimization** - Planning uses faster model, no tools
3. **Flexible workflow** - Users can skip planning if desired
4. **Better UX** - UI can show distinct planning and execution phases
5. **Cost optimization** - Planning uses cheaper Haiku model

### Why NOT a Flag?
- Harder to prevent accidental tool execution
- More complex conditional logic in existing endpoints
- Less clear for frontend developers
- Mixing concerns in same endpoint

---

## Implementation Plan

### 1. Data Model Changes

Add `TurnType` enum and update turn storage:

```python
# In agent_fastapi_server_multiturn.py

class TurnType(str, Enum):
    PLANNING = "planning"      # Clarification phase - no tool execution
    EXECUTION = "execution"    # Full agent execution with tools

# Update Turn class or dict to include turn_type
# Example turn structure:
{
    "turn_number": 1,
    "turn_type": "planning",  # NEW FIELD
    "turn_session_id": "abc123_turn_1",
    "query": "I want to analyze some data",
    "response": "I'd be happy to help! To provide the best analysis, could you tell me:\n1. What type of data?\n2. What's your analysis goal?\n3. Any specific visualizations?",
    "timestamp": "2025-01-10T10:00:00Z",
    "status": "completed",
    "model_used": "claude-haiku-3-5",  # Lighter model for planning
    "tools_used": [],  # No tools in planning mode
    "duration": 3.2
}
```

### 2. Create Planning Agent Configuration

```python
# In agent_fastapi_server_multiturn.py

def create_planning_agent(language: Language = Language.EN):
    """
    Create an agent for planning/clarification phase

    Key differences from execution agent:
    - Uses SAME model as execution (e.g., Claude Sonnet 4) for high-quality reasoning
    - NO tool access (planning only, no execution)
    - Focused system prompt for asking questions and building execution plans
    - Shorter timeout (60-90 seconds vs 600 seconds for execution)
    - Signals when ready for execution

    Why same model?
    - Planning quality is critical for execution success
    - Better understanding of complex biomedical requirements
    - More accurate execution plan generation
    - Cost of 2-3 planning turns << cost of failed execution
    """

    if language == Language.EN:
        planning_system_prompt = """You are a helpful AI assistant in planning mode.
Your goal is to understand the user's needs by asking clarifying questions.

DO NOT execute any analysis or use tools yet. Your job is to:
1. Ask 2-4 focused clarifying questions to understand:
   - What type of data/analysis they need
   - What their goals are
   - What outputs they expect
2. Help them refine their request
3. Build a clear plan of what you'll do

Keep responses concise (2-3 paragraphs max).

IMPORTANT - When to suggest execution:
- When you have enough information about: data type, analysis goals, and expected outputs
- When the user has answered your key questions
- When you can create a clear execution plan

Signal readiness by including this EXACT phrase at the end of your response:
"[READY_FOR_EXECUTION]"

When ready, structure your response like this:
1. Summarize what you understand
2. Outline the execution plan (3-5 steps)
3. End with: "I have enough information to proceed! [READY_FOR_EXECUTION]"

Example ready response:
"Great! I now understand you want to:
- Analyze gene expression data from your CSV file
- Perform hierarchical clustering
- Generate a heatmap and PCA plot

Here's my execution plan:
1. Load and validate the gene expression data
2. Perform data preprocessing and normalization
3. Apply hierarchical clustering
4. Generate heatmap visualization
5. Create PCA plot with cluster annotations

I have enough information to proceed! [READY_FOR_EXECUTION]"
"""
    else:  # Japanese
        planning_system_prompt = """あなたは計画モードのAIアシスタントです。
ユーザーのニーズを理解するために質問をすることが目標です。

まだ分析やツールの実行はしないでください。あなたの仕事は:
1. 2-4の焦点を絞った質問をして理解する:
   - どのようなデータ/分析が必要か
   - 目標は何か
   - どのような出力を期待しているか
2. リクエストを洗練させる
3. 実行計画を明確に作成する

回答は簡潔に（2-3段落以内）。

重要 - 実行を提案するタイミング:
- データタイプ、分析目標、期待される出力について十分な情報がある時
- ユーザーが重要な質問に答えた時
- 明確な実行計画を作成できる時

準備ができたら、このフレーズを応答の最後に含めてください:
"[READY_FOR_EXECUTION]"

準備ができた時の回答構造:
1. 理解した内容を要約
2. 実行計画を概説（3-5ステップ）
3. 最後に: "十分な情報が揃いました！実行に進むことができます。[READY_FOR_EXECUTION]"
"""

    agent_config = {
        "llm_source": "anthropic",  # or your preferred provider (same as execution)
        "model_name": "claude-sonnet-4",  # SAME MODEL as execution for quality
        "system_prompt": planning_system_prompt,
        "tools": [],  # NO TOOLS - this is key difference!
        "max_iterations": 1,  # Single response, no loops
        "language": language.value,
        "temperature": 0.7,  # Slightly more creative for questions
        "timeout": 90  # Shorter timeout than execution (90s vs 600s)
    }

    return agent_config


def create_execution_agent(language: Language = Language.EN):
    """
    Standard execution agent with full tool access
    (Your existing agent configuration)
    """
    # Your current A1 agent configuration
    pass
```

### 3. Create `/plan-session` Endpoint

```python
@app.post("/plan-session")
async def plan_session(
    session_id: Optional[str] = Form(None),  # None = new session
    message: str = Form(...),
    language: Language = Form(Language.EN),
    user_id: str = Form(...),
    files: List[UploadFile] = File(default=[])
):
    """
    Planning/clarification endpoint - agent asks questions without tool execution

    This creates "planning" turns in the multi-turn session that will be included
    in context when execution starts.

    Args:
        session_id: Existing session ID (None for new session)
        message: User's message/question
        language: Response language (en/jp)
        user_id: User identifier
        files: Optional file uploads (stored but not analyzed yet)

    Returns:
        {
            "session_id": "abc123",
            "turn_session_id": "abc123_turn_1",  # For status checking
            "turn_number": 1,
            "turn_type": "planning",
            "status": "queued",
            "message": "Planning request queued"
        }
    """

    # Validate user_id
    if not user_id or user_id.strip() == "":
        raise HTTPException(status_code=400, detail="user_id is required")

    # Validate message
    if not message or message.strip() == "":
        raise HTTPException(status_code=400, detail="message is required")

    try:
        # Check if this is a new session or continuation
        if session_id:
            # Continue existing session in planning mode
            multiturn_session = queue_manager.multiturn_sessions.get(session_id)

            if not multiturn_session:
                # Try to load from cloud storage
                unified_manager = get_unified_session_manager(queue_manager)
                cloud_session = await unified_manager.get_multiturn_session_by_id(session_id)

                if not cloud_session:
                    raise HTTPException(status_code=404, detail="Session not found")

                # Verify user ownership
                if cloud_session.get("user_id") != user_id:
                    raise HTTPException(status_code=403, detail="Access denied")

                # Load session into memory
                multiturn_session = queue_manager.restore_multiturn_session_from_cloud(cloud_session)
            else:
                # Verify user ownership for in-memory session
                if multiturn_session.user_id != user_id:
                    raise HTTPException(status_code=403, detail="Access denied")

            # Add new planning turn
            turn_number = multiturn_session.current_turn + 1
            turn_session_id = f"{session_id}_turn_{turn_number}"

        else:
            # Create new session starting with planning
            session_id = str(uuid.uuid4())
            turn_number = 1
            turn_session_id = f"{session_id}_turn_1"

            # Create new multi-turn session
            multiturn_session = MultiTurnSession(
                session_id=session_id,
                user_id=user_id,
                language=language,
                session_name=message[:50] + ("..." if len(message) > 50 else "")
            )
            queue_manager.multiturn_sessions[session_id] = multiturn_session

        # Handle file uploads (if any)
        uploaded_files = []
        if files:
            session_path = f"./chat_sessions/{session_id}"
            os.makedirs(session_path, exist_ok=True)

            for file in files:
                # Save file for later use in execution phase
                file_path = os.path.join(session_path, file.filename)
                with open(file_path, "wb") as f:
                    content = await file.read()
                    f.write(content)
                uploaded_files.append(file.filename)

        # Create planning request (lightweight, fast execution)
        planning_request = {
            "session_id": session_id,
            "turn_session_id": turn_session_id,
            "turn_number": turn_number,
            "turn_type": "planning",  # Mark as planning turn
            "message": message,
            "language": language,
            "user_id": user_id,
            "uploaded_files": uploaded_files,
            "agent_config": create_planning_agent(language),  # Use planning agent
            "timestamp": datetime.now(JST).isoformat(),
            "use_template": False  # No template matching for planning
        }

        # Add to queue (planning requests should be fast, so normal queue is fine)
        queue_manager.add_planning_request(planning_request)

        # Update multi-turn session
        multiturn_session.add_turn(
            turn_number=turn_number,
            turn_session_id=turn_session_id,
            turn_type="planning",
            query=message,
            files=uploaded_files
        )

        return JSONResponse({
            "session_id": session_id,
            "turn_session_id": turn_session_id,
            "turn_number": turn_number,
            "turn_type": "planning",
            "status": "queued",
            "position": queue_manager.get_queue_position(turn_session_id),
            "message": "Planning request queued successfully"
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in plan_session: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

### 4. Update Queue Manager

Add planning request handling:

```python
# In QueueManager class

def add_planning_request(self, request_data: dict):
    """Add a planning request to the queue (same model as execution, but no tools)"""
    turn_session_id = request_data["turn_session_id"]

    # Create UserRequest with planning configuration
    user_request = UserRequest(
        session_id=request_data["session_id"],
        turn_session_id=turn_session_id,
        message=request_data["message"],
        language=request_data["language"],
        user_id=request_data["user_id"],
        uploaded_files=request_data.get("uploaded_files", []),
        turn_number=request_data["turn_number"],
        turn_type="planning",  # NEW FIELD
        timestamp=request_data["timestamp"],
        use_template=False
    )

    # Set planning-specific configuration
    user_request.agent_config = request_data["agent_config"]
    # Shorter timeout since no tool execution (90s vs 600s for execution)
    user_request.timeout = 90

    self.queue.put(user_request)
    self.user_requests[turn_session_id] = user_request

    logger.info(f"Planning request added: {turn_session_id} (same model, no tools)")
```

### 5. Update Agent Execution Logic

Modify the agent execution to handle planning vs execution:

```python
def run_agent_with_context(user_request, context_data, parent_conn):
    """
    Run agent with appropriate configuration based on turn_type
    """

    if user_request.turn_type == "planning":
        # PLANNING MODE - No tools, fast model, focused prompt
        agent_config = user_request.agent_config

        # Create simple LLM chain without tools
        from langchain_anthropic import ChatAnthropic

        llm = ChatAnthropic(
            model=agent_config["model_name"],
            temperature=agent_config["temperature"]
        )

        # Build context from previous turns (if any)
        conversation_history = build_conversation_history(context_data)

        # Generate planning response
        prompt = f"""{agent_config['system_prompt']}

Previous conversation:
{conversation_history}

User: {user_request.message}

Your response (ask clarifying questions):"""

        response = llm.invoke(prompt)

        # Check if agent signals readiness for execution
        content = response.content
        ready_for_execution = "[READY_FOR_EXECUTION]" in content

        # Remove the signal from content (keep it clean for display)
        if ready_for_execution:
            content = content.replace("[READY_FOR_EXECUTION]", "").strip()

        # Send result back with readiness flag
        parent_conn.send({
            "type": "final_answer",
            "content": content,
            "turn_type": "planning",
            "ready_for_execution": ready_for_execution  # NEW FLAG
        })

    else:
        # EXECUTION MODE - Full agent with tools (existing logic)
        # Your existing agent execution code here
        pass
```

### 6. Update Context Building

Include planning turns in execution context:

```python
def build_execution_context(multiturn_session):
    """
    Build context for execution agent, including all planning turns
    """
    context = {
        "conversation_history": [],
        "uploaded_files": [],
        "planning_summary": None
    }

    planning_turns = []
    execution_turns = []

    for turn in multiturn_session.turns:
        if turn.turn_type == "planning":
            planning_turns.append(turn)
            context["conversation_history"].append({
                "role": "user",
                "content": turn.query
            })
            context["conversation_history"].append({
                "role": "assistant",
                "content": turn.response
            })
        else:
            execution_turns.append(turn)

    # Create planning summary if there were planning turns
    if planning_turns:
        context["planning_summary"] = f"""
The user had a planning conversation before this execution:
{format_planning_turns(planning_turns)}

Now they are ready for full execution with tool access.
"""

    return context
```

### 7. Response Structure Updates

The `/results` endpoint for planning turns should include the readiness flag:

```python
# Store ready_for_execution flag in turn data
turn_data = {
    "turn_number": turn_number,
    "turn_type": "planning",
    "query": message,
    "response": content,
    "ready_for_execution": ready_for_execution,  # NEW FIELD
    "timestamp": datetime.now(JST).isoformat(),
    "status": "completed"
}
```

Response from `/results/{turn_session_id}`:
```json
{
  "session_id": "abc123",
  "turn_session_id": "abc123_turn_2",
  "turn_number": 2,
  "turn_type": "planning",
  "status": "completed",
  "content": {
    "final_report": "Great! I now understand you want to:\n- Analyze gene expression...\n\nHere's my execution plan:\n1. Load data...\n2. Normalize...\n\nI have enough information to proceed!"
  },
  "ready_for_execution": true,  // ← NEW FLAG signals UI to show "Start Execution" button
  "timestamp": "2025-01-10T10:05:00Z"
}
```

### 8. Frontend Integration

```javascript
// Planning flow with execution readiness detection
async function startWithPlanning(message, userId) {
  // Step 1: Start planning session
  const planResponse = await fetch('/plan-session', {
    method: 'POST',
    body: createFormData({ message, user_id: userId })
  });
  const { session_id, turn_session_id } = await planResponse.json();

  // Step 2: Poll for planning response
  const planResult = await pollUntilComplete(turn_session_id, userId);

  // Step 3: Show planning response to user
  displayPlanningResponse(planResult);

  // Step 4: Check if agent suggests execution
  if (planResult.ready_for_execution) {
    // Show "Start Execution" button prominently
    showExecutionButton(session_id, planResult.content);
  } else {
    // Show "Continue Planning" input
    showContinuePlanningInput(session_id);
  }

  return { session_id, mode: 'planning', ready: planResult.ready_for_execution };
}

async function continuePlanning(sessionId, message, userId) {
  // Continue planning conversation
  const response = await fetch('/plan-session', {
    method: 'POST',
    body: createFormData({
      session_id: sessionId,
      message,
      user_id: userId
    })
  });

  const { turn_session_id } = await response.json();
  const result = await pollUntilComplete(turn_session_id, userId);

  // Check readiness again
  if (result.ready_for_execution) {
    showExecutionButton(sessionId, result.content);
  }

  return result;
}

async function startExecution(sessionId, userId) {
  // Transition to execution with full context
  // User can provide additional message or just proceed
  const message = "Please proceed with the analysis we discussed";

  const response = await fetch('/continue-session', {
    method: 'POST',
    body: createFormData({
      session_id: sessionId,
      message,
      user_id: userId
    })
  });

  const { turn_session_id } = await response.json();

  // Now poll for execution results (with thinking process, tool usage, etc.)
  return pollExecutionWithProgress(turn_session_id, userId);
}
```

### 9. UI/UX Implementation

**Visual States:**

**State 1: Initial Planning (not ready)**
```
┌──────────────────────────────────────────────┐
│ 🤔 Planning Mode                             │
├──────────────────────────────────────────────┤
│ User: I want to analyze some data            │
│                                              │
│ Assistant: I'd be happy to help!             │
│ Could you tell me:                           │
│ 1. What type of data do you have?            │
│ 2. What's your analysis goal?                │
│ 3. What outputs do you need?                 │
│                                              │
│ [Send Message]                               │ ← Only continue planning
└──────────────────────────────────────────────┘
```

**State 2: Planning Complete (ready for execution)**
```
┌──────────────────────────────────────────────┐
│ 🤔 Planning Mode  ✅ Ready for Execution     │
├──────────────────────────────────────────────┤
│ Assistant: Great! I now understand you want: │
│ - Analyze gene expression data               │
│ - Perform hierarchical clustering            │
│ - Generate heatmap and PCA visualization     │
│                                              │
│ Here's my execution plan:                    │
│ 1. Load and validate gene expression data   │
│ 2. Perform data preprocessing                │
│ 3. Apply hierarchical clustering             │
│ 4. Generate visualizations                   │
│                                              │
│ I have enough information to proceed!        │
│                                              │
│ ┌──────────────────────────────────────────┐ │
│ │  🚀 Start Execution                      │ │ ← Prominent green button
│ └──────────────────────────────────────────┘ │
│                                              │
│ [Continue Planning Instead]                  │ ← Subtle link
└──────────────────────────────────────────────┘
```

**State 3: Execution Phase**
```
┌──────────────────────────────────────────────┐
│ ⚙️ Execution Mode                            │
├──────────────────────────────────────────────┤
│ 🔧 Using tool: load_gene_expression_data     │
│ 🔧 Using tool: normalize_expression_values   │
│ 🔧 Using tool: hierarchical_clustering       │
│ 📊 Generating visualizations...              │
│                                              │
│ [View Thinking Process] [Stop Execution]     │
└──────────────────────────────────────────────┘
```

**React Component Example:**

```jsx
import React, { useState, useEffect } from 'react';

function PlanningInterface({ sessionId, turnSessionId, userId }) {
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    pollForResult(turnSessionId, userId);
  }, [turnSessionId]);

  async function pollForResult(turnSessionId, userId) {
    // Poll until complete
    const interval = setInterval(async () => {
      const res = await fetch(`/results/${turnSessionId}?user_id=${userId}`);
      const data = await res.json();

      if (data.status === 'completed') {
        clearInterval(interval);
        setResult(data);
        setLoading(false);
      }
    }, 2000);
  }

  if (loading) {
    return <div>Planning in progress...</div>;
  }

  return (
    <div className={`planning-card ${result.ready_for_execution ? 'ready' : ''}`}>
      <div className="planning-header">
        <span className="badge">🤔 Planning Mode</span>
        {result.ready_for_execution && (
          <span className="badge-success">✅ Ready for Execution</span>
        )}
      </div>

      <div className="planning-content">
        <div className="message assistant">
          {result.content.final_report}
        </div>
      </div>

      <div className="planning-actions">
        {result.ready_for_execution ? (
          <>
            <button
              className="btn-primary btn-large"
              onClick={() => handleStartExecution(sessionId)}
            >
              🚀 Start Execution
            </button>
            <button
              className="btn-secondary btn-small"
              onClick={() => handleContinuePlanning(sessionId)}
            >
              Continue Planning Instead
            </button>
          </>
        ) : (
          <div className="continue-planning-input">
            <input
              type="text"
              placeholder="Continue refining your request..."
              onKeyPress={(e) => {
                if (e.key === 'Enter') {
                  handleContinuePlanning(sessionId, e.target.value);
                }
              }}
            />
            <button onClick={() => handleContinuePlanning(sessionId)}>
              Send
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

async function handleStartExecution(sessionId) {
  const formData = new FormData();
  formData.append('session_id', sessionId);
  formData.append('message', 'Please proceed with the analysis we discussed');
  formData.append('user_id', userId);

  const response = await fetch('/continue-session', {
    method: 'POST',
    body: formData
  });

  const { turn_session_id } = await response.json();

  // Switch to execution view
  showExecutionView(turn_session_id);
}

async function handleContinuePlanning(sessionId, additionalMessage) {
  const formData = new FormData();
  formData.append('session_id', sessionId);
  formData.append('message', additionalMessage || 'I have more details to add');
  formData.append('user_id', userId);

  const response = await fetch('/plan-session', {
    method: 'POST',
    body: formData
  });

  const { turn_session_id } = await response.json();

  // Continue in planning view
  showPlanningView(turn_session_id);
}
```

**CSS Styling Example:**

```css
.planning-card {
  border: 2px solid #3b82f6;
  border-radius: 8px;
  padding: 20px;
  background: #eff6ff;
}

.planning-card.ready {
  border-color: #22c55e;
  background: #f0fdf4;
}

.planning-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 16px;
}

.badge {
  padding: 4px 12px;
  border-radius: 4px;
  background: #3b82f6;
  color: white;
  font-size: 14px;
}

.badge-success {
  background: #22c55e;
  animation: pulse 2s infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.7; }
}

.btn-primary.btn-large {
  width: 100%;
  padding: 16px;
  font-size: 18px;
  background: #22c55e;
  color: white;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  margin-bottom: 8px;
  transition: all 0.2s;
}

.btn-primary.btn-large:hover {
  background: #16a34a;
  transform: scale(1.02);
}

.btn-secondary.btn-small {
  width: 100%;
  padding: 8px;
  font-size: 14px;
  background: transparent;
  color: #6b7280;
  border: 1px solid #d1d5db;
  border-radius: 4px;
  cursor: pointer;
}
```

---

## Migration Path

### Phase 1: Add Planning Endpoint (Non-Breaking)
- Implement `/plan-session` endpoint
- Existing `/chat-queue` continues to work as before
- Users can opt-in to planning mode

### Phase 2: Update UI
- Add "Start with Planning" button in UI
- Show planning vs execution phases visually
- Allow users to toggle between modes

### Phase 3: Make Planning Default (Optional)
- Default new sessions to planning mode
- Add "Skip Planning" option for advanced users
- Measure impact on success rates

---

## Benefits Summary

1. **Better Query Quality**: Users refine requests before execution
2. **High-Quality Planning**: Uses same model as execution (e.g., Claude Sonnet 4) for excellent reasoning
3. **Cost Efficiency**: 2-3 planning turns (~$0.03-0.06) vs failed execution ($2-5) = huge savings
4. **Time Savings**: 2-5 seconds per planning turn vs 2-10 minutes for execution
5. **Better Execution Success Rate**: Clear requirements → better execution outcomes
6. **Better UX**: Clear planning vs execution phases
7. **Backward Compatible**: Existing flows continue to work
8. **Flexible**: Users can skip planning if desired
9. **🆕 Smart Readiness Detection**: Agent automatically suggests when to start execution
10. **🆕 Guided Workflow**: UI adapts based on agent's readiness signal
11. **🆕 Clear Execution Plans**: Users see what will happen before it runs
12. **🆕 Domain-Appropriate**: Same model understands complex biomedical requirements

---

## Open Questions

1. Should planning turns count toward billing/rate limits?
2. Should there be a max number of planning turns before forcing execution?
3. Should planning responses be stored in separate files or same as execution?
4. Should we auto-suggest execution when planning seems complete?

---

## Example Complete Flow with Readiness Detection

```bash
# 1. Start with planning (vague initial query)
curl -X POST http://localhost:8001/plan-session \
  -F "message=I want to analyze gene expression data" \
  -F "user_id=test_user"
# Response:
# {
#   "session_id": "abc123",
#   "turn_session_id": "abc123_turn_1",
#   "turn_number": 1,
#   "turn_type": "planning",
#   "status": "queued"
# }

# Check results
curl "http://localhost:8001/results/abc123_turn_1?user_id=test_user"
# Response:
# {
#   "status": "completed",
#   "turn_type": "planning",
#   "ready_for_execution": false,  ← Not ready yet
#   "content": {
#     "final_report": "I'd be happy to help analyze gene expression data!
#                      To provide the best analysis, could you tell me:
#                      1. What format is your data in (CSV, Excel, etc.)?
#                      2. What's your main analysis goal?
#                      3. What visualizations do you need?"
#   }
# }

# 2. Continue planning (provide more details)
curl -X POST http://localhost:8001/plan-session \
  -F "session_id=abc123" \
  -F "message=It's a CSV file with gene names and expression values.
              I want to do clustering and create a heatmap." \
  -F "user_id=test_user"
# Response:
# {
#   "turn_session_id": "abc123_turn_2",
#   "turn_number": 2,
#   "turn_type": "planning"
# }

# Check results again
curl "http://localhost:8001/results/abc123_turn_2?user_id=test_user"
# Response:
# {
#   "status": "completed",
#   "turn_type": "planning",
#   "ready_for_execution": false,  ← Still not quite ready
#   "content": {
#     "final_report": "Perfect! I understand you have CSV data with genes and expression values.
#                      Just one more question:
#                      - How many samples/conditions do you have?
#                      - Any specific clustering method preference (hierarchical, k-means)?"
#   }
# }

# 3. Provide final details
curl -X POST http://localhost:8001/plan-session \
  -F "session_id=abc123" \
  -F "message=I have 20 samples across 4 conditions.
              Hierarchical clustering would be great." \
  -F "user_id=test_user"
# Response:
# {
#   "turn_session_id": "abc123_turn_3",
#   "turn_number": 3,
#   "turn_type": "planning"
# }

# Check results - NOW READY! 🎉
curl "http://localhost:8001/results/abc123_turn_3?user_id=test_user"
# Response:
# {
#   "status": "completed",
#   "turn_type": "planning",
#   "ready_for_execution": true,  ← ✅ READY!
#   "content": {
#     "final_report": "Great! I now understand you want to:
#                      - Analyze gene expression data from CSV (20 samples, 4 conditions)
#                      - Perform hierarchical clustering
#                      - Generate a heatmap visualization
#
#                      Here's my execution plan:
#                      1. Load and validate the gene expression CSV data
#                      2. Perform data preprocessing and normalization
#                      3. Apply hierarchical clustering using Ward's method
#                      4. Generate an annotated heatmap with dendrograms
#                      5. Create supplementary visualizations (sample correlation, PCA if helpful)
#
#                      I have enough information to proceed!"
#   }
# }

# 4. User sees the green "Start Execution" button and clicks it
#    This triggers:
curl -X POST http://localhost:8001/continue-session \
  -F "session_id=abc123" \
  -F "message=Please proceed with the analysis we discussed" \
  -F "user_id=test_user"
# Response:
# {
#   "turn_session_id": "abc123_turn_4",  ← Now execution turn
#   "turn_number": 4,
#   "turn_type": "execution",  ← Changed to execution!
#   "status": "queued"
# }

# 5. Poll for execution progress (with tools, thinking process, etc.)
curl "http://localhost:8001/status/abc123_turn_4?user_id=test_user"
# {
#   "status": "processing",
#   "turn_type": "execution",
#   "progress": { "percentage": 45, "step": "Performing hierarchical clustering..." }
# }

# Get thinking process with tool usage
curl "http://localhost:8001/snapshots/abc123_turn_4?user_id=test_user"
# Shows full thinking process with tool executions
```

### Key Moments in the Flow

1. **Turn 1-2**: Agent asks clarifying questions, `ready_for_execution: false`
2. **Turn 3**: Agent has enough info, `ready_for_execution: true`, shows execution plan
3. **Turn 4**: User proceeds → Full execution with tool access begins
4. **Context Preserved**: All planning turns (1-3) are included in execution context

### What the User Sees

```
Turn 1 (Planning):
  User: "I want to analyze gene expression data"
  Agent: "I'd be happy to help! Could you tell me: ..."
  UI: [Continue Planning button only]

Turn 2 (Planning):
  User: "It's a CSV, I want clustering and heatmap"
  Agent: "Perfect! Just one more question: ..."
  UI: [Continue Planning button only]

Turn 3 (Planning):
  User: "20 samples, 4 conditions, hierarchical clustering"
  Agent: "Great! Here's my execution plan: 1... 2... 3... 4... 5... ✅"
  UI: [🚀 START EXECUTION button prominent] [Continue Planning instead link]

Turn 4 (Execution):
  Agent: *Loads CSV* → *Normalizes data* → *Clusters* → *Generates heatmap*
  UI: [Thinking process stream] [Tool usage logs] [Stop button]
```

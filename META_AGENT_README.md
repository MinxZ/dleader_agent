# MetaAgent System Documentation

## Overview

The **MetaAgent** is a hierarchical agent orchestration system designed to handle complex multi-step tasks that involve processing large quantities of items in parallel. It automatically decomposes complex queries, manages worker agents, monitors progress, handles failures, and aggregates results.

## Use Cases

Perfect for tasks like:
- **"Read and analyze 1000 research papers about X"**
- **"Process 500 patient records and extract clinical insights"**
- **"Analyze 200 gene sequences for mutations"**
- **"Summarize data from 300 clinical trial reports"**
- Any task requiring parallel processing of many items with intelligent aggregation

## Architecture

### Core Components

```
┌─────────────────────────────────────────────┐
│           MetaAgent (Orchestrator)          │
│  - Task decomposition                       │
│  - Worker management                        │
│  - Progress monitoring                      │
│  - Result aggregation                       │
│  - Checkpointing & recovery                 │
└─────────────────────────────────────────────┘
          │                │              │
          ▼                ▼              ▼
    ┌─────────┐      ┌─────────┐    ┌─────────┐
    │Worker 1 │      │Worker 2 │    │Worker 3 │
    │ (A1)    │      │ (A1)    │    │ (A1)    │
    └─────────┘      └─────────┘    └─────────┘
```

#### 1. **MetaAgent** (`dleader_agent/agent/meta_agent.py`)
The main orchestrator that coordinates the entire workflow.

#### 2. **TaskDecomposer**
Uses LLM reasoning to intelligently break down complex queries into subtasks:
- Analyzes the query structure
- Determines optimal batch size
- Creates independent, parallelizable subtasks

#### 3. **WorkerPool**
Manages multiple A1 agent instances:
- Configurable worker count (default: 3)
- Task queue management
- Worker health monitoring
- Automatic retry on failure

#### 4. **ResultAggregator**
Synthesizes results from all subtasks:
- Identifies patterns and themes
- Removes redundancy
- Creates coherent final summary
- Uses LLM for intelligent synthesis

#### 5. **Progress Tracking & Checkpointing**
- Real-time progress monitoring
- Automatic checkpointing after each subtask
- Recovery from failures
- Percentage completion tracking

## Installation & Setup

The MetaAgent is already integrated into the dleader_agent package. No additional installation needed.

```python
from dleader_agent.agent.meta_agent import MetaAgent
```

## Basic Usage

### Simple Example

```python
from dleader_agent.agent.meta_agent import MetaAgent

# Create meta-agent with 5 parallel workers
meta_agent = MetaAgent(
    max_workers=5,
    max_batch_size=50,  # 50 items per subtask
    max_retries=2
)

# Execute complex task
result = meta_agent.execute_complex_task(
    query="Read and analyze 1000 papers about mRNA vaccines"
)

# Access results
print(result.aggregated_result)
print(f"Status: {result.status}")
print(f"Completed: {result.completed_count}/{result.total_count}")
```

### With Progress Callbacks

```python
def progress_callback(update: dict):
    """Handle progress updates"""
    if update["type"] == "progress":
        print(f"Progress: {update['percentage']:.1f}%")
    elif update["type"] == "completed":
        print(f"Done! Result: {update['result']}")

meta_agent = MetaAgent(max_workers=3)
result = meta_agent.execute_complex_task(
    query="Analyze 500 clinical trial reports",
    progress_callback=progress_callback
)
```

### Async Execution

```python
# Start task in background
meta_session_id = meta_agent.execute_complex_task_async(
    query="Process 1000 gene sequences",
    progress_callback=my_callback
)

# Later, check progress
progress = meta_agent.get_progress(meta_session_id)
print(f"Completed: {progress['completed']}/{progress['total']}")
print(f"Percentage: {progress['percentage']:.1f}%")
```

## Configuration Options

### MetaAgent Parameters

```python
MetaAgent(
    max_workers=3,           # Number of parallel A1 agents (default: 3)
    max_batch_size=50,       # Items per subtask (default: 50)
    max_retries=2,           # Retry attempts for failed subtasks (default: 2)
    checkpoint_dir="./checkpoints",  # Checkpoint save location
    agent_config={           # Configuration passed to A1 agents
        "use_tool_retriever": True,
        "download_data_lake": False,
        "llm": "claude-sonnet-4-5-20250929"
    },
    llm=None                 # Custom LLM for decomposition/aggregation
)
```

### Recommended Configurations

**For Large Tasks (1000+ items):**
```python
meta_agent = MetaAgent(
    max_workers=5,
    max_batch_size=100,
    max_retries=3
)
```

**For Time-Sensitive Tasks:**
```python
meta_agent = MetaAgent(
    max_workers=10,  # More parallel workers
    max_batch_size=20,  # Smaller batches for faster feedback
    max_retries=1
)
```

**For Resource-Constrained Environments:**
```python
meta_agent = MetaAgent(
    max_workers=2,
    max_batch_size=25,
    max_retries=1
)
```

## FastAPI Integration

### Adding Endpoints

In your `agent_fastapi_server_multiturn.py`:

```python
from meta_agent_fastapi_endpoints import router as meta_agent_router

# Add to your FastAPI app
app.include_router(meta_agent_router)
```

### Available Endpoints

#### 1. Submit Meta-Task
```bash
POST /meta-task/submit
```
```json
{
  "query": "Read and analyze 1000 papers about cancer treatments",
  "user_id": "user123",
  "max_workers": 5,
  "max_batch_size": 50
}
```

**Response:**
```json
{
  "meta_session_id": "abc-123-def",
  "message": "Meta-task submitted successfully",
  "estimated_subtasks": 20
}
```

#### 2. Check Status
```bash
GET /meta-task/{meta_session_id}/status
```

**Response:**
```json
{
  "meta_session_id": "abc-123-def",
  "status": "running",
  "completed": 15,
  "failed": 0,
  "total": 20,
  "percentage": 75.0,
  "aggregated_result": null,
  "worker_status": {
    "worker_1": {"status": "busy", "current_task": "sub_15"},
    "worker_2": {"status": "idle", "current_task": null}
  }
}
```

#### 3. Get Results
```bash
GET /meta-task/{meta_session_id}/results
```

#### 4. Cancel Task
```bash
POST /meta-task/{meta_session_id}/cancel
```

#### 5. View Subtasks
```bash
GET /meta-task/{meta_session_id}/subtasks
```

## Progress Updates

Progress callbacks receive updates with different types:

### Update Types

1. **status** - General status messages
```python
{
    "type": "status",
    "message": "Starting agent initialization..."
}
```

2. **decomposition** - Task decomposition complete
```python
{
    "type": "decomposition",
    "message": "Task decomposed into 20 subtasks",
    "subtask_count": 20
}
```

3. **progress** - Progress update
```python
{
    "type": "progress",
    "completed": 15,
    "failed": 0,
    "total": 20,
    "percentage": 75.0
}
```

4. **retry** - Subtask retry attempt
```python
{
    "type": "retry",
    "message": "Retrying failed subtask (attempt 2)"
}
```

5. **completed** - Task complete
```python
{
    "type": "completed",
    "message": "Meta-task completed successfully",
    "result": "Final aggregated result..."
}
```

6. **error** - Error occurred
```python
{
    "type": "error",
    "message": "Meta-task failed: connection timeout"
}
```

## Checkpointing & Recovery

The MetaAgent automatically saves checkpoints:

### Checkpoint Location
```
./meta_agent_checkpoints/{meta_session_id}.json
```

### Loading from Checkpoint
```python
# Restore previous session
checkpoint = meta_agent.load_checkpoint("abc-123-def")
if checkpoint:
    print(f"Found checkpoint with {checkpoint['completed_count']} completed tasks")
```

### Recovery Example
```python
try:
    result = meta_agent.execute_complex_task(query)
except Exception as e:
    print(f"Task failed: {e}")
    # Checkpoint is already saved, can resume later
    checkpoint = meta_agent.load_checkpoint(meta_session_id)
```

## Example: Processing 1000 Papers

```python
from dleader_agent.agent.meta_agent import MetaAgent

# Initialize
meta_agent = MetaAgent(
    max_workers=5,
    max_batch_size=50,  # 50 papers per batch = 20 batches total
    max_retries=2
)

# Define callback for real-time updates
def on_progress(update):
    if update["type"] == "progress":
        completed = update["completed"]
        total = update["total"]
        pct = update["percentage"]
        print(f"📊 Progress: {completed}/{total} batches ({pct:.1f}%)")

# Execute
result = meta_agent.execute_complex_task(
    query="""Read and analyze 1000 recent papers about COVID-19 treatments.
    For each paper extract: title, authors, methodology, key findings, conclusions.
    Organize findings by treatment type and identify the most promising approaches.""",
    progress_callback=on_progress
)

# Results
print("\n=== FINAL SYNTHESIS ===")
print(result.aggregated_result)

print(f"\nStatistics:")
print(f"  Total batches: {result.total_count}")
print(f"  Successful: {result.completed_count}")
print(f"  Failed: {result.failed_count}")
print(f"  Duration: {(result.updated_at - result.created_at).total_seconds():.1f}s")
```

## Performance Considerations

### Optimal Worker Count

- **CPU-bound tasks**: Set `max_workers` to number of CPU cores
- **I/O-bound tasks** (API calls, file downloads): Can use more workers (5-10)
- **Memory-intensive**: Reduce workers to prevent OOM

### Batch Size Guidelines

| Total Items | Recommended Batch Size | Rationale |
|-------------|----------------------|-----------|
| 100-200     | 10-20               | Fine-grained progress |
| 200-500     | 25-50               | Balanced |
| 500-1000    | 50-100              | Efficient parallelization |
| 1000+       | 100-200             | Minimize overhead |

### Monitoring Resource Usage

```python
import psutil

def progress_with_monitoring(update):
    if update["type"] == "progress":
        cpu = psutil.cpu_percent()
        mem = psutil.virtual_memory().percent
        print(f"Progress: {update['percentage']:.1f}% | CPU: {cpu}% | Mem: {mem}%")
```

## Error Handling

### Common Scenarios

1. **Subtask Failure**: Automatically retried up to `max_retries` times
2. **Worker Crash**: New worker spawned, task reassigned
3. **Network Issues**: Captured in subtask error, retried
4. **LLM Errors**: Logged, subtask marked as failed

### Manual Error Recovery

```python
# Check failed subtasks
result = meta_agent.execute_complex_task(query)

failed_subtasks = [st for st in result.subtasks if st.status == TaskStatus.FAILED]
for subtask in failed_subtasks:
    print(f"Failed: {subtask.description}")
    print(f"Error: {subtask.error}")

# Optionally re-run specific subtasks manually
```

## Limitations & Future Work

### Current Limitations

1. **Worker Pool**: Fixed at initialization, not dynamically scaled
2. **No Dependency Management**: Subtasks must be independent
3. **Limited Streaming**: Results aggregated at end, not streamed incrementally
4. **Memory**: All results held in memory until aggregation

### Planned Enhancements

- [ ] Dynamic worker pool scaling based on load
- [ ] DAG-based task dependencies
- [ ] Streaming result aggregation
- [ ] Distributed execution across machines
- [ ] Advanced scheduling algorithms
- [ ] Result caching and deduplication

## Testing

Run the example script:

```bash
python meta_agent_example.py
```

Or test specific components:

```python
from dleader_agent.agent.meta_agent import TaskDecomposer

decomposer = TaskDecomposer()
subtasks = decomposer.decompose("Analyze 100 papers about AI", max_batch_size=20)
print(subtasks)  # Should create ~5 subtasks
```

## Troubleshooting

### Issue: Tasks hanging
**Solution**: Check worker logs, ensure LLM API is responsive

### Issue: High memory usage
**Solution**: Reduce `max_workers` or `max_batch_size`

### Issue: Slow aggregation
**Solution**: Consider using faster LLM for aggregation step

### Issue: Subtasks failing repeatedly
**Solution**: Check subtask descriptions, may need manual intervention

## Support & Contributing

For issues or questions:
- GitHub Issues: https://github.com/MinxZ/dleader_agent/issues
- Documentation: See `CLAUDE.md` for general agent usage

## License

Same as dleader_agent main project.

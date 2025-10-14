# MetaAgent Quick Reference Guide

## 🚀 Quick Start

### Parallel Mode (Fast)
```python
from dleader_agent.agent.meta_agent import MetaAgent

meta_agent = MetaAgent(max_workers=5, max_batch_size=50)
result = meta_agent.execute_complex_task(
    "Analyze 1000 papers about vaccines"
)
print(result.aggregated_result)
```

### Sequential Mode (Controlled)
```python
from dleader_agent.agent.meta_agent import MetaAgent

meta_agent = MetaAgent()
result = meta_agent.execute_complex_task_sequential(
    query="Analyze 1000 papers about vaccines",
    items_per_batch=50,  # 50 papers per batch
    pause_between_batches=2  # 2 second pause
)
print(result.aggregated_result)
```

## 📊 Mode Selection

| Scenario | Recommended Mode | Config |
|----------|-----------------|--------|
| **1000+ items, need speed** | Parallel | `max_workers=5-10` |
| **API with rate limits** | Sequential | `pause_between_batches=5` |
| **Low memory system** | Sequential | `items_per_batch=10-20` |
| **Development/testing** | Sequential | `items_per_batch=5` |
| **Batch job overnight** | Parallel | `max_workers=10` |
| **Need immediate feedback** | Sequential | `items_per_batch=10` |

## 🎛️ Parameters

### Parallel Mode
```python
MetaAgent(
    max_workers=5,           # 1-10 workers (default: 3)
    max_batch_size=50,       # Items per batch (default: 50)
    max_retries=2,           # Retry failed tasks (default: 2)
    checkpoint_dir="./checkpoints"
)
```

### Sequential Mode
```python
execute_complex_task_sequential(
    query="Your query",
    items_per_batch=10,      # Items per batch (overrides max_batch_size)
    pause_between_batches=2  # Seconds to pause (default: 0)
)
```

## 📡 API Endpoints

### Submit Task
```bash
# Parallel
POST /meta-task/submit
{
  "query": "Analyze 1000 papers",
  "user_id": "user123",
  "mode": "parallel",
  "max_workers": 5,
  "max_batch_size": 50
}

# Sequential
POST /meta-task/submit
{
  "query": "Analyze 1000 papers",
  "user_id": "user123",
  "mode": "sequential",
  "items_per_batch": 25,
  "pause_between_batches": 2
}
```

### Check Status
```bash
GET /meta-task/{meta_session_id}/status
```

### Get Results
```bash
GET /meta-task/{meta_session_id}/results
```

### Cancel Task
```bash
POST /meta-task/{meta_session_id}/cancel
```

## 🔄 Progress Callbacks

```python
def progress_callback(update):
    type = update["type"]

    if type == "decomposition":
        # Task split into batches
        print(f"Created {update['subtask_count']} batches")

    elif type == "progress":
        # Progress update
        pct = update["percentage"]
        print(f"Progress: {pct:.1f}%")

    elif type == "batch_complete":
        # Sequential mode: batch finished
        print(f"Batch {update['batch_number']} done!")
        print(f"Result preview: {update['batch_result'][:100]}")

    elif type == "completed":
        # All done
        print(update["result"])

# Use it
result = meta_agent.execute_complex_task_sequential(
    query="...",
    progress_callback=progress_callback
)
```

## 🔧 Configuration Examples

### High Speed (Resource-Heavy)
```python
meta_agent = MetaAgent(
    max_workers=10,
    max_batch_size=100,
    agent_config={"llm": "claude-sonnet-4-20250514"}
)
```

### Balanced
```python
meta_agent = MetaAgent(
    max_workers=5,
    max_batch_size=50
)
```

### Low Resource
```python
meta_agent = MetaAgent(max_workers=1)
result = meta_agent.execute_complex_task_sequential(
    query="...",
    items_per_batch=10
)
```

### Rate Limited API
```python
meta_agent = MetaAgent()
result = meta_agent.execute_complex_task_sequential(
    query="...",
    items_per_batch=5,
    pause_between_batches=6  # 10 batches/minute
)
```

## 📁 File Structure

```
dleader_agent/
├── dleader_agent/agent/meta_agent.py          # Core implementation
├── meta_agent_example.py                      # Parallel examples
├── meta_agent_sequential_example.py           # Sequential examples
├── meta_agent_fastapi_endpoints.py            # API endpoints
├── meta_agent_gradio_interface.py             # Web UI
├── test_meta_agent.py                         # Tests
├── META_AGENT_README.md                       # Full docs
├── META_AGENT_MODES_COMPARISON.md             # Mode comparison
└── META_AGENT_QUICK_REFERENCE.md              # This file
```

## 🧪 Testing

```bash
# Run examples
python meta_agent_example.py
python meta_agent_sequential_example.py

# Run tests
pytest test_meta_agent.py -v

# Start Gradio UI
python meta_agent_gradio_interface.py
# Access at http://localhost:7862
```

## 💡 Common Use Cases

### 1. Analyze Many Papers
```python
result = meta_agent.execute_complex_task(
    "Read and summarize 1000 papers about CRISPR gene editing"
)
```

### 2. Process Clinical Data
```python
result = meta_agent.execute_complex_task_sequential(
    query="Extract insights from 500 patient records",
    items_per_batch=25,
    pause_between_batches=1
)
```

### 3. Batch Gene Analysis
```python
result = meta_agent.execute_complex_task(
    "Analyze 300 gene sequences for mutations"
)
```

### 4. Rate-Limited API Calls
```python
result = meta_agent.execute_complex_task_sequential(
    query="Fetch data for 100 proteins from PDB",
    items_per_batch=10,
    pause_between_batches=6  # Respect rate limit
)
```

## 🎯 Decision Tree

```
Need to process many items?
├─ YES → Continue
└─ NO → Use regular A1 agent

Have rate limits?
├─ YES → Use Sequential mode with pause_between_batches
└─ NO → Continue

Need speed?
├─ YES → Use Parallel mode (5-10 workers)
└─ NO → Continue

Need to see results batch-by-batch?
├─ YES → Use Sequential mode
└─ NO → Use Parallel mode

Low memory?
├─ YES → Use Sequential mode
└─ NO → Use Parallel mode
```

## 🐛 Troubleshooting

| Problem | Solution |
|---------|----------|
| Out of memory | Reduce `max_workers` or use Sequential |
| Too slow | Increase `max_workers` or `items_per_batch` |
| Rate limit errors | Use Sequential with `pause_between_batches` |
| Tasks timing out | Increase timeout in `agent_config` |
| Want to stop early | Cancel via API, checkpoint saves progress |

## 📚 More Info

- **Full Documentation**: `META_AGENT_README.md`
- **Mode Comparison**: `META_AGENT_MODES_COMPARISON.md`
- **Examples**: `meta_agent_example.py`, `meta_agent_sequential_example.py`
- **Integration**: `INTEGRATE_META_AGENT.md`
- **Tests**: `test_meta_agent.py`

## 🆘 Support

```python
# Get help
from dleader_agent.agent.meta_agent import MetaAgent
help(MetaAgent)
help(MetaAgent.execute_complex_task)
help(MetaAgent.execute_complex_task_sequential)
```

## ✨ Key Takeaways

1. **Two modes**: Parallel (fast) and Sequential (controlled)
2. **Parallel**: 5-10x faster, uses more resources
3. **Sequential**: One batch at a time, full control
4. **Both return same result**, just different execution
5. **Use Sequential for rate limits** and debugging
6. **Use Parallel for speed** and large-scale tasks
7. **Customize batch size** for optimal performance
8. **Progress callbacks** show real-time updates
9. **Automatic checkpointing** enables recovery
10. **Works with existing A1 agents** seamlessly

---

**Ready to process your 1000-paper analysis!** 🚀

# MetaAgent Execution Modes: Parallel vs Sequential

## Overview

The MetaAgent now supports **two execution modes** for processing complex multi-step tasks:

1. **Parallel Mode** - Multiple workers execute batches simultaneously (faster)
2. **Sequential Mode** - Process one batch at a time (more control)

## Mode Comparison

| Feature | Parallel Mode | Sequential Mode |
|---------|---------------|-----------------|
| **Speed** | ⚡ Fast (5-10x faster) | 🐢 Slower (one at a time) |
| **Resource Usage** | 🔥 High (multiple workers) | ✅ Low (single worker) |
| **Memory** | 📊 Higher | 📊 Lower |
| **Control** | ⚙️ Less control | ⚙️ Full control |
| **Intermediate Results** | ⏰ Available at end | ✅ Immediate visibility |
| **Rate Limiting** | ❌ Difficult | ✅ Built-in support |
| **Debugging** | 🔍 Harder to debug | ✅ Easy to debug |
| **Checkpoint Frequency** | After all complete | After each batch |
| **Best For** | Large-scale tasks | Controlled processing |

## When to Use Each Mode

### Use Parallel Mode When:

✅ **Speed is critical**
- Processing 1000+ items quickly
- Time-sensitive analysis
- Batch jobs that can run overnight

✅ **Resources are available**
- Sufficient memory (2+ GB available)
- Multiple CPU cores
- No strict rate limits

✅ **Tasks are independent**
- No dependencies between items
- Can process in any order
- Results don't affect each other

### Use Sequential Mode When:

✅ **Rate limits exist**
- API rate limits (e.g., 10 requests/minute)
- Database query limits
- Cost constraints on API calls

✅ **Resources are limited**
- Low memory systems
- Shared environments
- Need to minimize CPU usage

✅ **Need immediate feedback**
- Want to see results batch-by-batch
- Need to verify quality early
- May want to stop early if results are good enough

✅ **Debugging or testing**
- Troubleshooting issues
- Testing new queries
- Validating approach before scaling

## Code Examples

### Parallel Mode (Default)

```python
from dleader_agent.agent.meta_agent import MetaAgent

# Create meta-agent
meta_agent = MetaAgent(
    max_workers=5,  # 5 parallel workers
    max_batch_size=50  # 50 items per batch
)

# Execute in parallel
result = meta_agent.execute_complex_task(
    query="Analyze 1000 papers about cancer treatments"
)

# Results available when all batches complete
print(result.aggregated_result)
```

**Output:**
```
Processing 20 batches in parallel with 5 workers...
✅ Batch 1 completed (worker_1)
✅ Batch 2 completed (worker_2)
✅ Batch 3 completed (worker_3)
... (all batches run simultaneously)
📊 Progress: 20/20 (100%)
🎉 Aggregated result: [final summary]
```

### Sequential Mode

```python
from dleader_agent.agent.meta_agent import MetaAgent

# Create meta-agent
meta_agent = MetaAgent()

# Execute sequentially
result = meta_agent.execute_complex_task_sequential(
    query="Analyze 1000 papers about cancer treatments",
    items_per_batch=50,  # 50 papers per batch
    pause_between_batches=2  # 2 second pause between batches
)

# Results available after each batch
print(result.aggregated_result)
```

**Output:**
```
Processing 20 batches sequentially...
📝 Batch 1/20: Analyzing papers 1-50...
✅ Batch 1 result: [partial summary]
⏸️ Pausing for 2 seconds...
📝 Batch 2/20: Analyzing papers 51-100...
✅ Batch 2 result: [partial summary]
... (one batch at a time)
📊 Progress: 20/20 (100%)
🎉 Aggregated result: [final summary]
```

## Batch Size Control

### Parallel Mode

Batch size affects how work is distributed:

```python
# Small batches = more tasks, better parallelization
meta_agent = MetaAgent(max_workers=10, max_batch_size=20)
# 1000 items → 50 batches → distributed across 10 workers

# Large batches = fewer tasks, less overhead
meta_agent = MetaAgent(max_workers=5, max_batch_size=100)
# 1000 items → 10 batches → distributed across 5 workers
```

### Sequential Mode

Batch size controls how many items processed together:

```python
# Small batches = fine-grained progress, more frequent feedback
result = meta_agent.execute_complex_task_sequential(
    query="Process 100 items",
    items_per_batch=10  # 10 batches, see results every 10 items
)

# Large batches = fewer iterations, faster processing
result = meta_agent.execute_complex_task_sequential(
    query="Process 100 items",
    items_per_batch=50  # 2 batches, fewer checkpoints
)
```

## Rate Limiting Examples

### Sequential Mode with Rate Limiting

Perfect for APIs with rate limits:

```python
# Example: API allows 10 requests/minute
# Process 5 items per batch, wait 6 seconds between batches
# = 10 batches/minute = within rate limit

result = meta_agent.execute_complex_task_sequential(
    query="Fetch data from rate-limited API for 100 items",
    items_per_batch=5,
    pause_between_batches=6  # 6 seconds = 10 batches/minute
)
```

### Parallel Mode with Rate Limiting

More complex, requires external rate limiter:

```python
# Not ideal - parallel mode can easily exceed rate limits
# Better to use sequential mode for rate-limited APIs
```

## Callback Progress Updates

Both modes support progress callbacks with different update patterns:

### Parallel Mode Callbacks

```python
def progress_callback(update):
    if update["type"] == "progress":
        # Updates as batches complete (unpredictable order)
        print(f"Progress: {update['percentage']:.1f}%")
        print(f"Completed: {update['completed']}/{update['total']}")

meta_agent.execute_complex_task(query, progress_callback=progress_callback)
```

Updates:
```
Progress: 20% (4/20 batches - unordered)
Progress: 40% (8/20 batches)
Progress: 60% (12/20 batches)
...
```

### Sequential Mode Callbacks

```python
def progress_callback(update):
    if update["type"] == "batch_complete":
        # Updates after EACH batch completes (ordered)
        print(f"Batch {update['batch_number']} done!")
        print(f"Result: {update['batch_result'][:100]}...")

    if update["type"] == "progress":
        print(f"Progress: {update['percentage']:.1f}%")

meta_agent.execute_complex_task_sequential(
    query,
    items_per_batch=10,
    progress_callback=progress_callback
)
```

Updates:
```
Batch 1 done! Result: [first 10 items summary]
Progress: 5% (1/20)
Batch 2 done! Result: [next 10 items summary]
Progress: 10% (2/20)
...
```

## API Usage

### Submit Parallel Task

```bash
curl -X POST http://localhost:8000/meta-task/submit \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Analyze 1000 papers",
    "user_id": "user123",
    "mode": "parallel",
    "max_workers": 5,
    "max_batch_size": 50
  }'
```

### Submit Sequential Task

```bash
curl -X POST http://localhost:8000/meta-task/submit \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Analyze 1000 papers",
    "user_id": "user123",
    "mode": "sequential",
    "items_per_batch": 25,
    "pause_between_batches": 2
  }'
```

## Performance Benchmarks

Based on typical paper analysis tasks (Claude Sonnet 4):

### Parallel Mode (5 workers)

| Items | Batch Size | Batches | Est. Time | Memory |
|-------|------------|---------|-----------|--------|
| 100   | 20         | 5       | 3-5 min   | ~800 MB |
| 500   | 50         | 10      | 10-15 min | ~1.5 GB |
| 1000  | 50         | 20      | 20-30 min | ~2 GB   |

### Sequential Mode

| Items | Batch Size | Batches | Est. Time | Memory |
|-------|------------|---------|-----------|--------|
| 100   | 20         | 5       | 15-20 min | ~400 MB |
| 500   | 50         | 10      | 60-90 min | ~500 MB |
| 1000  | 50         | 20      | 2-3 hours | ~600 MB |

*Times are estimates and vary based on task complexity and API response times*

## Gradio Interface

The Gradio interface supports both modes with dynamic UI:

### Parallel Mode UI

```
Execution Mode: ⚪ Parallel

⚡ Parallel Mode Settings:
  Max Workers: [slider: 1-10] → 5
  Batch Size: [slider: 10-200] → 50
```

### Sequential Mode UI

```
Execution Mode: ⚪ Sequential

🔄 Sequential Mode Settings:
  Items per Batch: [slider: 5-100] → 10
  Pause Between Batches: [slider: 0-30] → 2 seconds
```

The UI automatically shows/hides relevant settings based on selected mode.

## Best Practices

### Parallel Mode Best Practices

1. **Start with 3-5 workers** and increase if needed
2. **Batch size should be 50-100** for optimal distribution
3. **Monitor memory usage** - reduce workers if needed
4. **Use for batch jobs** that can run unattended

### Sequential Mode Best Practices

1. **Start with small batches (10-20)** for frequent feedback
2. **Use pause_between_batches** for rate limiting
3. **Monitor first few batches** before letting it run
4. **Perfect for development** and testing new queries

## Migration Guide

### Converting Parallel to Sequential

```python
# Before (parallel)
result = meta_agent.execute_complex_task(
    query="Process 1000 items"
)

# After (sequential)
result = meta_agent.execute_complex_task_sequential(
    query="Process 1000 items",
    items_per_batch=50,  # Control batch size
    pause_between_batches=0  # No pause unless needed
)
```

### Converting Sequential to Parallel

```python
# Before (sequential)
result = meta_agent.execute_complex_task_sequential(
    query="Process 1000 items",
    items_per_batch=50
)

# After (parallel) - adjust batch size accordingly
result = meta_agent.execute_complex_task(
    query="Process 1000 items"
    # max_batch_size inherited from MetaAgent initialization
)
```

## Troubleshooting

### Parallel Mode Issues

**Problem**: High memory usage
**Solution**: Reduce `max_workers` or `max_batch_size`

**Problem**: Tasks timing out
**Solution**: Increase timeout in agent_config or reduce batch size

**Problem**: Rate limit errors
**Solution**: Switch to sequential mode with pauses

### Sequential Mode Issues

**Problem**: Too slow
**Solution**: Increase `items_per_batch` or switch to parallel mode

**Problem**: Want to stop early
**Solution**: Use Ctrl+C or cancel via API - checkpoint saves progress

**Problem**: Rate limits still exceeded
**Solution**: Increase `pause_between_batches`

## Summary

Choose your mode based on your needs:

- **Need speed?** → Parallel mode
- **Have rate limits?** → Sequential mode
- **Want control?** → Sequential mode
- **Large scale (1000+)?** → Parallel mode
- **Testing/debugging?** → Sequential mode
- **Low resources?** → Sequential mode

Both modes provide the same final result - they just differ in execution strategy!

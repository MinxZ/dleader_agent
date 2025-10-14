# MetaAgent Complete Guide

## 🎯 Overview

The **MetaAgent** is a complete system for processing complex multi-step tasks that involve many items (papers, files, data points). It provides **three key capabilities**:

1. **Parallel Processing** - Fast execution with multiple workers
2. **Sequential Processing** - Controlled one-at-a-time execution
3. **Automatic File Distribution** - Subagents know exactly which files to process

## 📚 Quick Navigation

| Topic | File | Description |
|-------|------|-------------|
| **Getting Started** | This file | Overview and quick start |
| **Full Documentation** | `META_AGENT_README.md` | Complete feature documentation |
| **Mode Comparison** | `META_AGENT_MODES_COMPARISON.md` | Parallel vs Sequential |
| **Quick Reference** | `META_AGENT_QUICK_REFERENCE.md` | Quick lookup guide |
| **File Distribution** | `META_AGENT_FILE_DISTRIBUTION.md` | How file assignment works |
| **Integration** | `INTEGRATE_META_AGENT.md` | Adding to your server |
| **Examples** | `meta_agent_example.py` | Parallel mode examples |
| **Sequential Examples** | `meta_agent_sequential_example.py` | Sequential mode examples |
| **File Examples** | `meta_agent_file_list_example.py` | File distribution examples |

## 🚀 Quick Start (3 Steps)

### Step 1: Import
```python
from dleader_agent.agent.meta_agent import MetaAgent
```

### Step 2: Create MetaAgent
```python
meta_agent = MetaAgent(
    max_workers=5,        # For parallel mode
    max_batch_size=50     # Items per batch
)
```

### Step 3: Execute Task
```python
# Option A: Parallel (Fast)
result = meta_agent.execute_complex_task(
    query="Analyze 1000 papers about cancer: [paper1.pdf, paper2.pdf, ...]"
)

# Option B: Sequential (Controlled)
result = meta_agent.execute_complex_task_sequential(
    query="Analyze 1000 papers about cancer: [paper1.pdf, ...]",
    items_per_batch=50,
    pause_between_batches=2
)

# Access result
print(result.aggregated_result)
```

## 💡 Three Main Features

### 1. Parallel Mode (Speed)

**When to use:** Need fast results, have resources available

```python
meta_agent = MetaAgent(max_workers=5, max_batch_size=50)

result = meta_agent.execute_complex_task(
    "Analyze 1000 papers: [file1.pdf, file2.pdf, ...]"
)
```

**Benefits:**
- ⚡ 5-10x faster
- 📊 Multiple workers simultaneously
- 🎯 Best for large-scale batch jobs

### 2. Sequential Mode (Control)

**When to use:** Rate limits, need control, debugging

```python
meta_agent = MetaAgent()

result = meta_agent.execute_complex_task_sequential(
    query="Analyze 1000 papers: [file1.pdf, ...]",
    items_per_batch=50,        # Control batch size
    pause_between_batches=2    # Respect rate limits
)
```

**Benefits:**
- 🎮 Full control over execution
- ⏸️ Built-in rate limiting
- 👁️ See results batch-by-batch
- 💾 Lower resource usage

### 3. Automatic File Distribution (Clarity)

**Problem:** How do subagents know which files to process?

**Solution:** List files in your query, MetaAgent distributes them automatically!

```python
query = """
Analyze these 100 papers:
[paper_001.pdf, paper_002.pdf, ..., paper_100.pdf]

Extract: title, authors, key findings
"""

result = meta_agent.execute_complex_task(query)
```

**What happens:**
1. MetaAgent detects 100 files
2. Creates 10 batches (10 files each)
3. Each subagent gets explicit file list:
   ```
   Batch 1: paper_001.pdf through paper_010.pdf
   Batch 2: paper_011.pdf through paper_020.pdf
   ...
   ```
4. No confusion about which files to process!

## 📝 Common Use Cases

### Use Case 1: Analyze Many Papers

```python
meta_agent = MetaAgent(max_workers=5, max_batch_size=50)

query = """
Analyze these 1000 papers about COVID-19:
Files: paper_001.pdf, paper_002.pdf, ..., paper_1000.pdf

For each paper extract:
- Title and authors
- Study type and sample size
- Key findings
- Conclusions
"""

result = meta_agent.execute_complex_task(query)

# Result includes aggregated findings from all 1000 papers
```

### Use Case 2: Process Clinical Data (Rate Limited)

```python
meta_agent = MetaAgent()

query = """
Process patient records:
[patient_001.json, patient_002.json, ..., patient_500.json]

Extract: demographics, diagnosis, treatment outcomes
"""

result = meta_agent.execute_complex_task_sequential(
    query=query,
    items_per_batch=10,          # 10 patients at a time
    pause_between_batches=5      # 5 second pause (rate limiting)
)
```

### Use Case 3: Web Scraping

```python
meta_agent = MetaAgent(max_workers=3, max_batch_size=20)

query = """
Scrape data from:
https://example.com/page1.html
https://example.com/page2.html
...
https://example.com/page100.html

Extract: product names, prices, descriptions
"""

result = meta_agent.execute_complex_task(query)
```

### Use Case 4: Gene Sequence Analysis

```python
meta_agent = MetaAgent(max_workers=5, max_batch_size=50)

query = """
Analyze gene sequences:
./data/seq_001.fasta, ./data/seq_002.fasta, ..., ./data/seq_1000.fasta

Identify mutations and calculate conservation scores
"""

result = meta_agent.execute_complex_task(query)
```

## 🎨 Supported File Formats

The MetaAgent automatically detects files in these formats:

```python
# 1. List format
"[file1.pdf, file2.pdf, file3.pdf]"

# 2. Comma-separated with keyword
"Files: paper1.pdf, paper2.pdf, paper3.pdf"

# 3. File paths
"./data/file1.csv, /path/to/file2.txt"

# 4. URLs
"https://example.com/paper1.pdf, https://example.com/paper2.pdf"

# 5. Mixed
"Local: file1.pdf, URL: https://example.com/file2.pdf, Path: ./data/file3.csv"
```

## ⚙️ Configuration Guide

### For Speed (Parallel)
```python
MetaAgent(
    max_workers=10,       # More workers = faster
    max_batch_size=100,   # Larger batches = less overhead
    max_retries=2
)
```

### For Control (Sequential)
```python
MetaAgent()  # Just use defaults

# Then use sequential mode with custom settings
result = meta_agent.execute_complex_task_sequential(
    query="...",
    items_per_batch=10,          # Small batches = frequent feedback
    pause_between_batches=5      # Respect rate limits
)
```

### For Rate Limits
```python
# Example: API allows 10 requests/minute
# Process 5 items per batch, wait 6 seconds = 10 batches/minute

result = meta_agent.execute_complex_task_sequential(
    query="...",
    items_per_batch=5,
    pause_between_batches=6      # 6 seconds = stay under limit
)
```

### For Low Memory
```python
MetaAgent(max_workers=1)  # Single worker

result = meta_agent.execute_complex_task_sequential(
    query="...",
    items_per_batch=10  # Small batches
)
```

## 📊 Progress Monitoring

Both modes support progress callbacks:

```python
def progress_callback(update):
    type = update["type"]

    if type == "files_detected":
        # File detection
        print(f"📁 Found {update['file_count']} files")

    elif type == "decomposition":
        # Task split into batches
        print(f"🔍 Created {update['subtask_count']} batches")

    elif type == "progress":
        # Progress update
        pct = update['percentage']
        print(f"📊 Progress: {pct:.1f}%")

    elif type == "batch_complete":
        # Sequential: batch finished
        print(f"✅ Batch {update['batch_number']} done")
        print(f"Preview: {update['batch_result'][:100]}")

    elif type == "completed":
        # All done!
        print(f"✅ Complete!")
        print(update['result'])

# Use it
result = meta_agent.execute_complex_task(
    query="...",
    progress_callback=progress_callback
)
```

## 🌐 API Usage

### Submit Task
```bash
curl -X POST http://localhost:8000/meta-task/submit \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Analyze 1000 papers: [file1.pdf, ...]",
    "user_id": "user123",
    "mode": "parallel",
    "max_workers": 5,
    "max_batch_size": 50
  }'
```

### Check Status
```bash
curl http://localhost:8000/meta-task/{session_id}/status
```

### Get Results
```bash
curl http://localhost:8000/meta-task/{session_id}/results
```

## 🎯 Decision Tree

```
How many items to process?
├─ < 100 items
│  └─ Use regular A1 agent (no MetaAgent needed)
│
└─ 100+ items
   ├─ Have API rate limits?
   │  ├─ YES → Use Sequential mode with pause_between_batches
   │  └─ NO → Continue
   │
   ├─ Need speed?
   │  ├─ YES → Use Parallel mode (5-10 workers)
   │  └─ NO → Continue
   │
   ├─ Want to see results batch-by-batch?
   │  ├─ YES → Use Sequential mode (small batches)
   │  └─ NO → Continue
   │
   ├─ Low memory system?
   │  ├─ YES → Use Sequential mode
   │  └─ NO → Use Parallel mode
   │
   └─ Default → Use Parallel mode (fastest)
```

## ✅ Checklist: Before You Start

- [ ] I have a list of files/items to process (100+)
- [ ] I know if I have rate limits
- [ ] I've chosen mode: Parallel (speed) or Sequential (control)
- [ ] I've configured batch size appropriately
- [ ] My query includes file list in one of the supported formats
- [ ] I have a progress callback for monitoring (optional)

## 🔧 Integration Checklist

- [ ] `dleader_agent/agent/meta_agent.py` installed
- [ ] API endpoints added (if using FastAPI)
- [ ] Gradio interface available (if using UI)
- [ ] Environment variables configured
- [ ] Tested with small file list first

## 📖 Example Template

Copy and customize:

```python
from dleader_agent.agent.meta_agent import MetaAgent

# 1. Create meta-agent
meta_agent = MetaAgent(
    max_workers=5,           # Adjust based on needs
    max_batch_size=50        # Adjust based on needs
)

# 2. Define your query with file list
query = """
[YOUR TASK DESCRIPTION]

Files: [YOUR FILE LIST]

[WHAT TO EXTRACT/ANALYZE]
"""

# 3. Define progress callback (optional)
def on_progress(update):
    if update["type"] == "progress":
        print(f"Progress: {update['percentage']:.1f}%")

# 4. Execute
# Option A: Parallel (fast)
result = meta_agent.execute_complex_task(
    query=query,
    progress_callback=on_progress
)

# Option B: Sequential (controlled)
result = meta_agent.execute_complex_task_sequential(
    query=query,
    items_per_batch=10,
    pause_between_batches=0,
    progress_callback=on_progress
)

# 5. Access results
print(f"Status: {result.status}")
print(f"Completed: {result.completed_count}/{result.total_count}")
print(f"Result: {result.aggregated_result}")
```

## 🎓 Learning Path

1. **Start**: Read this guide
2. **Understand**: Check `META_AGENT_README.md` for full details
3. **Compare**: Read `META_AGENT_MODES_COMPARISON.md` to choose mode
4. **Files**: Read `META_AGENT_FILE_DISTRIBUTION.md` for file handling
5. **Practice**: Run `meta_agent_example.py`
6. **Sequential**: Try `meta_agent_sequential_example.py`
7. **Files**: Experiment with `meta_agent_file_list_example.py`
8. **Integrate**: Follow `INTEGRATE_META_AGENT.md` to add to your server
9. **Reference**: Keep `META_AGENT_QUICK_REFERENCE.md` handy

## 🐛 Troubleshooting

| Problem | Solution |
|---------|----------|
| Files not detected | Check format, add file extensions |
| Out of memory | Reduce `max_workers` or use Sequential |
| Too slow | Increase `max_workers`, use Parallel |
| Rate limit errors | Use Sequential with `pause_between_batches` |
| Tasks timing out | Increase timeout in `agent_config` |
| Wrong files processed | Test with `extract_file_list()` first |

## 📞 Support

- **Documentation**: Check the files listed in "Quick Navigation" above
- **Examples**: Run the example scripts
- **Issues**: GitHub Issues (MinxZ/dleader_agent)
- **Tests**: `pytest test_meta_agent.py -v`

## 🎉 Summary

The MetaAgent provides **three powerful capabilities**:

1. **⚡ Parallel Processing**
   - Fast execution (5-10x speedup)
   - Multiple workers
   - Best for large-scale tasks

2. **🎮 Sequential Processing**
   - Full control
   - Built-in rate limiting
   - See results batch-by-batch
   - Lower resource usage

3. **📁 Automatic File Distribution**
   - List files in your query
   - MetaAgent detects and distributes them
   - Each subagent knows exactly which files to process
   - No confusion, no duplication

**Ready to process your 1000-paper analysis!** 🚀

### Quick Start Command

```python
from dleader_agent.agent.meta_agent import MetaAgent

meta_agent = MetaAgent(max_workers=5, max_batch_size=50)

result = meta_agent.execute_complex_task("""
Analyze these papers: [paper1.pdf, paper2.pdf, ..., paper1000.pdf]
Extract key findings from each paper.
""")

print(result.aggregated_result)
```

That's it! Each subagent will know exactly which papers to process. 🎯

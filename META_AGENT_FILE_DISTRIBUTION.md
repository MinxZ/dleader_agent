# MetaAgent File Distribution

## Problem Solved

**Question:** How do subagents know which specific files/papers to process?

**Answer:** The MetaAgent now automatically **extracts file lists from your query** and **explicitly assigns files to each subagent**!

## How It Works

### 1. **Automatic File Detection**

The MetaAgent scans your query for:
- File paths: `./data/paper1.pdf`, `/path/to/file.csv`
- URLs: `https://example.com/paper.pdf`
- List format: `[file1.pdf, file2.pdf, file3.pdf]`
- Comma-separated: `Files: paper1.pdf, paper2.pdf`
- Mixed formats: Any combination of the above

### 2. **Intelligent Distribution**

Once files are detected:
1. Files are split into batches (e.g., 10 files per batch)
2. Each subagent receives an **explicit list** of files to process
3. Subagents know exactly which files are their responsibility

### 3. **Clear Instructions**

Each subagent's task includes:
- The main task description
- Batch number (e.g., "batch 1/10")
- Explicit list of file paths/URLs
- Instructions to access and process those specific files

## Supported File Formats

The system detects these patterns:

### 1. List Format (Brackets)
```python
query = """
Analyze these papers:
[paper1.pdf, paper2.pdf, paper3.pdf, paper4.pdf, paper5.pdf]

Extract key findings from each paper.
"""
```

**Extracted:** `['paper1.pdf', 'paper2.pdf', 'paper3.pdf', 'paper4.pdf', 'paper5.pdf']`

### 2. Keyword + Comma-Separated
```python
query = """
Process clinical trial data:

Files: trial_001.pdf, trial_002.pdf, trial_003.pdf,
       trial_004.pdf, trial_005.pdf, trial_006.pdf

Extract patient outcomes and adverse events.
"""
```

**Extracted:** `['trial_001.pdf', 'trial_002.pdf', 'trial_003.pdf', ...]`

### 3. Full File Paths
```python
query = """
Analyze gene expression data:
./data/samples/sample_001.csv
./data/samples/sample_002.csv
./data/samples/sample_003.csv
/absolute/path/sample_004.csv

Calculate differential expression.
"""
```

**Extracted:** `['./data/samples/sample_001.csv', './data/samples/sample_002.csv', ...]`

### 4. URLs
```python
query = """
Download and analyze these papers:
https://arxiv.org/pdf/2301.00001.pdf
https://arxiv.org/pdf/2301.00002.pdf
https://arxiv.org/pdf/2301.00003.pdf

Summarize main contributions.
"""
```

**Extracted:** `['https://arxiv.org/pdf/2301.00001.pdf', ...]`

### 5. Mixed Formats
```python
query = """
Analyze research materials:
- Local: ./papers/intro.pdf, ./papers/methods.pdf
- URLs: https://example.com/paper1.pdf, https://example.com/paper2.pdf
- Data: /data/dataset1.csv, /data/dataset2.csv
"""
```

**Extracted:** All files from all formats

## Example: Complete Flow

### Your Query
```python
query = """
Analyze these 30 research papers about CRISPR:
[paper_001.pdf, paper_002.pdf, paper_003.pdf, ..., paper_030.pdf]

For each paper extract:
- Title and authors
- Main research question
- Key findings
- Methodology
"""

meta_agent = MetaAgent(max_workers=3, max_batch_size=10)
result = meta_agent.execute_complex_task(query)
```

### What Happens

#### Step 1: File Detection
```
📁 Detected 30 files in query
Files: paper_001.pdf, paper_002.pdf, paper_003.pdf, ...
```

#### Step 2: Task Decomposition
```
🔍 Task decomposed into 3 sequential batches
Each batch will process specific files
```

#### Step 3: File Distribution

**Subagent 1 receives:**
```
Analyze these research papers about CRISPR:

Process these specific files (batch 1/3):
  - paper_001.pdf
  - paper_002.pdf
  - paper_003.pdf
  - paper_004.pdf
  - paper_005.pdf
  - paper_006.pdf
  - paper_007.pdf
  - paper_008.pdf
  - paper_009.pdf
  - paper_010.pdf

For each file:
1. Access the file at the path/URL provided
2. Complete the requested analysis
3. Include the filename in your results

For each paper extract:
- Title and authors
- Main research question
- Key findings
- Methodology
```

**Subagent 2 receives:**
```
Same task description

Process these specific files (batch 2/3):
  - paper_011.pdf
  - paper_012.pdf
  ...
  - paper_020.pdf
```

**Subagent 3 receives:**
```
Same task description

Process these specific files (batch 3/3):
  - paper_021.pdf
  - paper_022.pdf
  ...
  - paper_030.pdf
```

#### Step 4: Execution
- Each subagent processes only its assigned files
- No confusion about which files to process
- Results include file names for traceability

#### Step 5: Aggregation
- All results combined
- 30 papers analyzed
- Clear attribution to source files

## Usage Examples

### Example 1: Research Paper Analysis
```python
from dleader_agent.agent.meta_agent import MetaAgent

meta_agent = MetaAgent(max_workers=5, max_batch_size=10)

query = """
Analyze these 100 papers about COVID-19 vaccines:
[paper_001.pdf, paper_002.pdf, ..., paper_100.pdf]

For each paper extract:
- Vaccine type
- Trial phase
- Efficacy rate
- Adverse events
"""

result = meta_agent.execute_complex_task(query)
print(result.aggregated_result)
```

**Output:** Each subagent processes 10 papers, knows exactly which files to read.

### Example 2: Clinical Data Processing
```python
meta_agent = MetaAgent()

query = """
Process patient records:

Files: patient_001.json, patient_002.json, patient_003.json,
       patient_004.json, patient_005.json, ...patient_050.json

Extract: demographics, diagnosis, treatment outcomes
"""

result = meta_agent.execute_complex_task_sequential(
    query=query,
    items_per_batch=10,  # 10 patients per batch
    pause_between_batches=1
)
```

**Output:** Each batch processes 10 specific patient files.

### Example 3: Web Scraping
```python
meta_agent = MetaAgent(max_workers=3, max_batch_size=20)

query = """
Scrape data from these URLs:
https://example.com/page1.html
https://example.com/page2.html
...
https://example.com/page100.html

Extract product names, prices, and descriptions.
"""

result = meta_agent.execute_complex_task(query)
```

**Output:** Each subagent scrapes specific URLs from its batch.

## Behind the Scenes

### File Extraction Logic

```python
from dleader_agent.agent.meta_agent import TaskDecomposer

decomposer = TaskDecomposer()

# Extract files from query
files = decomposer.extract_file_list(query)
# Returns: ['file1.pdf', 'file2.pdf', ...]

# Create batches with file assignments
subtasks = decomposer.decompose_with_files(query, files, max_batch_size=10)
# Returns: List of subtask descriptions, each with specific file list
```

### Detection Patterns

The system uses regex patterns to find:

1. **URLs**: `https?://[^\s,\]\)\"]+`
2. **File paths**: `(?:\.\/|\/)?(?:[\w\-\.]+\/)*[\w\-\.]+\.(pdf|txt|csv|...)`
3. **List format**: `\[(.*?)\]`
4. **Keyword format**: `Files:|Papers:` followed by comma-separated items

### Batch Distribution Algorithm

```python
# Given 25 files and batch_size=10:
# Batch 1: files[0:10]   = files 1-10
# Batch 2: files[10:20]  = files 11-20
# Batch 3: files[20:25]  = files 21-25

for i in range(num_batches):
    start = i * batch_size
    end = min((i+1) * batch_size, total_files)
    batch_files = files[start:end]
    # Assign to subagent
```

## Benefits

### ✅ No Ambiguity
- Each subagent knows exactly which files to process
- No duplication of work
- No files missed

### ✅ Traceability
- Results include source file names
- Easy to trace findings back to specific papers
- Clear audit trail

### ✅ Flexibility
- Works with any file format
- Supports local paths and URLs
- Handles mixed formats

### ✅ Scalability
- Process hundreds or thousands of files
- Automatic batching
- Efficient distribution

## Progress Tracking

You'll see these events:

```python
def progress_callback(update):
    if update["type"] == "files_detected":
        print(f"📁 Found {update['file_count']} files")
        print(f"   First 10: {update['files']}")

    elif update["type"] == "decomposition":
        print(f"🔍 Created {update['subtask_count']} batches")

    elif update["type"] == "batch_complete":
        # Sequential mode: see which files were processed
        print(f"✅ Completed batch {update['batch_number']}")
```

## Limitations & Tips

### Current Limitations

1. **File extensions required**: Files must have extensions (.pdf, .csv, etc.)
2. **No wildcards**: Cannot use `*.pdf` patterns (yet)
3. **No directories**: Individual files only, not folder paths

### Tips for Best Results

1. **Be explicit**: List all files individually
2. **Use consistent naming**: `paper_001.pdf` better than `paper1.pdf`
3. **Include paths**: `./data/file.pdf` better than `file.pdf`
4. **Separate concerns**: Put file list separate from task description

### Good Example
```python
query = """
Task: Analyze these papers for key findings

Files:
paper_001.pdf
paper_002.pdf
paper_003.pdf

For each paper extract: title, authors, conclusions
"""
```

### Better Example
```python
query = """
Analyze these papers for key findings:
[paper_001.pdf, paper_002.pdf, paper_003.pdf]

Extract: title, authors, conclusions
"""
```

## Testing File Detection

Test what files will be detected:

```python
from dleader_agent.agent.meta_agent import TaskDecomposer

decomposer = TaskDecomposer()

# Your query
query = "Your query with files..."

# See what's detected
files = decomposer.extract_file_list(query)
print(f"Detected {len(files)} files:")
for f in files:
    print(f"  - {f}")

# See how they'll be distributed
subtasks = decomposer.decompose_with_files(query, files, max_batch_size=10)
print(f"\nWill create {len(subtasks)} batches")
for i, subtask in enumerate(subtasks, 1):
    print(f"\nBatch {i}:")
    print(subtask[:200] + "...")
```

## Summary

🎯 **Problem**: Subagents didn't know which files to process
✅ **Solution**: Automatic file detection and explicit assignment

🎯 **Before**: "Analyze 1000 papers" (Which ones?)
✅ **After**: "Process these specific files: [explicit list]"

🎯 **Result**: Each subagent knows exactly what to do!

### Key Takeaways

1. **Just list your files** in the query (any format)
2. **MetaAgent detects them** automatically
3. **Files are distributed** to subagents explicitly
4. **Each subagent knows** which files are theirs
5. **Results are traceable** back to source files

Now your subagents will always know which files they're working on! 🎉

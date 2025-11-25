# Automatic Template Matching Detection

## Overview

The system now **automatically decides** whether to use template matching based on query complexity using an LLM (same model as the main agent). This eliminates the need for users to manually specify `use_template=True/False`.

## How It Works

### LLM-Based Detection

The system uses **the same LLM as the main agent** (currently Claude Sonnet 4.5) to analyze each query and determine if it requires workflow template matching:

1. **Simple queries** (returns `NO`, skips template matching):
   - Simple math expressions: `1+1`, `2*3`
   - Greetings: `hello`, `hi there`
   - Basic questions: `what is DNA`, `help`
   - Single-word queries

2. **Complex queries** (returns `YES`, uses template matching):
   - Biomedical analysis workflows
   - Multi-step data processing
   - Statistical analysis or modeling
   - Tasks requiring multiple tools

### Implementation Details

**Function:** `should_use_template_matching(query: str, language: str = "en") -> bool`
- **Location:** `agent_fastapi_server_multiturn.py:84`
- **Model:** Same as main agent (currently `claude-sonnet-4-5-20250929`)
- **Max tokens:** 10 (just "YES" or "NO")
- **Temperature:** 0 (deterministic)
- **Fallback:** If LLM fails, defaults to `True` (safer to use template matching)

### API Changes

Both endpoints now accept `use_template` as **optional**:

#### `/chat-queue` (Start new session)
```python
use_template: Optional[bool] = Form(None)
```
- `None` (default): LLM automatically decides
- `True`: Force template matching
- `False`: Skip template matching

#### `/continue-session` (Continue existing session)
```python
use_template: Optional[bool] = Form(None)
```
- Same behavior as `/chat-queue`

### Performance

- **LLM call time:** ~100-500ms (same model as main agent)
- **Cost:** Uses same API key and model as main agent for consistency
- **Fallback:** If LLM fails, uses template matching (safe default)

## Testing

Run the test suite to verify detection works correctly:

```bash
python test_template_detection.py
```

### Test Results

All 19 test cases pass:
- ✓ Simple queries correctly identified (no template matching)
- ✓ Complex queries correctly identified (use template matching)
- ✓ Zero errors

## Examples

### Simple Queries (No Template Matching)
```
Query: "1+1"                 → use_template=False
Query: "hello"               → use_template=False
Query: "what is DNA"         → use_template=False
Query: "calculate 5+3"       → use_template=False
```

### Complex Queries (Use Template Matching)
```
Query: "Perform differential gene expression analysis on RNA-seq data"
→ use_template=True

Query: "I want to analyze protein-protein interactions in cancer cells"
→ use_template=True

Query: "Run a machine learning pipeline for drug discovery"
→ use_template=True
```

## Benefits

1. **Better UX:** Users don't need to understand template matching
2. **Intelligent:** LLM understands semantic meaning, not just keywords
3. **Consistent:** Uses the same LLM as main agent for uniform behavior
4. **Fast:** Quick classification with minimal overhead
5. **Safe:** Defaults to template matching if detection fails
6. **Multi-language:** Supports both English and Japanese

## Migration

Existing code continues to work:
- If `use_template` is explicitly passed, it's used as-is
- If `use_template` is omitted (or `None`), LLM decides automatically

No breaking changes!

## Configuration

The detection uses the same `ANTHROPIC_API_KEY` environment variable as the main agent.

## Logging

The system logs LLM decisions:
```
INFO: LLM decided: SKIP template matching for query: 1+1
INFO: LLM decided: USE template matching for query: Perform differential gene expression...
```

This helps with debugging and understanding the system's behavior.

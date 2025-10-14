# Template Reference Feature - Quick Start Guide

## What This Feature Does

When you ask the agent to perform a task, it now automatically checks if your request matches any of the pre-built workflow templates stored in the cloud (MongoDB). If it finds a match, it enhances your query with detailed instructions from that template, giving you better results without having to provide detailed instructions yourself.

## How to Use

**You don't need to do anything special!** The feature works automatically in the background.

Just submit your query as normal, and if it matches a template, you'll see a message like:

```
✓ Matched to template: Data Merge (confidence: high)
```

## Example Queries That Will Match Templates

### Data Merging

**Your Query:**
```
I need to merge two CSV files with different column names
```

**What Happens:**
- Automatically matches "Data Merge" template
- Agent receives comprehensive instructions on:
  - Handling multiple file formats
  - Column mapping strategies
  - Data standardization
  - Memory management for large datasets

### ASO Design

**Your Query:**
```
Help me design an antisense oligonucleotide for BRCA1
```

**What Happens:**
- Matches "ASO Design" template
- Agent receives guidance on:
  - Target RNA sequence analysis
  - ASO optimization strategies
  - Chemical modification selection

### QSPR Analysis

**Your Query:**
```
Can you perform QSPR analysis on drug-like compounds?
```

**What Happens:**
- Matches "QSPR Workflow" template
- Agent receives instructions on:
  - Dataset selection and filtering
  - Molecular descriptor calculation
  - Property relationship modeling

## Available Templates

Currently available templates (automatically loaded from cloud):

1. **QSPR Workflow** (~15 min, 13 tools)
   - Quantitative Structure-Property Relationship analysis

2. **ASO Design** (~8 min, 15 tools)
   - Antisense oligonucleotide design

3. **Data Curation (CYP)** (~8 min, 8 tools)
   - CYP450 experimental data extraction

4. **Patent Summarize** (~15 min, 10 tools)
   - Patent analysis for ASO modifications

5. **Data Merge** (~6 min, 12 tools)
   - Multi-format dataset merging

## When Templates DON'T Match

Templates only match **workflow requests**, not informational queries.

**Will NOT Match:**
- "What is QSPR?" (informational question)
- "How do I install RDKit?" (technical support)
- "Help me analyze data" (too vague)

**Will Match:**
- "Perform QSPR analysis on my compounds" (workflow request)
- "I need to merge datasets" (workflow request)
- "Design an ASO for my target gene" (workflow request)

## Checking if Your Query Matched

Look for these progress messages:

**Template Matched:**
```
✓ Checking for relevant workflow templates...
✓ Matched to template: Data Merge (confidence: high)
✓ Agent processing started...
```

**No Match:**
```
✓ Checking for relevant workflow templates...
✓ Agent processing started...
```

(No "Matched to template" message means no match was found)

## Benefits

### For You

✅ **Better Results**: Agent gets comprehensive workflow guidance
✅ **Save Time**: No need to provide detailed instructions
✅ **Consistency**: Standardized approaches to common tasks
✅ **Best Practices**: Templates encode expert knowledge

### Examples of Improvement

**Without Template:**
- You: "Merge two CSV files"
- Agent: Performs basic merge, might miss edge cases

**With Template:**
- You: "Merge two CSV files"
- Agent receives 3000+ character template with:
  - Column mapping strategies
  - Missing data handling
  - Data type standardization
  - Memory management for large files
  - Quality checks
- Result: More robust, production-ready merge

## Viewing Available Templates

You can view all available templates via the API:

```bash
curl http://your-server:8001/templates
```

Or visit the templates endpoint in your browser:
```
http://your-server:8001/templates
```

**Response includes:**
- Template titles
- Descriptions
- Estimated running times
- Number of tools used
- Whether they have detailed prompts

## FAQ

### Q: Do I need to mention the template name in my query?

**A:** No! The system automatically detects which template (if any) matches your query.

### Q: Can I disable this feature?

**A:** It works automatically, but if no template matches your query, it has zero effect. For matched queries, the enhancement is beneficial.

### Q: What if I want to do something slightly different from the template?

**A:** The LLM is smart enough to adapt the template to your specific needs. For example:
- Template is for multiple formats, you mention only CSV → Template adapts to focus on CSV
- Template is generic, you mention specific properties → Template adapts to your properties

### Q: How does this affect processing time?

**A:** Minimal impact (~1-2 seconds for template matching). The improved results are worth it!

### Q: Where are the templates stored?

**A:** In MongoDB (cloud storage), so they:
- Persist across server restarts
- Are shared across all server instances
- Can be updated without code changes

### Q: Can I request new templates?

**A:** Yes! Contact your admin to add new workflow templates to MongoDB.

### Q: What if MongoDB is down?

**A:** The system has a local file fallback, but this is only for emergencies. Normally, templates come from cloud storage.

## Technical Details (For Developers)

### How It Works

1. **Template Fetching**: Retrieves templates from MongoDB on first request, then caches for 5 minutes
2. **Matching**: Uses LLM to semantically match your query to templates (with keyword fallback)
3. **Augmentation**: Appends relevant template prompt to your query
4. **Processing**: Agent receives enhanced query and produces better results

### Files Involved

- `template_retriever.py` - Core retrieval and matching logic
- `agent_fastapi_server_multiturn.py` - Integration point (lines 1285-1321)
- MongoDB collection: `dleader_agent.workflow_templates`

### Testing

Run the test suite:
```bash
python test_template_retriever.py
```

### Documentation

- **Full Documentation**: `TEMPLATE_REFERENCE_FEATURE.md`
- **Implementation Summary**: `TEMPLATE_REFERENCE_IMPLEMENTATION_SUMMARY.md`
- **Quick Start**: `TEMPLATE_REFERENCE_QUICKSTART.md` (this file)

## Summary

The template reference feature makes your queries more effective by automatically applying expert workflow guidance when appropriate. You don't need to change how you interact with the agent - it just works better for common tasks!

**Key Points:**
- ✅ Works automatically
- ✅ No changes needed to your queries
- ✅ Only enhances queries that match known workflows
- ✅ Improves results for common biomedical research tasks
- ✅ Templates stored in cloud (MongoDB)
- ✅ Minimal performance impact

**Happy researching!** 🧬🔬

# Template Reference Feature for Agent Query Augmentation

## Overview

This feature enables the dleader_agent to automatically reference and apply workflow template prompts to user queries, similar to how it currently selects relevant tools for tasks. When a user submits a query that matches a known workflow template, the agent can augment the query with the full template prompt to provide better guidance and results.

## Key Features

✅ **Cloud-Based Template Storage**: Templates are fetched from MongoDB (cloud storage)
✅ **Intelligent Matching**: LLM-based matching with keyword fallback
✅ **Automatic Query Augmentation**: User queries are enhanced with template prompts
✅ **Template Modification**: Suggests adaptations when user needs differ slightly from template
✅ **Seamless Integration**: Works transparently within the existing agent workflow

## Architecture

### Components

1. **TemplateRetriever** (`template_retriever.py`)
   - Fetches templates from MongoDB cloud storage
   - Matches user queries to relevant templates using LLM
   - Augments queries with template prompts
   - Caches templates for performance (5-minute TTL)

2. **FastAPI Integration** (`agent_fastapi_server_multiturn.py`)
   - Initializes global template retriever instance
   - Integrates template matching into request processing
   - Provides progress updates for template matching

3. **MongoDB Storage**
   - Database: `dleader_agent` (or value from `SESSION_DB_NAME` env var)
   - Collection: `workflow_templates`
   - Fields: `title`, `description`, `running_time`, `tools`, `prompt`

### Data Flow

```
User Query
    ↓
Template Retriever
    ↓
[Fetch templates from MongoDB]
    ↓
[LLM-based matching]
    ↓
[If matched: Augment query with template prompt]
    ↓
Enhanced Query → Agent Processing
```

## Template Structure

Each template in MongoDB has the following structure:

```json
{
  "title": "Data Merge",
  "running_time": "~6 min",
  "tools": 12,
  "description": "Intelligently merge multi-format experimental datasets...",
  "prompt": "You have been given experimental datasets from different researchers..."
}
```

**Fields:**
- `title`: Template name (used as unique identifier)
- `running_time`: Estimated execution time
- `tools`: Number of tools typically used
- `description`: Brief summary of what the template does
- `prompt`: (Optional) Detailed prompt for the agent (this is what gets appended to user queries)

## How It Works

### 1. Template Fetching

When the agent starts processing a request, the template retriever:

1. Checks cache (5-minute TTL)
2. If cache miss, fetches templates from MongoDB:
   ```python
   collection = get_mongodb_collection("dleader_agent", "workflow_templates")
   templates = list(collection.find({}).sort("title", 1))
   ```
3. Falls back to local file only if MongoDB is unavailable (not recommended for production)

### 2. Template Matching

The retriever uses a two-stage matching process:

**Stage 1: LLM-Based Matching** (Primary)
- Sends user query + all template descriptions to LLM
- LLM analyzes semantic similarity and intent
- Returns match result with confidence level (high/medium/low/none)
- Can suggest modifications to template for specific user needs

**Stage 2: Keyword Matching** (Fallback)
- Simple keyword scoring if LLM unavailable
- Matches words in query against template titles and descriptions
- Requires score > 3 to match

**Example Matches:**
- "merge two CSV files" → Data Merge template (high confidence)
- "design ASO for BRCA1" → ASO Design template (high confidence)
- "analyze molecular properties" → QSPR Workflow (medium confidence, with modification)

**Example Non-Matches:**
- "What is QSPR?" → No match (informational query, not workflow request)
- "How do I install RDKit?" → No match (technical support, not workflow)

### 3. Query Augmentation

When a template matches, the user's query is augmented:

**Original Query:**
```
I want to merge three CSV files with different column names
```

**Augmented Query:**
```
I want to merge three CSV files with different column names

[WORKFLOW TEMPLATE REFERENCE: Data Merge]
You have been given experimental datasets from different researchers in MULTIPLE FILE FORMATS:
    - CSV files (comma-separated values)
    - Excel files (XLSX with multiple sheets)
    - Markdown files (MD with formatted tables)
    - Text files (TXT with unstructured lab notes)

[... full template prompt continues ...]

[TEMPLATE MODIFICATION NOTE]
Focus on CSV files specifically, as the user has three CSV files to merge.
```

The augmented query is then passed to `agent.go()` for processing.

## Implementation Details

### File: `template_retriever.py`

**Class: `TemplateRetriever`**

**Methods:**
- `fetch_templates_from_mongodb()`: Fetches templates from MongoDB cloud
- `get_templates()`: Returns cached or fresh templates
- `match_template(query, templates)`: Matches query to best template
- `augment_query_with_template(query, match_result)`: Augments query with template prompt
- `_format_templates_for_prompt(templates)`: Formats templates for LLM
- `_simple_keyword_match(query, templates)`: Fallback keyword matching

### File: `agent_fastapi_server_multiturn.py`

**Integration Points:**

1. **Import** (line 57):
   ```python
   from template_retriever import TemplateRetriever
   ```

2. **Global Instance** (lines 2387-2400):
   ```python
   template_retriever = None

   def get_template_retriever():
       global template_retriever
       if template_retriever is None:
           template_retriever = TemplateRetriever()
       return template_retriever
   ```

3. **Query Augmentation** (lines 1285-1321):
   ```python
   # In run_agent() function
   base_message = user_request.enhanced_message

   # Template matching & augmentation
   retriever = get_template_retriever()
   if retriever:
       match_result = retriever.match_template(base_message)
       if match_result.get("matched"):
           augmentation_result = retriever.augment_query_with_template(
               base_message, match_result
           )
           base_message = augmentation_result["augmented_query"]
   ```

## Configuration

### Environment Variables

- `SESSION_DB_NAME`: MongoDB database name (default: `dleader_agent`)
- MongoDB connection configured via existing `s3_mongodb` module

### Template Cache

- **TTL**: 300 seconds (5 minutes)
- **Purpose**: Reduces MongoDB queries for frequently accessed templates
- **Invalidation**: Automatic after TTL expires

## Usage Examples

### Example 1: Data Merge Workflow

**User Query:**
```
"I have three CSV files with molecular data, can you merge them?"
```

**What Happens:**
1. Template retriever fetches templates from MongoDB
2. LLM matches query to "Data Merge" template (high confidence)
3. Query is augmented with full Data Merge template prompt (3000+ characters)
4. Agent receives enhanced instructions on:
   - Handling multiple file formats
   - Column mapping strategies
   - Data standardization techniques
   - Memory management for large datasets
5. Agent produces better, more comprehensive results

**Progress Updates Shown to User:**
```
- "Checking for relevant workflow templates..."
- "Matched to template: Data Merge (confidence: high)"
- "Agent processing started..."
```

### Example 2: ASO Design

**User Query:**
```
"Help me design an antisense oligonucleotide targeting BRCA1 exon 11"
```

**What Happens:**
1. Matches to "ASO Design" template
2. Query augmented with ASO design best practices
3. Agent receives guidance on:
   - Target RNA sequence analysis
   - ASO optimization strategies
   - Chemical modification selection
   - Off-target analysis

### Example 3: No Match (Informational Query)

**User Query:**
```
"What is QSPR analysis?"
```

**What Happens:**
1. LLM determines this is an informational query, not a workflow request
2. No template matched
3. Query proceeds without augmentation
4. Agent answers the question directly without workflow template

## Testing

### Test Script: `test_template_retriever.py`

**Run tests:**
```bash
python test_template_retriever.py
```

**Tests include:**
1. Fetching templates from MongoDB
2. Matching various queries to templates
3. Query augmentation with template prompts

**Sample Output:**
```
✓ Fetched 5 templates from MongoDB (cloud)
✓ MATCHED: Data Merge (confidence: medium, keyword matching)
✓ MATCHED: ASO Design (confidence: medium, keyword matching)
✗ NO MATCH: "What is QSPR?" (informational query)
```

### Manual Testing with FastAPI

1. Start the FastAPI server:
   ```bash
   python agent_fastapi_server_multiturn.py
   ```

2. Send a query via `/chat-queue`:
   ```bash
   curl -X POST http://localhost:8001/chat-queue \
     -F "user_id=test_user" \
     -F "message=I want to merge two CSV files with drug data"
   ```

3. Check logs for template matching messages:
   ```
   ✓ Fetched 5 templates from MongoDB (cloud)
   ✓ Template matched: Data Merge (confidence: high)
   ```

## MongoDB Template Management

### Viewing Current Templates

**Via API:**
```bash
curl http://localhost:8001/templates
```

**Response:**
```json
{
  "templates": [
    {
      "title": "Data Merge",
      "running_time": "~6 min",
      "tools": 12,
      "description": "Intelligently merge multi-format...",
      "prompt": "You have been given experimental datasets..."
    }
  ],
  "total": 5,
  "source": "mongodb"
}
```

### Uploading/Updating Templates

**Via API:**
```bash
curl -X POST http://localhost:8001/upload-template \
  -H "Content-Type: application/json" \
  -d @templates/workflow_templates.json
```

**Response:**
```json
{
  "success": true,
  "message": "Templates uploaded successfully",
  "total_templates": 5
}
```

## Benefits

### For Users

1. **Better Results**: Agent receives comprehensive workflow guidance
2. **Consistency**: Standardized approaches to common tasks
3. **Time Savings**: No need to provide detailed instructions manually
4. **Best Practices**: Templates encode domain expertise

### For Development

1. **Knowledge Capture**: Workflow expertise encoded in reusable templates
2. **Easy Updates**: Modify templates in MongoDB without code changes
3. **Scalability**: Add new templates without touching agent code
4. **Cloud Storage**: Templates persist across ECS container restarts

## Monitoring & Debugging

### Check Template Source

Look for these log messages:

**Success:**
```
✓ Fetched 5 templates from MongoDB (cloud)
```

**MongoDB Unavailable (Warning):**
```
⚠️  WARNING: Could not load templates from MongoDB cloud storage
   Falling back to local file - NOT recommended for production!
  → Loaded 5 templates from local fallback file
```

**No Templates (Critical):**
```
✗ CRITICAL: No templates available from any source!
   Please ensure MongoDB is properly configured or local template file exists
```

### Check Template Matching

Look for these log messages in agent processing:

**Template Matched:**
```
✓ Template matched: Data Merge (confidence: high)
  Modification: Focus on CSV files specifically
```

**No Match:**
```
✗ No template matched: Informational query, not a workflow request
```

### Progress Updates to User

The user's progress feed will show:
```json
{
  "type": "template_matched",
  "message": "Matched to template: Data Merge (confidence: high)",
  "template_title": "Data Merge",
  "confidence": "high",
  "reasoning": "User explicitly requested data merging workflow"
}
```

## Troubleshooting

### Problem: Templates not loading from MongoDB

**Symptoms:**
```
✗ MongoDB module import failed: No module named 'func_mongodb'
```

**Solution:**
- Ensure `s3_mongodb` directory exists
- Check MongoDB credentials in environment variables
- Verify network connectivity to MongoDB Atlas

### Problem: Templates loading from local file instead of MongoDB

**Symptoms:**
```
⚠️  WARNING: Could not load templates from MongoDB cloud storage
  → Loaded 5 templates from local fallback file
```

**Solution:**
- Check MongoDB connection string
- Verify `SESSION_DB_NAME` environment variable
- Test MongoDB connection manually

### Problem: No templates matched for valid workflow queries

**Symptoms:**
```
✗ No template matched: No keyword matches found
```

**Solution:**
- Check if template descriptions contain relevant keywords
- Verify LLM is properly configured (check API keys)
- Review template descriptions in MongoDB for completeness

### Problem: Template matching too aggressive

**Symptoms:**
- Templates matching informational queries
- Wrong templates being selected

**Solution:**
- Update template descriptions to be more specific
- Adjust LLM matching prompt in `template_retriever.py`
- Consider adding negative examples to matching prompt

## Future Enhancements

1. **User-Specific Templates**: Allow users to create private templates
2. **Template Analytics**: Track which templates are most used
3. **Template Versioning**: Track changes to templates over time
4. **Multi-Template Matching**: Combine prompts from multiple templates
5. **Template Categories**: Organize templates by domain (genomics, drug discovery, etc.)
6. **Template Search**: Full-text search across template descriptions
7. **Template Ratings**: User feedback on template usefulness
8. **Dynamic Template Generation**: LLM creates custom templates from successful workflows

## API Reference

### GET /templates

Retrieve all available workflow templates.

**Response:**
```json
{
  "templates": [...],
  "total": 5,
  "source": "mongodb" | "local_backup" | "none"
}
```

### POST /upload-template

Upload or update workflow templates (admin only).

**Request Body:**
```json
{
  "templates": [
    {
      "title": "New Workflow",
      "running_time": "~10 min",
      "tools": 8,
      "description": "Description here",
      "prompt": "Optional detailed prompt"
    }
  ]
}
```

**Response:**
```json
{
  "success": true,
  "message": "Templates uploaded successfully",
  "total_templates": 6
}
```

## Best Practices

### For Template Creation

1. **Clear Titles**: Use descriptive, searchable titles
2. **Comprehensive Descriptions**: Include key terms users might search for
3. **Detailed Prompts**: Provide step-by-step guidance in prompts
4. **Realistic Timing**: Set accurate `running_time` estimates
5. **Tool Counts**: Update `tools` count when template workflow changes

### For Template Prompts

1. **Be Specific**: Provide clear, actionable instructions
2. **Include Examples**: Show expected inputs/outputs
3. **Handle Edge Cases**: Address common issues and variations
4. **Format Consistently**: Use clear sections and bullet points
5. **Test Thoroughly**: Verify templates produce good results

### For Production Deployment

1. **Always Use MongoDB**: Don't rely on local file fallback
2. **Monitor Template Source**: Check logs to ensure MongoDB usage
3. **Cache Configuration**: Adjust TTL based on template update frequency
4. **Regular Audits**: Review template usage and effectiveness
5. **Version Control**: Keep template JSON in git for backup

## Summary

The template reference feature enhances the dleader_agent by:

- ✅ Automatically detecting when user queries match known workflows
- ✅ Augmenting queries with comprehensive template prompts from MongoDB cloud storage
- ✅ Providing better, more consistent results for common tasks
- ✅ Allowing easy template updates without code changes
- ✅ Scaling seamlessly in cloud deployments (ECS)

The implementation is transparent to users, working automatically in the background to enhance their queries with relevant workflow expertise.

# Workflow Template API Implementation (MongoDB Cloud Storage)

## Overview
This document describes the implementation of workflow template management APIs for the dleader_agent FastAPI server. Templates are stored in MongoDB for persistence across ECS container restarts, with local file backup for resilience.

## Features Implemented

### 1. Template Data Model

#### Template Model (`agent_fastapi_server_multiturn.py:156`)
```python
class Template(BaseModel):
    title: str                    # Template name
    running_time: str             # Estimated execution time
    tools: int                    # Number of tools used
    description: str              # Brief description
    prompt: Optional[str] = None  # Optional detailed prompt
```

#### Request/Response Models
```python
class TemplateListRequest(BaseModel):
    templates: List[Template]

class TemplateResponse(BaseModel):
    success: bool
    message: str
    total_templates: Optional[int] = None
```

### 2. API Endpoints

#### Upload Templates: `POST /upload-template`
**Location**: `agent_fastapi_server_multiturn.py:3282`

**Purpose**: Upload a collection of workflow templates

**Request Body**:
```json
{
  "templates": [
    {
      "title": "QSPR Workflow",
      "running_time": "~15 min",
      "tools": 13,
      "description": "Quantitative Structure-Property Relationship workflow...",
      "prompt": "Optional detailed prompt"
    }
  ]
}
```

**Response**:
```json
{
  "success": true,
  "message": "Templates uploaded successfully",
  "total_templates": 5
}
```

**Implementation Details**:
- **Primary Storage**: MongoDB (`workflow_templates` collection)
- **Backup Storage**: Local file `templates/workflow_templates.json`
- Uses template `title` as unique identifier (`_id`) for upsert
- Adds `uploaded_at` timestamp to each template
- Uses `upsert_wrapper` for MongoDB operations
- Returns 503 error if MongoDB unavailable
- Atomic upsert: updates existing templates or inserts new ones
- Returns count of uploaded templates

#### Get Templates: `GET /templates`
**Location**: `agent_fastapi_server_multiturn.py:3307`

**Purpose**: Retrieve all available workflow templates

**Response**:
```json
{
  "templates": [
    {
      "title": "QSPR Workflow",
      "running_time": "~15 min",
      "tools": 13,
      "description": "Quantitative Structure-Property Relationship workflow...",
      "prompt": "Optional detailed prompt"
    }
  ],
  "total": 5
}
```

**Implementation Details**:
- **Primary Source**: MongoDB (`workflow_templates` collection)
- **Fallback Source**: Local file `templates/workflow_templates.json`
- Returns `source` field indicating data origin:
  - `mongodb`: Retrieved from MongoDB cloud storage
  - `local_backup`: Fallback to local file (MongoDB unavailable)
  - `none`: No templates found
- Removes internal MongoDB fields (`_id`, `uploaded_at`) from response
- Sorts templates alphabetically by title
- No authentication required (public access)
- Graceful degradation when MongoDB is unavailable

### 3. Template Storage Architecture

**Primary Storage**: MongoDB Cloud Database
- **Database**: `dleader_agent` (or value from `SESSION_DB_NAME` env var)
- **Collection**: `workflow_templates`
- **Document Structure**:
  ```json
  {
    "_id": "QSPR Workflow",  // Template title as unique ID
    "title": "QSPR Workflow",
    "running_time": "~15 min",
    "tools": 13,
    "description": "...",
    "prompt": "...",
    "uploaded_at": "2025-10-12T10:00:00Z"
  }
  ```
- **Benefits**:
  - Persists across ECS container restarts
  - Shared across multiple ECS instances
  - Centralized template management
  - Automatic replication and backup (via MongoDB Atlas)

**Backup Storage**: Local File System
- **Location**: `/home/ubuntu/dleader_agent/templates/workflow_templates.json`
- **Format**: JSON file with template array
  ```json
  {
    "templates": [...]
  }
  ```
- **Purpose**: Fallback when MongoDB is temporarily unavailable
- **Updated**: Every time templates are uploaded to MongoDB

### 4. Pre-loaded Templates

Five biomedical workflow templates are included:

1. **QSPR Workflow** (~15 min, 13 tools)
   - Quantitative Structure-Property Relationship analysis
   - Dataset selection and filtering

2. **ASO Design** (~8 min, 15 tools)
   - Antisense oligonucleotide design
   - Target RNA sequence optimization

3. **Data Curation (CYP)** (~8 min, 8 tools)
   - CYP450 experimental data extraction
   - Japanese terminology support

4. **Patent Summarize** (~15 min, 10 tools)
   - Patent analysis for ASO modifications
   - Structured summary generation

5. **Data Merge** (~6 min, 12 tools)
   - Multi-format dataset merging (CSV, Excel, Markdown, Text)
   - Intelligent column mapping and standardization
   - Includes detailed prompt for the agent

## Testing

### Test Script
**Location**: `/home/ubuntu/dleader_agent/test_template_upload.py`

**Usage**:
```bash
python test_template_upload.py
```

**What it tests**:
1. Upload templates via POST /upload-template
2. Retrieve templates via GET /templates
3. Verify template count and content

### Manual Testing with curl

#### Upload Templates:
```bash
curl -X POST http://localhost:8001/upload-template \
  -H "Content-Type: application/json" \
  -d @templates/workflow_templates.json
```

#### Get Templates:
```bash
curl http://localhost:8001/templates
```

## Use Cases

### 1. Frontend Template Gallery
The React interface can display available templates:
```javascript
const response = await fetch('http://server:8001/templates');
const { templates } = await response.json();

// Display template cards with:
// - Title
// - Running time
// - Tool count
// - Description
```

### 2. Quick Start Workflow
Users can select a template and use its prompt:
```javascript
const template = templates.find(t => t.title === 'Data Merge');
const response = await fetch('http://server:8001/chat-queue', {
  method: 'POST',
  body: new FormData({
    message: template.prompt || template.description,
    user_id: userId
  })
});
```

### 3. Template Management
Admin users can update templates:
```javascript
const newTemplates = {
  templates: [
    // Updated template list
  ]
};

await fetch('http://server:8001/upload-template', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(newTemplates)
});
```

## File Structure

```
/home/ubuntu/dleader_agent/
├── agent_fastapi_server_multiturn.py  # API implementation
├── templates/
│   └── workflow_templates.json        # Template storage
├── test_template_upload.py            # Test script
└── TEMPLATE_API_IMPLEMENTATION.md     # This documentation
```

## API Documentation Updated

The template endpoints have been added to:
- `/home/ubuntu/react_interface_demo/COMPLETE_API_DOCUMENTATION.md`
  - Section 17: Upload Workflow Templates
  - Section 18: Get Workflow Templates

## ECS Deployment Advantages

### Why MongoDB for Templates?

**Problem with Local Storage on ECS**:
- ECS containers are ephemeral
- Local files are lost on container restart/redeployment
- Each container instance has isolated storage
- Cannot share data across multiple containers

**MongoDB Solution**:
✅ **Persistence**: Data survives container restarts
✅ **Consistency**: All ECS instances share the same templates
✅ **Scalability**: Supports auto-scaling with multiple containers
✅ **Reliability**: MongoDB Atlas provides automatic backups
✅ **Performance**: Fast reads/writes with indexing on `_id` (title)

### Deployment Flow

1. **Initial Setup**: Upload templates once via POST /upload-template
2. **Storage**: Templates saved to MongoDB + local backup
3. **Container Restart**: New container retrieves templates from MongoDB
4. **Multiple Instances**: All containers read from same MongoDB collection
5. **Fallback**: If MongoDB temporarily unavailable, uses local backup

## Future Enhancements

1. **Template Versioning**: Track template updates over time with version history
2. **User-specific Templates**: Allow users to create private templates
3. **Template Categories**: Organize templates by domain (genomics, drug discovery, etc.)
4. **Template Search**: Search templates by keywords or tags
5. **Template Usage Analytics**: Track which templates are most popular via MongoDB aggregation
6. **Template Validation**: Validate prompt effectiveness
7. **Template Permissions**: Role-based access control for template management
8. **Template Preview**: Preview template execution results

## Notes

- ✅ Templates are stored in MongoDB (cloud) with local backup
- ✅ Persists across ECS container restarts
- ✅ Shared across all ECS instances
- No authentication required for GET /templates (public access)
- POST /upload-template can be restricted to admin users in future
- Templates include optional detailed prompts for complex workflows
- The Data Merge template includes a comprehensive 3000+ character prompt
- Uses upsert pattern: safe to re-upload templates (won't create duplicates)

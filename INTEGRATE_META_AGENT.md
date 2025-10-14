# Quick Integration Guide: Adding MetaAgent to Your Server

This guide shows how to integrate the MetaAgent system into your existing dleader_agent FastAPI server.

## Step-by-Step Integration

### Option 1: Add to Existing FastAPI Server (Recommended)

#### 1. Add MetaAgent Endpoints

Open `agent_fastapi_server_multiturn.py` and add the following import at the top:

```python
from meta_agent_fastapi_endpoints import router as meta_agent_router
```

Then, after your app initialization, add:

```python
# After: app = FastAPI(...)

# Include MetaAgent endpoints
app.include_router(meta_agent_router)
```

That's it! The MetaAgent endpoints are now available at your FastAPI server.

#### 2. Test the Integration

Start your server:
```bash
python agent_fastapi_server_multiturn.py
```

Test the endpoint:
```bash
curl -X POST http://localhost:8000/meta-task/submit \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Analyze 50 papers about vaccines",
    "user_id": "test_user",
    "max_workers": 3,
    "max_batch_size": 10
  }'
```

You should get a response with a `meta_session_id`.

### Option 2: Standalone MetaAgent Server

If you prefer to run MetaAgent separately:

#### Create `meta_agent_server.py`:

```python
from fastapi import FastAPI
from meta_agent_fastapi_endpoints import router as meta_agent_router
import uvicorn

app = FastAPI(title="MetaAgent Server")
app.include_router(meta_agent_router)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)
```

Run it:
```bash
python meta_agent_server.py
```

Now MetaAgent runs on port 8001, separate from your main server.

## Testing Your Integration

### 1. Run the Example Script

```bash
python meta_agent_example.py
```

This will demonstrate the MetaAgent working end-to-end.

### 2. Use the Gradio Interface

```bash
python meta_agent_gradio_interface.py
```

Open `http://localhost:7862` in your browser.

### 3. Run Tests

```bash
pytest test_meta_agent.py -v
```

## Usage in Your Application

### In Python Code

```python
from dleader_agent.agent.meta_agent import MetaAgent

# Create instance
meta_agent = MetaAgent(max_workers=5, max_batch_size=50)

# Execute task
result = meta_agent.execute_complex_task(
    query="Your complex task here"
)

# Access result
print(result.aggregated_result)
```

### Via REST API

```python
import requests

# Submit task
response = requests.post(
    "http://localhost:8000/meta-task/submit",
    json={
        "query": "Analyze 100 papers",
        "user_id": "user123",
        "max_workers": 3
    }
)
meta_session_id = response.json()["meta_session_id"]

# Check status
status = requests.get(
    f"http://localhost:8000/meta-task/{meta_session_id}/status"
)
print(status.json())
```

### In Your Gradio Interface

Add this tab to your existing Gradio interface:

```python
import gradio as gr

with gr.Blocks() as demo:
    # Your existing tabs...

    with gr.Tab("Complex Tasks (MetaAgent)"):
        query = gr.Textbox(
            label="Complex Query",
            placeholder="E.g., 'Analyze 1000 papers about...'"
        )
        submit_btn = gr.Button("Submit Complex Task")
        result = gr.Textbox(label="Result")

        def submit_meta_task(query_text):
            import requests
            resp = requests.post(
                "http://localhost:8000/meta-task/submit",
                json={"query": query_text, "user_id": "user"}
            )
            return resp.json()["meta_session_id"]

        submit_btn.click(submit_meta_task, query, result)
```

## Configuration

### Adjust Worker Count

For heavy tasks, increase workers in `meta_agent_fastapi_endpoints.py`:

```python
meta_agent = MetaAgent(
    max_workers=10,  # Increase for more parallelism
    max_batch_size=100,
    max_retries=3
)
```

### Custom Agent Configuration

Pass custom config to the A1 agents:

```python
meta_agent = MetaAgent(
    max_workers=5,
    agent_config={
        "use_tool_retriever": True,
        "download_data_lake": False,
        "llm": "claude-opus-4-20250514",  # Use better model
        "timeout_seconds": 1200  # 20 minute timeout
    }
)
```

## Monitoring & Debugging

### Enable Detailed Logging

```python
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("meta_agent")
```

### Check Checkpoints

Checkpoints are saved to `./meta_agent_checkpoints/`:

```bash
ls -la meta_agent_checkpoints/
cat meta_agent_checkpoints/abc-123-def.json
```

### Monitor Worker Status

```python
progress = meta_agent.get_progress(meta_session_id)
print(progress["worker_status"])
```

## Troubleshooting

### Problem: Import Error

```
ModuleNotFoundError: No module named 'meta_agent_fastapi_endpoints'
```

**Solution**: Ensure you're running from the root directory where the file exists.

### Problem: Port Already in Use

**Solution**: Change port in the Gradio interface or use a different port:

```python
demo.launch(server_port=7863)  # Different port
```

### Problem: Worker Not Starting

**Solution**: Check A1 agent configuration. Try:

```python
from dleader_agent.agent.a1 import A1

# Test if A1 can initialize
agent = A1(use_tool_retriever=False, download_data_lake=False)
print("A1 agent works!")
```

## Production Deployment

### 1. Use Process Manager

```bash
# Install PM2
npm install -g pm2

# Start with PM2
pm2 start agent_fastapi_server_multiturn.py --interpreter python3
pm2 start meta_agent_gradio_interface.py --interpreter python3
```

### 2. Add to Docker

In your `Dockerfile`, ensure these files are copied:

```dockerfile
COPY dleader_agent/agent/meta_agent.py /app/dleader_agent/agent/
COPY meta_agent_fastapi_endpoints.py /app/
COPY meta_agent_gradio_interface.py /app/
```

### 3. Environment Variables

Set these for production:

```bash
export META_AGENT_MAX_WORKERS=10
export META_AGENT_BATCH_SIZE=100
export META_AGENT_CHECKPOINT_DIR=/data/checkpoints
```

## Next Steps

1. ✅ Integrate MetaAgent endpoints into your FastAPI server
2. ✅ Test with the example script
3. ✅ Try the Gradio interface
4. ✅ Run tests to ensure everything works
5. ✅ Start using it for complex tasks!

## Example Use Cases

Now you can handle:

- **"Read and analyze 1000 research papers"**
- **"Process 500 patient records"**
- **"Analyze 300 clinical trial reports"**
- **"Compare 200 gene sequences"**
- **"Extract data from 100 PDF documents"**

All with automatic parallel processing, progress tracking, and intelligent result aggregation!

---

Need help? Check:
- `META_AGENT_README.md` - Full documentation
- `meta_agent_example.py` - Working examples
- `test_meta_agent.py` - Test cases

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Development Environment Setup
```bash
# Activate the dleader_agent environment
conda activate dleader_agent_e1

# Install/upgrade dleader_agent package
pip install dleader_agent --upgrade
# Or from source for latest updates
pip install git+https://github.com/MinxZ/dleader_agent.git@main
```

### Running Tests
```bash
# Run all tests
pytest

# Run specific test categories
pytest -m unit        # Unit tests only
pytest -m integration # Integration tests only

# Run with verbose output
pytest -v --tb=short
```

### Code Quality
```bash
# Run ruff for linting and formatting
ruff check .        # Check for linting issues
ruff format .       # Format code

# Ruff is configured in pyproject.toml with specific rules
# Line length: 120 characters
# Ignores: F401 (unused imports), E402 (module imports not at top)
```

### Running the Application

#### FastAPI Server (Multi-user with queue support)
```bash
# Basic server start
python agent_fastapi_server.py

# Custom configuration
python agent_fastapi_server.py --host 0.0.0.0 --port 8001

# Development mode with auto-reload
python agent_fastapi_server.py --reload
```

#### Gradio Interfaces
```bash
# Multi-user interface with full features (port 7860)
python agent_gradio_fastapi_multiturn.py

# Simplified single-user interface (port 7861)
python agent_gradio_simple.py

# Japanese language interface
python agent_interface_jp_gradio.py
```

## Architecture

### Core Agent System
The dleader_agent is a biomedical AI agent built on LangChain and LangGraph:

- **A1 Agent** (`dleader_agent/agent/a1.py`): Main agent class that orchestrates biomedical research tasks using LLM reasoning and tool execution. Supports multiple LLM providers (Anthropic, OpenAI, Azure, Gemini, Bedrock, Groq).

- **Tool Registry** (`dleader_agent/tool/tool_registry.py`): Dynamic tool loading system that discovers and registers biomedical analysis tools across different domains (genomics, proteomics, drug discovery, etc.).

- **Environment Management**: The agent manages a data lake (~11GB) containing biomedical databases and resources, automatically downloaded on first use to `./data/dleader_agent_data/`.

### Server Architecture
The FastAPI server provides REST API access with queue management:

- **QueueManager**: FIFO queue system processing one request at a time
- **SessionManager**: Handles file storage in `chat_sessions/` directories
- **WebSocket Support**: Real-time progress updates for long-running tasks
- **Multi-language**: Full support for English and Japanese interfaces

### Tool Modules
Biomedical tools are organized by domain in `dleader_agent/tool/`:
- `cancer_biology.py`, `immunology.py`, `genetics.py` - Domain-specific analysis tools
- `database.py` - Database query and retrieval functions
- `modeling.py` - ML and statistical modeling tools
- `preprocessing.py` - Data preprocessing utilities
- `support_tools.py` - Code execution and helper functions

Each tool module has a corresponding description file in `tool_description/` for the retriever system.

## Key Implementation Notes

### Session Management
- Sessions stored in `chat_sessions/` with unique IDs
- Each session folder contains: reports, thinking process, queries, uploaded files
- Fixed user `test_user_dleader` for simplified interface

### API Integration
- All API calls go through `/chat-queue` endpoint for queue management
- Status checking via `/check-status` with session ID
- File uploads handled per session via `/upload` endpoint

### Code Execution Safety
- Python code runs through `run_python_repl` with timeout controls
- R code execution via `run_r_code` function
- Bash scripts executed with `run_bash_script`
- Default timeout: 600 seconds (configurable)

### LLM Configuration
Configure via environment variables in `.env`:
- `ANTHROPIC_API_KEY` - Required for Claude models
- `OPENAI_API_KEY` - For OpenAI/Azure models
- `LLM_SOURCE` - Provider selection
- `dleader_agent_TIMEOUT_SECONDS` - Execution timeout

### MCP (Model Context Protocol) Support
The agent supports MCP servers for external tool integration. Configure with YAML files and add servers via `agent.add_mcp()`.
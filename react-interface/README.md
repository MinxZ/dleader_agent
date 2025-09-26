# DLeader Agent React Interface

A modern React interface for the DLeader Agent FastAPI server, featuring a ChatGPT-like UI.

## Features

- Chat interface similar to ChatGPT
- Session history in sidebar with hard delete functionality (right-click for context menu)
- Multi-turn conversation support
- File upload support
- Real-time status updates
- Start, Stop, and Share functionality
- Dark theme

## Installation

1. Install dependencies:
```bash
npm install
```

2. Make sure the FastAPI server is running on port 8001:
```bash
python agent_fastapi_server_multiturn.py
```

3. Start the React application:
```bash
npm start
```

The application will open at http://localhost:7861

## Usage

- **New Chat**: Click the "New Chat" button to start a new conversation
- **Send Message**: Type in the input field and press Enter or click the send button
- **Upload Files**: Click the paperclip icon to attach files
- **Stop Task**: Click the stop button while a task is running
- **Share Session**: Click the share button to download session results
- **Delete Session**: Right-click on a session in the sidebar and select "Hard Delete"

## API Integration

The application connects to the FastAPI server at `http://localhost:8001`. The proxy configuration in `package.json` handles API routing during development.
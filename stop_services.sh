#!/bin/bash

# Script to stop FastAPI server and Gradio interface

echo "=========================================="
echo "Stopping dleader_agent Services"
echo "=========================================="

# Get the script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

STOPPED=0

# Stop using PID files if they exist
if [ -f .fastapi.pid ]; then
    FASTAPI_PID=$(cat .fastapi.pid)
    if ps -p $FASTAPI_PID > /dev/null 2>&1; then
        echo "Stopping FastAPI server (PID: $FASTAPI_PID)..."
        kill $FASTAPI_PID
        STOPPED=$((STOPPED + 1))
    fi
    rm -f .fastapi.pid
fi

if [ -f .gradio.pid ]; then
    GRADIO_PID=$(cat .gradio.pid)
    if ps -p $GRADIO_PID > /dev/null 2>&1; then
        echo "Stopping Gradio interface (PID: $GRADIO_PID)..."
        kill $GRADIO_PID
        STOPPED=$((STOPPED + 1))
    fi
    rm -f .gradio.pid
fi

# Fallback: kill by process name
echo "Checking for any remaining processes..."
pkill -f agent_fastapi_server_multiturn.py && STOPPED=$((STOPPED + 1))
pkill -f agent_gradio_fastapi_multiturn_simplified.py && STOPPED=$((STOPPED + 1))

# Wait a moment
sleep 2

# Verify all stopped
REMAINING=$(ps aux | grep -E "agent_fastapi_server_multiturn|agent_gradio_fastapi_multiturn_simplified" | grep -v grep | wc -l)

if [ $REMAINING -eq 0 ]; then
    echo ""
    echo "✓ All services stopped successfully!"
else
    echo ""
    echo "Warning: Some processes may still be running. Force killing..."
    pkill -9 -f agent_fastapi_server_multiturn.py
    pkill -9 -f agent_gradio_fastapi_multiturn_simplified.py
    sleep 1
    echo "✓ Force kill completed"
fi

echo "=========================================="
echo "Services stopped"
echo "=========================================="

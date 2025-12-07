#!/bin/bash

# Script to start FastAPI server and Gradio interface

echo "=========================================="
echo "Starting dleader_agent Services"
echo "=========================================="

# Check if conda environment is activated
if [[ "$CONDA_DEFAULT_ENV" != "dleader_agent_e1" ]]; then
    echo "Warning: Conda environment 'dleader_agent_e1' is not activated"
    echo "Please run: conda activate dleader_agent_e1"
    echo ""
fi

# Get the script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo "Working directory: $SCRIPT_DIR"
echo ""

# Start FastAPI server
echo "Starting FastAPI server on port 8001..."
nohup python3 agent_fastapi_server_multiturn.py --host 0.0.0.0 --port 8001 --no-reload > fastapi_server.log 2>&1 &
FASTAPI_PID=$!
echo "FastAPI server started (PID: $FASTAPI_PID)"
echo "  - Local: http://localhost:8001"
echo "  - Health: http://localhost:8001/health"
echo "  - Logs: $SCRIPT_DIR/fastapi_server.log"
echo ""

# Wait for FastAPI to start
echo "Waiting for FastAPI server to be ready..."
sleep 3

# Check if FastAPI is healthy
for i in {1..10}; do
    if curl -s http://localhost:8001/health > /dev/null 2>&1; then
        echo "✓ FastAPI server is ready!"
        break
    fi
    echo "  Waiting... ($i/10)"
    sleep 1
done
echo ""

# Start Gradio interface
echo "Starting Gradio interface on port 7861..."
nohup python3 agent_gradio_fastapi_multiturn_simplified.py > gradio_interface.log 2>&1 &
GRADIO_PID=$!
echo "Gradio interface started (PID: $GRADIO_PID)"
echo "  - Local: http://localhost:7861"
echo "  - Logs: $SCRIPT_DIR/gradio_interface.log"
echo ""

# Wait for Gradio to start
echo "Waiting for Gradio interface to be ready..."
sleep 5

# Check if Gradio is serving
for i in {1..10}; do
    if curl -s http://localhost:7861 > /dev/null 2>&1; then
        echo "✓ Gradio interface is ready!"
        break
    fi
    echo "  Waiting... ($i/10)"
    sleep 1
done
echo ""

# Save PIDs to file for easy stopping
echo "$FASTAPI_PID" > .fastapi.pid
echo "$GRADIO_PID" > .gradio.pid

echo "=========================================="
echo "All services started successfully!"
echo "=========================================="
echo ""
echo "Access the Gradio interface at:"
echo "  http://localhost:7861"
echo ""
echo "FastAPI API endpoint:"
echo "  http://localhost:8001"
echo ""
echo "To stop services, run: ./stop_services.sh"
echo "To view logs:"
echo "  tail -f fastapi_server.log"
echo "  tail -f gradio_interface.log"
echo ""

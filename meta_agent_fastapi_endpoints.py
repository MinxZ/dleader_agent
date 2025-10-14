"""
FastAPI endpoints for MetaAgent integration.

This module provides REST API endpoints for submitting and monitoring
complex multi-step tasks using the MetaAgent system.

Add these endpoints to your existing FastAPI server by importing and including the router.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from dleader_agent.agent.meta_agent import MetaAgent

# Create router for meta-agent endpoints
router = APIRouter(prefix="/meta-task", tags=["meta-agent"])

# Global meta-agent instance (configure as needed)
meta_agent = MetaAgent(
    max_workers=3,
    max_batch_size=50,
    max_retries=2,
    checkpoint_dir="./meta_agent_checkpoints",
    agent_config={
        "use_tool_retriever": True,
        "download_data_lake": False,
        "llm": "claude-sonnet-4-20250514"
    }
)


# Request/Response models
class MetaTaskSubmitRequest(BaseModel):
    """Request model for submitting a meta-task"""
    query: str
    user_id: str
    max_workers: Optional[int] = None
    max_batch_size: Optional[int] = None
    mode: Optional[str] = "parallel"  # "parallel" or "sequential"
    items_per_batch: Optional[int] = None  # For sequential mode
    pause_between_batches: Optional[float] = 0  # For sequential mode


class MetaTaskSubmitResponse(BaseModel):
    """Response model for meta-task submission"""
    meta_session_id: str
    message: str
    estimated_subtasks: int


class MetaTaskStatusResponse(BaseModel):
    """Response model for meta-task status"""
    meta_session_id: str
    status: str
    completed: int
    failed: int
    total: int
    percentage: float
    aggregated_result: Optional[str] = None
    worker_status: dict
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class MetaTaskCancelResponse(BaseModel):
    """Response model for meta-task cancellation"""
    meta_session_id: str
    message: str
    was_running: bool


# Endpoints
@router.post("/submit", response_model=MetaTaskSubmitResponse)
async def submit_meta_task(request: MetaTaskSubmitRequest):
    """
    Submit a complex multi-step task to the MetaAgent.

    The task will be decomposed into subtasks and executed either in parallel or sequentially.

    Modes:
    - parallel (default): Multiple workers process subtasks simultaneously
    - sequential: Process one batch at a time with full control

    Args:
        request: MetaTaskSubmitRequest containing query and configuration

    Returns:
        MetaTaskSubmitResponse with meta_session_id for tracking
    """
    try:
        # Store progress updates in a list for this session
        progress_updates = []

        def progress_callback(update: dict):
            progress_updates.append({
                **update,
                "timestamp": datetime.now().isoformat()
            })

        # Determine execution mode
        mode = request.mode or "parallel"

        if mode == "sequential":
            # Sequential mode with custom batch control
            def run_sequential():
                meta_agent.execute_complex_task_sequential(
                    query=request.query,
                    items_per_batch=request.items_per_batch,
                    pause_between_batches=request.pause_between_batches or 0,
                    progress_callback=progress_callback
                )

            import threading
            import uuid
            meta_session_id = str(uuid.uuid4())
            thread = threading.Thread(target=run_sequential, daemon=True)
            thread.start()

            message = (f"Meta-task submitted successfully in SEQUENTIAL mode. "
                      f"Batches will be processed one at a time.")
            if request.items_per_batch:
                message += f" Batch size: {request.items_per_batch} items."
            if request.pause_between_batches:
                message += f" Pause: {request.pause_between_batches}s between batches."
        else:
            # Parallel mode (default)
            meta_session_id = meta_agent.execute_complex_task_async(
                query=request.query,
                progress_callback=progress_callback,
                mode="parallel"
            )
            message = "Meta-task submitted successfully in PARALLEL mode. Task is being decomposed and executed."

        return MetaTaskSubmitResponse(
            meta_session_id=meta_session_id,
            message=message,
            estimated_subtasks=0  # Will be updated once decomposition completes
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to submit meta-task: {str(e)}")


@router.get("/{meta_session_id}/status", response_model=MetaTaskStatusResponse)
async def get_meta_task_status(meta_session_id: str):
    """
    Get the current status and progress of a meta-task.

    Args:
        meta_session_id: The ID of the meta-task

    Returns:
        MetaTaskStatusResponse with detailed progress information
    """
    try:
        progress = meta_agent.get_progress(meta_session_id)

        if progress is None:
            # Try to load from checkpoint
            checkpoint_data = meta_agent.load_checkpoint(meta_session_id)
            if checkpoint_data:
                return MetaTaskStatusResponse(
                    meta_session_id=meta_session_id,
                    status=checkpoint_data["status"],
                    completed=checkpoint_data["completed_count"],
                    failed=checkpoint_data["failed_count"],
                    total=checkpoint_data["total_count"],
                    percentage=(checkpoint_data["completed_count"] / checkpoint_data["total_count"] * 100) if checkpoint_data["total_count"] > 0 else 0,
                    aggregated_result=checkpoint_data.get("aggregated_result"),
                    worker_status={},
                    created_at=checkpoint_data["created_at"],
                    updated_at=checkpoint_data["updated_at"]
                )
            else:
                raise HTTPException(status_code=404, detail=f"Meta-task {meta_session_id} not found")

        return MetaTaskStatusResponse(
            meta_session_id=meta_session_id,
            status=progress["status"],
            completed=progress["completed"],
            failed=progress["failed"],
            total=progress["total"],
            percentage=progress["percentage"],
            aggregated_result=progress.get("aggregated_result"),
            worker_status=progress["worker_status"]
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get meta-task status: {str(e)}")


@router.get("/{meta_session_id}/results")
async def get_meta_task_results(meta_session_id: str):
    """
    Get the final aggregated results of a completed meta-task.

    Args:
        meta_session_id: The ID of the meta-task

    Returns:
        JSON with results and metadata
    """
    try:
        progress = meta_agent.get_progress(meta_session_id)

        if progress is None:
            # Try loading from checkpoint
            checkpoint_data = meta_agent.load_checkpoint(meta_session_id)
            if checkpoint_data:
                return {
                    "meta_session_id": meta_session_id,
                    "status": checkpoint_data["status"],
                    "aggregated_result": checkpoint_data.get("aggregated_result"),
                    "completed": checkpoint_data["completed_count"],
                    "total": checkpoint_data["total_count"],
                    "failed": checkpoint_data["failed_count"]
                }
            else:
                raise HTTPException(status_code=404, detail=f"Meta-task {meta_session_id} not found")

        return {
            "meta_session_id": meta_session_id,
            "status": progress["status"],
            "aggregated_result": progress.get("aggregated_result"),
            "completed": progress["completed"],
            "total": progress["total"],
            "failed": progress["failed"]
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get meta-task results: {str(e)}")


@router.post("/{meta_session_id}/cancel", response_model=MetaTaskCancelResponse)
async def cancel_meta_task(meta_session_id: str):
    """
    Cancel a running meta-task.

    Args:
        meta_session_id: The ID of the meta-task to cancel

    Returns:
        MetaTaskCancelResponse with cancellation status
    """
    try:
        # Check if task exists
        progress = meta_agent.get_progress(meta_session_id)

        if progress is None:
            raise HTTPException(status_code=404, detail=f"Meta-task {meta_session_id} not found")

        was_running = progress["status"] == "running"

        # Shutdown worker pool (this will cancel all running subtasks)
        meta_agent.worker_pool.shutdown()

        # Update task status
        if meta_session_id in meta_agent.meta_tasks:
            from dleader_agent.agent.meta_agent import TaskStatus
            meta_agent.meta_tasks[meta_session_id].status = TaskStatus.CANCELLED
            meta_agent._save_checkpoint(meta_agent.meta_tasks[meta_session_id])

        return MetaTaskCancelResponse(
            meta_session_id=meta_session_id,
            message="Meta-task cancelled successfully" if was_running else "Meta-task was not running",
            was_running=was_running
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to cancel meta-task: {str(e)}")


@router.get("/{meta_session_id}/subtasks")
async def get_meta_task_subtasks(meta_session_id: str):
    """
    Get detailed information about all subtasks in a meta-task.

    Args:
        meta_session_id: The ID of the meta-task

    Returns:
        JSON with list of subtasks and their statuses
    """
    try:
        # Get from active meta-tasks
        if meta_session_id in meta_agent.meta_tasks:
            meta_state = meta_agent.meta_tasks[meta_session_id]
            return {
                "meta_session_id": meta_session_id,
                "total_subtasks": len(meta_state.subtasks),
                "subtasks": [st.to_dict() for st in meta_state.subtasks]
            }

        # Try loading from checkpoint
        checkpoint_data = meta_agent.load_checkpoint(meta_session_id)
        if checkpoint_data:
            return {
                "meta_session_id": meta_session_id,
                "total_subtasks": len(checkpoint_data["subtasks"]),
                "subtasks": checkpoint_data["subtasks"]
            }

        raise HTTPException(status_code=404, detail=f"Meta-task {meta_session_id} not found")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get subtasks: {str(e)}")


# Include this router in your main FastAPI app:
# from meta_agent_fastapi_endpoints import router as meta_agent_router
# app.include_router(meta_agent_router)

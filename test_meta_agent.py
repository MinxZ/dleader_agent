"""
Tests for MetaAgent system.

Run with: pytest test_meta_agent.py -v
"""

import json
import os
import tempfile
import time
from unittest.mock import MagicMock, patch

import pytest

from dleader_agent.agent.meta_agent import (
    MetaAgent,
    MetaTaskState,
    ResultAggregator,
    SubTask,
    TaskDecomposer,
    TaskStatus,
    WorkerPool,
)


class TestTaskDecomposer:
    """Tests for TaskDecomposer"""

    def test_decompose_with_number(self):
        """Test decomposition of tasks with clear item counts"""
        decomposer = TaskDecomposer()

        # Mock the LLM to return a simple JSON array
        with patch.object(decomposer, 'llm') as mock_llm:
            mock_response = MagicMock()
            mock_response.content = json.dumps([
                "Read papers 1-50",
                "Read papers 51-100"
            ])
            mock_llm.invoke.return_value = mock_response

            subtasks = decomposer.decompose("Read 100 papers", max_batch_size=50)

            assert len(subtasks) == 2
            assert "papers" in subtasks[0].lower()

    def test_decompose_fallback(self):
        """Test fallback when LLM returns invalid JSON"""
        decomposer = TaskDecomposer()

        with patch.object(decomposer, 'llm') as mock_llm:
            mock_response = MagicMock()
            mock_response.content = "Not valid JSON"
            mock_llm.invoke.return_value = mock_response

            subtasks = decomposer.decompose("Process 100 items", max_batch_size=25)

            # Should fall back to simple batching
            assert len(subtasks) == 4  # 100/25 = 4 batches
            assert "batch" in subtasks[0].lower()

    def test_simple_batches(self):
        """Test the simple batch creation fallback"""
        decomposer = TaskDecomposer()

        subtasks = decomposer._create_simple_batches("Analyze 60 genes", batch_size=20)

        assert len(subtasks) == 3
        assert "1-20" in subtasks[0]
        assert "21-40" in subtasks[1]
        assert "41-60" in subtasks[2]


class TestSubTask:
    """Tests for SubTask dataclass"""

    def test_subtask_creation(self):
        """Test creating a SubTask"""
        subtask = SubTask(
            subtask_id="test_001",
            description="Test task description"
        )

        assert subtask.subtask_id == "test_001"
        assert subtask.status == TaskStatus.PENDING
        assert subtask.result is None
        assert subtask.error is None

    def test_subtask_to_dict(self):
        """Test converting SubTask to dictionary"""
        subtask = SubTask(
            subtask_id="test_001",
            description="Test task",
            status=TaskStatus.COMPLETED,
            result="Success"
        )

        data = subtask.to_dict()

        assert data["subtask_id"] == "test_001"
        assert data["status"] == "completed"
        assert data["result"] == "Success"


class TestMetaTaskState:
    """Tests for MetaTaskState dataclass"""

    def test_meta_task_state_creation(self):
        """Test creating MetaTaskState"""
        state = MetaTaskState(
            meta_session_id="meta_001",
            original_query="Test query"
        )

        assert state.meta_session_id == "meta_001"
        assert state.status == TaskStatus.PENDING
        assert state.completed_count == 0
        assert state.total_count == 0

    def test_meta_task_state_to_dict(self):
        """Test converting MetaTaskState to dictionary"""
        subtask = SubTask(subtask_id="sub_001", description="Test")
        state = MetaTaskState(
            meta_session_id="meta_001",
            original_query="Test query",
            subtasks=[subtask],
            total_count=1
        )

        data = state.to_dict()

        assert data["meta_session_id"] == "meta_001"
        assert len(data["subtasks"]) == 1
        assert data["total_count"] == 1


class TestWorkerPool:
    """Tests for WorkerPool"""

    def test_worker_pool_creation(self):
        """Test creating a WorkerPool"""
        pool = WorkerPool(max_workers=2)

        assert pool.max_workers == 2
        assert len(pool.workers) == 0  # Not started yet

    def test_submit_task(self):
        """Test submitting a task to the pool"""
        pool = WorkerPool(max_workers=2)
        subtask = SubTask(subtask_id="test_001", description="Test task")

        pool.submit_task(subtask)

        assert pool.task_queue.qsize() == 1

    def test_worker_status(self):
        """Test getting worker status"""
        pool = WorkerPool(max_workers=2)

        # Start pool
        pool.start()
        time.sleep(0.5)  # Give workers time to initialize

        status = pool.get_worker_status()

        assert len(status) == 2
        assert "worker_1" in status
        assert "worker_2" in status

        # Cleanup
        pool.shutdown()


class TestResultAggregator:
    """Tests for ResultAggregator"""

    def test_aggregate_empty_results(self):
        """Test aggregating when no results are completed"""
        aggregator = ResultAggregator()

        result = aggregator.aggregate(
            "Test query",
            []
        )

        assert "No completed subtasks" in result

    def test_aggregate_with_results(self):
        """Test aggregating with completed results"""
        aggregator = ResultAggregator()

        # Mock LLM
        with patch.object(aggregator, 'llm') as mock_llm:
            mock_response = MagicMock()
            mock_response.content = "Aggregated summary of all results"
            mock_llm.invoke.return_value = mock_response

            subtask_results = [
                {
                    "status": TaskStatus.COMPLETED.value,
                    "description": "Task 1",
                    "result": "Result 1"
                },
                {
                    "status": TaskStatus.COMPLETED.value,
                    "description": "Task 2",
                    "result": "Result 2"
                }
            ]

            result = aggregator.aggregate("Test query", subtask_results)

            assert "Aggregated summary" in result
            mock_llm.invoke.assert_called_once()


class TestMetaAgent:
    """Tests for MetaAgent"""

    def test_meta_agent_creation(self):
        """Test creating a MetaAgent"""
        meta_agent = MetaAgent(
            max_workers=2,
            max_batch_size=10
        )

        assert meta_agent.max_workers == 2
        assert meta_agent.max_batch_size == 10
        assert meta_agent.max_retries == 2

    def test_checkpoint_save_load(self):
        """Test saving and loading checkpoints"""
        with tempfile.TemporaryDirectory() as tmpdir:
            meta_agent = MetaAgent(checkpoint_dir=tmpdir)

            # Create a meta-task state
            state = MetaTaskState(
                meta_session_id="test_123",
                original_query="Test query",
                total_count=5,
                completed_count=3
            )

            # Save checkpoint
            meta_agent._save_checkpoint(state)

            # Verify file exists
            checkpoint_path = os.path.join(tmpdir, "test_123.json")
            assert os.path.exists(checkpoint_path)

            # Load checkpoint
            loaded = meta_agent.load_checkpoint("test_123")

            assert loaded is not None
            assert loaded["meta_session_id"] == "test_123"
            assert loaded["completed_count"] == 3

    def test_get_progress_not_found(self):
        """Test getting progress for non-existent task"""
        meta_agent = MetaAgent()

        progress = meta_agent.get_progress("nonexistent_id")

        assert progress is None

    @pytest.mark.slow
    def test_execute_simple_task(self):
        """Test executing a simple task (integration test)"""
        # This is a slow integration test - skip in CI
        pytest.skip("Integration test - requires LLM access")

        meta_agent = MetaAgent(
            max_workers=1,
            max_batch_size=2,
            agent_config={
                "use_tool_retriever": False,
                "download_data_lake": False
            }
        )

        progress_updates = []

        def callback(update):
            progress_updates.append(update)

        result = meta_agent.execute_complex_task(
            query="Summarize 5 simple numbers: 1, 2, 3, 4, 5",
            progress_callback=callback
        )

        assert result.status in [TaskStatus.COMPLETED, TaskStatus.FAILED]
        assert len(progress_updates) > 0


class TestIntegration:
    """Integration tests for full workflow"""

    @pytest.mark.slow
    def test_full_workflow_mock(self):
        """Test full workflow with mocked components"""
        # Create meta-agent with minimal config
        meta_agent = MetaAgent(max_workers=1, max_batch_size=5)

        # Mock the decomposer
        with patch.object(meta_agent.decomposer, 'decompose') as mock_decompose:
            mock_decompose.return_value = [
                "Process items 1-5",
                "Process items 6-10"
            ]

            # Mock worker pool execution
            with patch.object(meta_agent.worker_pool, '_worker_loop'):
                # This would test the orchestration logic
                # Full implementation requires actual agent execution
                pass


def test_task_status_enum():
    """Test TaskStatus enum"""
    assert TaskStatus.PENDING.value == "pending"
    assert TaskStatus.RUNNING.value == "running"
    assert TaskStatus.COMPLETED.value == "completed"
    assert TaskStatus.FAILED.value == "failed"
    assert TaskStatus.CANCELLED.value == "cancelled"


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v", "--tb=short"])

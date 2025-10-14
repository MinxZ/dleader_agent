"""
MetaAgent: Orchestrator for complex multi-step tasks requiring multiple agent instances.

This module provides a hierarchical agent system that can break down complex tasks
(e.g., "read 1000 papers and summarize") into manageable subtasks, execute them in parallel,
monitor progress, and aggregate results.
"""

import asyncio
import json
import os
import queue
import threading
import time
import uuid
from collections.abc import Generator
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Optional

from langchain_core.messages import HumanMessage, SystemMessage

from dleader_agent.agent.a1 import A1
from dleader_agent.llm import get_llm


class TaskStatus(Enum):
    """Status of a subtask or meta-task"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class SubTask:
    """Represents a single subtask in a meta-task"""
    subtask_id: str
    description: str
    status: TaskStatus = TaskStatus.PENDING
    result: Optional[Any] = None
    error: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    retry_count: int = 0
    worker_id: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization"""
        return {
            "subtask_id": self.subtask_id,
            "description": self.description,
            "status": self.status.value,
            "result": self.result,
            "error": self.error,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "retry_count": self.retry_count,
            "worker_id": self.worker_id
        }


@dataclass
class MetaTaskState:
    """State of an entire meta-task"""
    meta_session_id: str
    original_query: str
    subtasks: list[SubTask] = field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    completed_count: int = 0
    failed_count: int = 0
    total_count: int = 0
    aggregated_result: Optional[Any] = None
    error: Optional[str] = None
    checkpoint_path: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization"""
        return {
            "meta_session_id": self.meta_session_id,
            "original_query": self.original_query,
            "subtasks": [st.to_dict() for st in self.subtasks],
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "completed_count": self.completed_count,
            "failed_count": self.failed_count,
            "total_count": self.total_count,
            "aggregated_result": self.aggregated_result,
            "error": self.error,
            "checkpoint_path": self.checkpoint_path
        }


class TaskDecomposer:
    """Decomposes complex tasks into manageable subtasks using LLM reasoning"""

    def __init__(self, llm=None):
        """Initialize the task decomposer

        Args:
            llm: Language model to use for task decomposition. If None, uses default from get_llm()
        """
        self.llm = llm or get_llm("claude-sonnet-4-20250514")

    def extract_file_list(self, query: str) -> list[str]:
        """Extract file paths or URLs from the query

        Args:
            query: The query text that may contain file paths or URLs

        Returns:
            List of file paths/URLs found in the query
        """
        import re

        files = []

        # Pattern 1: URLs (check first to avoid conflicts)
        url_pattern = r'https?://[^\s,\]\)"]+'
        urls = re.findall(url_pattern, query)
        files.extend(urls)

        # Pattern 2: File paths (with common extensions) - skip if already in URL
        file_pattern = r'(?:\.\/|\/|[A-Za-z]:\\)?(?:[\w\-\.]+\/)*[\w\-\.]+\.(?:pdf|txt|csv|json|md|doc|docx|xml|html)'
        file_matches = re.findall(file_pattern, query, re.IGNORECASE)
        # Only add if not part of a URL
        for match in file_matches:
            if not any(url for url in urls if match in url):
                files.append(match)

        # Pattern 3: Files in list format (e.g., [file1.pdf, file2.pdf])
        list_pattern = r'\[(.*?)\]'
        list_matches = re.findall(list_pattern, query)
        for match in list_matches:
            # Split by comma and clean
            items = [item.strip().strip('"\'') for item in match.split(',')]
            # Filter for file-like items
            files.extend([item for item in items if '.' in item and len(item) > 3])

        # Pattern 4: Comma-separated list of files
        if 'files:' in query.lower() or 'papers:' in query.lower():
            # Extract the part after "files:" or "papers:"
            parts = re.split(r'(?:files|papers):\s*', query, flags=re.IGNORECASE)
            if len(parts) > 1:
                file_section = parts[1].split('\n')[0]  # Get first line after keyword
                items = [item.strip().strip('"\'') for item in file_section.split(',')]
                files.extend([item for item in items if '.' in item and len(item) > 3])

        # Remove duplicates while preserving order
        seen = set()
        unique_files = []
        for f in files:
            if f not in seen:
                seen.add(f)
                unique_files.append(f)

        return unique_files

    def decompose_with_files(self, query: str, files: list[str], max_batch_size: int = 50) -> list[str]:
        """Decompose task with explicit file list assignment

        Args:
            query: The original complex query
            files: List of file paths/URLs to process
            max_batch_size: Maximum files per batch

        Returns:
            List of subtask descriptions with specific file assignments
        """
        import re

        if not files:
            # No files found, use regular decomposition
            return self.decompose(query, max_batch_size)

        # Create batches of files
        num_batches = (len(files) + max_batch_size - 1) // max_batch_size
        subtasks = []

        # Extract the main task (without file list)
        # Remove file list from query for cleaner subtask descriptions
        task_description = query
        for pattern in [r'\[.*?\]', r'(?:files|papers):\s*[^\n]+']:
            task_description = re.sub(pattern, '', task_description, flags=re.IGNORECASE)
        task_description = ' '.join(task_description.split())  # Clean whitespace

        for i in range(num_batches):
            start_idx = i * max_batch_size
            end_idx = min((i + 1) * max_batch_size, len(files))
            batch_files = files[start_idx:end_idx]

            # Create detailed subtask with explicit file list
            file_list_str = '\n'.join([f"  - {f}" for f in batch_files])
            subtask = f"""{task_description}

Process these specific files (batch {i+1}/{num_batches}):
{file_list_str}

For each file:
1. Access the file at the path/URL provided
2. Complete the requested analysis
3. Include the filename in your results"""

            subtasks.append(subtask)

        return subtasks

    def decompose(self, query: str, max_batch_size: int = 50) -> list[str]:
        """Decompose a complex query into subtasks

        Args:
            query: The original complex query
            max_batch_size: Maximum items per batch (e.g., papers per subtask)

        Returns:
            List of subtask descriptions
        """
        system_prompt = f"""You are a task decomposition expert. Your job is to break down complex tasks into manageable subtasks.

Given a complex task that involves processing many items (e.g., reading 1000 papers, analyzing datasets),
break it down into smaller, parallel-executable subtasks.

Guidelines:
1. Each subtask should be independent and executable in parallel
2. Batch size should be around {max_batch_size} items per subtask when dealing with large quantities
3. Identify the core task that needs to be repeated
4. Create clear, specific subtask descriptions
5. Return ONLY a JSON array of subtask descriptions, nothing else

Example:
Input: "Read and summarize 1000 papers about COVID-19 treatments"
Output: ["Read and summarize papers 1-50 about COVID-19 treatments", "Read and summarize papers 51-100 about COVID-19 treatments", ...]

Now decompose this task:"""

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=query)
        ]

        response = self.llm.invoke(messages)
        response_text = response.content.strip()

        # Extract JSON from response (handle markdown code blocks)
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0].strip()

        try:
            subtasks = json.loads(response_text)
            if isinstance(subtasks, list):
                return subtasks
            else:
                # Fallback: create simple batched tasks
                return self._create_simple_batches(query, max_batch_size)
        except json.JSONDecodeError:
            print(f"Failed to parse LLM response as JSON: {response_text}")
            return self._create_simple_batches(query, max_batch_size)

    def _create_simple_batches(self, query: str, batch_size: int) -> list[str]:
        """Fallback method to create simple batched subtasks"""
        # Try to extract number from query
        import re
        numbers = re.findall(r'\d+', query)

        if numbers:
            total_items = int(numbers[0])
            num_batches = (total_items + batch_size - 1) // batch_size

            subtasks = []
            for i in range(num_batches):
                start = i * batch_size + 1
                end = min((i + 1) * batch_size, total_items)
                subtasks.append(f"{query} (batch {i+1}: items {start}-{end})")
            return subtasks
        else:
            # No clear number found, just return the query as a single task
            return [query]


class WorkerPool:
    """Manages a pool of A1 agent workers for parallel task execution"""

    def __init__(self, max_workers: int = 3, agent_config: dict = None):
        """Initialize the worker pool

        Args:
            max_workers: Maximum number of concurrent workers
            agent_config: Configuration dict for A1 agents
        """
        self.max_workers = max_workers
        self.agent_config = agent_config or {}
        self.workers: dict[str, dict] = {}  # worker_id -> {agent, status, current_task}
        self.task_queue = queue.Queue()
        self.result_queue = queue.Queue()
        self.lock = threading.Lock()
        self.shutdown_flag = threading.Event()

    def submit_task(self, subtask: SubTask) -> None:
        """Submit a subtask to the worker pool"""
        self.task_queue.put(subtask)

    def start(self) -> None:
        """Start the worker pool"""
        for i in range(self.max_workers):
            worker_id = f"worker_{i+1}"
            worker_thread = threading.Thread(
                target=self._worker_loop,
                args=(worker_id,),
                daemon=True
            )
            worker_thread.start()

            with self.lock:
                self.workers[worker_id] = {
                    "thread": worker_thread,
                    "status": "idle",
                    "current_task": None
                }

    def _worker_loop(self, worker_id: str) -> None:
        """Main loop for a worker thread"""
        # Create agent instance for this worker
        agent = A1(**self.agent_config)

        while not self.shutdown_flag.is_set():
            try:
                # Get next task with timeout
                subtask = self.task_queue.get(timeout=1.0)

                # Update worker status
                with self.lock:
                    self.workers[worker_id]["status"] = "busy"
                    self.workers[worker_id]["current_task"] = subtask.subtask_id

                # Execute task
                subtask.status = TaskStatus.RUNNING
                subtask.start_time = datetime.now()
                subtask.worker_id = worker_id

                try:
                    # Run the agent
                    log, result = agent.go(subtask.description)

                    # Task completed successfully
                    subtask.status = TaskStatus.COMPLETED
                    subtask.result = result
                    subtask.end_time = datetime.now()

                except Exception as e:
                    # Task failed
                    subtask.status = TaskStatus.FAILED
                    subtask.error = str(e)
                    subtask.end_time = datetime.now()
                    print(f"Worker {worker_id} failed on subtask {subtask.subtask_id}: {e}")

                # Put result in queue
                self.result_queue.put(subtask)

                # Update worker status
                with self.lock:
                    self.workers[worker_id]["status"] = "idle"
                    self.workers[worker_id]["current_task"] = None

            except queue.Empty:
                continue
            except Exception as e:
                print(f"Worker {worker_id} encountered error: {e}")

    def shutdown(self) -> None:
        """Shutdown the worker pool gracefully"""
        self.shutdown_flag.set()

    def get_worker_status(self) -> dict:
        """Get status of all workers"""
        with self.lock:
            return {
                worker_id: {
                    "status": info["status"],
                    "current_task": info["current_task"]
                }
                for worker_id, info in self.workers.items()
            }


class ResultAggregator:
    """Aggregates results from multiple subtasks using LLM synthesis"""

    def __init__(self, llm=None):
        """Initialize the result aggregator

        Args:
            llm: Language model to use for result synthesis
        """
        self.llm = llm or get_llm("claude-sonnet-4-20250514")

    def aggregate(self, original_query: str, subtask_results: list[dict]) -> str:
        """Aggregate results from multiple subtasks

        Args:
            original_query: The original complex query
            subtask_results: List of subtask result dictionaries

        Returns:
            Aggregated summary
        """
        # Filter only completed tasks
        completed = [r for r in subtask_results if r["status"] == TaskStatus.COMPLETED.value and r["result"]]

        if not completed:
            return "No completed subtasks to aggregate."

        # Create aggregation prompt
        system_prompt = """You are a research synthesis expert. Your job is to aggregate and synthesize results from multiple independent subtasks into a coherent final answer.

Guidelines:
1. Identify common themes and patterns across results
2. Remove redundancy while preserving unique insights
3. Organize information logically
4. Provide a comprehensive summary that directly answers the original query
5. If there are conflicting findings, note them
6. Include key statistics and findings

Your output should be well-structured, comprehensive, and directly address the original query."""

        # Prepare results text
        results_text = "\n\n".join([
            f"=== Subtask {i+1}: {r['description']} ===\n{r['result']}"
            for i, r in enumerate(completed)
        ])

        user_message = f"""Original Query: {original_query}

Number of completed subtasks: {len(completed)}

Subtask Results:
{results_text}

Please provide a comprehensive synthesis that answers the original query."""

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_message)
        ]

        response = self.llm.invoke(messages)
        return response.content

    def aggregate_streaming(self, original_query: str, subtask_results: list[dict]) -> Generator[str, None, None]:
        """Stream aggregated results as they're synthesized

        Args:
            original_query: The original complex query
            subtask_results: List of subtask result dictionaries

        Yields:
            Chunks of aggregated text
        """
        # For now, return the full aggregation
        # In future, could implement true streaming with LLM streaming
        result = self.aggregate(original_query, subtask_results)
        yield result


class MetaAgent:
    """
    Meta-agent that orchestrates multiple A1 agents to handle complex multi-step tasks.

    Example usage:
        meta_agent = MetaAgent(max_workers=5)
        result = meta_agent.execute_complex_task(
            "Read and analyze 1000 papers about COVID-19 treatments"
        )
    """

    def __init__(
        self,
        max_workers: int = 3,
        max_batch_size: int = 50,
        max_retries: int = 2,
        checkpoint_dir: str = "./meta_agent_checkpoints",
        agent_config: dict = None,
        llm=None
    ):
        """Initialize the meta-agent

        Args:
            max_workers: Maximum number of parallel worker agents
            max_batch_size: Maximum items per subtask batch
            max_retries: Maximum retry attempts for failed subtasks
            checkpoint_dir: Directory for saving checkpoints
            agent_config: Configuration dict for A1 agents
            llm: Language model for task decomposition and aggregation
        """
        self.max_workers = max_workers
        self.max_batch_size = max_batch_size
        self.max_retries = max_retries
        self.checkpoint_dir = checkpoint_dir
        self.agent_config = agent_config or {}

        # Create checkpoint directory
        os.makedirs(checkpoint_dir, exist_ok=True)

        # Initialize components
        self.decomposer = TaskDecomposer(llm=llm)
        self.worker_pool = WorkerPool(max_workers=max_workers, agent_config=agent_config)
        self.aggregator = ResultAggregator(llm=llm)

        # Active meta-tasks
        self.meta_tasks: dict[str, MetaTaskState] = {}
        self.lock = threading.Lock()

    def execute_complex_task(
        self,
        query: str,
        meta_session_id: str = None,
        progress_callback: Callable[[dict], None] = None
    ) -> MetaTaskState:
        """Execute a complex task by decomposing it into subtasks

        Args:
            query: The complex query to execute
            meta_session_id: Optional session ID (generated if not provided)
            progress_callback: Optional callback for progress updates

        Returns:
            MetaTaskState with final results
        """
        # Generate session ID if not provided
        if meta_session_id is None:
            meta_session_id = str(uuid.uuid4())

        # Create meta-task state
        meta_state = MetaTaskState(
            meta_session_id=meta_session_id,
            original_query=query,
            status=TaskStatus.RUNNING
        )

        with self.lock:
            self.meta_tasks[meta_session_id] = meta_state

        try:
            # Step 1: Extract file list from query (if any)
            files = self.decomposer.extract_file_list(query)

            if files and progress_callback:
                progress_callback({
                    "type": "files_detected",
                    "message": f"Detected {len(files)} files in query",
                    "file_count": len(files),
                    "files": files[:10]  # Show first 10
                })

            # Step 2: Decompose task
            if progress_callback:
                progress_callback({
                    "type": "status",
                    "message": "Decomposing task into subtasks..."
                })

            # Use file-aware decomposition if files were found
            if files:
                subtask_descriptions = self.decomposer.decompose_with_files(query, files, self.max_batch_size)
            else:
                subtask_descriptions = self.decomposer.decompose(query, self.max_batch_size)

            # Create SubTask objects
            subtasks = [
                SubTask(
                    subtask_id=f"{meta_session_id}_sub_{i}",
                    description=desc
                )
                for i, desc in enumerate(subtask_descriptions)
            ]

            meta_state.subtasks = subtasks
            meta_state.total_count = len(subtasks)

            if progress_callback:
                progress_callback({
                    "type": "decomposition",
                    "message": f"Task decomposed into {len(subtasks)} subtasks",
                    "subtask_count": len(subtasks)
                })

            # Step 2: Start worker pool
            self.worker_pool.start()

            # Step 3: Submit all subtasks
            for subtask in subtasks:
                self.worker_pool.submit_task(subtask)

            if progress_callback:
                progress_callback({
                    "type": "status",
                    "message": f"Submitted {len(subtasks)} subtasks to worker pool"
                })

            # Step 4: Monitor progress and collect results
            completed = 0
            while completed < len(subtasks):
                try:
                    # Get result with timeout
                    result_subtask = self.worker_pool.result_queue.get(timeout=5.0)

                    # Update subtask in meta_state
                    for i, st in enumerate(meta_state.subtasks):
                        if st.subtask_id == result_subtask.subtask_id:
                            meta_state.subtasks[i] = result_subtask
                            break

                    if result_subtask.status == TaskStatus.COMPLETED:
                        completed += 1
                        meta_state.completed_count += 1
                    elif result_subtask.status == TaskStatus.FAILED:
                        meta_state.failed_count += 1

                        # Retry logic
                        if result_subtask.retry_count < self.max_retries:
                            result_subtask.retry_count += 1
                            result_subtask.status = TaskStatus.PENDING
                            self.worker_pool.submit_task(result_subtask)
                            if progress_callback:
                                progress_callback({
                                    "type": "retry",
                                    "message": f"Retrying failed subtask {result_subtask.subtask_id} (attempt {result_subtask.retry_count})"
                                })
                        else:
                            completed += 1

                    meta_state.updated_at = datetime.now()

                    # Progress update
                    if progress_callback:
                        progress_callback({
                            "type": "progress",
                            "completed": meta_state.completed_count,
                            "failed": meta_state.failed_count,
                            "total": meta_state.total_count,
                            "percentage": (meta_state.completed_count / meta_state.total_count) * 100
                        })

                    # Save checkpoint
                    self._save_checkpoint(meta_state)

                except queue.Empty:
                    continue

            # Step 5: Aggregate results
            if progress_callback:
                progress_callback({
                    "type": "status",
                    "message": "Aggregating results from all subtasks..."
                })

            aggregated_result = self.aggregator.aggregate(
                query,
                [st.to_dict() for st in meta_state.subtasks]
            )

            meta_state.aggregated_result = aggregated_result
            meta_state.status = TaskStatus.COMPLETED
            meta_state.updated_at = datetime.now()

            # Final checkpoint
            self._save_checkpoint(meta_state)

            if progress_callback:
                progress_callback({
                    "type": "completed",
                    "message": "Meta-task completed successfully",
                    "result": aggregated_result
                })

            return meta_state

        except Exception as e:
            meta_state.status = TaskStatus.FAILED
            meta_state.error = str(e)
            meta_state.updated_at = datetime.now()

            if progress_callback:
                progress_callback({
                    "type": "error",
                    "message": f"Meta-task failed: {str(e)}"
                })

            return meta_state

        finally:
            # Cleanup
            self.worker_pool.shutdown()

    def execute_complex_task_sequential(
        self,
        query: str,
        meta_session_id: str = None,
        progress_callback: Callable[[dict], None] = None,
        items_per_batch: int = None,
        pause_between_batches: float = 0
    ) -> MetaTaskState:
        """Execute a complex task sequentially (one batch at a time) instead of in parallel.

        This mode gives more control and is useful when:
        - You want to control resource usage
        - You need to process batches one at a time
        - You want to review intermediate results before continuing
        - You have rate limits to respect

        Args:
            query: The complex query to execute
            meta_session_id: Optional session ID (generated if not provided)
            progress_callback: Optional callback for progress updates
            items_per_batch: Number of items per batch (overrides max_batch_size if provided)
            pause_between_batches: Seconds to pause between batches (useful for rate limiting)

        Returns:
            MetaTaskState with final results
        """
        # Generate session ID if not provided
        if meta_session_id is None:
            meta_session_id = str(uuid.uuid4())

        # Use custom batch size if provided
        batch_size = items_per_batch if items_per_batch is not None else self.max_batch_size

        # Create meta-task state
        meta_state = MetaTaskState(
            meta_session_id=meta_session_id,
            original_query=query,
            status=TaskStatus.RUNNING
        )

        with self.lock:
            self.meta_tasks[meta_session_id] = meta_state

        # Create a single agent for sequential processing
        agent = A1(**self.agent_config)

        try:
            # Step 1: Extract file list from query (if any)
            files = self.decomposer.extract_file_list(query)

            if files and progress_callback:
                progress_callback({
                    "type": "files_detected",
                    "message": f"Detected {len(files)} files in query",
                    "file_count": len(files),
                    "files": files[:10]  # Show first 10
                })

            # Step 2: Decompose task
            if progress_callback:
                progress_callback({
                    "type": "status",
                    "message": f"Decomposing task into batches of {batch_size} items..."
                })

            # Use file-aware decomposition if files were found
            if files:
                subtask_descriptions = self.decomposer.decompose_with_files(query, files, batch_size)
            else:
                subtask_descriptions = self.decomposer.decompose(query, batch_size)

            # Create SubTask objects
            subtasks = [
                SubTask(
                    subtask_id=f"{meta_session_id}_sub_{i}",
                    description=desc
                )
                for i, desc in enumerate(subtask_descriptions)
            ]

            meta_state.subtasks = subtasks
            meta_state.total_count = len(subtasks)

            if progress_callback:
                progress_callback({
                    "type": "decomposition",
                    "message": f"Task decomposed into {len(subtasks)} sequential batches",
                    "subtask_count": len(subtasks),
                    "mode": "sequential"
                })

            # Step 2: Process subtasks sequentially
            for i, subtask in enumerate(subtasks, 1):
                if progress_callback:
                    progress_callback({
                        "type": "status",
                        "message": f"Processing batch {i}/{len(subtasks)}: {subtask.description[:100]}..."
                    })

                # Update subtask status
                subtask.status = TaskStatus.RUNNING
                subtask.start_time = datetime.now()
                subtask.worker_id = "sequential_worker"

                # Execute subtask
                retry_count = 0
                success = False

                while retry_count <= self.max_retries and not success:
                    try:
                        log, result = agent.go(subtask.description)

                        # Task completed successfully
                        subtask.status = TaskStatus.COMPLETED
                        subtask.result = result
                        subtask.end_time = datetime.now()
                        meta_state.completed_count += 1
                        success = True

                        if progress_callback:
                            progress_callback({
                                "type": "batch_complete",
                                "batch_number": i,
                                "batch_result": result[:200] + "..." if len(result) > 200 else result
                            })

                    except Exception as e:
                        retry_count += 1
                        subtask.retry_count = retry_count

                        if retry_count <= self.max_retries:
                            if progress_callback:
                                progress_callback({
                                    "type": "retry",
                                    "message": f"Batch {i} failed, retrying (attempt {retry_count}/{self.max_retries}): {str(e)}"
                                })
                            time.sleep(2)  # Brief pause before retry
                        else:
                            # Max retries exhausted
                            subtask.status = TaskStatus.FAILED
                            subtask.error = str(e)
                            subtask.end_time = datetime.now()
                            meta_state.failed_count += 1

                            if progress_callback:
                                progress_callback({
                                    "type": "batch_failed",
                                    "batch_number": i,
                                    "error": str(e)
                                })

                # Update progress
                meta_state.updated_at = datetime.now()

                if progress_callback:
                    progress_callback({
                        "type": "progress",
                        "completed": meta_state.completed_count,
                        "failed": meta_state.failed_count,
                        "total": meta_state.total_count,
                        "percentage": (meta_state.completed_count / meta_state.total_count) * 100,
                        "mode": "sequential"
                    })

                # Save checkpoint after each batch
                self._save_checkpoint(meta_state)

                # Pause between batches if specified
                if pause_between_batches > 0 and i < len(subtasks):
                    if progress_callback:
                        progress_callback({
                            "type": "status",
                            "message": f"Pausing for {pause_between_batches}s before next batch..."
                        })
                    time.sleep(pause_between_batches)

            # Step 3: Aggregate results
            if progress_callback:
                progress_callback({
                    "type": "status",
                    "message": "Aggregating results from all batches..."
                })

            aggregated_result = self.aggregator.aggregate(
                query,
                [st.to_dict() for st in meta_state.subtasks]
            )

            meta_state.aggregated_result = aggregated_result
            meta_state.status = TaskStatus.COMPLETED
            meta_state.updated_at = datetime.now()

            # Final checkpoint
            self._save_checkpoint(meta_state)

            if progress_callback:
                progress_callback({
                    "type": "completed",
                    "message": "Sequential task completed successfully",
                    "result": aggregated_result
                })

            return meta_state

        except Exception as e:
            meta_state.status = TaskStatus.FAILED
            meta_state.error = str(e)
            meta_state.updated_at = datetime.now()

            if progress_callback:
                progress_callback({
                    "type": "error",
                    "message": f"Sequential task failed: {str(e)}"
                })

            return meta_state

    def execute_complex_task_async(
        self,
        query: str,
        meta_session_id: str = None,
        progress_callback: Callable[[dict], None] = None,
        mode: str = "parallel"
    ) -> str:
        """Execute a complex task asynchronously in a background thread

        Args:
            query: The complex query to execute
            meta_session_id: Optional session ID (generated if not provided)
            progress_callback: Optional callback for progress updates
            mode: "parallel" (default) or "sequential"

        Returns:
            meta_session_id for tracking progress
        """
        if meta_session_id is None:
            meta_session_id = str(uuid.uuid4())

        def run_task():
            if mode == "sequential":
                self.execute_complex_task_sequential(query, meta_session_id, progress_callback)
            else:
                self.execute_complex_task(query, meta_session_id, progress_callback)

        thread = threading.Thread(target=run_task, daemon=True)
        thread.start()

        return meta_session_id

    def get_progress(self, meta_session_id: str) -> Optional[dict]:
        """Get current progress of a meta-task

        Args:
            meta_session_id: Session ID of the meta-task

        Returns:
            Progress dictionary or None if not found
        """
        with self.lock:
            if meta_session_id in self.meta_tasks:
                meta_state = self.meta_tasks[meta_session_id]
                return {
                    "meta_session_id": meta_session_id,
                    "status": meta_state.status.value,
                    "completed": meta_state.completed_count,
                    "failed": meta_state.failed_count,
                    "total": meta_state.total_count,
                    "percentage": (meta_state.completed_count / meta_state.total_count * 100) if meta_state.total_count > 0 else 0,
                    "aggregated_result": meta_state.aggregated_result,
                    "worker_status": self.worker_pool.get_worker_status()
                }
        return None

    def _save_checkpoint(self, meta_state: MetaTaskState) -> None:
        """Save checkpoint to disk"""
        checkpoint_path = os.path.join(
            self.checkpoint_dir,
            f"{meta_state.meta_session_id}.json"
        )

        try:
            with open(checkpoint_path, 'w') as f:
                json.dump(meta_state.to_dict(), f, indent=2)
            meta_state.checkpoint_path = checkpoint_path
        except Exception as e:
            print(f"Failed to save checkpoint: {e}")

    def load_checkpoint(self, meta_session_id: str) -> Optional[MetaTaskState]:
        """Load checkpoint from disk

        Args:
            meta_session_id: Session ID to load

        Returns:
            MetaTaskState or None if not found
        """
        checkpoint_path = os.path.join(
            self.checkpoint_dir,
            f"{meta_session_id}.json"
        )

        if not os.path.exists(checkpoint_path):
            return None

        try:
            with open(checkpoint_path, 'r') as f:
                data = json.load(f)

            # Reconstruct MetaTaskState
            # Note: This is a simplified reconstruction
            # In production, you'd want proper deserialization
            return data

        except Exception as e:
            print(f"Failed to load checkpoint: {e}")
            return None

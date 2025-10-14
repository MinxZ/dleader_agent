"""
Example demonstrating the MetaAgent for complex multi-step tasks.

This shows how to use the MetaAgent to handle tasks that require processing
multiple items in parallel, such as reading many papers or analyzing datasets.
"""

from dleader_agent.agent.meta_agent import MetaAgent


def progress_callback(update: dict):
    """Callback to print progress updates"""
    update_type = update.get("type")

    if update_type == "status":
        print(f"📌 {update['message']}")

    elif update_type == "decomposition":
        print(f"🔍 {update['message']}")
        print(f"   Total subtasks: {update['subtask_count']}")

    elif update_type == "progress":
        percentage = update['percentage']
        completed = update['completed']
        total = update['total']
        failed = update['failed']
        print(f"📊 Progress: {completed}/{total} completed ({percentage:.1f}%), {failed} failed")

    elif update_type == "retry":
        print(f"🔄 {update['message']}")

    elif update_type == "completed":
        print(f"✅ {update['message']}")
        print(f"\n{'='*60}")
        print("FINAL RESULT:")
        print(f"{'='*60}")
        print(update['result'])
        print(f"{'='*60}")

    elif update_type == "error":
        print(f"❌ {update['message']}")


def example_paper_analysis():
    """Example: Analyze multiple papers (simulated with smaller task)"""
    print("🧬 MetaAgent Example: Paper Analysis")
    print("="*60)

    # Create meta-agent with 3 parallel workers
    meta_agent = MetaAgent(
        max_workers=3,
        max_batch_size=10,  # Process 10 papers per subtask
        max_retries=2,
        agent_config={
            "use_tool_retriever": True,
            "download_data_lake": False,
            "llm": "claude-sonnet-4-5-20250929"
        }
    )

    # Example query - for demo, use a smaller number
    query = """Find and summarize 30 recent research papers about mRNA vaccines for COVID-19.
For each paper, extract: title, authors, key findings, methodology, and conclusions.
Organize the findings by theme and identify common patterns."""

    print(f"\n📝 Query: {query}\n")

    # Execute the complex task
    result = meta_agent.execute_complex_task(
        query=query,
        progress_callback=progress_callback
    )

    # Print final summary
    print(f"\n{'='*60}")
    print("META-TASK SUMMARY")
    print(f"{'='*60}")
    print(f"Status: {result.status.value}")
    print(f"Total subtasks: {result.total_count}")
    print(f"Completed: {result.completed_count}")
    print(f"Failed: {result.failed_count}")
    print(f"Duration: {(result.updated_at - result.created_at).total_seconds():.1f} seconds")

    return result


def example_simple_batch_task():
    """Example: Simple batch processing task"""
    print("🔧 MetaAgent Example: Batch Data Processing")
    print("="*60)

    meta_agent = MetaAgent(
        max_workers=2,
        max_batch_size=5,
        agent_config={
            "use_tool_retriever": False,
            "download_data_lake": False
        }
    )

    query = """Analyze 15 different gene sequences for common mutations.
For each sequence, identify: mutation type, location, potential impact, and conservation score."""

    print(f"\n📝 Query: {query}\n")

    result = meta_agent.execute_complex_task(
        query=query,
        progress_callback=progress_callback
    )

    return result


def example_async_execution():
    """Example: Asynchronous execution with progress monitoring"""
    print("⚡ MetaAgent Example: Async Execution")
    print("="*60)

    meta_agent = MetaAgent(max_workers=3, max_batch_size=10)

    query = "Process and analyze 25 protein structures from PDB database"

    print(f"\n📝 Query: {query}\n")
    print("Starting async execution...")

    # Start task asynchronously
    meta_session_id = meta_agent.execute_complex_task_async(
        query=query,
        progress_callback=progress_callback
    )

    print(f"Meta-session ID: {meta_session_id}")
    print("Task is running in background. You can monitor progress...")

    # In a real application, you would:
    # 1. Return the meta_session_id to the user
    # 2. Provide an API endpoint to check progress
    # 3. Use WebSocket for real-time updates

    # For demo, just wait a bit and check progress
    import time
    time.sleep(5)

    progress = meta_agent.get_progress(meta_session_id)
    if progress:
        print(f"\n📊 Current Progress:")
        print(f"   Status: {progress['status']}")
        print(f"   Completed: {progress['completed']}/{progress['total']}")
        print(f"   Percentage: {progress['percentage']:.1f}%")

    return meta_session_id


if __name__ == "__main__":
    print("🚀 MetaAgent Examples")
    print("="*60)
    print("\nThe MetaAgent automatically:")
    print("  • Decomposes complex tasks into subtasks")
    print("  • Executes subtasks in parallel using multiple agents")
    print("  • Monitors progress and handles failures")
    print("  • Aggregates results intelligently")
    print("  • Saves checkpoints for recovery")
    print()

    # Choose which example to run
    examples = {
        "1": ("Paper Analysis (Recommended)", example_paper_analysis),
        "2": ("Simple Batch Processing", example_simple_batch_task),
        "3": ("Async Execution Demo", example_async_execution)
    }

    print("Available examples:")
    for key, (name, _) in examples.items():
        print(f"  {key}. {name}")

    print("\nNote: For testing, examples use small batch sizes.")
    print("In production, you can process 1000+ items efficiently.\n")

    # Run the first example by default
    print("Running Example 1: Paper Analysis\n")
    example_paper_analysis()

    print("\n✨ MetaAgent example completed!")
    print("\nUsage in your code:")
    print("""
    from dleader_agent.agent.meta_agent import MetaAgent

    # Create meta-agent
    meta_agent = MetaAgent(max_workers=5, max_batch_size=50)

    # Execute complex task
    result = meta_agent.execute_complex_task(
        "Read and analyze 1000 papers about cancer treatments",
        progress_callback=your_callback_function
    )

    # Access results
    print(result.aggregated_result)
    print(f"Completed: {result.completed_count}/{result.total_count}")
    """)

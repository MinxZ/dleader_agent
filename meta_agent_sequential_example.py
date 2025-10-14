"""
Example demonstrating Sequential (Loop) Mode for MetaAgent.

This shows how to process batches one at a time with full control over
batch size, pauses between batches, and intermediate results.
"""

from dleader_agent.agent.meta_agent import MetaAgent


def progress_callback(update: dict):
    """Enhanced callback to show batch-by-batch progress"""
    update_type = update.get("type")

    if update_type == "status":
        print(f"📌 {update['message']}")

    elif update_type == "decomposition":
        mode = update.get('mode', 'parallel')
        print(f"🔍 {update['message']} (Mode: {mode.upper()})")
        print(f"   Total batches: {update['subtask_count']}")

    elif update_type == "batch_complete":
        batch_num = update['batch_number']
        result_preview = update['batch_result']
        print(f"\n✅ Batch {batch_num} completed!")
        print(f"   Preview: {result_preview}")

    elif update_type == "batch_failed":
        batch_num = update['batch_number']
        error = update['error']
        print(f"\n❌ Batch {batch_num} failed: {error}")

    elif update_type == "progress":
        percentage = update['percentage']
        completed = update['completed']
        total = update['total']
        failed = update['failed']
        mode = update.get('mode', 'parallel')
        print(f"\n📊 Overall Progress ({mode}): {completed}/{total} ({percentage:.1f}%), {failed} failed")

    elif update_type == "retry":
        print(f"🔄 {update['message']}")

    elif update_type == "completed":
        print(f"\n✅ {update['message']}")
        print(f"\n{'='*60}")
        print("FINAL AGGREGATED RESULT:")
        print(f"{'='*60}")
        print(update['result'])
        print(f"{'='*60}")

    elif update_type == "error":
        print(f"❌ {update['message']}")


def example_sequential_processing():
    """Example: Process items sequentially with custom batch size"""
    print("🔄 MetaAgent Sequential Mode Example")
    print("="*60)
    print("Processing batches one at a time for full control\n")

    # Create meta-agent (max_workers doesn't matter for sequential mode)
    meta_agent = MetaAgent(
        max_workers=1,  # Not used in sequential mode
        max_batch_size=10,  # Default batch size
        agent_config={
            "use_tool_retriever": True,
            "download_data_lake": False,
            "llm": "claude-sonnet-4-20250514"
        }
    )

    # Example query
    query = """Find and summarize 30 recent research papers about CRISPR gene editing.
For each paper, extract: title, authors, key innovation, and clinical implications."""

    print(f"📝 Query: {query}\n")
    print("Configuration:")
    print("  • Mode: Sequential (loop)")
    print("  • Batch size: 10 papers per batch")
    print("  • Pause between batches: 2 seconds")
    print()

    # Execute in sequential mode with custom settings
    result = meta_agent.execute_complex_task_sequential(
        query=query,
        items_per_batch=10,  # Process 10 papers at a time
        pause_between_batches=2,  # Wait 2 seconds between batches
        progress_callback=progress_callback
    )

    # Print summary
    print(f"\n{'='*60}")
    print("SEQUENTIAL PROCESSING SUMMARY")
    print(f"{'='*60}")
    print(f"Status: {result.status.value}")
    print(f"Total batches: {result.total_count}")
    print(f"Completed: {result.completed_count}")
    print(f"Failed: {result.failed_count}")
    print(f"Duration: {(result.updated_at - result.created_at).total_seconds():.1f} seconds")

    return result


def example_controlled_batch_sizes():
    """Example: Compare different batch sizes"""
    print("\n🔬 Comparing Different Batch Sizes")
    print("="*60)

    meta_agent = MetaAgent(
        agent_config={
            "use_tool_retriever": False,
            "download_data_lake": False
        }
    )

    query = "Analyze 50 gene sequences for mutations"

    # Test with different batch sizes
    batch_sizes = [5, 10, 25]

    for batch_size in batch_sizes:
        print(f"\n{'='*60}")
        print(f"Testing with batch size: {batch_size}")
        print(f"{'='*60}")

        result = meta_agent.execute_complex_task_sequential(
            query=query,
            items_per_batch=batch_size,
            progress_callback=lambda u: print(f"  {u.get('message', '')}")
            if u.get('type') == 'status' else None
        )

        batches = result.total_count
        print(f"Result: {batches} batches, "
              f"{result.completed_count} completed in "
              f"{(result.updated_at - result.created_at).total_seconds():.1f}s")


def example_with_rate_limiting():
    """Example: Respect rate limits with pauses"""
    print("\n⏱️  Sequential Processing with Rate Limiting")
    print("="*60)
    print("Useful for APIs with rate limits\n")

    meta_agent = MetaAgent(
        agent_config={
            "use_tool_retriever": False,
            "download_data_lake": False
        }
    )

    query = "Process 20 protein structures from PDB database"

    print("Configuration:")
    print("  • Batch size: 5 structures per batch")
    print("  • Pause: 5 seconds between batches (respecting rate limits)")
    print()

    result = meta_agent.execute_complex_task_sequential(
        query=query,
        items_per_batch=5,
        pause_between_batches=5,  # 5 second pause
        progress_callback=progress_callback
    )

    print(f"\nProcessed {result.completed_count} batches with rate limiting")
    return result


def example_inspect_intermediate_results():
    """Example: Inspect results after each batch"""
    print("\n🔍 Inspecting Intermediate Results")
    print("="*60)
    print("See results batch-by-batch as they complete\n")

    meta_agent = MetaAgent()

    # Store intermediate results
    batch_results = []

    def detailed_callback(update):
        """Callback that captures intermediate results"""
        if update.get("type") == "batch_complete":
            batch_num = update["batch_number"]
            result = update["batch_result"]
            batch_results.append({
                "batch": batch_num,
                "result": result
            })
            print(f"\n✅ Batch {batch_num} Result:")
            print(f"   {result[:150]}...")
            print(f"   Captured {len(batch_results)} batch results so far")

        elif update.get("type") == "progress":
            pct = update["percentage"]
            print(f"📊 Progress: {pct:.1f}%")

    query = "Summarize 15 articles about machine learning in healthcare"

    result = meta_agent.execute_complex_task_sequential(
        query=query,
        items_per_batch=5,
        progress_callback=detailed_callback
    )

    print(f"\n{'='*60}")
    print("INTERMEDIATE RESULTS SUMMARY")
    print(f"{'='*60}")
    print(f"Captured {len(batch_results)} batch results:")
    for br in batch_results:
        print(f"\n  Batch {br['batch']}:")
        print(f"    {br['result'][:100]}...")

    return result, batch_results


def comparison_parallel_vs_sequential():
    """Compare parallel and sequential modes"""
    print("\n⚖️  Parallel vs Sequential Mode Comparison")
    print("="*60)

    meta_agent = MetaAgent(
        max_workers=3,
        max_batch_size=10,
        agent_config={
            "use_tool_retriever": False,
            "download_data_lake": False
        }
    )

    query = "Analyze 30 data points for trends"

    print("📊 Mode Comparison:\n")

    # Sequential mode
    print("1. SEQUENTIAL MODE:")
    print("   ✅ Process one batch at a time")
    print("   ✅ Full control over each batch")
    print("   ✅ See intermediate results immediately")
    print("   ✅ Easy to pause/resume")
    print("   ✅ Lower memory usage")
    print("   ❌ Slower overall completion")
    print()

    # Parallel mode
    print("2. PARALLEL MODE:")
    print("   ✅ Process multiple batches simultaneously")
    print("   ✅ Faster overall completion")
    print("   ✅ Efficient resource utilization")
    print("   ❌ Higher memory usage")
    print("   ❌ Less control over individual batches")
    print()

    print("Choose based on your needs:")
    print("  • Sequential: Better for rate limits, debugging, controlled processing")
    print("  • Parallel: Better for speed, large-scale tasks, when resources allow")


if __name__ == "__main__":
    print("🚀 MetaAgent Sequential Mode Examples")
    print("="*60)
    print("\nSequential mode processes batches one at a time, giving you:")
    print("  • Full control over batch size")
    print("  • Ability to pause between batches")
    print("  • Immediate visibility into each batch result")
    print("  • Lower resource usage")
    print("  • Perfect for rate-limited APIs")
    print()

    # Available examples
    examples = {
        "1": ("Sequential Processing with Custom Batch Size", example_sequential_processing),
        "2": ("Different Batch Sizes Comparison", example_controlled_batch_sizes),
        "3": ("Rate Limiting with Pauses", example_with_rate_limiting),
        "4": ("Inspect Intermediate Results", example_inspect_intermediate_results),
        "5": ("Parallel vs Sequential Comparison", comparison_parallel_vs_sequential)
    }

    print("Available examples:")
    for key, (name, _) in examples.items():
        print(f"  {key}. {name}")

    print("\nRunning Example 1: Sequential Processing\n")
    example_sequential_processing()

    print("\n" + "="*60)
    print("✨ Example completed!")
    print("\nUsage in your code:")
    print("""
    from dleader_agent.agent.meta_agent import MetaAgent

    # Create meta-agent
    meta_agent = MetaAgent()

    # Sequential mode - process one batch at a time
    result = meta_agent.execute_complex_task_sequential(
        query="Analyze 1000 papers about cancer treatments",
        items_per_batch=50,  # 50 papers per batch
        pause_between_batches=2,  # 2 second pause between batches
        progress_callback=your_callback
    )

    # OR use parallel mode for speed
    result = meta_agent.execute_complex_task(
        query="Same query",
        progress_callback=your_callback
    )

    # Both return the same MetaTaskState with results
    print(result.aggregated_result)
    """)

    print("\n📝 Batch Control Examples:")
    print("""
    # Small batches for detailed progress
    items_per_batch=10  # Process 10 items at a time

    # Large batches for efficiency
    items_per_batch=100  # Process 100 items at a time

    # Respect API rate limits
    pause_between_batches=5  # 5 second pause

    # No pause (fastest sequential)
    pause_between_batches=0  # No pause (default)
    """)

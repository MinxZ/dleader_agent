"""
Example: Using MetaAgent with Explicit File Lists

This demonstrates how to provide file paths or URLs in your query,
and how the MetaAgent distributes them to subagents.
"""

from dleader_agent.agent.meta_agent import MetaAgent


def progress_callback(update: dict):
    """Callback to show progress with file distribution"""
    update_type = update.get("type")

    if update_type == "files_detected":
        print(f"📁 {update['message']}")
        print(f"   Files: {', '.join(update['files'])}")
        if update['file_count'] > len(update['files']):
            print(f"   ... and {update['file_count'] - len(update['files'])} more")

    elif update_type == "decomposition":
        print(f"🔍 {update['message']}")
        print(f"   Each batch will process specific files")

    elif update_type == "batch_complete":
        print(f"✅ Batch {update['batch_number']} completed")

    elif update_type == "progress":
        pct = update['percentage']
        completed = update['completed']
        total = update['total']
        print(f"📊 Progress: {completed}/{total} batches ({pct:.1f}%)")

    elif update_type == "completed":
        print(f"\n✅ All files processed!")
        print(f"\n{'='*60}")
        print("FINAL AGGREGATED RESULT:")
        print(f"{'='*60}")
        print(update['result'][:500] + "..." if len(update['result']) > 500 else update['result'])


def example_1_list_format():
    """Example 1: Files in list format [file1, file2, ...]"""
    print("=" * 60)
    print("EXAMPLE 1: Files in List Format")
    print("=" * 60)

    meta_agent = MetaAgent(max_workers=2, max_batch_size=5)

    # Query with file list in brackets
    query = """Analyze these research papers and extract key findings:
[paper1.pdf, paper2.pdf, paper3.pdf, paper4.pdf, paper5.pdf,
 paper6.pdf, paper7.pdf, paper8.pdf, paper9.pdf, paper10.pdf]

For each paper, extract:
- Title and authors
- Main research question
- Key findings
- Methodology used"""

    print(f"Query: {query}\n")

    result = meta_agent.execute_complex_task(
        query=query,
        progress_callback=progress_callback
    )

    print(f"\nProcessed {result.completed_count} batches")
    return result


def example_2_comma_separated():
    """Example 2: Comma-separated file list with 'files:' prefix"""
    print("\n" + "=" * 60)
    print("EXAMPLE 2: Comma-Separated with 'files:' Prefix")
    print("=" * 60)

    meta_agent = MetaAgent(max_workers=3, max_batch_size=10)

    query = """Summarize clinical trial data from these PDFs:

Files: trial_001.pdf, trial_002.pdf, trial_003.pdf, trial_004.pdf,
       trial_005.pdf, trial_006.pdf, trial_007.pdf, trial_008.pdf,
       trial_009.pdf, trial_010.pdf, trial_011.pdf, trial_012.pdf

Extract patient outcomes, adverse events, and efficacy data."""

    print(f"Query: {query}\n")

    result = meta_agent.execute_complex_task(
        query=query,
        progress_callback=progress_callback
    )

    print(f"\nProcessed {result.completed_count} batches")
    return result


def example_3_file_paths():
    """Example 3: Full file paths"""
    print("\n" + "=" * 60)
    print("EXAMPLE 3: Full File Paths")
    print("=" * 60)

    meta_agent = MetaAgent(max_workers=2, max_batch_size=3)

    query = """Analyze gene expression data from these CSV files:
./data/samples/sample_001.csv
./data/samples/sample_002.csv
./data/samples/sample_003.csv
./data/samples/sample_004.csv
./data/samples/sample_005.csv
./data/samples/sample_006.csv

Calculate differential expression and identify significant genes."""

    print(f"Query: {query}\n")

    result = meta_agent.execute_complex_task(
        query=query,
        progress_callback=progress_callback
    )

    print(f"\nProcessed {result.completed_count} batches")
    return result


def example_4_urls():
    """Example 4: URLs to papers"""
    print("\n" + "=" * 60)
    print("EXAMPLE 4: URLs to Papers")
    print("=" * 60)

    meta_agent = MetaAgent(max_workers=2, max_batch_size=5)

    query = """Download and analyze these research papers:

Papers:
https://arxiv.org/pdf/2301.00001.pdf
https://arxiv.org/pdf/2301.00002.pdf
https://arxiv.org/pdf/2301.00003.pdf
https://arxiv.org/pdf/2301.00004.pdf
https://arxiv.org/pdf/2301.00005.pdf
https://arxiv.org/pdf/2301.00006.pdf
https://arxiv.org/pdf/2301.00007.pdf
https://arxiv.org/pdf/2301.00008.pdf
https://arxiv.org/pdf/2301.00009.pdf
https://arxiv.org/pdf/2301.00010.pdf

Summarize the main contributions and methodologies."""

    print(f"Query: {query}\n")

    result = meta_agent.execute_complex_task(
        query=query,
        progress_callback=progress_callback
    )

    print(f"\nProcessed {result.completed_count} batches")
    return result


def example_5_sequential_with_files():
    """Example 5: Sequential processing with file list"""
    print("\n" + "=" * 60)
    print("EXAMPLE 5: Sequential Mode with File List")
    print("=" * 60)

    meta_agent = MetaAgent()

    query = """Process these patient records one batch at a time:
[patient_001.json, patient_002.json, patient_003.json, patient_004.json,
 patient_005.json, patient_006.json, patient_007.json, patient_008.json]

Extract demographic data, diagnosis, and treatment outcomes."""

    print(f"Query: {query}\n")

    result = meta_agent.execute_complex_task_sequential(
        query=query,
        items_per_batch=2,  # 2 files per batch
        pause_between_batches=1,
        progress_callback=progress_callback
    )

    print(f"\nProcessed {result.completed_count} batches sequentially")
    return result


def example_6_mixed_format():
    """Example 6: Mixed file paths and URLs"""
    print("\n" + "=" * 60)
    print("EXAMPLE 6: Mixed File Paths and URLs")
    print("=" * 60)

    meta_agent = MetaAgent(max_workers=2, max_batch_size=4)

    query = """Analyze these research materials:

Files to process:
- Local files: ./papers/intro.pdf, ./papers/methods.pdf, ./papers/results.pdf
- URLs: https://example.com/paper1.pdf, https://example.com/paper2.pdf
- Data files: /data/dataset1.csv, /data/dataset2.csv, /data/dataset3.csv

Compile a comprehensive literature review."""

    print(f"Query: {query}\n")

    result = meta_agent.execute_complex_task(
        query=query,
        progress_callback=progress_callback
    )

    print(f"\nProcessed {result.completed_count} batches")
    return result


def demo_file_extraction():
    """Demonstrate how file extraction works"""
    print("\n" + "=" * 60)
    print("DEMO: How File Extraction Works")
    print("=" * 60)

    from dleader_agent.agent.meta_agent import TaskDecomposer

    decomposer = TaskDecomposer()

    test_queries = [
        "Process [file1.pdf, file2.pdf, file3.pdf]",
        "Files: paper1.pdf, paper2.pdf, paper3.pdf",
        "./data/sample1.csv, ./data/sample2.csv",
        "https://example.com/doc1.pdf https://example.com/doc2.pdf",
        "Analyze /path/to/file1.txt and /path/to/file2.txt"
    ]

    for i, query in enumerate(test_queries, 1):
        print(f"\n{i}. Query: {query}")
        files = decomposer.extract_file_list(query)
        print(f"   Extracted files: {files}")


def show_subtask_distribution():
    """Show how files are distributed to subtasks"""
    print("\n" + "=" * 60)
    print("DEMO: File Distribution to Subtasks")
    print("=" * 60)

    from dleader_agent.agent.meta_agent import TaskDecomposer

    decomposer = TaskDecomposer()

    files = [f"paper_{i:03d}.pdf" for i in range(1, 26)]  # 25 files
    query = "Analyze these papers for key findings"

    print(f"Total files: {len(files)}")
    print(f"Files: {', '.join(files[:5])} ... {', '.join(files[-2:])}")
    print(f"\nBatch size: 10 files per batch")

    subtasks = decomposer.decompose_with_files(query, files, max_batch_size=10)

    print(f"\nCreated {len(subtasks)} subtasks:")
    for i, subtask in enumerate(subtasks, 1):
        print(f"\n--- Subtask {i} ---")
        print(subtask[:300] + "..." if len(subtask) > 300 else subtask)


if __name__ == "__main__":
    print("🧬 MetaAgent File List Examples")
    print("=" * 60)
    print("\nThe MetaAgent can automatically detect and distribute files from your query!")
    print("\nSupported formats:")
    print("  • List format: [file1.pdf, file2.pdf, ...]")
    print("  • Comma-separated: Files: paper1.pdf, paper2.pdf, ...")
    print("  • File paths: ./data/file1.csv, /path/to/file2.txt")
    print("  • URLs: https://example.com/paper.pdf")
    print("  • Mixed: Any combination of the above")
    print()

    # Run demos
    print("\n" + "=" * 60)
    print("DEMONSTRATION: File Extraction")
    print("=" * 60)
    demo_file_extraction()

    print("\n" + "=" * 60)
    print("DEMONSTRATION: Subtask Distribution")
    print("=" * 60)
    show_subtask_distribution()

    # Uncomment to run full examples (requires actual agent execution)
    # example_1_list_format()
    # example_2_comma_separated()
    # example_3_file_paths()
    # example_4_urls()
    # example_5_sequential_with_files()
    # example_6_mixed_format()

    print("\n" + "=" * 60)
    print("✨ How It Works:")
    print("=" * 60)
    print("""
1. You provide a query with file paths/URLs
2. MetaAgent detects and extracts all files
3. Files are split into batches (e.g., 10 files per batch)
4. Each subagent receives:
   - The main task description
   - Explicit list of files to process
   - Instructions to access those specific files
5. Results are aggregated across all batches

Example Query:
--------------
query = '''
Analyze these research papers:
[paper1.pdf, paper2.pdf, paper3.pdf, ..., paper100.pdf]

For each paper extract: title, authors, key findings
'''

MetaAgent will:
- Detect 100 files
- Create 10 batches (10 files each)
- Each subagent processes its assigned files
- Final result aggregates findings from all 100 papers
    """)

    print("\n📝 Template for Your Use:")
    print("=" * 60)
    print("""
from dleader_agent.agent.meta_agent import MetaAgent

meta_agent = MetaAgent(max_workers=5, max_batch_size=10)

# Your query with file list
query = '''
Analyze these papers:
[paper1.pdf, paper2.pdf, paper3.pdf, ...]

Extract: <what you want to extract>
'''

# Execute
result = meta_agent.execute_complex_task(query)

# Each subagent will know exactly which files to process!
print(result.aggregated_result)
    """)

    print("\n✅ The subagents will automatically know which files they're working on!")

"""
Gradio interface for MetaAgent - Complex Multi-Step Task Processing

This interface allows users to submit complex tasks that require processing
many items in parallel (e.g., "analyze 1000 papers") and monitor progress in real-time.
"""

import time
from datetime import datetime

import gradio as gr
import requests

# Configuration - adjust to match your FastAPI server
API_BASE_URL = "http://localhost:8000"


def submit_meta_task(query: str, user_id: str, max_workers: int, max_batch_size: int,
                     mode: str, items_per_batch: int, pause_between_batches: float):
    """Submit a complex task to the MetaAgent"""
    try:
        # Prepare request data
        request_data = {
            "query": query,
            "user_id": user_id,
            "mode": mode
        }

        # Add mode-specific parameters
        if mode == "parallel":
            request_data["max_workers"] = max_workers
            request_data["max_batch_size"] = max_batch_size
        else:  # sequential
            request_data["items_per_batch"] = items_per_batch
            request_data["pause_between_batches"] = pause_between_batches

        response = requests.post(
            f"{API_BASE_URL}/meta-task/submit",
            json=request_data,
            timeout=10
        )

        if response.status_code == 200:
            data = response.json()
            meta_session_id = data["meta_session_id"]
            return (
                f"✅ Task submitted successfully!\n\n"
                f"Meta-Session ID: {meta_session_id}\n"
                f"Status: Processing...\n\n"
                f"Use the session ID above to monitor progress.",
                meta_session_id
            )
        else:
            return f"❌ Error: {response.text}", ""

    except Exception as e:
        return f"❌ Failed to submit task: {str(e)}", ""


def check_meta_task_status(meta_session_id: str):
    """Check the status of a running meta-task"""
    if not meta_session_id:
        return "Please provide a valid meta-session ID", "", 0, ""

    try:
        response = requests.get(
            f"{API_BASE_URL}/meta-task/{meta_session_id}/status",
            timeout=10
        )

        if response.status_code == 200:
            data = response.json()

            status = data["status"]
            completed = data["completed"]
            failed = data["failed"]
            total = data["total"]
            percentage = data["percentage"]
            aggregated_result = data.get("aggregated_result", "")
            worker_status = data.get("worker_status", {})

            # Format worker status
            worker_info = "\n".join([
                f"  • {worker_id}: {info['status']}" +
                (f" (working on {info['current_task']})" if info['current_task'] else "")
                for worker_id, info in worker_status.items()
            ])

            status_text = f"""
📊 **Meta-Task Status**

**Session ID:** {meta_session_id}
**Status:** {status.upper()}
**Progress:** {completed}/{total} subtasks completed ({percentage:.1f}%)
**Failed:** {failed}

**Worker Status:**
{worker_info if worker_info else "  No active workers"}

**Last Updated:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
"""

            # Result text
            if aggregated_result:
                result_text = f"**Final Result:**\n\n{aggregated_result}"
            elif status == "running":
                result_text = "Task is still running. Results will appear when complete."
            elif status == "failed":
                result_text = "❌ Task failed. Check logs for details."
            else:
                result_text = "No results available yet."

            return status_text, result_text, percentage, status

        else:
            return f"❌ Error: {response.text}", "", 0, "error"

    except Exception as e:
        return f"❌ Failed to check status: {str(e)}", "", 0, "error"


def get_subtask_details(meta_session_id: str):
    """Get detailed information about all subtasks"""
    if not meta_session_id:
        return "Please provide a valid meta-session ID"

    try:
        response = requests.get(
            f"{API_BASE_URL}/meta-task/{meta_session_id}/subtasks",
            timeout=10
        )

        if response.status_code == 200:
            data = response.json()
            subtasks = data["subtasks"]

            if not subtasks:
                return "No subtasks found."

            # Format subtasks
            subtask_lines = []
            for i, st in enumerate(subtasks, 1):
                status_emoji = {
                    "completed": "✅",
                    "running": "🔄",
                    "pending": "⏳",
                    "failed": "❌",
                    "cancelled": "🚫"
                }.get(st["status"], "❓")

                line = f"{status_emoji} **Subtask {i}:** {st['status'].upper()}"
                if st.get("worker_id"):
                    line += f" (Worker: {st['worker_id']})"
                if st.get("error"):
                    line += f"\n   Error: {st['error'][:100]}..."

                subtask_lines.append(line)

            return "\n\n".join(subtask_lines)

        else:
            return f"❌ Error: {response.text}"

    except Exception as e:
        return f"❌ Failed to get subtasks: {str(e)}"


def cancel_meta_task(meta_session_id: str):
    """Cancel a running meta-task"""
    if not meta_session_id:
        return "Please provide a valid meta-session ID"

    try:
        response = requests.post(
            f"{API_BASE_URL}/meta-task/{meta_session_id}/cancel",
            timeout=10
        )

        if response.status_code == 200:
            data = response.json()
            return f"✅ {data['message']}"
        else:
            return f"❌ Error: {response.text}"

    except Exception as e:
        return f"❌ Failed to cancel task: {str(e)}"


def auto_refresh_status(meta_session_id: str, refresh_count: int):
    """Auto-refresh status for monitoring"""
    status_text, result_text, percentage, status = check_meta_task_status(meta_session_id)

    # Stop auto-refresh if task is complete or failed
    should_continue = status in ["running", "pending"]

    return status_text, result_text, percentage, should_continue


# Create Gradio interface
with gr.Blocks(title="MetaAgent - Complex Task Processing") as demo:
    gr.Markdown("""
    # 🧬 MetaAgent: Complex Multi-Step Task Processor

    Process large-scale tasks like analyzing 1000 papers, processing hundreds of datasets,
    or any task requiring parallel execution across many items.

    **How it works:**
    1. Submit your complex query
    2. MetaAgent decomposes it into subtasks
    3. Multiple workers execute subtasks in parallel
    4. Results are aggregated intelligently
    """)

    with gr.Tab("Submit Task"):
        gr.Markdown("## 📝 Submit a Complex Task")

        with gr.Row():
            with gr.Column():
                query_input = gr.Textbox(
                    label="Complex Query",
                    placeholder="E.g., 'Read and analyze 1000 papers about COVID-19 treatments'",
                    lines=5
                )

                user_id_input = gr.Textbox(
                    label="User ID",
                    placeholder="your_user_id",
                    value="demo_user"
                )

                mode_input = gr.Radio(
                    label="Execution Mode",
                    choices=["parallel", "sequential"],
                    value="parallel",
                    info="Parallel: faster, uses multiple workers. Sequential: one batch at a time, more control."
                )

                # Parallel mode settings
                with gr.Group(visible=True) as parallel_settings:
                    gr.Markdown("### ⚡ Parallel Mode Settings")
                    with gr.Row():
                        max_workers_input = gr.Slider(
                            label="Max Workers (parallel agents)",
                            minimum=1,
                            maximum=10,
                            value=3,
                            step=1
                        )

                        max_batch_input = gr.Slider(
                            label="Batch Size (items per subtask)",
                            minimum=10,
                            maximum=200,
                            value=50,
                            step=10
                        )

                # Sequential mode settings
                with gr.Group(visible=False) as sequential_settings:
                    gr.Markdown("### 🔄 Sequential Mode Settings")
                    items_per_batch_input = gr.Slider(
                        label="Items per Batch",
                        minimum=5,
                        maximum=100,
                        value=10,
                        step=5,
                        info="How many items to process in each batch"
                    )

                    pause_input = gr.Slider(
                        label="Pause Between Batches (seconds)",
                        minimum=0,
                        maximum=30,
                        value=0,
                        step=1,
                        info="Useful for rate limiting"
                    )

                submit_btn = gr.Button("🚀 Submit Task", variant="primary")

            with gr.Column():
                submit_output = gr.Textbox(
                    label="Submission Result",
                    lines=8,
                    interactive=False
                )

                meta_session_id_output = gr.Textbox(
                    label="Meta-Session ID (save this!)",
                    interactive=True
                )

        gr.Markdown("""
        ### Example Queries:
        - "Read and analyze 500 research papers about mRNA vaccines"
        - "Process 1000 patient records and extract clinical insights"
        - "Analyze 200 gene sequences for common mutations"
        - "Summarize findings from 300 clinical trial reports"

        ### Mode Selection:
        - **Parallel**: Faster completion, multiple workers process batches simultaneously
        - **Sequential**: Process one batch at a time, better control, lower resource usage
        """)

        # Toggle visibility based on mode selection
        def toggle_mode_settings(mode):
            if mode == "parallel":
                return gr.update(visible=True), gr.update(visible=False)
            else:
                return gr.update(visible=False), gr.update(visible=True)

        mode_input.change(
            fn=toggle_mode_settings,
            inputs=[mode_input],
            outputs=[parallel_settings, sequential_settings]
        )

    with gr.Tab("Monitor Progress"):
        gr.Markdown("## 📊 Monitor Task Progress")

        with gr.Row():
            with gr.Column():
                monitor_session_id = gr.Textbox(
                    label="Meta-Session ID",
                    placeholder="Enter session ID from submission"
                )

                check_btn = gr.Button("🔍 Check Status", variant="primary")
                auto_refresh_btn = gr.Button("🔄 Auto-Refresh (5s intervals)")

                with gr.Row():
                    refresh_indicator = gr.Textbox(
                        label="Auto-Refresh Status",
                        value="Stopped",
                        interactive=False
                    )

            with gr.Column():
                progress_bar = gr.Progress()
                status_output = gr.Markdown("No status yet. Enter session ID and click 'Check Status'.")

        result_output = gr.Markdown("Results will appear here when task completes.")

    with gr.Tab("Subtask Details"):
        gr.Markdown("## 🔍 View Subtask Details")

        subtask_session_id = gr.Textbox(
            label="Meta-Session ID",
            placeholder="Enter session ID"
        )

        view_subtasks_btn = gr.Button("📋 View All Subtasks")

        subtasks_output = gr.Markdown("Subtask details will appear here.")

    with gr.Tab("Cancel Task"):
        gr.Markdown("## 🛑 Cancel Running Task")

        cancel_session_id = gr.Textbox(
            label="Meta-Session ID",
            placeholder="Enter session ID to cancel"
        )

        cancel_btn = gr.Button("🚫 Cancel Task", variant="stop")

        cancel_output = gr.Textbox(
            label="Cancellation Result",
            interactive=False
        )

    # Event handlers
    submit_btn.click(
        fn=submit_meta_task,
        inputs=[query_input, user_id_input, max_workers_input, max_batch_input,
                mode_input, items_per_batch_input, pause_input],
        outputs=[submit_output, meta_session_id_output]
    )

    check_btn.click(
        fn=check_meta_task_status,
        inputs=[monitor_session_id],
        outputs=[status_output, result_output, progress_bar, gr.State()]
    )

    view_subtasks_btn.click(
        fn=get_subtask_details,
        inputs=[subtask_session_id],
        outputs=[subtasks_output]
    )

    cancel_btn.click(
        fn=cancel_meta_task,
        inputs=[cancel_session_id],
        outputs=[cancel_output]
    )

    # Auto-refresh functionality (simplified)
    # Note: For production, implement proper WebSocket or SSE for real-time updates


if __name__ == "__main__":
    print("🚀 Starting MetaAgent Gradio Interface")
    print("="*60)
    print("Make sure your FastAPI server is running at:", API_BASE_URL)
    print("Server should include MetaAgent endpoints from meta_agent_fastapi_endpoints.py")
    print("="*60)

    demo.launch(
        server_name="0.0.0.0",
        server_port=7862,
        share=False
    )

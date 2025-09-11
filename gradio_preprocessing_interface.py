"""
Gradio Interface for dleader_agent Preprocessing Agent

This interface allows users to upload data files, apply preprocessing steps,
and visualize the results using the dleader_agent preprocessing tools.
"""

import json
import os
import sys
import tempfile
import threading
import time
from contextlib import redirect_stdout

import gradio as gr
import pandas as pd

from dleader_agent.agent.a1 import A1
from dleader_agent.tool import preprocessing


def create_preprocessing_agent():
    """Create a minimal preprocessing agent"""
    agent = A1(
        use_tool_retriever=True,
        download_data_lake=False,
        llm='azure-gpt-4o'
    )
    
    # Clear defaults and configure for preprocessing only
    agent.data_lake_dict = {}
    agent.library_content_dict = {
        'pandas': 'Data manipulation and analysis library',
        'numpy': 'Numerical computing library',
        'scikit-learn': 'Machine learning library with preprocessing tools',
        'scipy': 'Scientific computing library'
    }
    
    # Keep only preprocessing tools
    preprocessing_modules = {
        'dleader_agent.tool.preprocessing': agent.module2api.get('dleader_agent.tool.preprocessing', [])
    }
    agent.module2api = preprocessing_modules
    agent.configure()
    
    return agent


def load_and_inspect_file(file):
    """Load and inspect uploaded file"""
    if file is None:
        return "No file uploaded", "", ""
    
    try:
        # Load data using preprocessing function
        result = preprocessing.load_and_inspect_data(file.name)
        
        if result is None:
            return "Error loading file", "", ""
        
        data = result['data']
        inspection = result['inspection']
        
        # Create summary text
        summary = f"""
📊 **Data Summary**
- Shape: {inspection['shape'][0]} rows × {inspection['shape'][1]} columns
- Missing Values: {sum(inspection['missing_values'].values())} total
- Duplicates: {inspection['duplicates']} rows
- Memory Usage: {inspection['memory_usage'] / 1024 / 1024:.2f} MB

🔢 **Numeric Columns**: {len(inspection['numeric_columns'])}
{', '.join(inspection['numeric_columns'][:5]) + ('...' if len(inspection['numeric_columns']) > 5 else '')}

🏷️ **Categorical Columns**: {len(inspection['categorical_columns'])}
{', '.join(inspection['categorical_columns'][:5]) + ('...' if len(inspection['categorical_columns']) > 5 else '')}
        """
        
        # Create detailed inspection
        detailed_info = json.dumps(inspection, indent=2, default=str)
        
        # Show first few rows
        preview = data.head(10).to_html(classes='table table-striped')
        
        return summary, detailed_info, preview
        
    except Exception as e:
        return f"Error processing file: {str(e)}", "", ""


def detect_quality_issues(file):
    """Detect data quality issues in uploaded file"""
    if file is None:
        return "No file uploaded"
    
    try:
        result = preprocessing.load_and_inspect_data(file.name)
        if result is None:
            return "Error loading file"
        
        data = result['data']
        issues = preprocessing.detect_data_quality_issues(data)
        
        # Format issues report
        report = "🔍 **Data Quality Issues Report**\n\n"
        
        if issues['high_missing_columns']:
            report += "⚠️ **High Missing Value Columns:**\n"
            for col, pct in issues['high_missing_columns'].items():
                report += f"   - {col}: {pct*100:.1f}% missing\n"
            report += "\n"
        
        if issues['high_cardinality_categorical']:
            report += "🔢 **High Cardinality Categorical Variables:**\n"
            for item in issues['high_cardinality_categorical']:
                report += f"   - {item['column']}: {item['unique_count']} unique values\n"
            report += "\n"
        
        if issues['highly_correlated_pairs']:
            report += "🔗 **Highly Correlated Feature Pairs:**\n"
            for pair in issues['highly_correlated_pairs']:
                report += f"   - {pair['feature1']} ↔ {pair['feature2']}: {pair['correlation']:.3f}\n"
            report += "\n"
        
        if issues['potential_duplicates'] > 0:
            report += f"👥 **Duplicate Rows**: {issues['potential_duplicates']}\n\n"
        
        if issues['outlier_columns']:
            report += "📈 **Columns with Outliers:**\n"
            for col_info in issues['outlier_columns']:
                report += f"   - {col_info['column']}: {col_info['outlier_count']} outliers ({col_info['outlier_percentage']:.1f}%)\n"
            report += "\n"
        
        if not any([issues['high_missing_columns'], issues['high_cardinality_categorical'], 
                   issues['highly_correlated_pairs'], issues['potential_duplicates'], 
                   issues['outlier_columns']]):
            report += "✅ **No significant data quality issues detected!**"
        
        return report
        
    except Exception as e:
        return f"Error detecting quality issues: {str(e)}"


def preprocess_data(file, missing_strategy, outlier_method, normalization_method, encoding_method):
    """Apply preprocessing pipeline to uploaded data"""
    if file is None:
        return "No file uploaded", ""
    
    try:
        # Load data
        result = preprocessing.load_and_inspect_data(file.name)
        if result is None:
            return "Error loading file", ""
        
        data = result['data']
        
        # Apply preprocessing pipeline
        pipeline_result = preprocessing.create_data_preprocessing_pipeline(
            data,
            missing_strategy=missing_strategy,
            outlier_method=outlier_method,
            normalization_method=normalization_method,
            encoding_method=encoding_method
        )
        
        processed_data = pipeline_result['processed_data']
        report = pipeline_result['report']
        
        # Create summary
        summary = f"""
🔄 **Preprocessing Pipeline Complete**

📊 **Shape Changes:**
   - Original: {report['original_shape'][0]} rows × {report['original_shape'][1]} columns
   - Processed: {report['processed_shape'][0]} rows × {report['processed_shape'][1]} columns
   - Rows changed: {report['shape_change']['rows_change']}
   - Columns changed: {report['shape_change']['columns_change']}

🧹 **Missing Values:**
   - Original: {report['missing_values']['original']}
   - Processed: {report['missing_values']['processed']}

⚙️ **Steps Performed:**
{chr(10).join([f"   • {step}" for step in report['steps_performed']])}
        """
        
        # Show processed data preview
        preview = processed_data.head(10).to_html(classes='table table-striped')
        
        # Save processed data to temp file for download
        temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False)
        processed_data.to_csv(temp_file.name, index=False)
        temp_file.close()
        
        return summary, preview, temp_file.name
        
    except Exception as e:
        return f"Error preprocessing data: {str(e)}", "", None


class StreamingCapture:
    """Capture stdout and provide real-time updates"""
    def __init__(self):
        self.content = ""
        self.original_stdout = sys.stdout
        
    def write(self, text):
        self.content += text
        self.original_stdout.write(text)  # Still show in console
        self.original_stdout.flush()
        
    def flush(self):
        self.original_stdout.flush()
        
    def get_content(self):
        return self.content


def chat_with_agent_streaming(message, history, uploaded_files):
    """Stream agent responses with real-time updates"""
    if not message.strip():
        yield history, "", "😴 Please enter a message..."
        return
    
    try:
        # Initialize components
        yield history, "", "🔄 **Initializing agent...**"
        
        # Create agent
        agent = create_preprocessing_agent()
        
        # Add uploaded files to agent's data lake if any
        if uploaded_files:
            agent.data_lake_dict = {}
            for file in uploaded_files:
                filename = os.path.basename(file.name)
                try:
                    data = pd.read_csv(file.name)
                    agent.data_lake_dict[filename] = f"User uploaded dataset with {data.shape[0]} rows and {data.shape[1]} columns"
                except:
                    agent.data_lake_dict[filename] = "User uploaded file (format auto-detected)"
            agent.configure()
            yield history, "", f"📋 **Files loaded:** {len(uploaded_files)} files added to agent context"
        
        yield history, "", "🚀 **Starting agent processing...**"
        
        # Set up streaming capture
        stream_capture = StreamingCapture()
        
        # Container for results
        result_container = {"result": None, "error": None, "completed": False}
        accumulated_steps = ""
        
        def run_agent():
            try:
                with redirect_stdout(stream_capture):
                    _, result = agent.go(message)
                result_container["result"] = result
            except Exception as e:
                result_container["error"] = str(e)
            finally:
                result_container["completed"] = True
        
        # Start agent in background
        agent_thread = threading.Thread(target=run_agent)
        agent_thread.start()
        
        # Monitor and stream updates
        last_content_length = 0
        while not result_container["completed"]:
            current_content = stream_capture.get_content()
            if len(current_content) > last_content_length:
                # New content available - show incremental update
                new_content = current_content[last_content_length:]
                accumulated_steps += new_content
                steps_display = f"🔄 **Agent Steps (Live):**\n```\n{accumulated_steps}\n```"
                yield history, "", steps_display
                last_content_length = len(current_content)
            time.sleep(0.3)  # Update every 300ms
        
        # Wait for thread completion
        agent_thread.join()
        
        # Get final content
        final_content = stream_capture.get_content()
        if len(final_content) > last_content_length:
            new_content = final_content[last_content_length:]
            accumulated_steps += new_content
        
        # Format final response
        if result_container["error"]:
            final_response = f"❌ **Error:** {result_container['error']}"
            final_steps = f"❌ **Agent encountered an error**\n```\n{accumulated_steps}\n```"
        elif result_container["result"]:
            final_response = f"✅ **Agent Response:**\n\n{result_container['result']}"
            final_steps = f"✅ **Agent Steps Completed:**\n```\n{accumulated_steps}\n```"
        else:
            final_response = "✅ **Agent processing completed**"
            final_steps = f"✅ **Agent Steps Completed:**\n```\n{accumulated_steps}\n```"
        
        # Add to chat history
        full_response = f"**Steps:**\n```\n{accumulated_steps}\n```\n\n{final_response}"
        history.append([message, full_response])
        
        yield history, "", final_steps
        
    except Exception as e:
        error_response = f"❌ **Error with agent processing:** {str(e)}"
        history.append([message, error_response])
        yield history, "", f"❌ **Error:** {str(e)}"


def add_data_to_agent(files):
    """Add uploaded files to the agent's data context"""
    if not files:
        return "No files uploaded"
    
    try:
        file_info = []
        for file in files:
            filename = os.path.basename(file.name)
            try:
                # Try to read as CSV first
                data = pd.read_csv(file.name)
                file_info.append(f"✅ **{filename}**: {data.shape[0]} rows × {data.shape[1]} columns")
            except:
                try:
                    # Try other formats
                    if filename.endswith('.xlsx') or filename.endswith('.xls'):
                        data = pd.read_excel(file.name)
                        file_info.append(f"✅ **{filename}**: {data.shape[0]} rows × {data.shape[1]} columns (Excel)")
                    elif filename.endswith('.json'):
                        with open(file.name, 'r') as f:
                            json.load(f)  # Just validate JSON format
                        file_info.append(f"✅ **{filename}**: JSON file loaded")
                    else:
                        file_info.append(f"✅ **{filename}**: File uploaded (format will be auto-detected)")
                except:
                    file_info.append(f"⚠️ **{filename}**: File uploaded but format not recognized")
        
        return f"**Files Added to Agent Context:**\n\n" + "\n".join(file_info) + "\n\nYou can now chat with the agent about these files!"
        
    except Exception as e:
        return f"Error adding files: {str(e)}"


# Create Gradio interface
def create_interface():
    with gr.Blocks(title="dleader_agent Preprocessing Agent Chat", theme=gr.themes.Soft()) as demo:
        gr.Markdown("""
        # 🧬 dleader_agent Preprocessing Agent Chat
        
        Upload your data files and chat with the dleader_agent agent for intelligent preprocessing assistance.
        """)
        
        with gr.Row():
            with gr.Column(scale=1):
                gr.Markdown("### 📁 Add Data Files")
                file_input = gr.File(
                    label="Upload Data Files", 
                    file_types=[".csv", ".xlsx", ".xls", ".json", ".parquet"],
                    file_count="multiple"
                )
                add_data_btn = gr.Button("📋 Add Files to Agent Context", variant="secondary")
                file_status = gr.Markdown(label="File Status")
            
            with gr.Column(scale=2):
                gr.Markdown("### 🤖 Chat with Agent")
                chatbot = gr.Chatbot(
                    label="Agent Conversation",
                    height=400,
                    show_copy_button=True
                )
                
                # Real-time steps display
                gr.Markdown("### 🔄 Agent Steps (Real-time)")
                steps_display = gr.Markdown(
                    label="Current Processing Steps",
                    value="Ready to process your request...",
                    height=150
                )
                
                with gr.Row():
                    msg_input = gr.Textbox(
                        label="Message",
                        placeholder="Ask the agent to analyze your data, perform preprocessing, or explain steps...",
                        lines=3,
                        scale=4
                    )
                    send_btn = gr.Button("Send", variant="primary", scale=1)
                
                gr.Markdown("""
                **Example queries:**
                - "Analyze my uploaded dataset and tell me about data quality issues"
                - "Clean missing values and remove outliers from my data"
                - "Create a preprocessing pipeline for machine learning"
                - "Show me before/after statistics for the preprocessing steps"
                """)
        
        # Store uploaded files in state
        uploaded_files_state = gr.State([])
        
        # Event handlers
        def update_files_state(files):
            return files
        
        file_input.change(
            fn=update_files_state,
            inputs=[file_input],
            outputs=[uploaded_files_state]
        )
        
        add_data_btn.click(
            fn=add_data_to_agent,
            inputs=[file_input],
            outputs=[file_status]
        )
        
        def send_message(message, history, files):
            # Clear input immediately
            yield history, "", "🔄 Processing..."
            
            # Stream the agent response
            for update in chat_with_agent_streaming(message, history, files):
                yield update
        
        send_btn.click(
            fn=send_message,
            inputs=[msg_input, chatbot, uploaded_files_state],
            outputs=[chatbot, msg_input, steps_display]
        ).then(
            lambda: "",  # Clear input after processing
            outputs=[msg_input]
        )
        
        msg_input.submit(
            fn=send_message,
            inputs=[msg_input, chatbot, uploaded_files_state],
            outputs=[chatbot, msg_input, steps_display]
        ).then(
            lambda: "",  # Clear input after processing
            outputs=[msg_input]
        )
    
    return demo


if __name__ == "__main__":
    demo = create_interface()
    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
        debug=True
    )
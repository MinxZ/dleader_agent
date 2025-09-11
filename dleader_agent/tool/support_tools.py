import sys
from io import StringIO

# Create a persistent namespace that will be shared across all executions
_persistent_namespace = {}


def run_python_repl(command: str) -> str:
    """Executes the provided Python command in a persistent environment and returns the output.
    Variables defined in one execution will be available in subsequent executions.
    """

    def execute_in_repl(command: str) -> str:
        """Helper function to execute the command in the persistent environment."""
        old_stdout = sys.stdout
        sys.stdout = mystdout = StringIO()

        # Use the persistent namespace
        global _persistent_namespace

        try:
            # Execute the command in the persistent namespace
            exec(command, _persistent_namespace)
            output = mystdout.getvalue()
        except Exception as e:
            output = f"Error: {str(e)}"
        finally:
            sys.stdout = old_stdout
        return output

    command = command.strip("```").strip()
    return execute_in_repl(command)


def read_function_source_code(function_name: str) -> str:
    """Read the source code of a function from any module path.

    Parameters
    ----------
        function_name (str): Fully qualified function name (e.g., 'bioagentos.tool.support_tools.write_python_code')

    Returns
    -------
        str: The source code of the function

    """
    import importlib
    import inspect

    # Split the function name into module path and function name
    parts = function_name.split(".")
    module_path = ".".join(parts[:-1])
    func_name = parts[-1]

    try:
        # Import the module
        module = importlib.import_module(module_path)

        # Get the function object from the module
        function = getattr(module, func_name)

        # Get the source code of the function
        source_code = inspect.getsource(function)

        return source_code
    except (ImportError, AttributeError) as e:
        return f"Error: Could not find function '{function_name}'. Details: {str(e)}"


def read_and_summarize_image(image_source: str, mode: str = "general", prompt: str = None, model: str = "claude-sonnet-4-20250514") -> str:
    """Read an image from URL or local path using LLM and provide a summary of its contents.

    Parameters
    ----------
        image_source (str): URL or local path to the image file to analyze
        mode (str): Analysis mode - "general", "scientific", "medical", "data_viz", "text_extraction", or "custom"
        prompt (str): Custom prompt for analysis (overrides mode-based prompt)
        model (str): LLM model to use for image analysis

    Returns
    -------
        str: A text summary of the image contents

    """
    import base64
    import os

    import requests
    from langchain_core.messages import HumanMessage

    from dleader_agent.llm import get_llm

    # Define mode-specific prompts
    mode_prompts = {
        "general": "Describe what you see in this image in detail.",
        "scientific": "Analyze this image from a scientific perspective. Describe any experimental setups, data, graphs, charts, or scientific equipment you observe. Include any measurements, scales, or quantitative information visible.",
        "medical": "Analyze this medical image. Describe any anatomical structures, pathological findings, medical equipment, or diagnostic information visible. Note any abnormalities or significant features.",
        "data_viz": "Analyze this data visualization or chart. Describe the type of chart, axes labels, data trends, key findings, and any statistical information presented. Extract numerical values if visible.",
        "text_extraction": "Extract and transcribe all text visible in this image. Include any labels, captions, titles, or written content you can see.",
        "custom": "Analyze this image based on the provided custom prompt."
    }
    
    # Determine the analysis prompt
    if prompt:
        analysis_prompt = prompt
    elif mode in mode_prompts:
        analysis_prompt = mode_prompts[mode]
    else:
        return f"Error: Invalid mode '{mode}'. Available modes: {', '.join(mode_prompts.keys())}"
    
    try:
        # Check if it's a URL or local path
        is_url = image_source.startswith(('http://', 'https://'))
        
        if is_url:
            # Handle URL
            try:
                response = requests.get(image_source, timeout=30)
                response.raise_for_status()
                image_data = response.content
                
                # Try to determine content type from headers
                content_type = response.headers.get('content-type', '').lower()
                if 'image' not in content_type:
                    return f"Error: URL does not appear to contain an image. Content-Type: {content_type}"
                
                # Map content type to media type
                if 'jpeg' in content_type or 'jpg' in content_type:
                    media_type = 'image/jpeg'
                elif 'png' in content_type:
                    media_type = 'image/png'
                elif 'gif' in content_type:
                    media_type = 'image/gif'
                elif 'webp' in content_type:
                    media_type = 'image/webp'
                elif 'bmp' in content_type:
                    media_type = 'image/bmp'
                else:
                    media_type = 'image/jpeg'  # Default fallback
                    
            except requests.exceptions.RequestException as e:
                return f"Error downloading image from URL: {str(e)}"
                
        else:
            # Handle local file path
            if not os.path.exists(image_source):
                return f"Error: Image file not found at path: {image_source}"
            
            # Check if file is an image format
            valid_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}
            file_extension = os.path.splitext(image_source)[1].lower()
            if file_extension not in valid_extensions:
                return f"Error: Unsupported file format. Please use one of: {', '.join(valid_extensions)}"
            
            # Read local file
            with open(image_source, 'rb') as image_file:
                image_data = image_file.read()
            
            # Determine media type based on file extension
            media_type_map = {
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg', 
                '.png': 'image/png',
                '.gif': 'image/gif',
                '.bmp': 'image/bmp',
                '.webp': 'image/webp'
            }
            media_type = media_type_map.get(file_extension, 'image/jpeg')
        
        # Encode image to base64
        encoded_image = base64.b64encode(image_data).decode('utf-8')
        
        # Initialize the LLM using get_llm
        llm = get_llm(model=model)
        
        # Create message with image
        message = HumanMessage(
            content=[
                {
                    "type": "text",
                    "text": analysis_prompt
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{media_type};base64,{encoded_image}"
                    }
                }
            ]
        )
        
        # Get response from LLM
        response = llm.invoke([message])
        return response.content
        
    except Exception as e:
        return f"Error processing image: {str(e)}"


# def request_human_feedback(question, context, reason_for_uncertainty):
#     """
#     Request human feedback on a question.

#     Parameters:
#         question (str): The question that needs human feedback.
#         context (str): Context or details that help the human understand the situation.
#         reason_for_uncertainty (str): Explanation for why the LLM is uncertain about its answer.

#     Returns:
#         str: The feedback provided by the human.
#     """
#     print("Requesting human feedback...")
#     print(f"Question: {question}")
#     print(f"Context: {context}")
#     print(f"Reason for Uncertainty: {reason_for_uncertainty}")

#     # Capture human feedback
#     human_response = input("Please provide your feedback: ")

#     return human_response

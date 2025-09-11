description = [
    {
        "description": "Executes the provided Python command in the notebook environment and returns the output.",
        "name": "run_python_repl",
        "optional_parameters": [],
        "required_parameters": [
            {
                "default": None,
                "description": "Python command to execute in the notebook environment",
                "name": "command",
                "type": "str",
            }
        ],
    },
    {
        "description": "Read the source code of a function from any module path.",
        "name": "read_function_source_code",
        "optional_parameters": [],
        "required_parameters": [
            {
                "default": None,
                "description": "Fully qualified function name "
                "(e.g., "
                "'bioagentos.tool.support_tools.write_python_code')",
                "name": "function_name",
                "type": "str",
            }
        ],
    },
    {
        "description": "Read an image from URL or local path using LLM and provide a summary of its contents.",
        "name": "read_and_summarize_image",
        "optional_parameters": [
            {
                "default": "general",
                "description": "Analysis mode: 'general', 'scientific', 'medical', 'data_viz', 'text_extraction', or 'custom'",
                "name": "mode",
                "type": "str",
            },
            {
                "default": None,
                "description": "Custom prompt for analysis (overrides mode-based prompt)",
                "name": "prompt",
                "type": "str",
            },
            {
                "default": "claude-sonnet-4-20250514",
                "description": "LLM model to use for image analysis",
                "name": "model",
                "type": "str",
            }
        ],
        "required_parameters": [
            {
                "default": None,
                "description": "URL or local path to the image file to analyze",
                "name": "image_source",
                "type": "str",
            }
        ],
    },
]

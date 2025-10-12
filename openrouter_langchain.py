"""
OpenRouter integration for LangChain
"""

import os
from typing import Optional, Dict, Any
from langchain_openai import ChatOpenAI
from langchain_core.language_models.chat_models import BaseChatModel


def get_openrouter_llm(
    model: str,
    api_key: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: Optional[int] = None,
    stop_sequences: Optional[list[str]] = None,
    headers: Optional[Dict[str, str]] = None,
    **kwargs
) -> BaseChatModel:
    """
    Create a LangChain LLM instance configured for OpenRouter.

    Args:
        model: The model name from OpenRouter (e.g., "anthropic/claude-3.5-sonnet",
               "openai/gpt-4-turbo", "google/gemini-pro", etc.)
        api_key: OpenRouter API key. If None, will try to get from OPENROUTER_API_KEY env var
        temperature: Temperature setting for generation (0.0 to 1.0)
        max_tokens: Maximum tokens to generate. If None, uses model default
        stop_sequences: List of sequences that will stop generation
        headers: Additional HTTP headers (e.g., {"HTTP-Referer": "your-app-url"})
        **kwargs: Additional parameters to pass to ChatOpenAI

    Returns:
        BaseChatModel: Configured LangChain model instance

    Example:
        >>> llm = get_openrouter_llm(
        ...     model="anthropic/claude-3.5-sonnet",
        ...     api_key="your-api-key",
        ...     temperature=0.5
        ... )
        >>> response = llm.invoke("What is the capital of France?")
    """

    # Get API key from parameter or environment
    if api_key is None:
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise ValueError(
                "OpenRouter API key not provided. "
                "Please set OPENROUTER_API_KEY environment variable or pass api_key parameter"
            )

    # Set up default headers if not provided
    if headers is None:
        headers = {}

    # Add default headers for OpenRouter
    default_headers = {
        "HTTP-Referer": os.getenv("OPENROUTER_REFERER", "http://localhost:3000"),
        "X-Title": os.getenv("OPENROUTER_APP_NAME", "LangChain OpenRouter App")
    }

    # Merge headers (user provided headers take precedence)
    final_headers = {**default_headers, **headers}

    # Build configuration
    config = {
        "model": model,
        "temperature": temperature,
        "api_key": api_key,
        "base_url": "https://openrouter.ai/api/v1",
        "stop_sequences": stop_sequences,
        "default_headers": final_headers,
        **kwargs
    }

    # Add max_tokens if specified
    if max_tokens is not None:
        config["max_tokens"] = max_tokens

    # Create and return the LLM instance
    return ChatOpenAI(**config)


def list_available_models():
    """
    List some popular models available on OpenRouter.

    Returns:
        Dict of model categories and their models
    """
    return {
        "anthropic": [
            "anthropic/claude-3.5-sonnet",
            "anthropic/claude-3-opus",
            "anthropic/claude-3-haiku",
            "anthropic/claude-2.1",
            "anthropic/claude-instant-1.2"
        ],
        "openai": [
            "openai/gpt-4-turbo",
            "openai/gpt-4",
            "openai/gpt-3.5-turbo",
            "openai/gpt-4-32k"
        ],
        "google": [
            "google/gemini-pro",
            "google/gemini-pro-vision",
            "google/palm-2-code-bison"
        ],
        "meta": [
            "meta-llama/llama-3-70b-instruct",
            "meta-llama/llama-3-8b-instruct",
            "meta-llama/llama-2-70b-chat"
        ],
        "mistral": [
            "mistralai/mixtral-8x7b-instruct",
            "mistralai/mistral-7b-instruct",
            "mistralai/mistral-medium"
        ],
        "other": [
            "databricks/dbrx-instruct",
            "cohere/command-r-plus",
            "deepseek/deepseek-chat"
        ]
    }


def create_openrouter_chain(
    model: str,
    api_key: Optional[str] = None,
    prompt_template: Optional[str] = None,
    **llm_kwargs
):
    """
    Create a simple LangChain chain with OpenRouter LLM.

    Args:
        model: OpenRouter model name
        api_key: OpenRouter API key
        prompt_template: Optional prompt template string
        **llm_kwargs: Additional arguments for the LLM

    Returns:
        A LangChain chain or LLM instance

    Example:
        >>> chain = create_openrouter_chain(
        ...     model="anthropic/claude-3.5-sonnet",
        ...     prompt_template="Translate the following to French: {text}"
        ... )
        >>> result = chain.invoke({"text": "Hello world"})
    """
    from langchain_core.prompts import ChatPromptTemplate

    # Create the LLM
    llm = get_openrouter_llm(model=model, api_key=api_key, **llm_kwargs)

    # If no prompt template, return just the LLM
    if prompt_template is None:
        return llm

    # Create a chain with the prompt template
    prompt = ChatPromptTemplate.from_template(prompt_template)
    chain = prompt | llm

    return chain


# Example usage
if __name__ == "__main__":
    # Example 1: Basic usage
    print("Example 1: Basic OpenRouter LLM")
    print("-" * 40)

    # Set your API key as environment variable or pass directly
    # os.environ["OPENROUTER_API_KEY"] = "your-api-key-here"

    try:
        llm = get_openrouter_llm(
            model="anthropic/claude-3.5-sonnet",
            temperature=0.7,
            max_tokens=100
        )

        response = llm.invoke("What is LangChain in one sentence?")
        print(f"Response: {response.content}")
    except ValueError as e:
        print(f"Error: {e}")
        print("Please set OPENROUTER_API_KEY environment variable")

    print("\n")

    # Example 2: List available models
    print("Example 2: Available models on OpenRouter")
    print("-" * 40)
    models = list_available_models()
    for category, model_list in models.items():
        print(f"\n{category.upper()}:")
        for model in model_list[:3]:  # Show first 3 of each category
            print(f"  - {model}")

    print("\n")

    # Example 3: Using with a prompt template
    print("Example 3: Using with prompt template")
    print("-" * 40)

    try:
        chain = create_openrouter_chain(
            model="openai/gpt-3.5-turbo",
            prompt_template="You are a helpful assistant. Answer this question concisely: {question}",
            temperature=0.5
        )

        result = chain.invoke({"question": "What is machine learning?"})
        print(f"Templated response: {result.content}")
    except Exception as e:
        print(f"Error: {e}")
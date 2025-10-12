"""
Example usage of OpenRouter with LangChain integration
"""

import os
from dleader_agent.llm import get_llm
from openrouter_langchain import get_openrouter_llm, create_openrouter_chain

def example_direct_openrouter():
    """Example using the standalone OpenRouter function"""
    print("=" * 60)
    print("Example 1: Direct OpenRouter LLM usage")
    print("=" * 60)

    # Make sure to set your API key
    # os.environ["OPENROUTER_API_KEY"] = "your-api-key-here"

    try:
        # Create an OpenRouter LLM instance
        llm = get_openrouter_llm(
            model="anthropic/claude-3.5-sonnet",  # OpenRouter model format
            temperature=0.7,
            max_tokens=150
        )

        # Use the LLM
        response = llm.invoke("Explain quantum computing in 2 sentences.")
        print(f"Response: {response.content}")

    except Exception as e:
        print(f"Error: {e}")
        print("Please set OPENROUTER_API_KEY environment variable")


def example_integrated_openrouter():
    """Example using OpenRouter through the integrated get_llm function"""
    print("\n" + "=" * 60)
    print("Example 2: OpenRouter via integrated get_llm function")
    print("=" * 60)

    try:
        # Use OpenRouter through the main get_llm function
        llm = get_llm(
            model="anthropic/claude-3.5-sonnet",
            source="OpenRouter",
            temperature=0.5,
            api_key=os.getenv("OPENROUTER_API_KEY", "")
        )

        response = llm.invoke("What is machine learning?")
        print(f"Response: {response.content}")

    except Exception as e:
        print(f"Error: {e}")


def example_with_chain():
    """Example using OpenRouter with LangChain chains"""
    print("\n" + "=" * 60)
    print("Example 3: OpenRouter with LangChain chains")
    print("=" * 60)

    try:
        # Create a chain with a prompt template
        chain = create_openrouter_chain(
            model="openai/gpt-4-turbo",
            prompt_template="You are a helpful coding assistant. Explain this concept in simple terms: {concept}",
            temperature=0.3
        )

        # Use the chain
        result = chain.invoke({"concept": "recursion in programming"})
        print(f"Response: {result.content}")

    except Exception as e:
        print(f"Error: {e}")


def example_multiple_models():
    """Example comparing responses from different models"""
    print("\n" + "=" * 60)
    print("Example 4: Comparing different models via OpenRouter")
    print("=" * 60)

    models = [
        "anthropic/claude-3-haiku",
        "openai/gpt-3.5-turbo",
        "google/gemini-pro"
    ]

    question = "What is Python?"

    for model_name in models:
        try:
            print(f"\n{model_name}:")
            print("-" * 30)

            llm = get_openrouter_llm(
                model=model_name,
                temperature=0.5,
                max_tokens=50
            )

            response = llm.invoke(question)
            print(f"{response.content[:150]}...")  # Show first 150 chars

        except Exception as e:
            print(f"Error with {model_name}: {e}")


def example_streaming():
    """Example with streaming responses"""
    print("\n" + "=" * 60)
    print("Example 5: Streaming responses from OpenRouter")
    print("=" * 60)

    try:
        llm = get_openrouter_llm(
            model="anthropic/claude-3.5-sonnet",
            temperature=0.7,
            streaming=True  # Enable streaming
        )

        print("Streaming response: ", end="")
        for chunk in llm.stream("Write a haiku about programming"):
            print(chunk.content, end="", flush=True)
        print()  # New line after streaming

    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    print("🚀 OpenRouter + LangChain Examples")
    print("=" * 60)
    print("Note: Set OPENROUTER_API_KEY environment variable before running")
    print()

    # Run examples
    example_direct_openrouter()
    example_integrated_openrouter()
    example_with_chain()
    example_multiple_models()
    example_streaming()
"""
Simple text-based agent using OpenRouter with Qwen model
"""

import os
import time
from dleader_agent.agent.a1 import A1


def create_openrouter_text_agent():
    """Create an agent configured for text-based Q&A using OpenRouter."""

    # Initialize agent with OpenRouter Qwen model
    agent = A1(
        use_tool_retriever=True,
        download_data_lake=False,
        llm='qwen/qwen3-vl-235b-a22b-thinking',
        source='OpenRouter',  # Specify OpenRouter as the source
        api_key=os.getenv("OPENROUTER_API_KEY", "")
    )

    # Clear default data lake
    agent.data_lake_dict = {}

    # Keep literature tools for scientific text analysis
    text_modules = {
        'dleader_agent.tool.support_tools': agent.module2api.get('dleader_agent.tool.support_tools', []),
        'dleader_agent.tool.literature': agent.module2api.get('dleader_agent.tool.literature', [])
    }
    agent.module2api = text_modules

    print("✅ Configured OpenRouter text agent with Qwen model")
    return agent


def ask_question(question):
    """Ask a simple question to the OpenRouter agent."""

    print(f"🔍 Question: {question}")
    print("="*50)

    # Check for API key
    if not os.getenv("OPENROUTER_API_KEY"):
        print("⚠️  Warning: OPENROUTER_API_KEY not set in environment")
        print("Please set it with: export OPENROUTER_API_KEY='your-key-here'")
        return None, None

    # Create agent
    agent = create_openrouter_text_agent()

    # Get response
    log, result = agent.go(question)

    print("📋 Agent Response (via OpenRouter):")
    print(result)
    print("\n" + "="*50)

    # Save results
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    with open(f'openrouter_response_{timestamp}.txt', 'w') as f:
        f.write(f"Model: qwen/qwen3-vl-235b-a22b-thinking (via OpenRouter)\n")
        f.write(f"Question: {question}\n")
        f.write(f"Response: {result}\n")
        f.write(f"\nLog:\n{log}")

    return log, result


def test_openrouter_models():
    """Test different models available on OpenRouter."""

    print("🧪 Testing Multiple OpenRouter Models")
    print("="*60)

    # Different models to test
    models = [
        "qwen/qwen3-vl-235b-a22b-thinking",
        "anthropic/claude-3.5-sonnet",
        "openai/gpt-4-turbo",
        "google/gemini-pro"
    ]

    question = "What is RNA?"

    for model_name in models:
        print(f"\n📊 Testing model: {model_name}")
        print("-"*40)

        try:
            agent = A1(
                use_tool_retriever=True,
                download_data_lake=False,
                llm=model_name,
                source='OpenRouter',
                api_key=os.getenv("OPENROUTER_API_KEY", "")
            )

            # Clear data lake and configure modules
            agent.data_lake_dict = {}
            text_modules = {
                'dleader_agent.tool.support_tools': agent.module2api.get('dleader_agent.tool.support_tools', []),
                'dleader_agent.tool.literature': agent.module2api.get('dleader_agent.tool.literature', [])
            }
            agent.module2api = text_modules

            # Get response
            log, result = agent.go(question)

            print(f"✅ {model_name} response (first 200 chars):")
            print(result[:200] + "..." if len(result) > 200 else result)

        except Exception as e:
            print(f"❌ Error with {model_name}: {e}")

        time.sleep(1)  # Small delay between requests


def direct_openrouter_test():
    """Test OpenRouter directly without the agent framework."""

    print("\n🔧 Direct OpenRouter Test")
    print("="*60)

    from dleader_agent.llm import get_llm

    try:
        # Create LLM directly
        llm = get_llm(
            model="qwen/qwen3-vl-235b-a22b-thinking",
            source="OpenRouter",
            temperature=0.7,
            api_key=os.getenv("OPENROUTER_API_KEY", "")
        )

        # Test direct invocation
        response = llm.invoke("Explain DNA in one sentence.")
        print(f"Direct response: {response.content}")

    except Exception as e:
        print(f"Error in direct test: {e}")
        print("Make sure OPENROUTER_API_KEY is set")


if __name__ == "__main__":
    print("🧬 OpenRouter Text Agent with Qwen Model")
    print("="*60)

    # Make sure API key is set
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        print("⚠️  OPENROUTER_API_KEY not found in environment variables")
        print("Please set it with:")
        print("  export OPENROUTER_API_KEY='your-openrouter-api-key'")
        print("\nYou can get an API key from: https://openrouter.ai/keys")
        exit(1)

    print(f"✅ API Key found (length: {len(api_key)} chars)")
    print()

    # Example usage with the Qwen model via OpenRouter
    question = "introduce rna"

    # You can change the question to anything you want
    # question = "what is DNA?"
    # question = "explain protein synthesis"
    # question = "describe CRISPR technology"

    # Test main question
    log, result = ask_question(question)

    # Optional: Test direct OpenRouter usage
    print("\n" + "="*60)
    direct_openrouter_test()

    # Optional: Test multiple models (comment out if you want to save API credits)
    # test_openrouter_models()
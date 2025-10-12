"""
Simple text-based agent for answering questions
"""

import time
from dleader_agent.agent.a1 import A1


def create_text_agent():
    """Create an agent configured for text-based Q&A."""

    # Initialize agent
    agent = A1(
        use_tool_retriever=True,
        download_data_lake=False,
        llm='claude-sonnet-4-20250514'
    )

    # Clear default data lake
    agent.data_lake_dict = {}

    # Keep literature tools for scientific text analysis
    text_modules = {
        'dleader_agent.tool.support_tools': agent.module2api.get('dleader_agent.tool.support_tools', []),
        'dleader_agent.tool.literature': agent.module2api.get('dleader_agent.tool.literature', [])
    }
    agent.module2api = text_modules

    print("✅ Configured text agent")
    return agent


def ask_question(question):
    """Ask a simple question to the agent."""

    print(f"🔍 Question: {question}")
    print("="*50)

    # Create agent
    agent = create_text_agent()

    # Get response
    log, result = agent.go(question)

    print("📋 Agent Response:")
    print(result)
    print("\n" + "="*50)

    # Save results
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    with open(f'response_{timestamp}.txt', 'w') as f:
        f.write(f"Question: {question}\n")
        f.write(f"Response: {result}\n")
        f.write(f"\nLog:\n{log}")

    return log, result


if __name__ == "__main__":
    print("🧬 Simple Text Agent")
    print("="*60)

    # Example usage with simple text input
    question = "introduce rna"

    # You can change the question to anything you want
    # question = "what is DNA?"
    # question = "explain protein synthesis"
    # question = "describe CRISPR technology"

    log, result = ask_question(question)
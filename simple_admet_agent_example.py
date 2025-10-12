#!/usr/bin/env python3
"""
Simple ADMET Prediction Example using dleader_agent A1 Agent

This example shows how to use the dleader_agent AI agent to predict
ADMET properties for chemical compounds using natural language prompts.

The agent will automatically handle:
- SMILES validation
- ADMET property prediction
- Results interpretation
"""

from dleader_agent.agent.a1 import A1


def main():
    """Run ADMET prediction using the A1 agent."""

    print("=" * 60)
    print("ADMET Prediction using dleader_agent A1 Agent")
    print("=" * 60)

    # Initialize the agent
    # The data lake will be downloaded on first run (~11GB)
    # You can use different LLM models:
    # - 'claude-sonnet-4-20250514' (default)
    # - 'gpt-4o-mini'
    # - 'azure-o4-mini'
    # - other supported models

    print("\nInitializing A1 agent...")
    agent = A1(
        path='./data',  # Data directory
        llm='claude-sonnet-4-20250514',  # LLM model to use
        download_data_lake=False  # Set to True on first run to download data
    )

    # Example prompt for ADMET prediction
    # You can modify the SMILES string to predict for different compounds
    prompt = """
    Predict ADMET properties for this compound: CC(C)CC1=CC=C(C=C1)C(C)C(=O)O

    This is Ibuprofen. Please provide comprehensive ADMET predictions including:
    - Absorption properties (solubility, permeability, bioavailability)
    - Distribution (BBB penetration, protein binding)
    - Metabolism (CYP interactions)
    - Excretion (clearance, half-life)
    - Toxicity assessments

    Please use the MPNN model type for prediction.
    """

    print("\nSending prompt to agent...")
    print("-" * 40)
    print("Prompt:", prompt.strip())
    print("-" * 40)

    # Get the agent's response
    log, result = agent.go(prompt)

    # Display results
    print("\n" + "=" * 60)
    print("AGENT RESPONSE:")
    print("=" * 60)
    print(result)

    # Optionally display the detailed log
    # print("\n" + "=" * 60)
    # print("DETAILED LOG:")
    # print("=" * 60)
    # print(log)

    print("\n" + "=" * 60)
    print("Prediction complete!")
    print("=" * 60)


def advanced_example():
    """Advanced example with multiple compounds and comparison."""

    print("\n" + "=" * 60)
    print("ADVANCED: Comparing Multiple Compounds")
    print("=" * 60)

    agent = A1(
        path='./data',
        llm='claude-sonnet-4-20250514',
        download_data_lake=False
    )

    # Prompt for comparing multiple compounds
    advanced_prompt = """
    Compare the ADMET properties of these three compounds:

    1. Aspirin: CC(=O)OC1=CC=CC=C1C(=O)O
    2. Ibuprofen: CC(C)CC1=CC=C(C=C1)C(C)C(=O)O
    3. Naproxen: CC(C1=CC2=C(C=C1)C=C(C=C2)OC)C(=O)O

    For each compound:
    - Predict key ADMET properties
    - Identify potential safety concerns
    - Compare their pharmacokinetic profiles
    - Suggest which might have better oral bioavailability

    Use the MPNN model for all predictions.
    """

    print("\nAnalyzing multiple compounds...")
    log, result = agent.go(advanced_prompt)

    print("\nComparison Results:")
    print("-" * 40)
    print(result)

    return result


if __name__ == "__main__":
    # Run the simple example
    main()

    # Uncomment to run the advanced example
    # advanced_example()
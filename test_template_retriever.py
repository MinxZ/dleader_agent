"""
Test script for the template retriever functionality.

This script tests:
1. Fetching templates from MongoDB
2. Matching queries to templates
3. Query augmentation with template prompts
"""

import os
import sys

# Add current directory to path
sys.path.insert(0, os.getcwd())

from template_retriever import TemplateRetriever


def test_fetch_templates():
    """Test fetching templates from MongoDB"""
    print("=" * 80)
    print("TEST 1: Fetching Templates from MongoDB")
    print("=" * 80)

    retriever = TemplateRetriever()
    templates = retriever.get_templates()

    print(f"\nFetched {len(templates)} templates")

    if templates:
        print("\nTemplates available:")
        for i, template in enumerate(templates):
            title = template.get("title", "Unknown")
            description = template.get("description", "No description")[:100]
            has_prompt = "Yes" if template.get("prompt") else "No"
            print(f"\n  [{i}] {title}")
            print(f"      Description: {description}...")
            print(f"      Has Prompt: {has_prompt}")
    else:
        print("\n⚠️  No templates found!")

    return templates


def test_template_matching(templates):
    """Test matching queries to templates"""
    print("\n" + "=" * 80)
    print("TEST 2: Template Matching")
    print("=" * 80)

    retriever = TemplateRetriever()

    # Test cases
    test_queries = [
        "I need to merge two CSV files with molecular data",
        "Help me design an antisense oligonucleotide for BRCA1 gene",
        "Can you perform QSPR analysis on drug-like compounds?",
        "Combine multiple datasets from different formats",
        "What is QSPR?",  # Should NOT match (informational)
        "Analyze molecular properties and predict solubility",
    ]

    print("\nTesting query matching:\n")

    for query in test_queries:
        print(f"\nQuery: \"{query}\"")
        print("-" * 80)

        match_result = retriever.match_template(query, templates)

        matched = match_result.get("matched")
        if matched:
            template = match_result.get("template", {})
            title = template.get("title", "Unknown")
            confidence = match_result.get("confidence", "unknown")
            reasoning = match_result.get("reasoning", "")
            modification = match_result.get("modification")

            print(f"✓ MATCHED: {title}")
            print(f"  Confidence: {confidence}")
            print(f"  Reasoning: {reasoning}")
            if modification:
                print(f"  Modification: {modification}")
        else:
            reasoning = match_result.get("reasoning", "Unknown")
            print(f"✗ NO MATCH")
            print(f"  Reasoning: {reasoning}")


def test_query_augmentation(templates):
    """Test augmenting queries with template prompts"""
    print("\n" + "=" * 80)
    print("TEST 3: Query Augmentation")
    print("=" * 80)

    retriever = TemplateRetriever()

    test_query = "I want to merge three CSV files with different column names"

    print(f"\nOriginal Query: \"{test_query}\"\n")
    print("-" * 80)

    # First match the template
    match_result = retriever.match_template(test_query, templates)

    if match_result.get("matched"):
        template = match_result.get("template", {})
        print(f"Matched Template: {template.get('title', 'Unknown')}")
        print(f"Confidence: {match_result.get('confidence', 'unknown')}")

        # Augment the query
        augmentation_result = retriever.augment_query_with_template(test_query, match_result)

        print(f"\nTemplate Used: {augmentation_result.get('template_used', 'None')}")
        if augmentation_result.get('modification_applied'):
            print(f"Modification: {augmentation_result['modification_applied']}")

        print("\n--- AUGMENTED QUERY ---")
        print(augmentation_result["augmented_query"])
        print("-" * 80)
    else:
        print("No template matched, query would not be augmented")


def main():
    """Run all tests"""
    print("\n")
    print("╔" + "=" * 78 + "╗")
    print("║" + " " * 20 + "TEMPLATE RETRIEVER TEST SUITE" + " " * 29 + "║")
    print("╚" + "=" * 78 + "╝")
    print("\n")

    # Test 1: Fetch templates
    templates = test_fetch_templates()

    if not templates:
        print("\n⚠️  Cannot continue tests without templates!")
        print("Please ensure:")
        print("  1. MongoDB is configured and running")
        print("  2. Templates have been uploaded via POST /upload-template")
        print("  3. Or local templates file exists at templates/workflow_templates.json")
        return

    # Test 2: Template matching
    test_template_matching(templates)

    # Test 3: Query augmentation
    test_query_augmentation(templates)

    print("\n" + "=" * 80)
    print("✓ All tests completed!")
    print("=" * 80)
    print("\n")


if __name__ == "__main__":
    main()

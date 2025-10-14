#!/usr/bin/env python3
"""Debug script to test template matching for MALAT1 ASO query."""

import os
import sys

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from template_retriever import TemplateRetriever


def main():
    """Test template matching with MALAT1 ASO query."""

    # Initialize retriever
    print("=" * 80)
    print("TEMPLATE RETRIEVER DEBUG TEST")
    print("=" * 80)
    print()

    try:
        retriever = TemplateRetriever()
        print("✓ Template retriever initialized")
        print()
    except Exception as e:
        print(f"✗ Failed to initialize retriever: {e}")
        return

    # Fetch templates
    print("-" * 80)
    print("FETCHING TEMPLATES")
    print("-" * 80)
    try:
        templates = retriever.get_templates()
        print(f"✓ Fetched {len(templates)} templates")
        print()

        if templates:
            print("Available templates:")
            for idx, template in enumerate(templates):
                title = template.get("title", "Unknown")
                description = template.get("description", "No description")[:100]
                print(f"  [{idx}] {title}")
                print(f"      {description}...")
            print()
        else:
            print("✗ No templates found!")
            print()

    except Exception as e:
        print(f"✗ Error fetching templates: {e}")
        import traceback
        traceback.print_exc()
        return

    # Test query
    query = "Find 5 antisense oligonucleotide candidates for human MALAT1 (lncRNA)."
    print("-" * 80)
    print("TESTING QUERY MATCHING")
    print("-" * 80)
    print(f"Query: {query}")
    print()

    try:
        match_result = retriever.match_template(query)

        print("Match Result:")
        print(f"  Matched: {match_result.get('matched')}")
        print(f"  Confidence: {match_result.get('confidence')}")
        print(f"  Reasoning: {match_result.get('reasoning')}")

        if match_result.get("matched"):
            template = match_result.get("template")
            if template:
                print(f"  Template Title: {template.get('title')}")
                print(f"  Template Description: {template.get('description', 'N/A')[:200]}...")
                print(f"  Has Prompt: {'Yes' if template.get('prompt') else 'No'}")

                if match_result.get("modification"):
                    print(f"  Suggested Modification: {match_result.get('modification')}")
        else:
            print(f"  ✗ No template matched")

        print()

        # Test augmentation
        if match_result.get("matched"):
            print("-" * 80)
            print("TESTING QUERY AUGMENTATION")
            print("-" * 80)

            augment_result = retriever.augment_query_with_template(query, match_result)

            print(f"Template Used: {augment_result.get('template_used')}")
            print(f"Modification Applied: {augment_result.get('modification_applied')}")
            print()
            print("Augmented Query (first 500 chars):")
            print("-" * 40)
            print(augment_result.get('augmented_query', '')[:500])
            print("...")
            print()

    except Exception as e:
        print(f"✗ Error during template matching: {e}")
        import traceback
        traceback.print_exc()
        return

    print("=" * 80)
    print("TEST COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    main()

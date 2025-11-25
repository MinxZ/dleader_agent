"""
Test script for LLM-based automatic template matching detection
"""

import sys
import os
sys.path.insert(0, os.getcwd())

from agent_fastapi_server_multiturn import should_use_template_matching


def test_template_detection():
    """Test various queries to verify LLM-based automatic template detection"""

    test_cases = [
        # Simple queries - should NOT use template matching
        ("1+1", False, "Simple math"),
        ("2*3", False, "Simple multiplication"),
        ("calculate 5+3", False, "Simple calculation"),
        ("hello", False, "Single word greeting"),
        ("hi there", False, "Short greeting"),
        ("what is DNA", False, "Short question"),
        ("help", False, "Single word"),
        ("test", False, "Single word test"),
        ("thanks", False, "Thank you"),

        # Complex queries - should USE template matching
        ("Perform differential gene expression analysis on RNA-seq data", True, "Complex analysis"),
        ("I want to analyze protein-protein interactions in cancer cells", True, "Biomedical analysis"),
        ("Run a machine learning pipeline for drug discovery", True, "ML workflow"),
        ("Compare gene expression patterns between tumor and normal samples", True, "Complex comparison"),
        ("Can you help me with pathway enrichment analysis", True, "Analysis request"),
        ("Analyze the genomic data from multiple samples", True, "Data analysis"),
        ("I need to perform statistical analysis on gene expression data", True, "Statistical analysis"),

        # Edge cases - let LLM decide
        ("what is gene expression analysis workflow", None, "Medium length question"),
        ("analyze gene data", None, "Short analysis request"),
        ("explain how to do pathway analysis", None, "Instruction request"),
    ]

    print("Testing LLM-based automatic template matching detection")
    print("Using same LLM as main agent (Claude Sonnet 4.5) for classification\n")
    print("=" * 80)

    total = 0
    correct = 0
    errors = 0

    for query, expected, description in test_cases:
        try:
            result = should_use_template_matching(query, language="en")

            # If expected is None, we're just testing that it doesn't error
            if expected is None:
                status = "✓ OK  "
                total += 1
                correct += 1
            else:
                status = "✓ PASS" if result == expected else "✗ FAIL"
                total += 1
                if result == expected:
                    correct += 1

            print(f"{status} | {description:40s} | use_template={result} (expected: {expected if expected is not None else 'any'})")
            print(f"       Query: '{query}'")
            print()

        except Exception as e:
            print(f"✗ ERROR | {description:40s} | Error: {str(e)}")
            print(f"       Query: '{query}'")
            print()
            errors += 1
            total += 1

    print("=" * 80)
    print(f"Results: {correct}/{total} correct, {errors} errors")

    if errors == 0 and correct == total:
        print("✓ All tests passed!")
        return True
    else:
        print("✗ Some tests failed or had errors")
        return False


if __name__ == "__main__":
    # Check for API key
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Error: ANTHROPIC_API_KEY environment variable not set")
        print("Please set it with: export ANTHROPIC_API_KEY=your_key_here")
        sys.exit(1)

    success = test_template_detection()
    sys.exit(0 if success else 1)

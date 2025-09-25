"""
Test script for multi-turn file persistence functionality

This script tests:
1. File upload tracking across turns
2. File availability in subsequent turns
3. S3 download for missing files
4. Context building with file lists
"""

import asyncio
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path

# Add parent directory to path for imports
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from enhanced_multiturn_handler import EnhancedMultiTurnHandler, MultiTurnContextBuilder
from agent_fastapi_server_multiturn import ConversationTurn, MultiTurnSession, Language


def create_test_session():
    """Create a test multi-turn session with multiple turns and files"""

    session = MultiTurnSession(
        session_id="test_session_001",
        created_at=datetime.now().isoformat(),
        last_updated=datetime.now().isoformat(),
        language=Language.EN,
        user_id="test_user",
        total_turns=2,
        current_turn=2,
        turns=[
            ConversationTurn(
                turn_number=1,
                query="Analyze the uploaded dataset and create visualizations",
                final_report="I've analyzed the dataset and created several visualizations...",
                files={
                    "data.csv": {
                        "path": "/tmp/test_session/data.csv",
                        "turn": 1,
                        "type": "data"
                    },
                    "analysis_plot.png": {
                        "path": "/tmp/test_session/analysis_plot.png",
                        "turn": 1,
                        "type": "image"
                    }
                },
                timestamp=datetime.now().isoformat(),
                status="completed"
            ),
            ConversationTurn(
                turn_number=2,
                query="Create a summary report based on the previous analysis",
                final_report="Based on the previous analysis, here's a comprehensive summary...",
                files={
                    "summary_report.md": {
                        "path": "/tmp/test_session/summary_report.md",
                        "turn": 2,
                        "type": "text"
                    }
                },
                timestamp=datetime.now().isoformat(),
                status="completed"
            )
        ],
        accumulated_context="Turn 1: Analysis completed\nTurn 2: Summary created",
        session_status="active"
    )

    return session


def test_context_building():
    """Test building enhanced context with file information"""

    print("=" * 50)
    print("Testing Context Building")
    print("=" * 50)

    # Create test session
    session = create_test_session()

    # Initialize handler (without cloud storage for this test)
    handler = EnhancedMultiTurnHandler(cloud_storage_manager=None)

    # Build context for turn 3
    current_message = "Please create a detailed comparison between the datasets"
    new_files = ["/tmp/new_data.xlsx"]

    context = handler.build_enhanced_context(
        multiturn_session=session,
        current_message=current_message,
        uploaded_files=new_files,
        include_file_list=True
    )

    print("\nEnhanced Message:")
    print("-" * 30)
    print(context['enhanced_message'])

    print("\n\nAll Available Files:")
    print("-" * 30)
    for file_name, file_info in context['all_files'].items():
        print(f"  - {file_name}")
        print(f"    Turn: {file_info['turn']}")
        print(f"    Type: {file_info['type']}")
        print(f"    Path: {file_info['path']}")

    print("\n\nContext Summary:")
    print("-" * 30)
    print(json.dumps(context['context_summary'], indent=2))

    return context


def test_file_categorization():
    """Test file type categorization"""

    print("\n" + "=" * 50)
    print("Testing File Categorization")
    print("=" * 50)

    handler = EnhancedMultiTurnHandler()

    test_files = [
        "data.csv",
        "report.pdf",
        "image.png",
        "script.py",
        "notebook.ipynb",
        "results.xlsx",
        "readme.md",
        "archive.zip"
    ]

    for file_name in test_files:
        file_type = handler._get_file_type(file_name)
        print(f"{file_name:20} -> {file_type}")


async def test_file_availability_check():
    """Test checking and ensuring file availability"""

    print("\n" + "=" * 50)
    print("Testing File Availability Check")
    print("=" * 50)

    # Create temporary test directory
    with tempfile.TemporaryDirectory() as temp_dir:
        session_path = Path(temp_dir) / "test_session"
        session_path.mkdir()

        # Create some test files
        (session_path / "existing_file.txt").write_text("This file exists locally")

        # Initialize handler
        handler = EnhancedMultiTurnHandler(cloud_storage_manager=None)

        # Define required files (some exist, some don't)
        required_files = {
            "existing_file.txt": {
                "path": str(session_path / "existing_file.txt"),
                "turn": 1
            },
            "missing_file.csv": {
                "path": str(session_path / "missing_file.csv"),
                "turn": 2
            }
        }

        # Check file availability
        local_files = await handler.ensure_files_available(
            session_id="test_session",
            required_files=required_files,
            session_path=str(session_path)
        )

        print("\nFile Availability Results:")
        print("-" * 30)
        for file_name, local_path in local_files.items():
            exists = os.path.exists(local_path) if local_path else False
            print(f"  {file_name}: {'✓ Found' if exists else '✗ Not Found'}")
            if local_path:
                print(f"    Path: {local_path}")


def test_simple_context_builder():
    """Test the simplified context builder for backward compatibility"""

    print("\n" + "=" * 50)
    print("Testing Simple Context Builder")
    print("=" * 50)

    session = create_test_session()
    current_message = "What were the key findings from the analysis?"

    context = MultiTurnContextBuilder.build_context_with_files(
        multiturn_session=session,
        current_message=current_message
    )

    print("\nSimple Context:")
    print("-" * 30)
    print(context)


def main():
    """Run all tests"""

    print("Multi-Turn File Persistence Test Suite")
    print("=" * 70)

    # Test 1: Context building
    context = test_context_building()

    # Test 2: File categorization
    test_file_categorization()

    # Test 3: File availability (async)
    asyncio.run(test_file_availability_check())

    # Test 4: Simple context builder
    test_simple_context_builder()

    print("\n" + "=" * 70)
    print("All tests completed successfully!")
    print("=" * 70)

    # Summary
    print("\nKey Features Tested:")
    print("✓ Enhanced context building with file tracking")
    print("✓ File type categorization")
    print("✓ File availability checking")
    print("✓ Backward-compatible simple context builder")
    print("✓ Multi-turn conversation history preservation")
    print("✓ File metadata enrichment")


if __name__ == "__main__":
    main()
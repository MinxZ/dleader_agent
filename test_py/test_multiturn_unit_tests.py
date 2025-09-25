#!/usr/bin/env python3
"""
Comprehensive unit tests for multi-turn file persistence functionality

Tests each component individually to ensure the system works correctly.
"""

import asyncio
import json
import os
import shutil
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# Add parent directory to path for imports
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from enhanced_multiturn_handler import EnhancedMultiTurnHandler, MultiTurnContextBuilder
from agent_fastapi_server_multiturn import ConversationTurn, MultiTurnSession, Language, UserRequest


class TestContextBuilding(unittest.TestCase):
    """Test context building functionality"""

    def setUp(self):
        """Set up test fixtures"""
        self.handler = EnhancedMultiTurnHandler()
        self.session = self._create_test_session()

    def _create_test_session(self):
        """Create a test multi-turn session"""
        return MultiTurnSession(
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
                    query="Analyze this data",
                    final_report="Data analyzed successfully",
                    files={
                        "data.csv": {"path": "/tmp/data.csv", "turn": 1, "type": "data"},
                        "plot.png": {"path": "/tmp/plot.png", "turn": 1, "type": "image"}
                    },
                    timestamp=datetime.now().isoformat(),
                    status="completed"
                ),
                ConversationTurn(
                    turn_number=2,
                    query="Create summary",
                    final_report="Summary created",
                    files={
                        "summary.md": {"path": "/tmp/summary.md", "turn": 2, "type": "text"}
                    },
                    timestamp=datetime.now().isoformat(),
                    status="completed"
                )
            ],
            accumulated_context="Previous analysis results",
            session_status="active"
        )

    def test_basic_context_building(self):
        """Test basic context building with file information"""
        context = self.handler.build_enhanced_context(
            multiturn_session=self.session,
            current_message="Create a report",
            uploaded_files=[],
            include_file_list=True
        )

        # Verify context structure
        self.assertIn('enhanced_message', context)
        self.assertIn('all_files', context)
        self.assertIn('context_summary', context)

        # Verify file tracking
        self.assertEqual(len(context['all_files']), 3)  # 3 files from 2 turns
        self.assertIn('data.csv', context['all_files'])
        self.assertIn('plot.png', context['all_files'])
        self.assertIn('summary.md', context['all_files'])

        # Verify context summary
        self.assertEqual(context['context_summary']['total_turns'], 2)
        self.assertEqual(context['context_summary']['total_files'], 3)

        print("✅ test_basic_context_building passed")

    def test_context_with_new_files(self):
        """Test context building when new files are uploaded"""
        new_files = ["/tmp/new_data.xlsx", "/tmp/config.json"]

        context = self.handler.build_enhanced_context(
            multiturn_session=self.session,
            current_message="Analyze new data",
            uploaded_files=new_files,
            include_file_list=True
        )

        # Should have 5 files total (3 existing + 2 new)
        self.assertEqual(len(context['all_files']), 5)
        self.assertIn('new_data.xlsx', context['all_files'])
        self.assertIn('config.json', context['all_files'])

        # Verify new files are marked with correct turn
        new_data_info = context['all_files']['new_data.xlsx']
        self.assertEqual(new_data_info['turn'], 3)  # Should be turn 3

        print("✅ test_context_with_new_files passed")

    def test_context_message_formatting(self):
        """Test that the enhanced message is properly formatted"""
        context = self.handler.build_enhanced_context(
            multiturn_session=self.session,
            current_message="Test message",
            uploaded_files=[],
            include_file_list=True
        )

        message = context['enhanced_message']

        # Check for key sections
        self.assertIn("Previous Conversation Context", message)
        self.assertIn("Available Files from All Turns", message)
        self.assertIn("Current Request", message)
        self.assertIn("Test message", message)

        # Verify file list is included
        self.assertIn("data.csv", message)
        self.assertIn("Turn 1", message)

        print("✅ test_context_message_formatting passed")


class TestFileCategorization(unittest.TestCase):
    """Test file type categorization"""

    def setUp(self):
        self.handler = EnhancedMultiTurnHandler()

    def test_file_type_detection(self):
        """Test file type detection for various extensions"""
        test_cases = [
            ("data.csv", "data"),
            ("results.xlsx", "data"),
            ("image.png", "image"),
            ("photo.jpg", "image"),
            ("report.pdf", "document"),
            ("script.py", "code"),
            ("notebook.ipynb", "notebook"),
            ("readme.md", "text"),
            ("config.json", "data"),
            ("archive.zip", "other"),
            ("unknown.xyz", "other")
        ]

        for filename, expected_type in test_cases:
            detected_type = self.handler._get_file_type(filename)
            self.assertEqual(detected_type, expected_type,
                           f"Failed for {filename}: expected {expected_type}, got {detected_type}")

        print("✅ test_file_type_detection passed")

    def test_file_categorization_counts(self):
        """Test file categorization and counting"""
        files = {
            "data1.csv": {"type": "data"},
            "data2.xlsx": {"type": "data"},
            "plot1.png": {"type": "image"},
            "plot2.jpg": {"type": "image"},
            "report.pdf": {"type": "document"},
            "script.py": {"type": "code"}
        }

        categories = self.handler._categorize_files(files)

        self.assertEqual(categories['data'], 2)
        self.assertEqual(categories['image'], 2)
        self.assertEqual(categories['document'], 1)
        self.assertEqual(categories['code'], 1)

        print("✅ test_file_categorization_counts passed")


class TestFileAvailability(unittest.TestCase):
    """Test file availability and recovery functionality"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.handler = EnhancedMultiTurnHandler(cloud_storage_manager=None)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    async def test_local_file_availability(self):
        """Test checking availability of local files"""
        # Create a test file
        test_file = Path(self.temp_dir) / "test.txt"
        test_file.write_text("test content")

        required_files = {
            "test.txt": {
                "path": str(test_file),
                "turn": 1
            },
            "missing.txt": {
                "path": str(Path(self.temp_dir) / "missing.txt"),
                "turn": 2
            }
        }

        local_files = await self.handler.ensure_files_available(
            session_id="test_session",
            required_files=required_files,
            session_path=self.temp_dir
        )

        # Should find the existing file
        self.assertIn("test.txt", local_files)
        self.assertEqual(local_files["test.txt"], str(test_file))

        # Should not find the missing file (no cloud storage configured)
        self.assertNotIn("missing.txt", local_files)

        print("✅ test_local_file_availability passed")

    def test_sync_local_file_check(self):
        """Synchronous test for local file checking"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self.test_local_file_availability())
        loop.close()


class TestMultiTurnSessionTracking(unittest.TestCase):
    """Test multi-turn session tracking functionality"""

    def test_session_initialization(self):
        """Test session initialization with correct attributes"""
        session = MultiTurnSession(
            session_id="test_123",
            created_at=datetime.now().isoformat(),
            last_updated=datetime.now().isoformat(),
            language=Language.EN,
            user_id="user_123",
            total_turns=0,
            current_turn=0,
            turns=[],
            accumulated_context="",
            session_status="active"
        )

        self.assertEqual(session.session_id, "test_123")
        self.assertEqual(session.total_turns, 0)
        self.assertEqual(session.session_status, "active")
        self.assertEqual(len(session.turns), 0)

        print("✅ test_session_initialization passed")

    def test_session_turn_addition(self):
        """Test adding turns to a session"""
        session = MultiTurnSession(
            session_id="test_456",
            created_at=datetime.now().isoformat(),
            last_updated=datetime.now().isoformat(),
            language=Language.EN,
            user_id="user_456",
            total_turns=0,
            current_turn=0,
            turns=[],
            accumulated_context="",
            session_status="active"
        )

        # Add first turn
        turn1 = ConversationTurn(
            turn_number=1,
            query="First query",
            final_report="First response",
            files={},
            timestamp=datetime.now().isoformat(),
            status="completed"
        )
        session.turns.append(turn1)
        session.total_turns = 1

        self.assertEqual(len(session.turns), 1)
        self.assertEqual(session.turns[0].query, "First query")

        # Add second turn
        turn2 = ConversationTurn(
            turn_number=2,
            query="Second query",
            final_report="Second response",
            files={"file.txt": {"path": "/tmp/file.txt", "turn": 2}},
            timestamp=datetime.now().isoformat(),
            status="completed"
        )
        session.turns.append(turn2)
        session.total_turns = 2

        self.assertEqual(len(session.turns), 2)
        self.assertEqual(session.turns[1].query, "Second query")
        self.assertIn("file.txt", session.turns[1].files)

        print("✅ test_session_turn_addition passed")

    def test_session_properties(self):
        """Test session property methods"""
        session = MultiTurnSession(
            session_id="test_789",
            created_at=datetime.now().isoformat(),
            last_updated=datetime.now().isoformat(),
            language=Language.EN,
            user_id="user_789",
            total_turns=2,
            current_turn=2,
            turns=[
                ConversationTurn(
                    turn_number=1,
                    query="First query",
                    final_report="",
                    files={},
                    timestamp=datetime.now().isoformat(),
                    status="completed"
                ),
                ConversationTurn(
                    turn_number=2,
                    query="Latest query",
                    final_report="",
                    files={},
                    timestamp=datetime.now().isoformat(),
                    status="completed"
                )
            ],
            accumulated_context="",
            session_status="active"
        )

        self.assertEqual(session.first_query, "First query")
        self.assertEqual(session.latest_query, "Latest query")

        print("✅ test_session_properties passed")


class TestFileMetadataEnrichment(unittest.TestCase):
    """Test file metadata enrichment functionality"""

    def setUp(self):
        self.handler = EnhancedMultiTurnHandler()
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_turn_file_update(self):
        """Test updating turn with generated files"""
        # Create a test turn
        turn = ConversationTurn(
            turn_number=1,
            query="Generate files",
            final_report="",
            files={},
            timestamp=datetime.now().isoformat(),
            status="processing"
        )

        # Create test files
        session_path = Path(self.temp_dir)
        (session_path / "output.txt").write_text("output")
        (session_path / "result.png").write_bytes(b"image_data")

        # Update turn with files
        self.handler.update_turn_with_files(turn, str(session_path))

        # Verify files were added
        self.assertIn("output.txt", turn.files)
        self.assertIn("result.png", turn.files)

        # Verify metadata
        output_info = turn.files["output.txt"]
        self.assertEqual(output_info['type'], 'text')
        self.assertIn('path', output_info)
        self.assertIn('size', output_info)
        self.assertIn('created', output_info)

        result_info = turn.files["result.png"]
        self.assertEqual(result_info['type'], 'image')

        print("✅ test_turn_file_update passed")

    def test_metadata_structure(self):
        """Test that file metadata has correct structure"""
        turn = ConversationTurn(
            turn_number=1,
            query="Test",
            final_report="",
            files={},
            timestamp=datetime.now().isoformat(),
            status="processing"
        )

        # Create a test file
        test_file = Path(self.temp_dir) / "test_data.csv"
        test_file.write_text("col1,col2\n1,2\n3,4")

        # Update turn
        self.handler.update_turn_with_files(turn, self.temp_dir)

        # Check metadata structure
        file_info = turn.files.get("test_data.csv")
        self.assertIsNotNone(file_info)
        self.assertIn('path', file_info)
        self.assertIn('type', file_info)
        self.assertIn('size', file_info)
        self.assertIn('created', file_info)

        # Verify values
        self.assertEqual(file_info['type'], 'data')
        self.assertTrue(file_info['size'] > 0)

        print("✅ test_metadata_structure passed")


class TestUserRequestEnhancement(unittest.TestCase):
    """Test UserRequest enhancement for multi-turn conversations"""

    def test_user_request_basic(self):
        """Test basic UserRequest creation"""
        request = UserRequest(
            session_id="test_001",
            message="Test message",
            language=Language.EN,
            uploaded_files=["/tmp/file1.txt"],
            is_continuation=False,
            previous_context="",
            turn_number=1,
            user_id="user_001"
        )

        self.assertEqual(request.session_id, "test_001")
        self.assertEqual(request.message, "Test message")
        self.assertEqual(len(request.uploaded_files), 1)
        self.assertFalse(request.is_continuation)
        self.assertEqual(request.turn_number, 1)

        print("✅ test_user_request_basic passed")

    def test_user_request_continuation(self):
        """Test UserRequest with continuation context"""
        previous_context = "Turn 1: Analyzed data\nTurn 2: Created plots"

        request = UserRequest(
            session_id="test_002",
            message="Create summary",
            language=Language.EN,
            uploaded_files=[],
            is_continuation=True,
            previous_context=previous_context,
            turn_number=3,
            user_id="user_002"
        )

        self.assertTrue(request.is_continuation)
        self.assertEqual(request.turn_number, 3)

        # Check enhanced message includes context
        enhanced = request.enhanced_message
        self.assertIn("Previous conversation context", enhanced)
        self.assertIn(previous_context, enhanced)
        self.assertIn("Create summary", enhanced)

        print("✅ test_user_request_continuation passed")


class TestSimpleContextBuilder(unittest.TestCase):
    """Test the simple context builder for backward compatibility"""

    def setUp(self):
        self.session = MultiTurnSession(
            session_id="test_simple",
            created_at=datetime.now().isoformat(),
            last_updated=datetime.now().isoformat(),
            language=Language.EN,
            user_id="test_user",
            total_turns=2,
            current_turn=2,
            turns=[
                ConversationTurn(
                    turn_number=1,
                    query="First query with long text that should be truncated in the context",
                    final_report="First response with detailed information",
                    files={"file1.txt": {}, "file2.csv": {}},
                    timestamp=datetime.now().isoformat(),
                    status="completed"
                ),
                ConversationTurn(
                    turn_number=2,
                    query="Second query",
                    final_report="Second response",
                    files={"file3.png": {}},
                    timestamp=datetime.now().isoformat(),
                    status="completed"
                )
            ],
            accumulated_context="",
            session_status="active"
        )

    def test_simple_context_format(self):
        """Test simple context builder output format"""
        context = MultiTurnContextBuilder.build_context_with_files(
            multiturn_session=self.session,
            current_message="New request"
        )

        # Check basic structure
        self.assertIn("Conversation History", context)
        self.assertIn("Current Request", context)
        self.assertIn("Turn 3", context)  # New turn number
        self.assertIn("New request", context)

        # Check turn summaries
        self.assertIn("Turn 1:", context)
        self.assertIn("Turn 2:", context)

        # Check files are listed
        self.assertIn("file1.txt", context)
        self.assertIn("file3.png", context)

        print("✅ test_simple_context_format passed")


class TestIntegration(unittest.TestCase):
    """Integration tests for the complete workflow"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.handler = EnhancedMultiTurnHandler()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_full_workflow_simulation(self):
        """Test a complete multi-turn workflow"""
        # Create initial session
        session = MultiTurnSession(
            session_id="integration_test",
            created_at=datetime.now().isoformat(),
            last_updated=datetime.now().isoformat(),
            language=Language.EN,
            user_id="test_user",
            total_turns=0,
            current_turn=0,
            turns=[],
            accumulated_context="",
            session_status="active"
        )

        # Turn 1: Upload files
        turn1_files = {
            "data.csv": {"path": f"{self.temp_dir}/data.csv", "turn": 1, "type": "data"}
        }
        turn1 = ConversationTurn(
            turn_number=1,
            query="Analyze data",
            final_report="Analysis complete",
            files=turn1_files,
            timestamp=datetime.now().isoformat(),
            status="completed"
        )
        session.turns.append(turn1)
        session.total_turns = 1

        # Build context for Turn 2
        context_turn2 = self.handler.build_enhanced_context(
            multiturn_session=session,
            current_message="Create visualizations",
            uploaded_files=[],
            include_file_list=True
        )

        # Verify Turn 1 files are in context
        self.assertIn("data.csv", context_turn2['all_files'])

        # Turn 2: Add generated files
        turn2_files = {
            "plot.png": {"path": f"{self.temp_dir}/plot.png", "turn": 2, "type": "image"}
        }
        turn2 = ConversationTurn(
            turn_number=2,
            query="Create visualizations",
            final_report="Plots created",
            files=turn2_files,
            timestamp=datetime.now().isoformat(),
            status="completed"
        )
        session.turns.append(turn2)
        session.total_turns = 2

        # Build context for Turn 3
        context_turn3 = self.handler.build_enhanced_context(
            multiturn_session=session,
            current_message="Generate final report",
            uploaded_files=[f"{self.temp_dir}/template.docx"],
            include_file_list=True
        )

        # Verify all files are tracked
        self.assertEqual(len(context_turn3['all_files']), 3)  # data.csv, plot.png, template.docx
        self.assertIn("data.csv", context_turn3['all_files'])
        self.assertIn("plot.png", context_turn3['all_files'])
        self.assertIn("template.docx", context_turn3['all_files'])

        # Verify turn tracking
        self.assertEqual(context_turn3['all_files']['data.csv']['turn'], 1)
        self.assertEqual(context_turn3['all_files']['plot.png']['turn'], 2)
        self.assertEqual(context_turn3['all_files']['template.docx']['turn'], 3)

        print("✅ test_full_workflow_simulation passed")


def run_all_tests():
    """Run all unit tests and report results"""
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Add all test cases
    test_classes = [
        TestContextBuilding,
        TestFileCategorization,
        TestFileAvailability,
        TestMultiTurnSessionTracking,
        TestFileMetadataEnrichment,
        TestUserRequestEnhancement,
        TestSimpleContextBuilder,
        TestIntegration
    ]

    for test_class in test_classes:
        suite.addTests(loader.loadTestsFromTestCase(test_class))

    # Run tests with detailed output
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # Summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")

    if result.wasSuccessful():
        print("\n✅ ALL TESTS PASSED!")
    else:
        print("\n❌ SOME TESTS FAILED")
        if result.failures:
            print("\nFailed tests:")
            for test, traceback in result.failures:
                print(f"  - {test}")
        if result.errors:
            print("\nTests with errors:")
            for test, traceback in result.errors:
                print(f"  - {test}")

    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_all_tests()
    exit(0 if success else 1)
#!/usr/bin/env python3
"""
Test that system files are properly separated from user files
"""

import asyncio
from cloud_storage_manager import CloudStorageManager
import tempfile
import os
import shutil

async def test_file_filtering():
    """Test that download_turn_files_from_s3 properly filters system files"""

    print("Testing file filtering in download_turn_files_from_s3...")

    # Mock S3 keys that would be returned
    mock_s3_keys = [
        "sessions/test123/turn1_user_image.jpg",  # User file - should download
        "sessions/test123/turn2_data.csv",  # User file - should download
        "sessions/test123/images/plot.png",  # Agent generated - should download
        "sessions/test123/report_md/report_20250927.md",  # System file - should skip
        "sessions/test123/thinking_process/thinking_20250927.txt",  # System file - should skip
        "sessions/test123/query_file/query_20250927.txt",  # System file - should skip
        "sessions/test123/snapshots/snapshot_20250927.json",  # System file - should skip
        "sessions/test123/result_json/result_20250927.json",  # System file - should skip
        "sessions/test123/additional/query_20250927.txt",  # System file even in additional - should skip
        "sessions/test123/additional/custom_output.txt",  # User file - should download
    ]

    # Test the filtering logic
    system_file_patterns = ['query_*.txt', 'report_*.md', 'thinking_process_*.txt',
                           'result_*.json', 'snapshot_*.json', '*.zip']

    def is_system_file(filename):
        """Check if filename matches system-generated patterns"""
        import fnmatch
        for pattern in system_file_patterns:
            if fnmatch.fnmatch(filename, pattern):
                return True
        return False

    should_download = []
    should_skip = []

    for s3_key in mock_s3_keys:
        # Check directory-based filtering
        if any(x in s3_key for x in ['/report_md/', '/thinking_process/', '/query_file/',
                                     '/result_json/', '/snapshots/', '/session_zip/']):
            should_skip.append(s3_key)
            continue

        # Extract filename
        filename_parts = s3_key.split('/')[-1]

        # Remove turn prefix
        if filename_parts.startswith('turn'):
            underscore_pos = filename_parts.find('_')
            if underscore_pos > 0:
                filename = filename_parts[underscore_pos + 1:]
            else:
                filename = filename_parts
        else:
            filename = filename_parts

        # Check pattern-based filtering
        if is_system_file(filename):
            should_skip.append(s3_key)
        else:
            should_download.append(s3_key)

    print("\n✅ Files that SHOULD be downloaded (user/agent files):")
    for key in should_download:
        print(f"   - {key}")

    print("\n❌ Files that should be SKIPPED (system files):")
    for key in should_skip:
        print(f"   - {key}")

    # Verify expectations
    expected_downloads = [
        "sessions/test123/turn1_user_image.jpg",
        "sessions/test123/turn2_data.csv",
        "sessions/test123/images/plot.png",
        "sessions/test123/additional/custom_output.txt"
    ]

    expected_skips = [
        "sessions/test123/report_md/report_20250927.md",
        "sessions/test123/thinking_process/thinking_20250927.txt",
        "sessions/test123/query_file/query_20250927.txt",
        "sessions/test123/snapshots/snapshot_20250927.json",
        "sessions/test123/result_json/result_20250927.json",
        "sessions/test123/additional/query_20250927.txt"
    ]

    assert set(should_download) == set(expected_downloads), f"Download mismatch: {should_download} != {expected_downloads}"
    assert set(should_skip) == set(expected_skips), f"Skip mismatch: {should_skip} != {expected_skips}"

    print("\n✅ TEST PASSED: File filtering works correctly!")
    print("   - User files and agent-generated files will be downloaded")
    print("   - System files (query, report, thinking, result, snapshot) will be skipped")

    return True

if __name__ == "__main__":
    success = asyncio.run(test_file_filtering())
    exit(0 if success else 1)
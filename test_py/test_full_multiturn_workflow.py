"""
Comprehensive test for multi-turn workflow with file persistence

This test simulates a complete multi-turn conversation workflow:
1. First turn: Upload data, agent creates plots
2. Stop first session, start second session
3. Delete local files to simulate cloud-only storage
4. Second turn: Verify files are recovered from S3 and can be used
5. Download ZIP with all results
"""

import asyncio
import json
import os
import shutil
import tempfile
import time
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import aiohttp
import pandas as pd
import requests


class MultiturnWorkflowTest:
    """Test class for multi-turn workflow with file persistence"""

    def __init__(self, server_url: str = "http://localhost:8001"):
        self.server_url = server_url
        self.test_dir = Path(tempfile.mkdtemp(prefix="multiturn_test_"))
        self.session_id = None
        self.turn_session_ids = []
        self.user_id = f"test_user_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        print(f"Test directory: {self.test_dir}")
        print(f"Test user ID: {self.user_id}")

    def create_test_data_file(self) -> Path:
        """Create a test CSV file with specific data"""
        data = {
            'product': ['Product A', 'Product B', 'Product C', 'Product D', 'Product E'],
            'sales': [1200, 1500, 900, 1800, 2100],
            'profit': [300, 450, 200, 600, 750],
            'region': ['North', 'South', 'East', 'West', 'Central'],
            'special_code': ['TEST-001', 'TEST-002', 'TEST-003', 'TEST-004', 'TEST-005']
        }

        df = pd.DataFrame(data)
        file_path = self.test_dir / "test_sales_data.csv"
        df.to_csv(file_path, index=False)

        print(f"Created test data file: {file_path}")
        print(f"Data preview:\n{df.head()}")

        return file_path

    def create_metadata_file(self) -> Path:
        """Create a metadata JSON file with specific information"""
        metadata = {
            "experiment_id": "EXP-2024-001",
            "timestamp": datetime.now().isoformat(),
            "parameters": {
                "analysis_type": "sales_profit_correlation",
                "visualization_required": True,
                "color_scheme": "viridis",
                "plot_title": "Sales and Profit Analysis Q4 2024"
            },
            "secret_key": "MULTITURN-TEST-KEY-42",
            "instructions": "Use this color scheme and title for all plots"
        }

        file_path = self.test_dir / "metadata.json"
        with open(file_path, 'w') as f:
            json.dump(metadata, f, indent=2)

        print(f"Created metadata file: {file_path}")
        print(f"Metadata: {json.dumps(metadata, indent=2)}")

        return file_path

    async def start_first_turn(self) -> Dict:
        """Start the first turn with file uploads and plotting request"""
        print("\n" + "="*60)
        print("TURN 1: Starting first turn with data upload")
        print("="*60)

        # Create test files
        data_file = self.create_test_data_file()
        metadata_file = self.create_metadata_file()

        # Prepare the request
        url = f"{self.server_url}/chat-queue"

        # The prompt that will make the agent create plots
        prompt = """
        Please analyze the uploaded sales data (test_sales_data.csv) and metadata.json file:

        1. Read the metadata.json to get the plot title and color scheme
        2. Create a bar chart showing sales by product using the specified color scheme
        3. Create a scatter plot showing sales vs profit correlation
        4. Save both plots as PNG files with descriptive names
        5. Extract and display the secret_key from metadata.json
        6. Create a summary report that includes:
           - The experiment_id from metadata
           - Statistics about the sales data
           - The special_codes from the CSV

        IMPORTANT: Save all plots as PNG files in the session folder.
        """

        # Submit with files
        async with aiohttp.ClientSession() as session:
            data = aiohttp.FormData()
            data.add_field('message', prompt)
            data.add_field('user_id', self.user_id)
            data.add_field('language', 'en')

            # Add files
            data.add_field('files',
                          open(data_file, 'rb'),
                          filename='test_sales_data.csv',
                          content_type='text/csv')
            data.add_field('files',
                          open(metadata_file, 'rb'),
                          filename='metadata.json',
                          content_type='application/json')

            async with session.post(url, data=data) as response:
                result = await response.json()
                self.session_id = result['session_id']
                self.turn_session_ids.append(result['session_id'])

                print(f"First turn started:")
                print(f"  Session ID: {self.session_id}")
                print(f"  Status: {result['status']}")

                return result

    async def wait_for_completion(self, session_id: str, max_wait: int = 120) -> Dict:
        """Wait for a session to complete"""
        print(f"\nWaiting for session {session_id} to complete...")

        url = f"{self.server_url}/status/{session_id}"
        params = {'user_id': self.user_id}

        start_time = time.time()
        last_status = None

        async with aiohttp.ClientSession() as session:
            while time.time() - start_time < max_wait:
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        result = await response.json()
                        current_status = result.get('status', 'unknown')

                        if current_status != last_status:
                            print(f"  Status: {current_status}")
                            last_status = current_status

                        if result.get('is_complete'):
                            print(f"  Session completed in {time.time() - start_time:.1f} seconds")

                            # Extract key information
                            if result.get('json_result'):
                                content = result['json_result'].get('content', {})
                                if content.get('final_report'):
                                    print("\n  Final Report Preview:")
                                    print("  " + content['final_report'][:200] + "...")

                            return result

                await asyncio.sleep(2)

        raise TimeoutError(f"Session {session_id} did not complete within {max_wait} seconds")

    async def stop_session(self, session_id: str) -> bool:
        """Stop a running session"""
        print(f"\nStopping session {session_id}...")

        url = f"{self.server_url}/stop-session"
        data = {
            'session_id': session_id,
            'user_id': self.user_id
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=data) as response:
                if response.status == 200:
                    result = await response.json()
                    print(f"  Stop result: {result.get('message', 'Stopped')}")
                    return True
                else:
                    print(f"  Failed to stop: {response.status}")
                    return False

    def delete_local_files(self, session_id: str):
        """Delete local session files to simulate cloud-only storage"""
        print(f"\nDeleting local files for session {session_id}...")

        # Find and delete session directories
        patterns = [
            f"session_storage/{session_id}*",
            f"chat_sessions/{session_id}*",
            f"multiturn_sessions/{session_id}*",
            f"temp_uploads/{session_id}*"
        ]

        deleted_count = 0
        for pattern in patterns:
            for path in Path.cwd().glob(pattern):
                if path.exists():
                    print(f"  Deleting: {path}")
                    if path.is_dir():
                        shutil.rmtree(path)
                    else:
                        path.unlink()
                    deleted_count += 1

        print(f"  Deleted {deleted_count} local items")
        return deleted_count

    async def start_second_turn(self) -> Dict:
        """Start second turn that should recover files from S3"""
        print("\n" + "="*60)
        print("TURN 2: Starting second turn (files should be recovered from S3)")
        print("="*60)

        # Prompt that requires files from first turn
        prompt = """
        Please continue the analysis from the previous turn:

        1. Load the plots that were created in the first turn (they should be PNG files)
        2. Extract and report the secret_key that was in the metadata.json from turn 1
        3. List all the special_codes that were in the test_sales_data.csv from turn 1
        4. Create a new combined visualization that shows both sales and profit in a single chart
        5. Verify you can read the experiment_id from the previous metadata
        6. Create a final summary that references data from both turns

        IMPORTANT: Explicitly state whether you found the files from turn 1 and what their names are.
        """

        url = f"{self.server_url}/continue-session"

        async with aiohttp.ClientSession() as session:
            data = aiohttp.FormData()
            data.add_field('session_id', self.session_id)
            data.add_field('message', prompt)
            data.add_field('user_id', self.user_id)
            data.add_field('language', 'en')

            async with session.post(url, data=data) as response:
                result = await response.json()
                turn_session_id = result.get('turn_session_id')
                self.turn_session_ids.append(turn_session_id)

                print(f"Second turn started:")
                print(f"  Session ID: {self.session_id}")
                print(f"  Turn Session ID: {turn_session_id}")
                print(f"  Turn Number: {result.get('turn_number')}")

                return result

    async def get_session_metadata(self, session_id: str) -> Dict:
        """Get session metadata including file information"""
        print(f"\nFetching metadata for session {session_id}...")

        url = f"{self.server_url}/multiturn-session/{session_id}"
        params = {'user_id': self.user_id}

        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    result = await response.json()

                    # Extract file information
                    print("\n  Files tracked across turns:")
                    for turn in result.get('turns', []):
                        if turn.get('files'):
                            print(f"\n    Turn {turn['turn_number']}:")
                            for file_name, file_info in turn['files'].items():
                                if isinstance(file_info, dict):
                                    print(f"      - {file_name}")
                                    print(f"        Path: {file_info.get('path', 'N/A')}")
                                    print(f"        Type: {file_info.get('type', 'N/A')}")

                    return result
                else:
                    print(f"  Failed to get metadata: {response.status}")
                    return {}

    async def download_session_zip(self, session_id: str) -> Path:
        """Download session results as ZIP"""
        print(f"\nDownloading ZIP for session {session_id}...")

        # Try different session IDs (main session or turn-specific)
        for sid in [session_id] + self.turn_session_ids:
            url = f"{self.server_url}/download/{sid}"
            params = {'user_id': self.user_id}

            try:
                response = requests.get(url, params=params, stream=True)
                if response.status_code == 200:
                    zip_path = self.test_dir / f"{sid}_results.zip"

                    with open(zip_path, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            f.write(chunk)

                    print(f"  Downloaded ZIP to: {zip_path}")

                    # List ZIP contents
                    with zipfile.ZipFile(zip_path, 'r') as zf:
                        print("\n  ZIP contents:")
                        for file_info in zf.filelist:
                            print(f"    - {file_info.filename} ({file_info.file_size} bytes)")

                    return zip_path
            except Exception as e:
                print(f"  Failed to download from {sid}: {e}")
                continue

        print("  No ZIP file could be downloaded")
        return None

    def verify_results(self, turn1_result: Dict, turn2_result: Dict, metadata: Dict) -> bool:
        """Verify that the multi-turn workflow worked correctly"""
        print("\n" + "="*60)
        print("VERIFICATION: Checking results")
        print("="*60)

        checks = []

        # Check 1: Turn 1 completed successfully
        check1 = turn1_result.get('is_complete', False)
        checks.append(("Turn 1 completed", check1))

        # Check 2: Turn 2 completed successfully
        check2 = turn2_result.get('is_complete', False)
        checks.append(("Turn 2 completed", check2))

        # Check 3: Files were tracked across turns
        has_files = any(turn.get('files') for turn in metadata.get('turns', []))
        checks.append(("Files tracked across turns", has_files))

        # Check 4: Secret key was found (should be in reports)
        secret_found = False
        for result in [turn1_result, turn2_result]:
            if result.get('json_result'):
                content = str(result['json_result'].get('content', {}))
                if 'MULTITURN-TEST-KEY-42' in content:
                    secret_found = True
                    break
        checks.append(("Secret key found", secret_found))

        # Check 5: Special codes were extracted
        codes_found = False
        for result in [turn1_result, turn2_result]:
            if result.get('json_result'):
                content = str(result['json_result'].get('content', {}))
                if 'TEST-001' in content or 'TEST-002' in content:
                    codes_found = True
                    break
        checks.append(("Special codes extracted", codes_found))

        # Check 6: Plots were created (look for .png in file lists)
        plots_created = False
        for turn in metadata.get('turns', []):
            if turn.get('files'):
                for file_name in turn['files'].keys():
                    if file_name.endswith('.png'):
                        plots_created = True
                        break
        checks.append(("Plots created", plots_created))

        # Print results
        print("\nVerification Results:")
        all_passed = True
        for check_name, passed in checks:
            status = "✓ PASS" if passed else "✗ FAIL"
            print(f"  {status}: {check_name}")
            if not passed:
                all_passed = False

        return all_passed

    async def run_full_test(self):
        """Run the complete multi-turn workflow test"""
        try:
            print("\n" + "="*70)
            print("MULTI-TURN WORKFLOW TEST WITH FILE PERSISTENCE")
            print("="*70)

            # Step 1: Start first turn with file uploads
            await self.start_first_turn()

            # Step 2: Wait for first turn to complete
            turn1_result = await self.wait_for_completion(self.session_id)

            # Step 3: Get metadata to see files
            metadata1 = await self.get_session_metadata(self.session_id)

            # Step 4: Delete local files (simulate cloud-only storage)
            self.delete_local_files(self.session_id)

            # Step 5: Start second turn (should recover files from S3)
            turn2_response = await self.start_second_turn()
            turn2_session_id = turn2_response.get('turn_session_id')

            # Step 6: Wait for second turn to complete
            turn2_result = await self.wait_for_completion(turn2_session_id)

            # Step 7: Get updated metadata
            metadata2 = await self.get_session_metadata(self.session_id)

            # Step 8: Download ZIP file
            zip_path = await self.download_session_zip(self.session_id)

            # Step 9: Verify results
            success = self.verify_results(turn1_result, turn2_result, metadata2)

            # Summary
            print("\n" + "="*70)
            print("TEST SUMMARY")
            print("="*70)
            print(f"Test User: {self.user_id}")
            print(f"Session ID: {self.session_id}")
            print(f"Total Turns: {len(self.turn_session_ids)}")
            print(f"ZIP Downloaded: {zip_path is not None}")
            print(f"All Checks Passed: {success}")
            print("="*70)

            if success:
                print("\n🎉 SUCCESS: Multi-turn workflow test PASSED!")
            else:
                print("\n❌ FAILURE: Some checks failed. Review the results above.")

            return success

        except Exception as e:
            print(f"\n❌ ERROR: Test failed with exception: {e}")
            import traceback
            traceback.print_exc()
            return False

        finally:
            # Cleanup
            print(f"\nCleaning up test directory: {self.test_dir}")
            shutil.rmtree(self.test_dir, ignore_errors=True)


async def main():
    """Main test runner"""
    # Check if server is running
    server_url = "http://localhost:8001"

    print("Checking if server is running...")
    try:
        response = requests.get(f"{server_url}/health")
        if response.status_code != 200:
            print(f"❌ Server health check failed: {response.status_code}")
            print("Please ensure the FastAPI server is running:")
            print("  python agent_fastapi_server_multiturn.py")
            return
        print("✓ Server is running")
    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to server")
        print("Please start the FastAPI server first:")
        print("  python agent_fastapi_server_multiturn.py")
        return

    # Run the test
    test = MultiturnWorkflowTest(server_url)
    success = await test.run_full_test()

    # Exit with appropriate code
    exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
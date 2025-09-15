"""
Agent FastAPI Client Example

This example demonstrates how to interact with the FastAPI agent server
that supports multiple concurrent users with queue management.
"""

import asyncio
import json
import time
import websockets
from typing import Optional
import requests
import aiohttp

class AgentClient:
    def __init__(self, base_url: str = "http://localhost:8001"):
        self.base_url = base_url
        self.session_id: Optional[str] = None
    
    async def start_chat(self, message: str, language: str = "en") -> str:
        """Start a new chat session"""
        async with aiohttp.ClientSession() as session:
            payload = {
                "message": message,
                "language": language,
                "session_id": self.session_id
            }
            
            async with session.post(f"{self.base_url}/chat", json=payload) as response:
                if response.status == 200:
                    result = await response.json()
                    self.session_id = result["session_id"]
                    print(f"Chat started. Session ID: {self.session_id}")
                    return self.session_id
                else:
                    error_text = await response.text()
                    raise Exception(f"Failed to start chat: {error_text}")
    
    async def get_queue_status(self) -> dict:
        """Get current queue position"""
        if not self.session_id:
            raise ValueError("No active session")
        
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.base_url}/chat/{self.session_id}/queue") as response:
                if response.status == 200:
                    return await response.json()
                else:
                    return {"error": f"Failed to get queue status: {response.status}"}
    
    async def get_status(self) -> dict:
        """Get current session status"""
        if not self.session_id:
            raise ValueError("No active session")
        
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.base_url}/chat/{self.session_id}/status") as response:
                if response.status == 200:
                    return await response.json()
                else:
                    return {"error": f"Failed to get status: {response.status}"}
    
    async def upload_files(self, file_paths: list) -> dict:
        """Upload files for the current session"""
        if not self.session_id:
            raise ValueError("No active session")
        
        files = []
        for file_path in file_paths:
            with open(file_path, 'rb') as f:
                files.append(('files', (file_path, f.read())))
        
        response = requests.post(f"{self.base_url}/upload/{self.session_id}", files=files)
        return response.json()
    
    async def monitor_progress(self, callback=None):
        """Monitor progress via WebSocket"""
        if not self.session_id:
            raise ValueError("No active session")
        
        ws_url = f"ws://localhost:8001/ws/{self.session_id}"
        
        try:
            async with websockets.connect(ws_url) as websocket:
                print("Connected to WebSocket for real-time updates...")
                
                while True:
                    try:
                        message = await asyncio.wait_for(websocket.recv(), timeout=1.0)
                        data = json.loads(message)
                        
                        if callback:
                            callback(data)
                        else:
                            self._default_progress_callback(data)
                        
                        if data.get("is_complete"):
                            print("✅ Processing completed!")
                            break
                            
                    except asyncio.TimeoutError:
                        continue
                        
        except Exception as e:
            print(f"WebSocket connection error: {e}")
    
    def _default_progress_callback(self, data):
        """Default callback for progress updates"""
        status = data.get("status", "unknown")
        
        if status == "queued":
            print(f"📋 Status: Queued")
        elif status == "processing":
            print(f"🔄 Status: Processing...")
            
            # Show progress updates
            progress_updates = data.get("progress_updates", [])
            for update in progress_updates:
                if update.get("type") == "status":
                    print(f"   📝 {update.get('message')}")
                elif update.get("type") == "thinking_update":
                    # Show only new thinking content (truncated for readability)
                    new_content = update.get("content", "")
                    if new_content.strip():
                        print(f"   🧠 Agent thinking: {new_content[:100]}...")
                elif update.get("type") == "completion":
                    print(f"   ✅ Processing completed!")
                elif update.get("type") == "error":
                    print(f"   ❌ Error: {update.get('error')}")
        
        elif status == "completed":
            print(f"✅ Status: Completed")
        elif status == "error":
            print(f"❌ Status: Error - {data.get('error')}")


async def example_single_user():
    """Example of single user interaction"""
    print("=== Single User Example ===")
    
    client = AgentClient()
    
    try:
        # Start a chat
        message = "Analyze any patterns in data and create a simple visualization"
        await client.start_chat(message, language="en")
        
        # Check queue status
        queue_status = await client.get_queue_status()
        print(f"Queue position: {queue_status}")
        
        # Monitor progress
        await client.monitor_progress()
        
        # Get final status
        final_status = await client.get_status()
        print(f"Final status: {final_status.get('status')}")
        
    except Exception as e:
        print(f"Error: {e}")


async def example_multiple_users():
    """Example of multiple users with queue management"""
    print("=== Multiple Users Example ===")
    
    async def user_session(user_id: int, message: str, language: str = "en"):
        client = AgentClient()
        
        try:
            print(f"👤 User {user_id}: Starting chat...")
            await client.start_chat(message, language=language)
            
            # Check initial queue position
            queue_status = await client.get_queue_status()
            print(f"👤 User {user_id}: Queue position {queue_status.get('position', 'unknown')}")
            
            # Custom callback to show user ID
            def progress_callback(data):
                status = data.get("status", "unknown")
                if status == "processing":
                    print(f"👤 User {user_id}: Now processing...")
                elif status == "completed":
                    print(f"👤 User {user_id}: ✅ Completed!")
                elif data.get("is_complete"):
                    print(f"👤 User {user_id}: ✅ Session finished!")
            
            # Monitor progress
            await client.monitor_progress(callback=progress_callback)
            
        except Exception as e:
            print(f"👤 User {user_id}: Error - {e}")
    
    # Create multiple concurrent user sessions
    tasks = [
        user_session(1, "Create a simple bar chart with sample data", "en"),
        user_session(2, "データの傾向を分析して、簡単な可視化を作成してください", "jp"),
        user_session(3, "Generate a random dataset and perform basic statistics", "en"),
    ]
    
    # Run all sessions concurrently
    await asyncio.gather(*tasks)


async def example_with_file_upload():
    """Example with file upload"""
    print("=== File Upload Example ===")
    
    client = AgentClient()
    
    try:
        # Create a sample CSV file for testing
        import pandas as pd
        sample_data = pd.DataFrame({
            'name': ['Alice', 'Bob', 'Charlie'],
            'age': [25, 30, 35],
            'score': [85, 92, 78]
        })
        sample_file = "/tmp/sample_data.csv"
        sample_data.to_csv(sample_file, index=False)
        
        # Start chat
        await client.start_chat("Analyze the uploaded CSV file and create visualizations", language="en")
        
        # Upload file
        upload_result = await client.upload_files([sample_file])
        print(f"Upload result: {upload_result}")
        
        # Monitor progress
        await client.monitor_progress()
        
    except Exception as e:
        print(f"Error: {e}")


def check_server_health():
    """Check if the server is running"""
    try:
        response = requests.get("http://localhost:8001/health")
        if response.status_code == 200:
            health_data = response.json()
            print(f"🟢 Server is healthy!")
            print(f"   Queue size: {health_data.get('queue_size', 0)}")
            print(f"   Currently processing: {health_data.get('is_processing', False)}")
            if health_data.get('current_session'):
                print(f"   Current session: {health_data.get('current_session')}")
            return True
        else:
            print(f"🔴 Server health check failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"🔴 Cannot connect to server: {e}")
        print("💡 Make sure to start the server first:")
        print("   python agent_fastapi_server.py --port 8001")
        return False


async def main():
    """Main example runner"""
    print("🚀 Agent FastAPI Client Examples")
    print("=" * 50)
    
    # Check server health first
    if not check_server_health():
        return
    
    print("\nChoose an example to run:")
    print("1. Single user interaction")
    print("2. Multiple users with queue")
    print("3. File upload example")
    print("4. All examples")
    
    try:
        choice = input("Enter choice (1-4): ").strip()
        
        if choice == "1":
            await example_single_user()
        elif choice == "2":
            await example_multiple_users()
        elif choice == "3":
            await example_with_file_upload()
        elif choice == "4":
            await example_single_user()
            print("\n" + "="*50 + "\n")
            await example_multiple_users()
            print("\n" + "="*50 + "\n")
            await example_with_file_upload()
        else:
            print("Invalid choice")
    
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")


if __name__ == "__main__":
    asyncio.run(main())
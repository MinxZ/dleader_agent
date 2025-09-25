"""
Enhanced Multi-Turn Handler with File Persistence

This module provides enhanced functionality for handling multi-turn conversations
with proper file persistence across turns, including S3/MongoDB integration.
"""

import os
import json
import logging
import shutil
from typing import Dict, List, Optional, Any
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

class EnhancedMultiTurnHandler:
    """
    Handles multi-turn conversation context building with file persistence
    """

    def __init__(self, cloud_storage_manager=None):
        self.cloud_storage_manager = cloud_storage_manager
        self.session_files_cache = {}  # Cache for tracking files across turns

    def build_enhanced_context(self,
                              multiturn_session,
                              current_message: str,
                              uploaded_files: List[str] = None,
                              include_file_list: bool = True) -> Dict[str, Any]:
        """
        Build enhanced context for multi-turn conversations including:
        - Previous turn prompts and responses
        - List of all files available from previous turns
        - Current turn message and files

        Args:
            multiturn_session: MultiTurnSession object
            current_message: Current user message
            uploaded_files: Files uploaded in current turn
            include_file_list: Whether to include detailed file list

        Returns:
            Dict containing enhanced context and message
        """

        # Build comprehensive context from all previous turns
        context_parts = []
        all_available_files = {}

        # Process each previous turn
        for turn in multiturn_session.turns:
            if turn.status == "completed":
                # Add turn prompt
                context_parts.append(f"=== Turn {turn.turn_number} ===")
                context_parts.append(f"User Query: {turn.query}")

                # Add turn response/report
                if turn.final_report:
                    context_parts.append(f"Assistant Response:\n{turn.final_report[:500]}...")  # Truncate long reports

                # Track files from this turn
                if turn.files:
                    for file_name, file_info in turn.files.items():
                        all_available_files[file_name] = {
                            'turn': turn.turn_number,
                            'path': file_info if isinstance(file_info, str) else file_info.get('path'),
                            'type': self._get_file_type(file_name)
                        }

        # Add current turn files
        if uploaded_files:
            for file_path in uploaded_files:
                file_name = os.path.basename(file_path)
                all_available_files[file_name] = {
                    'turn': multiturn_session.total_turns + 1,
                    'path': file_path,
                    'type': self._get_file_type(file_name)
                }

        # Build the enhanced message
        enhanced_message_parts = []

        # Add previous conversation context
        if context_parts:
            enhanced_message_parts.append("=== Previous Conversation Context ===")
            enhanced_message_parts.extend(context_parts[-6:])  # Include last 3 turns max to avoid token limits
            enhanced_message_parts.append("")

        # Add file availability information
        if include_file_list and all_available_files:
            enhanced_message_parts.append("=== Available Files from All Turns ===")
            for file_name, file_info in all_available_files.items():
                enhanced_message_parts.append(
                    f"- {file_name} (Turn {file_info['turn']}, Type: {file_info['type']})"
                )
            enhanced_message_parts.append("")

        # Add current request
        enhanced_message_parts.append("=== Current Request ===")
        enhanced_message_parts.append(current_message)
        enhanced_message_parts.append("")
        enhanced_message_parts.append(
            "Please provide a response that builds upon the previous analysis, "
            "uses the available files as needed, and addresses the current question."
        )

        enhanced_message = "\n".join(enhanced_message_parts)

        return {
            'enhanced_message': enhanced_message,
            'all_files': all_available_files,
            'context_summary': {
                'total_turns': multiturn_session.total_turns,
                'total_files': len(all_available_files),
                'file_types': self._categorize_files(all_available_files)
            }
        }

    async def ensure_files_available(self,
                                    session_id: str,
                                    required_files: Dict[str, Dict],
                                    session_path: str) -> Dict[str, str]:
        """
        Ensure all required files are available locally, downloading from S3 if needed

        Args:
            session_id: Session identifier
            required_files: Dict of files needed with their metadata
            session_path: Local session directory path

        Returns:
            Dict mapping file names to local paths
        """

        local_files = {}
        os.makedirs(session_path, exist_ok=True)

        for file_name, file_info in required_files.items():
            local_path = file_info.get('path')

            # Check if file exists locally
            if local_path and os.path.exists(local_path):
                local_files[file_name] = local_path
                logger.info(f"File {file_name} found locally at {local_path}")
            else:
                # Try to download from S3
                if self.cloud_storage_manager:
                    downloaded_path = await self._download_file_from_s3(
                        session_id, file_name, session_path, file_info
                    )
                    if downloaded_path:
                        local_files[file_name] = downloaded_path
                        logger.info(f"File {file_name} downloaded from S3 to {downloaded_path}")
                    else:
                        logger.warning(f"File {file_name} not found locally or in S3")
                else:
                    logger.warning(f"File {file_name} not found locally and cloud storage not configured")

        return local_files

    async def _download_file_from_s3(self,
                                    session_id: str,
                                    file_name: str,
                                    session_path: str,
                                    file_info: Dict) -> Optional[str]:
        """
        Download a file from S3 to local storage

        Args:
            session_id: Session identifier
            file_name: Name of file to download
            session_path: Local directory to save file
            file_info: File metadata including S3 info

        Returns:
            Local path to downloaded file or None if failed
        """

        try:
            # Retrieve session from cloud to get S3 keys
            session_data = await self.cloud_storage_manager.retrieve_session_from_cloud(session_id)

            if not session_data:
                logger.warning(f"Session {session_id} not found in cloud storage")
                return None

            # Find the S3 key for this file
            s3_files = session_data.get('s3_files', {})
            s3_key = None

            # Search through different file categories
            for category, files in s3_files.items():
                if isinstance(files, list):
                    for f in files:
                        if f.get('filename') == file_name:
                            s3_key = f.get('s3_key')
                            break
                elif isinstance(files, dict) and files.get('filename') == file_name:
                    s3_key = files.get('s3_key')
                    break

            if not s3_key:
                logger.warning(f"S3 key not found for file {file_name}")
                return None

            # Download file from S3
            local_file_path = os.path.join(session_path, file_name)

            self.cloud_storage_manager.s3_client.download_file(
                self.cloud_storage_manager.bucket_name,
                s3_key,
                local_file_path
            )

            logger.info(f"Successfully downloaded {file_name} from S3")
            return local_file_path

        except Exception as e:
            logger.error(f"Error downloading file {file_name} from S3: {e}")
            return None

    def _get_file_type(self, file_name: str) -> str:
        """Determine file type from extension"""
        ext = Path(file_name).suffix.lower()

        type_map = {
            '.csv': 'data',
            '.xlsx': 'data',
            '.xls': 'data',
            '.tsv': 'data',
            '.json': 'data',
            '.png': 'image',
            '.jpg': 'image',
            '.jpeg': 'image',
            '.gif': 'image',
            '.bmp': 'image',
            '.svg': 'image',
            '.pdf': 'document',
            '.txt': 'text',
            '.md': 'text',
            '.py': 'code',
            '.ipynb': 'notebook'
        }

        return type_map.get(ext, 'other')

    def _categorize_files(self, files: Dict) -> Dict[str, int]:
        """Categorize files by type and return counts"""
        categories = {}
        for file_name, file_info in files.items():
            file_type = file_info.get('type', 'other')
            categories[file_type] = categories.get(file_type, 0) + 1
        return categories

    def update_turn_with_files(self, turn: 'ConversationTurn', session_path: str):
        """
        Update a conversation turn with information about generated files

        Args:
            turn: ConversationTurn object to update
            session_path: Path to session directory
        """

        if not os.path.exists(session_path):
            return

        # Scan for new files generated during this turn
        generated_files = {}

        for file_path in Path(session_path).glob("*"):
            if file_path.is_file():
                file_name = file_path.name
                # Check if this is a new file (not in turn.files yet)
                if not turn.files or file_name not in turn.files:
                    generated_files[file_name] = {
                        'path': str(file_path),
                        'type': self._get_file_type(file_name),
                        'size': file_path.stat().st_size,
                        'created': datetime.fromtimestamp(file_path.stat().st_ctime).isoformat()
                    }

        # Update turn files
        if generated_files:
            if not turn.files:
                turn.files = {}
            turn.files.update(generated_files)
            logger.info(f"Added {len(generated_files)} generated files to turn {turn.turn_number}")


class MultiTurnContextBuilder:
    """
    Alternative simplified context builder for backward compatibility
    """

    @staticmethod
    def build_context_with_files(multiturn_session, current_message: str) -> str:
        """
        Build a simple context string with file information

        Args:
            multiturn_session: MultiTurnSession object
            current_message: Current user message

        Returns:
            Enhanced message string
        """

        context_parts = []

        # Add summary of previous turns
        if multiturn_session.turns:
            context_parts.append("=== Conversation History ===")
            for turn in multiturn_session.turns[-3:]:  # Last 3 turns
                context_parts.append(f"\nTurn {turn.turn_number}:")
                context_parts.append(f"User: {turn.query[:200]}...")
                if turn.final_report:
                    context_parts.append(f"Assistant: {turn.final_report[:200]}...")
                if turn.files:
                    context_parts.append(f"Files: {', '.join(turn.files.keys())}")

        # Add current message
        context_parts.append(f"\n=== Current Request (Turn {multiturn_session.total_turns + 1}) ===")
        context_parts.append(current_message)

        return "\n".join(context_parts)


# Export main components
__all__ = ['EnhancedMultiTurnHandler', 'MultiTurnContextBuilder']
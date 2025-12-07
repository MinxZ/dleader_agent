#!/usr/bin/env python3
"""
Automated endpoint extraction script for Phase 4.

This script extracts all 25 endpoints from agent_fastapi_server_multiturn.py
and places them in the appropriate route files.
"""

import re
import sys


def find_function_end(lines, start_line):
    """
    Find the end of a function starting at start_line.
    Returns the line number where the function ends.
    """
    # Start from the line with 'def' or 'async def'
    indent_level = len(lines[start_line]) - len(lines[start_line].lstrip())

    # Find the first line after start that has same or less indentation (and is not empty/comment)
    for i in range(start_line + 1, len(lines)):
        line = lines[i]

        # Skip empty lines and comments
        if line.strip() == '' or line.strip().startswith('#'):
            continue

        # Check indentation
        current_indent = len(line) - len(line.lstrip())

        # If we find a decorator or function at same level or less, we found the end
        if current_indent <= indent_level and (line.strip().startswith('@') or
                                                line.strip().startswith('def ') or
                                                line.strip().startswith('async def ')):
            return i - 1

    # If we reach here, function goes to end of file
    return len(lines) - 1


def extract_endpoint(lines, start_line, endpoint_name):
    """
    Extract an endpoint starting at start_line (the @app decorator line).
    Returns a tuple of (extracted_lines, end_line).
    """
    # Start from the decorator line
    extracted = []

    # Find where the function definition starts
    func_start = start_line
    while func_start < len(lines) and not ('def ' in lines[func_start] or 'async def' in lines[func_start]):
        extracted.append(lines[func_start])
        func_start += 1

    # Find function end
    func_end = find_function_end(lines, func_start)

    # Extract the function
    extracted.extend(lines[func_start:func_end + 1])

    return extracted, func_end


def create_route_file_content(route_name, endpoints_code, imports):
    """
    Create the complete content for a route file.
    """
    content = f'''"""
{route_name.capitalize()} route handlers for dleader_agent API.
"""

from typing import List, Optional

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

{imports}

router = APIRouter(tags=["{route_name}"])


{endpoints_code}
'''
    return content


def main():
    print("="*80)
    print("Phase 4: Automated Endpoint Extraction")
    print("="*80)
    print()

    # Read the source file
    print("Reading source file...")
    with open('agent_fastapi_server_multiturn.py', 'r') as f:
        lines = f.readlines()

    print(f"✓ Loaded {len(lines)} lines")
    print()

    # Define all endpoints with their line numbers and target route files
    endpoints_map = {
        'chat': [
            (2623, 'start_chat_queue', '/chat-queue'),
            (3880, 'continue_session', '/continue-session'),
        ],
        'sessions': [
            (2766, 'get_progress', '/progress/{session_id}'),
            (2771, 'get_status', '/status/{session_id}'),
            (3307, 'get_session_results', '/results/{session_id}'),
            (3567, 'stop_task', '/stop/{session_id}'),
            (3597, 'get_session_snapshots', '/snapshots/{session_id}'),
            (3837, 'get_all_sessions', '/all-sessions'),
        ],
        'multiturn': [
            (4111, 'get_multiturn_session', '/multiturn-session/{session_id}'),
            (4204, 'get_all_multiturn_sessions', '/multiturn-sessions'),
            (4286, 'get_turn_report', '/turn-report/{session_id}/{turn_number}'),
            (4313, 'get_session_context', '/session-context/{session_id}'),
            (4470, 'rename_multisession', '/rename-multisession'),
        ],
        'files': [
            (2888, 'download_session_zip', '/download/{session_id}'),
            (2976, 'download_individual_file', '/download-file/{session_id}/{filename:path}'),
            (4935, 'get_download_urls', '/download-urls/{session_id}'),
        ],
        'sharing': [
            (4332, 'share_session', '/share-session'),
            (4392, 'unshare_session', '/unshare-session'),
            (4429, 'get_shared_sessions', '/shared-sessions'),
        ],
        'templates': [
            (4542, 'upload_template', '/upload-template'),
            (4600, 'get_templates', '/templates'),
        ],
        'users': [
            (4659, 'get_user_name', '/user/{user_id}/name'),
            (4718, 'update_user_name', '/user/{user_id}/name'),
        ],
        'admin': [
            (4645, 'health_check', '/health'),
            (4791, 'hard_delete_session', '/hard-delete/{session_id}'),
        ],
    }

    # Common imports for all route files
    common_imports = """from api import queue_manager
from api.models import (
    ConversationTurn,
    Language,
    MultiTurnSession,
    RenameMultiSessionRequest,
    ShareSessionRequest,
    Template,
    TemplateListRequest,
    TemplateResponse,
)
from api.utils import (
    create_session_zip,
    generate_file_urls,
    get_template_retriever,
)
from cloud_storage_manager import cloud_storage_manager
from unified_session_manager import UnifiedSessionManager"""

    # Extract endpoints for each route file
    for route_name, endpoints in endpoints_map.items():
        print(f"Processing {route_name}.py ({len(endpoints)} endpoints)...")

        all_endpoint_code = []

        for line_num, func_name, path in endpoints:
            # Line numbers in the map are 1-indexed, convert to 0-indexed
            start_idx = line_num - 1

            # Find the @app decorator
            while start_idx > 0 and not lines[start_idx].strip().startswith('@app.'):
                start_idx -= 1

            # Extract the endpoint
            endpoint_lines, end_idx = extract_endpoint(lines, start_idx, func_name)

            # Replace @app with @router
            for i, line in enumerate(endpoint_lines):
                if '@app.' in line:
                    endpoint_lines[i] = line.replace('@app.', '@router.')

            all_endpoint_code.extend(endpoint_lines)
            all_endpoint_code.append('\n\n')

            print(f"  ✓ Extracted {func_name} ({path})")

        # Create the route file content
        endpoints_code = ''.join(all_endpoint_code)
        route_content = create_route_file_content(route_name, endpoints_code, common_imports)

        # Write to file
        route_file = f'api/routes/{route_name}.py'
        with open(route_file, 'w') as f:
            f.write(route_content)

        print(f"✓ Created {route_file}")
        print()

    print("="*80)
    print("Extraction Complete!")
    print("="*80)
    print()
    print(f"✓ Extracted 25 endpoints across 8 route files")
    print()
    print("Next: Verify compilation...")


if __name__ == "__main__":
    main()

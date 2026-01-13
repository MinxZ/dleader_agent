#!/usr/bin/env python3
"""
Download all templates from the API and save to local directory.

Usage:
    python download_templates.py [--output-dir OUTPUT_DIR] [--api-url API_URL] [--user-id USER_ID]

Examples:
    python download_templates.py
    python download_templates.py --output-dir ../template-prompt
    python download_templates.py --api-url http://localhost:8001 --user-id DLeader
"""

import argparse
import json
import os
import re
from datetime import datetime
from pathlib import Path

import requests


def sanitize_filename(name: str) -> str:
    """Convert template title to a safe filename."""
    # Replace spaces and special chars with underscores
    name = re.sub(r'[^\w\s-]', '', name)
    name = re.sub(r'[\s]+', '_', name)
    return name.lower()


def download_templates(
    api_url: str = "http://localhost:8001",
    user_id: str = "DLeader",
    output_dir: str = "../template-prompt"
) -> dict:
    """
    Download all templates from the API and save to local directory.

    Args:
        api_url: Base URL of the API server
        user_id: User ID for authentication
        output_dir: Directory to save templates

    Returns:
        dict with download results
    """
    # Resolve output directory
    output_path = Path(output_dir).resolve()
    output_path.mkdir(parents=True, exist_ok=True)

    print(f"Downloading templates from {api_url}")
    print(f"Output directory: {output_path}")
    print()

    # Fetch templates from API
    try:
        response = requests.get(
            f"{api_url}/templates",
            params={"user_id": user_id},
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as e:
        print(f"Error fetching templates: {e}")
        return {"success": False, "error": str(e)}

    templates = data.get("templates", [])
    print(f"Found {len(templates)} templates")
    print()

    results = {
        "success": True,
        "downloaded": [],
        "failed": [],
        "total": len(templates),
        "timestamp": datetime.now().isoformat()
    }

    # Save each template
    for i, template in enumerate(templates, 1):
        title = template.get("title", f"template_{i}")
        session_id = template.get("session_id", "unknown")

        # Create filename from title
        filename = f"{sanitize_filename(title)}.json"
        filepath = output_path / filename

        try:
            # Save template as JSON
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(template, f, indent=2, ensure_ascii=False)

            print(f"  [{i}/{len(templates)}] Saved: {filename}")
            print(f"           Title: {title}")
            print(f"           Session ID: {session_id}")
            print(f"           Prompt length: {len(template.get('prompt', ''))} chars")

            results["downloaded"].append({
                "title": title,
                "filename": filename,
                "session_id": session_id
            })
        except Exception as e:
            print(f"  [{i}/{len(templates)}] FAILED: {title} - {e}")
            results["failed"].append({
                "title": title,
                "error": str(e)
            })

        print()

    # Save summary file
    summary_path = output_path / "_summary.json"
    summary = {
        "downloaded_at": results["timestamp"],
        "api_url": api_url,
        "user_id": user_id,
        "total_templates": len(templates),
        "templates": [
            {
                "title": t.get("title"),
                "filename": f"{sanitize_filename(t.get('title', f'template_{i}'))}.json",
                "session_id": t.get("session_id"),
                "description": t.get("description", "")[:100],
                "tools": t.get("tools", [])
            }
            for i, t in enumerate(templates, 1)
        ]
    }

    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print(f"Summary saved to: {summary_path}")
    print()
    print(f"Download complete: {len(results['downloaded'])} succeeded, {len(results['failed'])} failed")

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Download all templates from the API and save to local directory"
    )
    parser.add_argument(
        "--output-dir", "-o",
        default="../template-prompt",
        help="Output directory for templates (default: ../template-prompt)"
    )
    parser.add_argument(
        "--api-url", "-u",
        default="http://localhost:8001",
        help="API server URL (default: http://localhost:8001)"
    )
    parser.add_argument(
        "--user-id", "-i",
        default="DLeader",
        help="User ID for authentication (default: DLeader)"
    )

    args = parser.parse_args()

    results = download_templates(
        api_url=args.api_url,
        user_id=args.user_id,
        output_dir=args.output_dir
    )

    # Exit with error code if any failures
    if not results["success"] or results.get("failed"):
        exit(1)


if __name__ == "__main__":
    main()

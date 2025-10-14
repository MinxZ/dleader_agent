"""
Template Retriever for matching user queries to workflow templates.

This module provides functionality to:
1. Fetch template descriptions from MongoDB (cloud storage)
2. Use LLM-based matching to select the most relevant template(s)
3. Augment user queries with template prompts
"""

import json
import os
from typing import Any, Dict, List, Optional

from dleader_agent.llm import get_llm


class TemplateRetriever:
    """Retrieve and match workflow templates to user queries."""

    def __init__(self, llm=None):
        """Initialize the template retriever.

        Args:
            llm: Optional LLM instance to use for matching. If None, will create a new one.
        """
        self.llm = llm
        self.templates_cache = None
        self.cache_timestamp = None
        self.cache_ttl = 300  # Cache templates for 5 minutes

    def fetch_templates_from_mongodb(self) -> List[Dict[str, Any]]:
        """Fetch all templates from MongoDB cloud storage.

        This method prioritizes MongoDB (cloud) as the primary source.
        Local file is only used as an emergency fallback.

        Returns:
            List of template dictionaries with fields: title, description, prompt, etc.
        """
        templates = []

        # PRIMARY SOURCE: MongoDB (Cloud Storage)
        # This is the correct and recommended source for production
        try:
            import sys

            # Add s3_mongodb directory to path if not already there
            s3_mongodb_path = os.path.join(os.getcwd(), 's3_mongodb')
            if s3_mongodb_path not in sys.path:
                sys.path.insert(0, s3_mongodb_path)

            from func_mongodb import get_mongodb_collection

            # Get templates collection from MongoDB
            database_name = os.getenv("SESSION_DB_NAME", "dleader_agent")
            collection = get_mongodb_collection(database_name, "workflow_templates")

            if collection is not None:
                templates = list(collection.find({}).sort("title", 1))
                # Remove MongoDB internal fields
                for template in templates:
                    if "_id" in template:
                        template.pop("_id", None)
                    if "uploaded_at" in template:
                        template.pop("uploaded_at", None)

                print(f"✓ Fetched {len(templates)} templates from MongoDB (cloud)")
                return templates
            else:
                print("✗ MongoDB collection is None - connection may have failed")

        except ImportError as e:
            print(f"✗ MongoDB module import failed: {e}")
            print(f"   Make sure s3_mongodb module is available")
        except Exception as e:
            print(f"✗ Error accessing MongoDB: {e}")

        # FALLBACK: Local file (only for development/testing)
        # WARNING: This should NOT be used in production!
        print("⚠️  WARNING: Could not load templates from MongoDB cloud storage")
        print("   Falling back to local file - NOT recommended for production!")

        try:
            templates_file = os.path.join(os.getcwd(), "templates", "workflow_templates.json")
            if os.path.exists(templates_file):
                with open(templates_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    templates = data.get("templates", [])
                    print(f"  → Loaded {len(templates)} templates from local fallback file")
                    return templates
            else:
                print(f"  → Local template file not found: {templates_file}")
        except Exception as e:
            print(f"✗ Error reading local template file: {e}")

        print("✗ CRITICAL: No templates available from any source!")
        print("   Please ensure MongoDB is properly configured or local template file exists")
        return []

    def get_templates(self) -> List[Dict[str, Any]]:
        """Get templates with caching.

        Returns:
            List of template dictionaries.
        """
        import time

        # Check if cache is valid
        if self.templates_cache is not None and self.cache_timestamp is not None:
            if time.time() - self.cache_timestamp < self.cache_ttl:
                return self.templates_cache

        # Fetch fresh templates
        templates = self.fetch_templates_from_mongodb()
        self.templates_cache = templates
        self.cache_timestamp = time.time()

        return templates

    def match_template(self, query: str, templates: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """Match a user query to the most relevant template using LLM.

        Args:
            query: User's query string
            templates: Optional list of templates. If None, will fetch from MongoDB.

        Returns:
            Dictionary with:
            - matched: bool (whether a template was matched)
            - template: dict or None (the matched template)
            - confidence: str (high/medium/low/none)
            - reasoning: str (explanation of the match)
            - modification: str or None (suggested modification to template prompt)
        """
        if templates is None:
            templates = self.get_templates()

        if not templates:
            return {
                "matched": False,
                "template": None,
                "confidence": "none",
                "reasoning": "No templates available",
                "modification": None
            }

        # Create LLM if not provided
        llm = self.llm
        if llm is None:
            try:
                llm = get_llm("claude-sonnet-4-5-20250929")
            except:
                # Fallback to a simple matching if LLM not available
                return self._simple_keyword_match(query, templates)

        # Format templates for LLM
        templates_text = self._format_templates_for_prompt(templates)

        # Create matching prompt
        prompt = f"""You are an expert at matching user queries to workflow templates in biomedical research.

USER QUERY: {query}

AVAILABLE WORKFLOW TEMPLATES:
{templates_text}

Your task is to determine if any of these templates are relevant to the user's query.

Analyze the user's intent and determine:
1. Is there a template that matches this query? (Consider both exact matches and partial matches)
2. If yes, which template is the best match?
3. How confident are you in this match? (high/medium/low)
4. Should the template prompt be used as-is, or should it be modified for this specific query?

Respond in the following JSON format:
{{
    "matched": true or false,
    "template_index": <index of matched template, or null if no match>,
    "confidence": "high" or "medium" or "low" or "none",
    "reasoning": "<brief explanation of why this template matches or doesn't match>",
    "modification": "<if the template should be modified, describe how; otherwise null>",
    "use_prompt": true or false (whether to use the full template prompt)
}}

Examples of when to match:
- User asks to "merge datasets" → matches "Data Merge" template (high confidence)
- User asks to "combine two CSV files" → matches "Data Merge" template (high confidence, modification: "focus on CSV only")
- User asks about "QSPR analysis for drug properties" → matches "QSPR Workflow" (high confidence)
- User asks to "analyze molecular properties" → matches "QSPR Workflow" (medium confidence, modification: "focus on the specific properties mentioned")
- User asks to "design ASO for target gene" → matches "ASO Design" (high confidence)

Examples of when NOT to match:
- User asks "what is QSPR?" → no match (informational query, not a workflow request)
- User asks "how do I install RDKit?" → no match (technical support, not a workflow)
- User's query is too vague: "help me analyze data" → no match (need more specificity)

Be generous in matching - if the query is clearly requesting a workflow similar to a template, match it even if not exactly the same.

Respond ONLY with valid JSON, no other text."""

        try:
            response = llm.invoke(prompt)
            response_text = response.content if hasattr(response, 'content') else str(response)

            # Extract JSON from response
            import re
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())

                # Add the actual template object if matched
                if result.get("matched") and result.get("template_index") is not None:
                    idx = result["template_index"]
                    if 0 <= idx < len(templates):
                        result["template"] = templates[idx]
                    else:
                        result["matched"] = False
                        result["template"] = None
                else:
                    result["template"] = None

                return result
            else:
                print(f"Could not extract JSON from LLM response: {response_text}")
                return self._simple_keyword_match(query, templates)

        except Exception as e:
            print(f"Error matching template with LLM: {e}")
            return self._simple_keyword_match(query, templates)

    def _format_templates_for_prompt(self, templates: List[Dict[str, Any]]) -> str:
        """Format templates for LLM prompt.

        Args:
            templates: List of template dictionaries

        Returns:
            Formatted string of templates
        """
        formatted = []
        for idx, template in enumerate(templates):
            title = template.get("title", "Unknown")
            description = template.get("description", "No description")
            running_time = template.get("running_time", "Unknown")
            tools = template.get("tools", "Unknown")
            has_prompt = "Yes" if template.get("prompt") else "No"

            formatted.append(f"""[{idx}] {title}
   Description: {description}
   Running Time: {running_time}
   Tools Used: {tools}
   Has Detailed Prompt: {has_prompt}""")

        return "\n\n".join(formatted)

    def _simple_keyword_match(self, query: str, templates: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Simple keyword-based matching fallback.

        Args:
            query: User's query
            templates: List of templates

        Returns:
            Match result dictionary
        """
        query_lower = query.lower()
        best_match = None
        best_score = 0

        for template in templates:
            title = template.get("title", "").lower()
            description = template.get("description", "").lower()

            # Simple keyword matching
            score = 0
            words = query_lower.split()
            for word in words:
                if len(word) > 3:  # Only consider words longer than 3 chars
                    if word in title:
                        score += 3
                    if word in description:
                        score += 1

            if score > best_score:
                best_score = score
                best_match = template

        if best_score > 3:
            return {
                "matched": True,
                "template": best_match,
                "confidence": "medium",
                "reasoning": f"Keyword matching (score: {best_score})",
                "modification": None,
                "use_prompt": True
            }

        return {
            "matched": False,
            "template": None,
            "confidence": "none",
            "reasoning": "No keyword matches found",
            "modification": None,
            "use_prompt": False
        }

    def augment_query_with_template(
        self,
        query: str,
        match_result: Optional[Dict[str, Any]] = None
    ) -> Dict[str, str]:
        """Augment user query with template prompt if matched.

        Args:
            query: Original user query
            match_result: Optional pre-computed match result. If None, will compute.

        Returns:
            Dictionary with:
            - original_query: str (original query)
            - augmented_query: str (query with template prompt appended)
            - template_used: str or None (template title if used)
            - modification_applied: str or None (description of modification)
        """
        if match_result is None:
            match_result = self.match_template(query)

        if not match_result.get("matched") or not match_result.get("use_prompt", True):
            return {
                "original_query": query,
                "augmented_query": query,
                "template_used": None,
                "modification_applied": None
            }

        template = match_result.get("template")
        if not template or not template.get("prompt"):
            return {
                "original_query": query,
                "augmented_query": query,
                "template_used": template.get("title") if template else None,
                "modification_applied": None
            }

        template_prompt = template.get("prompt", "")
        template_title = template.get("title", "Unknown Template")
        modification = match_result.get("modification")

        # Build augmented query
        augmented = f"""{query}

[WORKFLOW TEMPLATE REFERENCE: {template_title}]
{template_prompt}"""

        # Add modification note if applicable
        if modification:
            augmented += f"""

[TEMPLATE MODIFICATION NOTE]
{modification}"""

        return {
            "original_query": query,
            "augmented_query": augmented,
            "template_used": template_title,
            "modification_applied": modification
        }

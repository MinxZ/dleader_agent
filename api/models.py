"""
Pydantic models and data structures for FastAPI server
"""

from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import queue

from pydantic import BaseModel

# Language and timezone configurations
JST = timezone(timedelta(hours=9))


class Language(str, Enum):
    """Supported languages"""
    EN = "en"
    JP = "jp"


class TurnType(str, Enum):
    """Types of conversation turns"""
    PLANNING = "planning"  # Clarification/planning phase - no tool execution
    EXECUTION = "execution"  # Full agent execution with tools


def now_jst():
    """Get current time in JST (UTC+9)"""
    return datetime.now(JST)


# Request/Response Models
class ChatRequest(BaseModel):
    """Chat request model"""
    message: str
    language: Language = Language.EN
    session_id: Optional[str] = None
    user_id: Optional[str] = None


class ChatResponse(BaseModel):
    """Chat response model"""
    session_id: str
    status: str
    thinking_content: Optional[str] = None
    final_report: Optional[str] = None
    progress_updates: List[Dict[str, Any]] = []
    session_path: Optional[str] = None
    error: Optional[str] = None


class QueueStatus(BaseModel):
    """Queue status model"""
    position: int
    estimated_wait_time: int  # in seconds
    total_users_in_queue: int


class SessionInfo(BaseModel):
    """Session information model"""
    session_id: str
    status: str
    created_at: str
    language: Language
    query: str


# Multi-Turn Data Structures
class ConversationTurn(BaseModel):
    """Represents a single turn in a multi-turn conversation"""
    turn_number: int
    turn_type: str = "execution"  # "planning" or "execution" (TurnType enum)
    query: str
    response_content: Optional[str] = None
    final_report: Optional[str] = None
    files: Optional[Dict[str, Any]] = None
    timestamp: str
    status: str = "processing"
    ready_for_execution: Optional[bool] = None  # Only relevant for planning turns


class MultiTurnSession(BaseModel):
    """Multi-turn conversation session"""
    session_id: str
    session_name: str = ""
    created_at: str
    last_updated: str
    language: Language
    user_id: Optional[str] = None
    total_turns: int = 0
    current_turn: int = 0
    turns: List[ConversationTurn] = []
    accumulated_context: str = ""
    session_status: str = "active"  # active, completed, error

    # Sharing metadata
    is_shared: bool = False
    shared_at: Optional[str] = None

    @property
    def first_query(self) -> str:
        """Get the first query from the turns"""
        return self.turns[0].query if self.turns else ""

    @property
    def latest_query(self) -> str:
        """Get the latest query from the turns"""
        return self.turns[-1].query if self.turns else ""


class ContinueRequest(BaseModel):
    """Request to continue a multi-turn session"""
    session_id: str
    message: str
    language: Language = Language.EN
    user_id: Optional[str] = None


class RenameMultiSessionRequest(BaseModel):
    """Request to rename a multi-turn session"""
    session_id: str
    new_name: str
    user_id: str


# Template Models
class Template(BaseModel):
    """Template model for workflow templates"""
    title: str
    running_time: str
    tools: int
    description: str
    prompt: Optional[str] = None


class TemplateListRequest(BaseModel):
    """Request with list of templates"""
    templates: List[Template]


class TemplateResponse(BaseModel):
    """Response for template operations"""
    success: bool
    message: str
    total_templates: Optional[int] = None


# Sharing Models
class ShareSessionRequest(BaseModel):
    """Request to share a session"""
    session_id: str
    user_id: Optional[str] = None


class SharedSessionInfo(BaseModel):
    """Information about a shared session"""
    session_id: str
    title: str
    description: Optional[str] = None
    tags: List[str]
    visibility: str
    shared_by: str
    shared_at: str
    total_turns: int
    language: str
    first_query: str
    last_query: str


# Queue Management System
class UserRequest:
    """Represents a user request in the queue system"""

    def __init__(self, session_id: str, message: str, language: Language, uploaded_files: List[str] = None,
                 is_continuation: bool = False, previous_context: str = "", turn_number: int = 1, user_id: str = None,
                 turn_type: str = "execution"):
        self.session_id = session_id
        self.message = message
        self.language = language
        self.uploaded_files = uploaded_files or []
        self.created_at = datetime.now()
        self.status = "queued"
        self.progress_queue = queue.Queue()
        self.result = None
        self.error = None
        self.is_complete = False
        self.is_cancelled = False
        self.agent_thread = None
        self.agent_process = None
        self.process_queue = None
        self.json_result = None
        self.periodic_snapshots = []
        self.last_snapshot_time = None
        self.session_path = None
        self.all_progress_updates = []
        self.user_id = user_id
        self.task_start_time = None
        self.stop_requested = False

        # Multi-turn specific attributes
        self.is_continuation = is_continuation
        self.previous_context = previous_context
        self.turn_number = turn_number
        self.turn_type = turn_type  # "planning" or "execution"
        self.enhanced_message = self._build_enhanced_message()

        # Planning mode specific attributes
        self.ready_for_execution = None  # Set after planning turn completes
        self.agent_config = None  # Custom agent config for planning mode

        # Template matching attributes
        self.template_matched = False
        self.template_title = None
        self.template_confidence = None
        self.template_reasoning = None
        self.template_modification = None
        self.augmented_query = None

    def _build_enhanced_message(self):
        """Build enhanced message with previous context for multi-turn conversations"""
        if self.is_continuation and self.previous_context:
            return f"""Previous conversation context:
{self.previous_context}

Current question/request:
{self.message}

Please provide a response that builds upon the previous analysis and addresses the current question."""
        return self.message

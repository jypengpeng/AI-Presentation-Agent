"""
Streamlit UI for the Autonomous Presentation Agent

Features:
- Apple-style minimal design
- Left panel: Task management and settings
- Right panel: Main input area with streaming dialog
- Multi-task support with persistence
"""

import os
import json
import re
import shutil
import time
import asyncio
import threading
import streamlit as st
import streamlit.components.v1 as components
from pathlib import Path
from dotenv import load_dotenv
from agent_core import Agent, SlideRefiner, ToolCallInfo
from task_manager import TaskManager, Task
from typing import Optional, List, Tuple
from directory_picker import pick_directory, pick_files_or_directory, is_valid_directory, PickResult
from workspace_copier import WorkspaceCopier, ScanResult
from slide_generator import SlideGenerator, get_slide_status_summary, parse_presentation_plan

# Load environment variables from .env file
load_dotenv()


# ============================================================================
# Page Configuration
# ============================================================================

st.set_page_config(
    page_title="AI 生成 PPT",
    page_icon="🎨",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Apple-style Custom CSS - Matching reference design exactly
st.markdown("""
<style>
    /* CSS Variables - Apple Style */
    :root {
        --bg: #f5f6f7;
        --card: #ffffff;
        --text: #0f172a;
        --muted: #6b7280;
        --border: #e5e7eb;
        --accent: #0a84ff;
        --accent-dark: #0f172a;
        --shadow: 0 10px 30px rgba(17,24,39,.08);
        --radius: 16px;
    }
    
    /* Hide Streamlit default elements */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    .stDeployButton {display: none;}
    
    /* Reset and base styles */
    .stApp {
        background-color: var(--bg) !important;
    }
    
    /* Main container - Centered card */
    .main .block-container {
        max-width: 1100px !important;
        padding: 40px !important;
        margin: 40px auto !important;
        background: var(--card) !important;
        border-radius: 20px !important;
        box-shadow: var(--shadow) !important;
    }
    
    /* Hide sidebar completely */
    [data-testid="stSidebar"] {
        display: none !important;
    }
    
    /* Side title styling */
    .side-title {
        font-weight: 700;
        font-size: 12px;
        color: var(--muted);
        margin-bottom: 10px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    
    /* Headline - Large bold title */
    .headline {
        font-size: 40px !important;
        font-weight: 900 !important;
        margin-bottom: 8px !important;
        color: var(--text) !important;
        line-height: 1.2 !important;
        font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", sans-serif !important;
    }
    
    .sub-headline {
        color: #94a3b8 !important;
        margin-bottom: 22px !important;
        font-size: 16px !important;
    }
    
    /* Text area styling */
    .stTextArea textarea {
        border: 1px solid var(--border) !important;
        background: #f8fafc !important;
        border-radius: 12px !important;
        padding: 16px !important;
        font-size: 15px !important;
        min-height: 180px !important;
        resize: vertical !important;
    }
    
    .stTextArea textarea:focus {
        border-color: var(--accent) !important;
        box-shadow: 0 0 0 3px rgba(10, 132, 255, 0.1) !important;
    }
    
    .stTextArea textarea::placeholder {
        color: #9ca3af !important;
    }
    
    /* Text input styling */
    .stTextInput input {
        border: 1px solid var(--border) !important;
        background: #f8fafc !important;
        border-radius: 12px !important;
        padding: 12px !important;
        font-size: 15px !important;
    }
    
    .stTextInput input:focus {
        border-color: var(--accent) !important;
        box-shadow: 0 0 0 3px rgba(10, 132, 255, 0.1) !important;
    }
    
    /* Button styling - Default */
    .stButton > button {
        border: 1px solid var(--border) !important;
        background: var(--card) !important;
        color: var(--text) !important;
        border-radius: 10px !important;
        padding: 8px 16px !important;
        font-weight: 600 !important;
        transition: all 0.2s ease !important;
        font-size: 14px !important;
    }
    
    .stButton > button:hover {
        background: #f3f4f6 !important;
        border-color: #d1d5db !important;
    }
    
    /* Primary button - Generate PPT */
    .stButton > button[kind="primary"],
    .stButton > button[data-testid="baseButton-primary"] {
        background: #cbd5e1 !important;
        color: #fff !important;
        border: none !important;
        border-radius: 14px !important;
        padding: 14px 28px !important;
        font-weight: 700 !important;
        font-size: 16px !important;
        transition: all 0.25s ease !important;
    }
    
    .stButton > button[kind="primary"]:hover,
    .stButton > button[data-testid="baseButton-primary"]:hover {
        background: var(--accent-dark) !important;
        box-shadow: 0 0 0 8px rgba(15,23,42,.12) !important;
        transform: translateY(-1px) !important;
    }
    
    /* Secondary button styling for active task */
    .stButton > button[kind="secondary"][data-testid="baseButton-secondary"] {
        border-radius: 12px !important;
    }
    
    /* Task button - active state (dark background) */
    div[data-testid="column"] .stButton > button[kind="primary"] {
        background: var(--accent-dark) !important;
        color: #fff !important;
        border-radius: 12px !important;
        padding: 10px 14px !important;
        font-size: 14px !important;
    }
    
    /* Chip/Template buttons */
    .chip-button .stButton > button {
        background: #f3f4f6 !important;
        border: none !important;
        border-radius: 999px !important;
        padding: 10px 18px !important;
        color: #475569 !important;
        font-weight: 700 !important;
    }
    
    .chip-button .stButton > button:hover {
        background: #edeff2 !important;
    }
    
    /* Streaming dialog - Fixed position floating box */
    .stream-dialog {
        position: fixed;
        bottom: 24px;
        right: 24px;
        width: 420px;
        max-height: 520px;
        background: var(--card);
        border: 1px solid var(--border);
        border-radius: 16px;
        box-shadow: 0 20px 40px rgba(0,0,0,.15);
        z-index: 9999;
        overflow: hidden;
        display: flex;
        flex-direction: column;
    }
    
    .stream-dialog-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 14px 18px;
        border-bottom: 1px solid var(--border);
        background: #fafbfc;
    }
    
    .stream-dialog-title {
        font-weight: 700;
        font-size: 14px;
        color: var(--text);
    }
    
    .stream-dialog-body {
        padding: 16px 18px;
        overflow-y: auto;
        max-height: 420px;
        flex: 1;
    }
    
    .stream-dialog-close {
        background: none;
        border: none;
        cursor: pointer;
        padding: 4px 8px;
        border-radius: 6px;
        color: var(--muted);
        font-size: 16px;
    }
    
    .stream-dialog-close:hover {
        background: #f3f4f6;
    }
    
    /* Chat message styling - compact for dialog */
    .chat-msg {
        padding: 10px 12px;
        border-radius: 10px;
        margin-bottom: 8px;
        font-size: 13px;
        line-height: 1.5;
    }
    
    .chat-msg.user {
        background: #e3f2fd;
        border-left: 3px solid #2196f3;
    }
    
    .chat-msg.assistant {
        background: #f5f5f5;
        border-left: 3px solid #4caf50;
    }
    
    .chat-msg.tool {
        background: #fff3e0;
        border-left: 3px solid #ff9800;
        font-family: 'SF Mono', Monaco, monospace;
        font-size: 12px;
    }
    
    .chat-msg.error {
        background: #ffebee;
        border-left: 3px solid #f44336;
    }
    
    .chat-msg.success {
        background: #e8f5e9;
        border-left: 3px solid #4caf50;
    }
    
    /* Tool badge */
    .tool-badge {
        display: inline-block;
        background: #ff9800;
        color: white;
        padding: 2px 8px;
        border-radius: 4px;
        font-weight: 600;
        font-size: 11px;
        margin-right: 6px;
    }
    
    /* Footer styling */
    .footer-text {
        display: flex;
        align-items: center;
        justify-content: space-between;
        color: #94a3b8;
        font-size: 13px;
        margin-top: 24px;
        padding-top: 16px;
        border-top: 1px solid var(--border);
    }
    
    .footer-text a {
        color: #64748b;
        text-decoration: none;
    }
    
    .footer-text a:hover {
        text-decoration: underline;
    }
    
    /* Label styling */
    .stTextInput label, .stTextArea label {
        font-size: 13px !important;
        color: var(--muted) !important;
        font-weight: 500 !important;
    }
    
    /* Divider/separator styling */
    hr {
        border: none !important;
        border-top: 1px solid var(--border) !important;
        margin: 16px 0 !important;
    }
    
    /* Caption styling */
    .stCaption {
        color: var(--muted) !important;
    }
    
    /* Column gap adjustment */
    [data-testid="column"] {
        padding: 0 8px !important;
    }
    
    /* Grid view card styling */
    .slide-card {
        background: var(--card);
        border: 1px solid var(--border);
        border-radius: 12px;
        padding: 16px;
        transition: all 0.2s ease;
    }
    
    .slide-card:hover {
        border-color: var(--accent);
        box-shadow: 0 4px 12px rgba(10, 132, 255, 0.15);
    }
    
    .slide-card.completed {
        border-left: 4px solid #4caf50;
    }
    
    .slide-card.generating {
        border-left: 4px solid #2196f3;
        animation: pulse 1.5s infinite;
    }
    
    .slide-card.pending {
        border-left: 4px solid #9e9e9e;
    }
    
    .slide-card.failed {
        border-left: 4px solid #f44336;
    }
    
    @keyframes pulse {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.6; }
    }
    
    /* Markdown styling */
    .stMarkdown p {
        margin-bottom: 0.5rem;
    }
    
    /* Info/Warning/Error boxes */
    .stAlert {
        border-radius: 12px !important;
    }
</style>
""", unsafe_allow_html=True)


# ============================================================================
# Session State Initialization
# ============================================================================

def init_session_state():
    """Initialize session state variables."""
    # API configuration from .env (read-only)
    if "api_key" not in st.session_state:
        st.session_state.api_key = os.environ.get("OPENAI_API_KEY", "")
    
    if "base_url" not in st.session_state:
        st.session_state.base_url = os.environ.get("OPENAI_BASE_URL", "")
    
    if "model" not in st.session_state:
        st.session_state.model = os.environ.get("OPENAI_MODEL", "gpt-4o")
    
    # Task manager
    if "task_manager" not in st.session_state:
        st.session_state.task_manager = TaskManager()
    
    # Agents dictionary (task_id -> Agent)
    if "agents" not in st.session_state:
        st.session_state.agents = {}
    
    # Processing state
    if "is_processing" not in st.session_state:
        st.session_state.is_processing = False
    
    # Preview refresh key
    if "preview_key" not in st.session_state:
        st.session_state.preview_key = 0
    
    # New task dialog state
    if "show_new_task_dialog" not in st.session_state:
        st.session_state.show_new_task_dialog = False
    
    # Edit task name state
    if "editing_task_name" not in st.session_state:
        st.session_state.editing_task_name = False
    
    # Directory/file picker state
    if "pending_source_dir" not in st.session_state:
        st.session_state.pending_source_dir = None
    
    if "pending_pick_result" not in st.session_state:
        st.session_state.pending_pick_result = None  # PickResult object
    
    if "pending_scan_result" not in st.session_state:
        st.session_state.pending_scan_result = None
    
    if "show_size_warning" not in st.session_state:
        st.session_state.show_size_warning = False
    
    if "copy_in_progress" not in st.session_state:
        st.session_state.copy_in_progress = False
    
    # Sync confirmation state
    if "confirm_sync" not in st.session_state:
        st.session_state.confirm_sync = False
    
    # Presentation plan editing state
    if "pending_presentation_plan" not in st.session_state:
        st.session_state.pending_presentation_plan = None
    
    if "show_plan_editor" not in st.session_state:
        st.session_state.show_plan_editor = False
    
    if "plan_editor_error" not in st.session_state:
        st.session_state.plan_editor_error = None
    
    # Slide generation state
    if "slide_generation_in_progress" not in st.session_state:
        st.session_state.slide_generation_in_progress = False
    
    if "slide_generation_stats" not in st.session_state:
        st.session_state.slide_generation_stats = None
    
    # Slide generation concurrency from env (0 = unlimited, default)
    if "slide_concurrency" not in st.session_state:
        st.session_state.slide_concurrency = int(os.environ.get("SLIDE_GENERATION_CONCURRENCY", "0"))
    
    # Slide generation timeout from env
    if "slide_timeout" not in st.session_state:
        st.session_state.slide_timeout = float(os.environ.get("SLIDE_GENERATION_TIMEOUT", "120"))
    
    # Current workflow phase
    if "current_phase" not in st.session_state:
        st.session_state.current_phase = "collecting"  # collecting -> architect -> editing_plan -> designing -> completed
    
    # Grid view state
    if "grid_expanded_slide" not in st.session_state:
        st.session_state.grid_expanded_slide = None  # ID of currently expanded slide
    
    if "last_refresh_time" not in st.session_state:
        st.session_state.last_refresh_time = 0
    
    if "auto_refresh_enabled" not in st.session_state:
        st.session_state.auto_refresh_enabled = True
    
    # Slide modification state
    if "slide_modification_in_progress" not in st.session_state:
        st.session_state.slide_modification_in_progress = False
    
    # Streaming dialog state
    if "show_streaming_dialog" not in st.session_state:
        st.session_state.show_streaming_dialog = False
    
    if "streaming_dialog_content" not in st.session_state:
        st.session_state.streaming_dialog_content = []
    
    if "streaming_current_text" not in st.session_state:
        st.session_state.streaming_current_text = ""
    
    # Template selection state
    if "selected_template" not in st.session_state:
        st.session_state.selected_template = None
    
    # Force main view flag (prevents auto-redirect to grid view)
    if "force_main_view" not in st.session_state:
        st.session_state.force_main_view = False
    
    # Pending generation message (for inline processing)
    if "pending_generation_message" not in st.session_state:
        st.session_state.pending_generation_message = None
    
    # Selected template value (for filling text area)
    if "selected_template_value" not in st.session_state:
        st.session_state.selected_template_value = ""


init_session_state()


# ============================================================================
# Helper Functions
# ============================================================================

def get_current_task() -> Optional[Task]:
    """Get the current active task."""
    return st.session_state.task_manager.get_active_task()


def infer_task_phase(task: Task) -> str:
    """
    Infer the current workflow phase based on task files.
    
    This function examines the task's workspace to determine which phase
    the task is actually in, regardless of what session_state.current_phase says.
    
    Returns one of: "collecting", "editing_plan", "designing"
    """
    if not task:
        return "collecting"
    
    slides_dir = get_slides_dir(task)
    if not slides_dir:
        # No slides directory - still in collecting phase
        return "collecting"
    
    manifest_path = slides_dir / "manifest.json"
    plan_path = slides_dir / "presentation_plan.json"
    
    if not plan_path.exists():
        # No plan yet - collecting phase
        return "collecting"
    
    if plan_path.exists() and not manifest_path.exists():
        # Plan exists but no manifest - show plan editor
        return "editing_plan"
    
    # Both plan and manifest exist - check slide statuses
    try:
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        slides = manifest.get("slides", [])
        
        if not slides:
            return "collecting"
        
        # If manifest has slides, we're in designing phase (grid view)
        return "designing"
    except:
        return "collecting"


def sync_phase_with_task():
    """
    Synchronize session_state.current_phase with the actual task state.
    
    This should be called:
    1. At the start of main() to handle page refreshes
    2. When switching tasks
    3. After certain operations that might change task state
    """
    task = get_current_task()
    if not task:
        st.session_state.current_phase = "collecting"
        return
    
    # Don't override if user explicitly requested main view
    if st.session_state.get("force_main_view"):
        st.session_state.current_phase = "collecting"
        return
    
    # Don't override if we're in a user-initiated editing session
    # (show_plan_editor is True means user is actively editing the plan)
    if st.session_state.get("show_plan_editor") and st.session_state.current_phase == "editing_plan":
        return
    
    # Don't override if slide generation is actively in progress
    if st.session_state.get("slide_generation_in_progress"):
        return
    
    inferred_phase = infer_task_phase(task)
    
    # If we have a plan file but show_plan_editor is not set,
    # and inferred phase is editing_plan, also set show_plan_editor
    if inferred_phase == "editing_plan":
        plan_path = Path(task.workspace_dir) / "slides" / "presentation_plan.json"
        if plan_path.exists():
            try:
                plan_content = plan_path.read_text(encoding='utf-8')
                st.session_state.pending_presentation_plan = plan_content
                st.session_state.show_plan_editor = True
            except:
                pass
    
    st.session_state.current_phase = inferred_phase


def get_html_content() -> Optional[str]:
    """Get the content of the HTML file for preview."""
    task = get_current_task()
    if not task:
        return None
    
    html_path = Path(task.workspace_dir) / task.html_file
    
    if html_path.exists():
        try:
            return html_path.read_text(encoding='utf-8')
        except Exception as e:
            return f"<html><body><p style='color:red'>Error reading file: {e}</p></body></html>"
    
    return None


def get_slides_dir(task: Task) -> Optional[Path]:
    """Get the slides directory for a task."""
    slides_dir = Path(task.workspace_dir) / "slides"
    if slides_dir.exists() and slides_dir.is_dir():
        return slides_dir
    return None


def get_slide_files(task: Task) -> List[Path]:
    """Get list of slide HTML files in order."""
    slides_dir = get_slides_dir(task)
    if not slides_dir:
        return []
    
    manifest_path = slides_dir / "manifest.json"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
            files = []
            for slide in manifest.get("slides", []):
                slide_file = slides_dir / slide.get("file", "")
                if slide_file.exists():
                    files.append(slide_file)
            return files
        except:
            pass
    
    # Fallback: glob for slide_*.html
    return sorted(slides_dir.glob("slide_*.html"))


def get_slide_content(task: Task, slide_index: int) -> Optional[str]:
    """Get content of a specific slide file."""
    files = get_slide_files(task)
    if 0 <= slide_index < len(files):
        try:
            return files[slide_index].read_text(encoding='utf-8')
        except:
            pass
    return None


def create_slide_generator(task: Task) -> Optional[SlideGenerator]:
    """Create a SlideGenerator instance for the task."""
    if not st.session_state.api_key:
        return None
    
    return SlideGenerator(
        api_key=st.session_state.api_key,
        workspace_dir=task.workspace_dir,
        model=st.session_state.model,
        base_url=st.session_state.base_url if st.session_state.base_url else None,
        concurrency=st.session_state.slide_concurrency,
        task_timeout=st.session_state.slide_timeout
    )


def count_slides(html_content: str) -> int:
    """Count the number of slides in the HTML content."""
    if not html_content:
        return 0
    
    # Try to count <section> tags (reveal.js style)
    section_count = len(re.findall(r'<section[^>]*>', html_content))
    if section_count > 0:
        return section_count
    
    # Try to count divs with slide class
    slide_count = len(re.findall(r'<div[^>]*class="[^"]*slide[^"]*"[^>]*>', html_content, re.IGNORECASE))
    return max(slide_count, 1)


def prepare_html_for_preview(html_content: str, container_height: int = 600) -> str:
    """
    Prepare HTML content for iframe preview by fixing viewport and positioning issues.
    
    In Streamlit's components.html(), content is rendered in an iframe with fixed height.
    This causes issues with:
    - 100vh units (refers to iframe height, not browser viewport)
    - position: fixed (positions relative to iframe, not browser)
    - overflow: hidden on body (may clip content)
    
    This function injects CSS fixes to make the content display correctly in the iframe.
    
    Args:
        html_content: The original HTML content
        container_height: The height of the iframe container in pixels
        
    Returns:
        Modified HTML content suitable for iframe preview
    """
    if not html_content:
        return html_content
    
    # CSS fixes for iframe compatibility
    iframe_fix_css = f"""
<style id="iframe-preview-fixes">
    /* Fix viewport units - use container height instead of vh */
    html, body {{
        height: {container_height}px !important;
        min-height: {container_height}px !important;
        max-height: {container_height}px !important;
        overflow: auto !important;
    }}
    
    /* Convert fixed positioning to absolute within container */
    .fixed {{
        position: absolute !important;
    }}
    
    /* Ensure slide container fills the iframe */
    .slide-container {{
        height: {container_height}px !important;
        min-height: {container_height}px !important;
        overflow: auto !important;
    }}
    
    /* Fix navigation indicator positioning */
    [class*="fixed"][class*="bottom"] {{
        position: absolute !important;
        bottom: 16px !important;
    }}
    
    /* Ensure flex containers don't overflow */
    .h-full {{
        height: 100% !important;
        max-height: {container_height - 32}px !important;
    }}
    
    /* Allow scrolling for content that exceeds container */
    .flex-1 {{
        overflow: auto !important;
        min-height: 0 !important;
    }}
</style>
"""
    
    # Inject the CSS fix right before </head> or at the start of <body>
    if '</head>' in html_content:
        html_content = html_content.replace('</head>', f'{iframe_fix_css}</head>')
    elif '<body' in html_content:
        # Find the end of the body tag
        body_match = re.search(r'<body[^>]*>', html_content)
        if body_match:
            insert_pos = body_match.end()
            html_content = html_content[:insert_pos] + iframe_fix_css + html_content[insert_pos:]
    else:
        # Fallback: prepend to content
        html_content = iframe_fix_css + html_content
    
    return html_content


def format_tool_args(args: dict) -> str:
    """Format tool arguments for display."""
    formatted = []
    for key, value in args.items():
        if isinstance(value, str) and len(value) > 100:
            value = value[:100] + "..."
        elif isinstance(value, list) and len(value) > 5:
            value = value[:5] + ["..."]
        formatted.append(f"  {key}: {json.dumps(value, ensure_ascii=False)}")
    return "\n".join(formatted)


def render_chat_message(event: dict):
    """Render a single chat event."""
    event_type = event.get("type")
    
    if event_type == "user_message":
        st.markdown(f"""
        <div class="chat-message user-message">
            <strong>👤 You:</strong><br>
            {event.get("content", "")}
        </div>
        """, unsafe_allow_html=True)
    
    elif event_type == "assistant_message":
        content = event.get("content", "")
        if content:
            st.markdown(f"""
            <div class="chat-message assistant-message">
                <strong>🤖 Assistant:</strong><br>
                {content}
            </div>
            """, unsafe_allow_html=True)
    
    elif event_type == "tool_call":
        tc = event.get("tool_call")
        if tc:
            # Handle both ToolCallInfo objects and dicts
            if isinstance(tc, dict):
                name = tc.get("name", "")
                arguments = tc.get("arguments", {})
            else:
                name = tc.name
                arguments = tc.arguments
            args_str = format_tool_args(arguments)
            st.markdown(f"""
            <div class="chat-message tool-call">
                <span class="tool-badge">🔧 {name}</span><br>
                <pre>{args_str}</pre>
            </div>
            """, unsafe_allow_html=True)
    
    elif event_type == "tool_result":
        tc = event.get("tool_call")
        if tc:
            # Handle both ToolCallInfo objects and dicts
            if isinstance(tc, dict):
                result = tc.get("result", {})
                name = tc.get("name", "")
                success = result.get("success", False) if isinstance(result, dict) else False
                data = result.get("data") if isinstance(result, dict) else None
                error = result.get("error") if isinstance(result, dict) else None
            else:
                result = tc.result
                name = tc.name
                success = result.success if result else False
                data = result.data if result else None
                error = result.error if result else None
            
            if success:
                # Format the result data
                if data:
                    if name == "execute_command":
                        output = data.get("output", "")
                        if len(output) > 500:
                            output = output[:500] + "\n... (truncated)"
                        result_str = f"Exit code: {data.get('exit_code', 'N/A')}\n\nOutput:\n{output}"
                    else:
                        result_str = json.dumps(data, indent=2, ensure_ascii=False)
                        if len(result_str) > 500:
                            result_str = result_str[:500] + "\n... (truncated)"
                else:
                    result_str = "Success"
                
                st.markdown(f"""
                <div class="chat-message tool-result-success">
                    <strong>✅ Result:</strong>
                    <pre>{result_str}</pre>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown(f"""
                <div class="chat-message tool-result-error">
                    <strong>❌ Error:</strong> {error}
                </div>
                """, unsafe_allow_html=True)
    
    elif event_type == "task_completed":
        st.markdown(f"""
        <div class="completion-message">
            <strong>✨ Task Completed:</strong><br>
            {event.get("result", "")}
        </div>
        """, unsafe_allow_html=True)
    
    elif event_type == "error":
        st.markdown(f"""
        <div class="error-message">
            <strong>❌ Error:</strong> {event.get("error", "")}
        </div>
        """, unsafe_allow_html=True)


def get_or_create_agent(task: Task) -> Optional[Agent]:
    """Get or create an agent for the given task."""
    if not st.session_state.api_key:
        st.error("请在 .env 文件中配置 OPENAI_API_KEY")
        return None
    
    if not st.session_state.model:
        st.error("请在 .env 文件中配置 OPENAI_MODEL")
        return None
    
    # Check if we already have an agent for this task
    if task.id in st.session_state.agents:
        agent = st.session_state.agents[task.id]
        # Check if settings have changed
        if (agent.workspace_dir != Path(task.workspace_dir).resolve() or
            agent.model != st.session_state.model):
            # Need to create a new agent
            del st.session_state.agents[task.id]
        else:
            return agent
    
    # Create new agent
    try:
        # Build system prompt with custom prompt if provided
        system_prompt_path = "system_prompt.txt"
        
        agent = Agent(
            api_key=st.session_state.api_key,
            workspace_dir=task.workspace_dir,
            model=st.session_state.model,
            base_url=st.session_state.base_url if st.session_state.base_url else None,
            system_prompt_path=system_prompt_path
        )
        
        # Append custom prompt if provided
        if task.custom_prompt:
            agent.system_prompt += f"\n\n## 额外指示\n\n{task.custom_prompt}"
        
        # Restore conversation history
        agent.messages = []
        for event in task.chat_history:
            event_type = event.get("type")
            if event_type == "user_message":
                agent.messages.append({"role": "user", "content": event.get("content", "")})
            elif event_type == "assistant_message":
                agent.messages.append({"role": "assistant", "content": event.get("content", "")})
        
        st.session_state.agents[task.id] = agent
        return agent
    
    except Exception as e:
        st.error(f"Failed to initialize agent: {e}")
        return None


# ============================================================================
# Sidebar - Task List
# ============================================================================

def get_directory_preview(directory: str, max_items: int = 20) -> Tuple[List[str], List[str], int, int]:
    """
    Get a preview of directory contents.
    
    Args:
        directory: Path to the directory
        max_items: Maximum number of items to return
        
    Returns:
        Tuple of (files, dirs, total_files, total_dirs)
    """
    files = []
    dirs = []
    total_files = 0
    total_dirs = 0
    
    try:
        items = sorted(os.listdir(directory))
        for item in items:
            item_path = os.path.join(directory, item)
            if os.path.isdir(item_path):
                total_dirs += 1
                if len(dirs) < max_items:
                    dirs.append(item)
            else:
                total_files += 1
                if len(files) < max_items:
                    files.append(item)
    except Exception as e:
        pass
    
    return files, dirs, total_files, total_dirs


def handle_directory_selection():
    """Handle the directory/file selection and copy process."""
    # Open file/directory picker
    pick_result = pick_files_or_directory("选择工作目录或文件")
    
    if pick_result:
        st.session_state.pending_pick_result = pick_result
        st.session_state.pending_source_dir = pick_result.base_dir
        
        # Scan based on selection type
        copier = WorkspaceCopier()
        
        if pick_result.is_files:
            # User selected specific files
            scan_result = copier.scan_files(pick_result.files, pick_result.base_dir)
        else:
            # User selected a directory
            scan_result = copier.scan_directory(pick_result.base_dir)
        
        st.session_state.pending_scan_result = scan_result
        
        # Check if size warning is needed
        if copier.needs_size_warning(scan_result):
            st.session_state.show_size_warning = True
        # Don't auto-proceed, let user confirm after seeing the file list
    else:
        st.session_state.pending_source_dir = None
        st.session_state.pending_pick_result = None
        st.session_state.pending_scan_result = None


def create_task_with_copy():
    """Create a new task and copy the workspace."""
    source_dir = st.session_state.pending_source_dir
    pick_result = st.session_state.pending_pick_result
    
    if not source_dir:
        return
    
    task_manager = st.session_state.task_manager
    
    # Create the task first (this generates the workspace path)
    task = task_manager.create_task(source_dir)
    
    # Now copy the files
    st.session_state.copy_in_progress = True
    
    try:
        copier = WorkspaceCopier()
        
        if pick_result and pick_result.is_files:
            # Copy only selected files
            result = copier.copy_files(pick_result.files, pick_result.base_dir, task.workspace_dir)
        else:
            # Copy entire directory
            result = copier.copy_directory(source_dir, task.workspace_dir)
        
        if result.success:
            st.success(f"✅ 已复制 {result.files_copied} 个文件 ({result.total_size_mb:.1f} MB)")
        else:
            st.error(f"复制失败: {result.error}")
            # Delete the task if copy failed
            task_manager.delete_task(task.id)
    
    finally:
        st.session_state.copy_in_progress = False
        st.session_state.pending_source_dir = None
        st.session_state.pending_pick_result = None
        st.session_state.pending_scan_result = None
        st.session_state.show_size_warning = False
        st.session_state.show_new_task_dialog = False
        st.session_state.preview_key += 1


def render_task_list():
    """Render task list section."""
    st.subheader("📋 任务列表")
    
    task_manager = st.session_state.task_manager
    tasks = task_manager.list_tasks()
    active_task = task_manager.get_active_task()
    
    # New task button
    if st.button("➕ 新建任务", use_container_width=True, disabled=st.session_state.copy_in_progress):
        st.session_state.show_new_task_dialog = True
        st.rerun()
    
    # New task dialog
    if st.session_state.show_new_task_dialog:
        with st.expander("新建任务", expanded=True):
            # Copy in progress
            if st.session_state.copy_in_progress:
                st.info("⏳ 正在复制文件...")
                st.progress(0.5)
            
            # Normal state - show directory picker button
            elif not st.session_state.pending_source_dir:
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("📂 选择目录", use_container_width=True, type="primary"):
                        handle_directory_selection()
                        st.rerun()
                with col2:
                    if st.button("取消", use_container_width=True):
                        st.session_state.show_new_task_dialog = False
                        st.rerun()
            
            # Directory/files selected - show preview and confirm
            else:
                source_dir = st.session_state.pending_source_dir
                pick_result = st.session_state.pending_pick_result
                
                if pick_result and pick_result.is_files:
                    # Show selected files info
                    st.info(f"📄 已选择 {len(pick_result.files)} 个文件")
                    st.caption(f"📁 来自: {pick_result.base_dir}")
                else:
                    st.info(f"📁 已选择目录: {source_dir}")
                
                # Show scan statistics
                scan_result = st.session_state.pending_scan_result
                if scan_result:
                    st.caption(
                        f"📊 将复制 {scan_result.total_files} 个文件, "
                        f"{scan_result.total_size_mb:.1f} MB "
                        f"(忽略 {scan_result.skipped_by_ignore} 项)"
                    )
                
                # Size warning
                if st.session_state.show_size_warning:
                    st.warning(
                        f"⚠️ 选择的内容较大 ({scan_result.total_size_mb:.1f} MB)，"
                        f"复制可能需要一些时间。"
                    )
                
                # Show content preview
                if pick_result and pick_result.is_files:
                    # Show selected files list
                    st.markdown("**📄 已选择的文件:**")
                    relative_files = pick_result.relative_files
                    file_list = "  \n".join([f"📄 {f}" for f in relative_files[:15]])
                    if len(relative_files) > 15:
                        file_list += f"  \n... 还有 {len(relative_files) - 15} 个文件"
                    st.markdown(file_list)
                else:
                    # Show directory contents preview
                    st.markdown("**📂 目录内容预览:**")
                    files, dirs, total_files, total_dirs = get_directory_preview(source_dir)
                    
                    # Display directories first
                    if dirs:
                        dir_list = "  \n".join([f"📁 {d}/" for d in dirs[:10]])
                        if total_dirs > 10:
                            dir_list += f"  \n... 还有 {total_dirs - 10} 个目录"
                        st.markdown(dir_list)
                    
                    # Display files
                    if files:
                        file_list = "  \n".join([f"📄 {f}" for f in files[:10]])
                        if total_files > 10:
                            file_list += f"  \n... 还有 {total_files - 10} 个文件"
                        st.markdown(file_list)
                    
                    if not dirs and not files:
                        st.caption("(空目录)")
                
                st.divider()
                
                # Action buttons
                col1, col2, col3 = st.columns(3)
                with col1:
                    if st.button("✅ 确认创建", use_container_width=True, type="primary"):
                        create_task_with_copy()
                        st.rerun()
                with col2:
                    if st.button("🔄 重新选择", use_container_width=True):
                        st.session_state.pending_source_dir = None
                        st.session_state.pending_pick_result = None
                        st.session_state.pending_scan_result = None
                        st.session_state.show_size_warning = False
                        handle_directory_selection()
                        st.rerun()
                with col3:
                    if st.button("❌ 取消", use_container_width=True):
                        st.session_state.pending_source_dir = None
                        st.session_state.pending_pick_result = None
                        st.session_state.pending_scan_result = None
                        st.session_state.show_size_warning = False
                        st.session_state.show_new_task_dialog = False
                        st.rerun()
    
    # Task list
    if not tasks:
        st.caption("暂无任务，点击上方按钮创建")
    else:
        for task in tasks:
            is_active = active_task and task.id == active_task.id
            icon = "✓" if is_active else "○"
            
            col1, col2 = st.columns([4, 1])
            with col1:
                if st.button(
                    f"{icon} {task.name}",
                    key=f"task_{task.id}",
                    use_container_width=True,
                    type="primary" if is_active else "secondary"
                ):
                    if not is_active:
                        task_manager.switch_task(task.id)
                        st.session_state.preview_key += 1
                        # Reset editor state when switching tasks
                        st.session_state.show_plan_editor = False
                        st.session_state.pending_presentation_plan = None
                        st.session_state.grid_expanded_slide = None
                        # Sync phase with the new task's actual state
                        sync_phase_with_task()
                        st.rerun()
            
            with col2:
                if st.button("🗑️", key=f"del_{task.id}", help="删除任务"):
                    task_manager.delete_task(task.id)
                    if task.id in st.session_state.agents:
                        del st.session_state.agents[task.id]
                    st.rerun()


# ============================================================================
# Sidebar - Current Task Settings
# ============================================================================

def sync_workspace(task: Task):
    """Sync workspace from source directory."""
    if not task.source_dir or not os.path.isdir(task.source_dir):
        st.error("源目录不存在或无法访问")
        return
    
    task_manager = st.session_state.task_manager
    
    try:
        # Clear existing workspace
        workspace_path = Path(task.workspace_dir)
        if workspace_path.exists():
            shutil.rmtree(workspace_path)
        
        # Copy again
        copier = WorkspaceCopier()
        result = copier.copy_directory(task.source_dir, task.workspace_dir)
        
        if result.success:
            task_manager.update_sync_time(task.id)
            st.success(f"✅ 同步完成: {result.files_copied} 个文件 ({result.total_size_mb:.1f} MB)")
            
            # Clear agent cache
            if task.id in st.session_state.agents:
                del st.session_state.agents[task.id]
        else:
            st.error(f"同步失败: {result.error}")
    
    except Exception as e:
        st.error(f"同步出错: {e}")
    
    finally:
        st.session_state.confirm_sync = False
        st.session_state.preview_key += 1


def render_task_settings():
    """Render current task settings section."""
    task = get_current_task()
    if not task:
        st.info("请先创建或选择一个任务")
        return
    
    st.subheader("⚙️ 当前任务设置")
    
    task_manager = st.session_state.task_manager
    
    # Task name
    new_name = st.text_input(
        "任务名称",
        value=task.name,
        key="task_name_input"
    )
    if new_name != task.name:
        task_manager.update_task(task.id, name=new_name)
    
    # HTML file path
    new_html_file = st.text_input(
        "HTML 文件路径",
        value=task.html_file,
        help="相对于工作目录的路径",
        key="task_html_input"
    )
    if new_html_file != task.html_file:
        task_manager.update_task(task.id, html_file=new_html_file)
        st.session_state.preview_key += 1
    
    # Custom prompt
    with st.expander("自定义提示词", expanded=False):
        new_prompt = st.text_area(
            "额外指示",
            value=task.custom_prompt,
            height=100,
            help="将附加到系统提示词末尾",
            key="task_prompt_input"
        )
        if new_prompt != task.custom_prompt:
            task_manager.update_task(task.id, custom_prompt=new_prompt)
            if task.id in st.session_state.agents:
                del st.session_state.agents[task.id]
    
    st.divider()
    
    # Actions
    st.subheader("🎬 操作")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("🔄 刷新预览", use_container_width=True):
            st.session_state.preview_key += 1
            st.rerun()
    
    with col2:
        if st.button("🗑️ 清空对话", use_container_width=True):
            task_manager.clear_chat_history(task.id)
            if task.id in st.session_state.agents:
                st.session_state.agents[task.id].reset()
            st.rerun()
    
    # Sync button (only if source_dir exists)
    if task.source_dir and os.path.isdir(task.source_dir):
        st.divider()
        
        if st.session_state.confirm_sync:
            st.warning("⚠️ 重新同步将覆盖工作目录中的所有更改，确定要继续吗？")
            col1, col2 = st.columns(2)
            with col1:
                if st.button("确认同步", use_container_width=True, type="primary"):
                    sync_workspace(task)
                    st.rerun()
            with col2:
                if st.button("取消", use_container_width=True):
                    st.session_state.confirm_sync = False
                    st.rerun()
        else:
            if st.button("🔄 重新同步", use_container_width=True, help="从源目录重新复制文件"):
                st.session_state.confirm_sync = True
                st.rerun()
    
    st.divider()
    
    # Info
    st.subheader("ℹ️ 信息")
    
    # Source directory info
    if task.source_dir:
        st.caption(f"📁 源目录: `{task.source_dir}`")
        if task.last_sync_at:
            st.caption(f"🕐 最后同步: {task.last_sync_at[:19].replace('T', ' ')}")
    
    st.caption(f"📂 工作目录: `{task.workspace_dir}`")
    
    html_path = Path(task.workspace_dir) / task.html_file
    if html_path.exists():
        st.caption("✅ HTML 文件存在")
        html_content = get_html_content()
        slide_count = count_slides(html_content) if html_content else 0
        st.caption(f"📊 检测到 {slide_count} 页幻灯片")
    else:
        st.caption("⚠️ HTML 文件不存在")
    
    # Show slides directory status
    slides_dir = get_slides_dir(task)
    if slides_dir:
        status = get_slide_status_summary(slides_dir)
        if "error" not in status:
            st.caption(
                f"📁 Slides: {status.get('completed', 0)}/{status.get('total', 0)} 完成"
            )
            if status.get('failed', 0) > 0:
                st.caption(f"⚠️ {status.get('failed', 0)} 页生成失败")
    
    st.caption(f"💬 对话消息: {len(task.chat_history)} 条")


# ============================================================================
# Sidebar
# ============================================================================

def render_sidebar():
    """Render the complete sidebar."""
    with st.sidebar:
        st.title("⚙️ 设置")
        
        render_task_list()
        
        st.divider()
        
        render_task_settings()


# ============================================================================
# Main Content - Chat Panel
# ============================================================================

def render_chat_panel():
    """Render the chat panel."""
    task = get_current_task()
    
    if not task:
        st.info("👈 请先在侧边栏创建或选择一个任务")
        return
    
    st.subheader(f"💬 {task.name}")
    
    # Chat history container
    chat_container = st.container()
    
    with chat_container:
        for event in task.chat_history:
            render_chat_message(event)
    
    # Streaming output placeholder - will be used during processing
    if "streaming_placeholder" not in st.session_state:
        st.session_state.streaming_placeholder = None
    
    # Create placeholder for live updates during processing
    live_update_container = st.empty()
    
    # Input area
    st.divider()
    
    with st.form(key="chat_form", clear_on_submit=True):
        user_input = st.text_area(
            "Your message",
            placeholder="描述您想要创建的内容...",
            height=100,
            label_visibility="collapsed"
        )
        
        col1, col2, col3 = st.columns([3, 1, 1])
        
        with col1:
            submit_btn = st.form_submit_button(
                "🚀 发送",
                use_container_width=True,
                disabled=st.session_state.is_processing
            )
        
        with col2:
            stop_btn = st.form_submit_button(
                "⏹️ 停止",
                use_container_width=True
            )
    
    # Process user input
    if submit_btn and user_input.strip():
        process_user_message(task, user_input.strip(), live_update_container)
    
    if stop_btn:
        st.session_state.is_processing = False
        st.rerun()


def process_user_message(task: Task, message: str, live_container=None):
    """Process a user message and run the agent with live streaming updates."""
    st.session_state.is_processing = True
    
    # Get or create agent for this task
    agent = get_or_create_agent(task)
    
    if agent is None:
        st.session_state.is_processing = False
        return
    
    task_manager = st.session_state.task_manager
    
    # Track events for live display
    live_events = []
    current_streaming_text = ""
    
    # Flag to track if we should do a rerun
    should_rerun = True
    
    # Throttling for streaming updates to reduce WebSocket pressure
    last_render_time = 0
    RENDER_THROTTLE_MS = 300  # Only render every 300ms during streaming
    
    def render_live_events(force: bool = False):
        """Render all live events including streaming text.
        
        Args:
            force: If True, render regardless of throttle
        """
        nonlocal last_render_time
        
        if live_container is None:
            return
        
        # Apply throttling unless forced
        current_time = time.time() * 1000
        if not force and (current_time - last_render_time) < RENDER_THROTTLE_MS:
            return
        
        last_render_time = current_time
        
        try:
            with live_container.container():
                for evt in live_events:
                    render_chat_message(evt)
                
                # Show current streaming text if any
                if current_streaming_text:
                    # Truncate very long streaming text to reduce WebSocket payload
                    display_text = current_streaming_text
                    if len(display_text) > 2000:
                        display_text = display_text[-2000:] + "\n... (showing last 2000 chars)"
                    
                    st.markdown(f"""
                    <div class="chat-message assistant-message">
                        <strong>🤖 Assistant:</strong> <span style="color: #888;">(正在输入...)</span><br>
                        <pre style="white-space: pre-wrap; word-wrap: break-word;">{display_text}</pre>
                    </div>
                    """, unsafe_allow_html=True)
        except Exception:
            # Ignore rendering errors (e.g., WebSocket closed)
            # The task results are still saved to task_manager
            pass
    
    # Run agent and collect events with streaming
    try:
        for event in agent.run(message, stream=True):
            event_type = event.get("type")
            
            # Handle streaming events - update live display with throttling
            if event_type == "streaming_delta":
                current_streaming_text = event.get("accumulated", "")
                render_live_events(force=False)  # Throttled
                continue  # Don't save streaming deltas to history
            
            elif event_type == "streaming_complete":
                # Streaming finished, save the complete message to history
                complete_content = event.get("content", "")
                if complete_content:
                    # Create an assistant_message event for the complete response
                    assistant_event = {"type": "assistant_message", "content": complete_content}
                    task_manager.add_chat_message(task.id, assistant_event)
                    live_events.append(assistant_event)
                current_streaming_text = ""
                render_live_events(force=True)
                continue
            
            # Convert ToolCallInfo to dict for serialization
            if event_type in ["tool_call", "tool_result"]:
                tc = event.get("tool_call")
                if tc and not isinstance(tc, dict):
                    event = {
                        "type": event_type,
                        "tool_call": {
                            "id": tc.id,
                            "name": tc.name,
                            "arguments": tc.arguments,
                            "result": {
                                "success": tc.result.success if tc.result else False,
                                "data": tc.result.data if tc.result else None,
                                "error": tc.result.error if tc.result else None
                            } if tc.result else None
                        }
                    }
            
            # Add to task's chat history (this persists the result even if UI fails)
            task_manager.add_chat_message(task.id, event)
            
            # Add to live events for display
            live_events.append(event)
            render_live_events(force=True)  # Force render for non-streaming events
            
            # Refresh preview if file might have changed
            if event_type == "tool_result":
                tc = event.get("tool_call")
                if tc:
                    tc_name = tc.get("name") if isinstance(tc, dict) else tc.name
                    if tc_name == "write_file":
                        st.session_state.preview_key += 1
                        
                        # Check if presentation_plan.json was written - trigger slide generation
                        tc_args = tc.get("arguments") if isinstance(tc, dict) else tc.arguments
                        if tc_args:
                            files_written = tc_args.get("files", [])
                            for file_entry in files_written:
                                file_path = file_entry.get("path", "") if isinstance(file_entry, dict) else ""
                                if "presentation_plan.json" in file_path:
                                    # Phase complete - trigger slide generation
                                    handle_phase_complete(task, "architect", "", live_container)
                    
                    # Handle phase_complete tool
                    elif tc_name == "phase_complete":
                        tc_result = tc.get("result") if isinstance(tc, dict) else tc.result
                        if tc_result:
                            result_data = tc_result.get("data") if isinstance(tc_result, dict) else tc_result.data
                            if result_data and result_data.get("phase_complete"):
                                phase = result_data.get("phase", "")
                                summary = result_data.get("summary", "")
                                handle_phase_complete(task, phase, summary, live_container)
                                # Stop current agent loop since we're transitioning
                                st.session_state.is_processing = False
                                break
            
            # Check if we should stop
            if not st.session_state.is_processing:
                break
    
    except Exception as e:
        # Check if it's a connection/WebSocket error that we can safely ignore
        error_str = str(e).lower()
        is_connection_error = any(keyword in error_str for keyword in [
            'websocket', 'connection', 'stream', 'closed', 'eof'
        ])
        
        if is_connection_error:
            # Connection was lost - results are already saved to task_manager
            # Don't try to render error or rerun since connection is gone
            should_rerun = False
        else:
            # Real error - record it
            try:
                error_event = {"type": "error", "error": str(e)}
                task_manager.add_chat_message(task.id, error_event)
                live_events.append(error_event)
                render_live_events(force=True)
            except Exception:
                # Ignore errors during error handling (connection may be closed)
                pass
    
    finally:
        st.session_state.is_processing = False
        
        # Try to clean up and rerun, but handle errors gracefully
        if should_rerun:
            try:
                # Small delay to let pending WebSocket messages drain
                time.sleep(0.1)
                
                # Clear live container and do final rerun to show saved history
                if live_container:
                    live_container.empty()
                st.rerun()
            except Exception:
                # Rerun failed (e.g., WebSocket closed) - that's OK, state is saved
                pass


# ============================================================================
# Main Content - Preview Panel
# ============================================================================

# ============================================================================
# Grid View Functions
# ============================================================================

def get_manifest_data(task: Task) -> Optional[dict]:
    """Get manifest data for the task's slides."""
    slides_dir = get_slides_dir(task)
    if not slides_dir:
        return None
    
    manifest_path = slides_dir / "manifest.json"
    if not manifest_path.exists():
        return None
    
    try:
        return json.loads(manifest_path.read_text(encoding='utf-8'))
    except:
        return None


def get_slide_status_icon(status: str) -> str:
    """Get the icon for a slide status."""
    icons = {
        "pending": "⏳",
        "generating": "🔄",
        "completed": "✅",
        "failed": "❌",
        "modified": "✏️"
    }
    return icons.get(status, "❓")


def render_slide_card(task: Task, slide_meta: dict, index: int):
    """Render a single slide card in the grid."""
    slide_id = slide_meta.get("id", f"slide_{index + 1}")
    slide_title = slide_meta.get("title", f"Slide {index + 1}")
    slide_type = slide_meta.get("type", "unknown")
    slide_status = slide_meta.get("status", "pending")
    slide_file = slide_meta.get("file", "")
    
    is_expanded = st.session_state.grid_expanded_slide == slide_id
    
    # Card container
    with st.container():
        # Card header with status and title
        col1, col2 = st.columns([4, 1])
        
        with col1:
            st.markdown(f"**{index + 1}. {slide_title}**")
            st.caption(f"`{slide_type}`")
        
        with col2:
            status_icon = get_slide_status_icon(slide_status)
            st.markdown(f"<div class='status-icon'>{status_icon}</div>", unsafe_allow_html=True)
        
        # Preview thumbnail or placeholder
        slides_dir = get_slides_dir(task)
        if slides_dir and slide_status == "completed":
            slide_path = slides_dir / slide_file
            if slide_path.exists():
                try:
                    slide_content = slide_path.read_text(encoding='utf-8')
                    # Show a small preview with iframe fixes
                    preview_content = prepare_html_for_preview(slide_content, container_height=120)
                    components.html(preview_content, height=120, scrolling=False)
                except:
                    st.info("预览加载失败")
            else:
                st.info("文件不存在")
        elif slide_status == "generating":
            st.info("🔄 正在生成...")
        elif slide_status == "failed":
            st.error("❌ 生成失败")
        else:
            st.info("⏳ 等待生成")
        
        # Expand/collapse button
        if slide_status == "completed":
            if st.button("🔍 查看/编辑", key=f"expand_{slide_id}", use_container_width=True):
                if is_expanded:
                    st.session_state.grid_expanded_slide = None
                else:
                    st.session_state.grid_expanded_slide = slide_id
                st.rerun()


def render_expanded_slide_view(task: Task, manifest: dict):
    """Render the expanded view for editing a slide."""
    slide_id = st.session_state.grid_expanded_slide
    if not slide_id:
        return
    
    # Find the slide in manifest
    slides = manifest.get("slides", [])
    slide_meta = None
    slide_index = -1
    for i, s in enumerate(slides):
        if s.get("id") == slide_id:
            slide_meta = s
            slide_index = i
            break
    
    if not slide_meta:
        st.error("未找到幻灯片")
        st.session_state.grid_expanded_slide = None
        return
    
    slides_dir = get_slides_dir(task)
    if not slides_dir:
        st.error("未找到幻灯片目录")
        return
    
    # Header with back button
    col1, col2, col3 = st.columns([1, 3, 1])
    with col1:
        if st.button("← 返回网格", use_container_width=True):
            st.session_state.grid_expanded_slide = None
            st.rerun()
    with col2:
        st.subheader(f"📄 {slide_meta.get('title', 'Slide')}")
    with col3:
        st.caption(f"第 {slide_index + 1} / {len(slides)} 页")
    
    st.divider()
    
    # Left-right layout: preview on left, edit on right
    col_preview, col_edit = st.columns([7, 3])
    
    with col_preview:
        st.markdown("**预览**")
        slide_file = slide_meta.get("file", "")
        slide_path = slides_dir / slide_file
        
        if slide_path.exists():
            try:
                slide_content = slide_path.read_text(encoding='utf-8')
                # Apply iframe fixes for correct preview rendering
                preview_content = prepare_html_for_preview(slide_content, container_height=500)
                components.html(preview_content, height=500, scrolling=True)
            except Exception as e:
                st.error(f"预览加载失败: {e}")
        else:
            st.warning("幻灯片文件不存在")
    
    with col_edit:
        st.markdown("**✏️ 修改此幻灯片**")
        
        modification_input = st.text_area(
            "请描述您想要的修改",
            placeholder="例如：将标题改为红色，添加一个柱状图...",
            height=150,
            key=f"modify_{slide_id}"
        )
        
        # Placeholder for streaming output - will be populated during modification
        streaming_container = st.empty()
        
        if st.button(
            "🔄 应用修改",
            type="primary",
            use_container_width=True,
            disabled=st.session_state.slide_modification_in_progress
        ):
            if modification_input.strip():
                apply_slide_modification(task, slide_index, slide_id, modification_input.strip(), streaming_container)
    
    st.divider()
    
    # Navigation buttons
    col1, col2, col3 = st.columns([1, 2, 1])
    with col1:
        if slide_index > 0:
            prev_slide = slides[slide_index - 1]
            if st.button("← 上一页", use_container_width=True):
                st.session_state.grid_expanded_slide = prev_slide.get("id")
                st.rerun()
    with col3:
        if slide_index < len(slides) - 1:
            next_slide = slides[slide_index + 1]
            if st.button("下一页 →", use_container_width=True):
                st.session_state.grid_expanded_slide = next_slide.get("id")
                st.rerun()


def apply_slide_modification(task: Task, slide_index: int, slide_id: str, feedback: str, streaming_container=None):
    """Apply modification to a slide using the Designer agent with streaming output."""
    st.session_state.slide_modification_in_progress = True
    
    slides_dir = get_slides_dir(task)
    if not slides_dir:
        st.error("未找到幻灯片目录")
        st.session_state.slide_modification_in_progress = False
        return
    
    # Create generator and regenerate
    generator = create_slide_generator(task)
    if not generator:
        st.error("无法创建生成器")
        st.session_state.slide_modification_in_progress = False
        return
    
    def create_designer_agent(system_prompt: str) -> Agent:
        return Agent(
            api_key=st.session_state.api_key,
            workspace_dir=task.workspace_dir,
            model=st.session_state.model,
            base_url=st.session_state.base_url if st.session_state.base_url else None,
            system_prompt_override=system_prompt,
            include_image_tool=True  # Enable image generation for Designer agents
        )
    
    # Track streaming state
    current_streaming_text = ""
    live_events = []
    last_render_time = 0
    RENDER_THROTTLE_MS = 300
    
    def render_streaming_output(force: bool = False):
        """Render streaming output to the container."""
        nonlocal last_render_time
        
        if streaming_container is None:
            return
        
        # Apply throttling unless forced
        current_time = time.time() * 1000
        if not force and (current_time - last_render_time) < RENDER_THROTTLE_MS:
            return
        
        last_render_time = current_time
        
        try:
            with streaming_container.container():
                # Show streaming indicator
                st.markdown("**🔄 LLM 响应:**")
                
                # Show completed events (tool calls, results)
                for evt in live_events:
                    evt_type = evt.get("type")
                    if evt_type == "tool_call":
                        tc = evt.get("tool_call")
                        if tc:
                            tc_name = tc.get("name") if isinstance(tc, dict) else tc.name
                            st.markdown(f"🔧 调用工具: `{tc_name}`")
                    elif evt_type == "tool_result":
                        tc = evt.get("tool_call")
                        if tc:
                            tc_result = tc.get("result") if isinstance(tc, dict) else tc.result
                            if tc_result:
                                success = tc_result.get("success") if isinstance(tc_result, dict) else tc_result.success
                                if success:
                                    st.markdown("✅ 工具执行成功")
                                else:
                                    error = tc_result.get("error") if isinstance(tc_result, dict) else tc_result.error
                                    st.markdown(f"❌ 工具执行失败: {error}")
                
                # Show current streaming text
                if current_streaming_text:
                    display_text = current_streaming_text
                    # Truncate if too long
                    if len(display_text) > 1500:
                        display_text = display_text[-1500:]
                        display_text = "...\n" + display_text
                    
                    st.markdown(
                        f"""<div style="
                            background-color: #f0f7ff;
                            border: 1px solid #d0e3ff;
                            border-radius: 8px;
                            padding: 12px;
                            max-height: 300px;
                            overflow-y: auto;
                            font-family: monospace;
                            font-size: 12px;
                            white-space: pre-wrap;
                            word-wrap: break-word;
                        ">{display_text}<span style="animation: blink 1s infinite;">▌</span></div>
                        <style>
                            @keyframes blink {{
                                0%, 50% {{ opacity: 1; }}
                                51%, 100% {{ opacity: 0; }}
                            }}
                        </style>
                        """,
                        unsafe_allow_html=True
                    )
        except Exception:
            # Ignore rendering errors
            pass
    
    try:
        # Initial render to show loading state
        if streaming_container:
            with streaming_container.container():
                st.markdown("**⏳ 正在处理修改请求...**")
        
        for event in generator.regenerate_slide(
            slides_dir=slides_dir,
            slide_id=slide_id,
            user_feedback=feedback,
            create_agent_func=create_designer_agent,
            stream=True  # Enable streaming
        ):
            event_type = event.get("type")
            
            # Handle streaming events
            if event_type == "streaming_delta":
                current_streaming_text = event.get("accumulated", "")
                render_streaming_output(force=False)
                continue
            
            elif event_type == "streaming_complete":
                # Clear streaming text, content is now complete
                current_streaming_text = ""
                render_streaming_output(force=True)
                continue
            
            # Convert ToolCallInfo to dict for display
            if event_type in ["tool_call", "tool_result"]:
                tc = event.get("tool_call")
                if tc and not isinstance(tc, dict):
                    event = {
                        "type": event_type,
                        "tool_call": {
                            "id": tc.id,
                            "name": tc.name,
                            "arguments": tc.arguments,
                            "result": {
                                "success": tc.result.success if tc.result else False,
                                "data": tc.result.data if tc.result else None,
                                "error": tc.result.error if tc.result else None
                            } if tc.result else None
                        }
                    }
                
                live_events.append(event)
                render_streaming_output(force=True)
            
            if event_type == "error":
                st.error(event.get("error", "未知错误"))
            elif event_type == "task_completed":
                if streaming_container:
                    with streaming_container.container():
                        st.success("✅ 幻灯片已更新")
                st.session_state.preview_key += 1
    
    except Exception as e:
        st.error(f"修改失败: {e}")
    
    finally:
        st.session_state.slide_modification_in_progress = False
        st.rerun()


def regenerate_all_slides_from_plan(task: Task):
    """
    Regenerate all slides using the existing presentation_plan.json.
    
    This function:
    1. Reads the existing presentation_plan.json
    2. Resets all slide statuses to pending in manifest.json
    3. Starts background slide generation
    """
    from datetime import datetime
    
    slides_dir = get_slides_dir(task)
    if not slides_dir:
        st.error("未找到幻灯片目录")
        return False
    
    plan_path = slides_dir / "presentation_plan.json"
    if not plan_path.exists():
        st.error("未找到演示文稿规划文件")
        return False
    
    # Parse the plan
    plan = parse_presentation_plan(plan_path)
    if not plan:
        st.error("无法解析演示文稿规划")
        return False
    
    # Reset all slide statuses to pending in manifest.json
    manifest_path = slides_dir / "manifest.json"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
            for slide in manifest.get("slides", []):
                slide["status"] = "pending"
                slide["generated_at"] = None
            manifest["completed_slides"] = 0
            manifest["updated_at"] = datetime.utcnow().isoformat() + "Z"
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
        except Exception as e:
            st.error(f"重置幻灯片状态失败: {e}")
            return False
    
    # Start background generation
    st.session_state.slide_generation_in_progress = True
    
    # Capture configuration
    api_key = st.session_state.api_key
    base_url = st.session_state.base_url
    model = st.session_state.model
    concurrency = st.session_state.slide_concurrency
    timeout = st.session_state.slide_timeout
    workspace_dir = task.workspace_dir
    
    def run_generation():
        try:
            trigger_slide_generation_background(
                workspace_dir=workspace_dir,
                api_key=api_key,
                base_url=base_url,
                model=model,
                concurrency=concurrency,
                timeout=timeout,
                skip_framework=True  # Use existing framework, just regenerate content
            )
        except Exception as e:
            print(f"Background slide regeneration error: {e}")
    
    thread = threading.Thread(target=run_generation, daemon=True)
    thread.start()
    
    return True


def render_grid_view():
    """Render the full-screen grid view for slide monitoring and editing."""
    task = get_current_task()
    if not task:
        st.info("👈 请先在侧边栏创建或选择一个任务")
        return
    
    # Check if a slide is expanded
    if st.session_state.grid_expanded_slide:
        manifest = get_manifest_data(task)
        if manifest:
            render_expanded_slide_view(task, manifest)
        else:
            st.error("无法读取幻灯片数据")
            st.session_state.grid_expanded_slide = None
        return
    
    # Top navigation bar with back button
    col_back, col_title = st.columns([1, 5])
    with col_back:
        if st.button("← 返回主页", use_container_width=True, type="secondary", key="grid_back_btn"):
            st.session_state.current_phase = "collecting"
            st.session_state.grid_expanded_slide = None
            st.session_state.force_main_view = True  # Prevent auto-redirect
            st.rerun()
    with col_title:
        st.subheader("📊 幻灯片生成监控")
    
    # Get manifest data
    manifest = get_manifest_data(task)
    
    if not manifest:
        st.warning("未找到幻灯片数据。请先完成演示文稿规划。")
        
        # Option to go back to chat
        if st.button("← 返回对话", use_container_width=False):
            st.session_state.current_phase = "collecting"
            st.rerun()
        return
    
    slides = manifest.get("slides", [])
    total = len(slides)
    completed = sum(1 for s in slides if s.get("status") == "completed")
    failed = sum(1 for s in slides if s.get("status") == "failed")
    generating = sum(1 for s in slides if s.get("status") == "generating")
    pending = sum(1 for s in slides if s.get("status") == "pending")
    
    # Progress bar and stats
    col1, col2 = st.columns([3, 1])
    with col1:
        progress = completed / max(total, 1)
        st.progress(progress, text=f"已完成 {completed}/{total} 页")
    with col2:
        if failed > 0:
            st.error(f"❌ {failed} 失败")
        elif generating > 0:
            st.info(f"🔄 {generating} 生成中")
        elif pending > 0:
            st.warning(f"⏳ {pending} 等待中")
        else:
            st.success("✅ 全部完成")
    
    st.divider()
    
    # Grid of slide cards
    # Calculate number of columns (responsive-ish)
    num_cols = 4 if total > 6 else 3 if total > 3 else min(total, 3)
    num_cols = max(1, num_cols)
    
    # Create rows of cards
    for row_start in range(0, total, num_cols):
        cols = st.columns(num_cols)
        for col_idx, slide_idx in enumerate(range(row_start, min(row_start + num_cols, total))):
            with cols[col_idx]:
                render_slide_card(task, slides[slide_idx], slide_idx)
    
    st.divider()
    
    # Action buttons - two rows for better organization
    col1, col2, col3 = st.columns([2, 2, 2])
    
    with col1:
        if st.button("📦 导出为单文件", use_container_width=True, disabled=(completed < total)):
            export_slides(task)
    
    with col2:
        if st.button("🔄 刷新状态", use_container_width=True):
            st.session_state.preview_key += 1
            st.rerun()
    
    with col3:
        # Show regenerate button only when not actively generating
        has_active_generation = generating > 0 or st.session_state.slide_generation_in_progress
        if st.button(
            "🔁 重新生成全部",
            use_container_width=True,
            disabled=has_active_generation,
            help="使用现有规划重新生成所有幻灯片"
        ):
            if regenerate_all_slides_from_plan(task):
                st.success("✅ 已开始重新生成所有幻灯片")
                st.rerun()
    
    # Second row of action buttons
    col4, col5, col6 = st.columns([2, 2, 2])
    
    with col4:
        if st.button("📝 编辑规划", use_container_width=True, help="返回编辑演示文稿规划"):
            # Load the plan into editor
            slides_dir = get_slides_dir(task)
            if slides_dir:
                plan_path = slides_dir / "presentation_plan.json"
                if plan_path.exists():
                    try:
                        plan_content = plan_path.read_text(encoding='utf-8')
                        st.session_state.pending_presentation_plan = plan_content
                        st.session_state.show_plan_editor = True
                        st.session_state.current_phase = "editing_plan"
                        st.rerun()
                    except Exception as e:
                        st.error(f"读取规划文件失败: {e}")
    
    with col6:
        if st.button("🔙 重新开始", use_container_width=True, help="返回对话页面重新开始"):
            st.session_state.current_phase = "collecting"
            st.session_state.grid_expanded_slide = None
            st.rerun()
    
    # Auto-refresh logic
    has_pending_or_generating = pending > 0 or generating > 0
    
    if has_pending_or_generating and st.session_state.auto_refresh_enabled:
        # Check if enough time has passed since last refresh
        current_time = time.time()
        if current_time - st.session_state.last_refresh_time >= 3:  # 3 seconds
            st.session_state.last_refresh_time = current_time
            time.sleep(0.5)  # Small delay to avoid too rapid refreshes
            st.rerun()


def render_plan_editor():
    """Render the presentation plan editor dialog."""
    task = get_current_task()
    if not task:
        return
    
    if not st.session_state.show_plan_editor:
        return
    
    st.subheader("📝 编辑演示文稿规划")
    
    st.markdown("""
    **Architect Agent 已完成规划。** 请检查以下 JSON 内容，您可以：
    - 修改幻灯片的标题、内容和类型
    - 调整幻灯片的顺序（修改 id）
    - 添加或删除幻灯片
    - 修改主题颜色
    
    确认无误后，点击"确认并生成"开始生成幻灯片。
    """)
    
    # Show error if any
    if st.session_state.plan_editor_error:
        st.error(f"❌ {st.session_state.plan_editor_error}")
    
    # JSON editor
    plan_content = st.session_state.pending_presentation_plan or ""
    
    # Try to format the JSON for better readability
    try:
        parsed = json.loads(plan_content)
        formatted_content = json.dumps(parsed, ensure_ascii=False, indent=2)
    except:
        formatted_content = plan_content
    
    edited_plan = st.text_area(
        "演示文稿规划 (JSON)",
        value=formatted_content,
        height=400,
        key="plan_editor_textarea",
        help="这是 Architect Agent 生成的演示文稿规划，您可以直接编辑 JSON 内容"
    )
    
    # Preview slide count
    try:
        preview_plan = json.loads(edited_plan)
        slide_count = len(preview_plan.get("slides", []))
        st.caption(f"📊 共 {slide_count} 页幻灯片")
        
        # Show slide titles
        with st.expander("查看幻灯片列表", expanded=False):
            for i, slide in enumerate(preview_plan.get("slides", [])):
                slide_title = slide.get("title", f"幻灯片 {i+1}")
                st.markdown(f"{i+1}. {slide_title}")
    except json.JSONDecodeError as e:
        st.caption(f"⚠️ JSON 格式无效: {e.msg} (行 {e.lineno}, 列 {e.colno})")
        # Show a helper to validate online
        st.caption("💡 提示: 可以复制 JSON 到 [jsonlint.com](https://jsonlint.com) 检查语法错误")
    except Exception as e:
        st.caption(f"⚠️ JSON 格式无效: {str(e)}")
    
    st.divider()
    
    # Action buttons
    col1, col2, col3 = st.columns([2, 2, 1])
    
    with col1:
        if st.button("✅ 确认并生成", type="primary", use_container_width=True):
            confirm_and_start_generation(task, edited_plan)
            st.rerun()
    
    with col2:
        if st.button("🔄 重新生成规划", use_container_width=True):
            # Clear the editor and re-run architect
            st.session_state.show_plan_editor = False
            st.session_state.pending_presentation_plan = None
            st.session_state.plan_editor_error = None
            st.session_state.current_phase = "architect"
            st.info("请在聊天中发送新的指令来重新生成规划")
            st.rerun()
    
    with col3:
        if st.button("❌ 取消", use_container_width=True):
            st.session_state.show_plan_editor = False
            st.session_state.pending_presentation_plan = None
            st.session_state.plan_editor_error = None
            st.session_state.current_phase = "collecting"
            st.rerun()


def render_preview_panel():
    """Render the HTML preview panel."""
    task = get_current_task()
    
    if not task:
        st.info("📄 选择任务后将显示预览")
        return
    
    # Check if we should show the plan editor instead
    if st.session_state.show_plan_editor:
        render_plan_editor()
        return
    
    st.subheader("🖼️ 预览")
    
    # Check for multi-file slides
    slides_dir = get_slides_dir(task)
    slide_files = get_slide_files(task) if slides_dir else []
    
    # Show export button if slides exist
    if slide_files:
        col1, col2 = st.columns([3, 1])
        with col2:
            if st.button("📦 导出", use_container_width=True, help="合并为单个 HTML 文件"):
                export_slides(task)
    
    html_content = get_html_content()
    
    if html_content:
        # Slide navigation
        slide_count = count_slides(html_content)
        
        if slide_count > 1:
            st.caption(f"📊 检测到 {slide_count} 页幻灯片")
            
            # Slide selector
            cols = st.columns(min(slide_count, 10))
            for i in range(min(slide_count, 10)):
                with cols[i]:
                    if st.button(f"{i + 1}", key=f"slide_{i}", use_container_width=True):
                        st.session_state.task_manager.update_task(
                            task.id, selected_slide=i
                        )
            
            if slide_count > 10:
                st.caption("(显示前 10 页)")
        
        st.divider()
        
        # Create placeholder for refinement live updates
        refinement_live_container = st.empty()
        
        # Slide refinement
        with st.expander("✏️ 修改当前幻灯片", expanded=False):
            refinement_input = st.text_area(
                "修改请求",
                placeholder=f"您希望如何修改第 {task.selected_slide + 1} 页?",
                height=80,
                key="refinement_input"
            )
            
            if st.button("🔄 应用修改", use_container_width=True):
                if refinement_input.strip():
                    refine_current_slide(task, refinement_input.strip(), refinement_live_container)
        
        st.divider()
        
        # HTML preview
        try:
            # Inject JavaScript to navigate to specific slide if needed
            if slide_count > 1:
                nav_script = f"""
                <script>
                    // Wait for reveal.js to load
                    if (typeof Reveal !== 'undefined') {{
                        Reveal.slide({task.selected_slide}, 0);
                    }}
                </script>
                """
                html_content = html_content.replace('</body>', f'{nav_script}</body>')
            
            # Apply iframe fixes for correct preview rendering
            preview_content = prepare_html_for_preview(html_content, container_height=600)
            components.html(
                preview_content,
                height=600,
                scrolling=True
            )
        except Exception as e:
            st.error(f"渲染预览时出错: {e}")
    
    else:
        # Check if we have multi-file slides to show
        if slide_files:
            render_multi_slide_preview(task, slide_files)
        else:
            st.info("📄 未找到 HTML 文件。开始对话以创建一个!")
            
            # Show a placeholder
            st.markdown("""
            <div style="
                height: 400px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                border-radius: 10px;
                display: flex;
                align-items: center;
                justify-content: center;
                color: white;
                font-size: 1.5rem;
                text-align: center;
            ">
                🎨 您的演示文稿将在这里显示
            </div>
            """, unsafe_allow_html=True)


def render_multi_slide_preview(task: Task, slide_files: List[Path]):
    """Render preview for multi-file slides."""
    slides_dir = get_slides_dir(task)
    if not slides_dir:
        return
    
    # Slide status
    status = get_slide_status_summary(slides_dir)
    if "error" not in status:
        total = status.get("total", len(slide_files))
        completed = status.get("completed", 0)
        
        st.progress(completed / max(total, 1), text=f"已完成 {completed}/{total} 页")
    
    # Slide selector
    st.caption(f"📊 共 {len(slide_files)} 页幻灯片")
    
    cols = st.columns(min(len(slide_files), 10))
    for i, slide_file in enumerate(slide_files[:10]):
        with cols[i]:
            btn_type = "primary" if i == task.selected_slide else "secondary"
            if st.button(f"{i + 1}", key=f"mslide_{i}", use_container_width=True, type=btn_type):
                st.session_state.task_manager.update_task(task.id, selected_slide=i)
                st.rerun()
    
    if len(slide_files) > 10:
        st.caption("(显示前 10 页)")
    
    st.divider()
    
    # Show selected slide
    selected_idx = min(task.selected_slide, len(slide_files) - 1)
    if selected_idx >= 0:
        slide_content = get_slide_content(task, selected_idx)
        if slide_content:
            try:
                # Apply iframe fixes for correct preview rendering
                preview_content = prepare_html_for_preview(slide_content, container_height=600)
                components.html(preview_content, height=600, scrolling=True)
            except Exception as e:
                st.error(f"渲染幻灯片时出错: {e}")
        else:
            st.info("⏳ 该幻灯片正在生成中...")
    
    # Slide modification
    with st.expander("✏️ 修改当前幻灯片", expanded=False):
        refinement_input = st.text_area(
            "修改请求",
            placeholder=f"您希望如何修改第 {selected_idx + 1} 页?",
            height=80,
            key="multi_refinement_input"
        )
        
        if st.button("🔄 应用修改", use_container_width=True, key="multi_refine_btn"):
            if refinement_input.strip():
                regenerate_slide(task, selected_idx, refinement_input.strip())


def export_slides(task: Task):
    """Export slides to a ZIP package containing HTML and PPTX."""
    slides_dir = get_slides_dir(task)
    if not slides_dir:
        st.error("未找到幻灯片目录")
        return
    
    generator = create_slide_generator(task)
    if not generator:
        st.error("无法创建导出器")
        return
    
    try:
        # Show progress indicator
        with st.spinner("正在生成导出包（包含 HTML 和 PPTX）..."):
            # Use return_bytes=True to get ZIP data in memory, avoiding file locking issues
            result = generator.create_zip_package(slides_dir, include_pptx=True, return_bytes=True)
        
        # Ensure we have bytes data
        if isinstance(result, bytes):
            zip_data: bytes = result
        else:
            # If return_bytes failed, read from file path
            with open(result, "rb") as f:
                zip_data = f.read()
        
        st.success(f"✅ 导出成功!")
        
        # Provide download button directly with bytes data
        st.download_button(
            label="📥 下载演示文稿包 (ZIP)",
            data=zip_data,
            file_name="presentation.zip",
            mime="application/zip",
            use_container_width=True
        )
        
        st.caption("包含 presentation.html 和 presentation.pptx（如果生成成功）")
        st.session_state.preview_key += 1
        
    except Exception as e:
        st.error(f"导出失败: {e}")
        import traceback
        st.code(traceback.format_exc())


def validate_presentation_plan(plan_json: str) -> Tuple[bool, Optional[dict], Optional[str]]:
    """
    Validate a presentation plan JSON string.
    
    Simplified schema - only requires: id, title, content for each slide.
    
    Args:
        plan_json: JSON string to validate
        
    Returns:
        Tuple of (is_valid, parsed_plan, error_message)
    """
    # Clean the input - remove potential invisible characters that can cause issues
    # This handles issues from copy-paste or text_area processing
    cleaned_json = plan_json.strip()
    
    # Remove BOM if present
    if cleaned_json.startswith('\ufeff'):
        cleaned_json = cleaned_json[1:]
    
    # Replace problematic whitespace characters
    import re
    # Replace non-breaking spaces and other unicode spaces with regular space
    cleaned_json = re.sub(r'[\u00a0\u2000-\u200b\u2028\u2029\u202f\u205f\u3000]', ' ', cleaned_json)
    
    try:
        plan = json.loads(cleaned_json)
    except json.JSONDecodeError as e:
        # Provide more detailed error information
        error_line = e.lineno
        error_col = e.colno
        error_pos = e.pos
        
        # Try to show context around the error
        lines = cleaned_json.split('\n')
        context_lines = []
        
        if error_line and error_line > 0:
            start_line = max(0, error_line - 3)
            end_line = min(len(lines), error_line + 2)
            
            for i in range(start_line, end_line):
                line_num = i + 1
                marker = ">>> " if line_num == error_line else "    "
                line_content = lines[i] if i < len(lines) else ""
                # Truncate very long lines
                if len(line_content) > 100:
                    if error_col and line_num == error_line and error_col > 50:
                        # Show around the error position
                        start = max(0, error_col - 50)
                        end = min(len(line_content), error_col + 50)
                        line_content = f"...{line_content[start:end]}..."
                    else:
                        line_content = line_content[:100] + "..."
                context_lines.append(f"{marker}L{line_num}: {line_content}")
        
        context_str = "\n".join(context_lines) if context_lines else ""
        
        error_msg = f"JSON 解析错误: {e.msg}\n"
        error_msg += f"位置: 第 {error_line} 行, 第 {error_col} 列 (字符位置 {error_pos})\n"
        if context_str:
            error_msg += f"\n错误位置附近内容:\n{context_str}"
        
        return False, None, error_msg
    
    # Check required fields
    if not isinstance(plan, dict):
        return False, None, "JSON 必须是一个对象"
    
    if "slides" not in plan:
        return False, None, "缺少必需的 'slides' 字段"
    
    if not isinstance(plan.get("slides"), list):
        return False, None, "'slides' 必须是一个数组"
    
    if len(plan.get("slides", [])) == 0:
        return False, None, "'slides' 数组不能为空"
    
    # Validate each slide - simplified schema: only id, title, content required
    for i, slide in enumerate(plan.get("slides", [])):
        if not isinstance(slide, dict):
            return False, None, f"第 {i+1} 个幻灯片必须是一个对象"
        
        if "id" not in slide:
            return False, None, f"第 {i+1} 个幻灯片缺少 'id' 字段"
        
        if "title" not in slide:
            return False, None, f"第 {i+1} 个幻灯片缺少 'title' 字段"
        
        if "content" not in slide:
            return False, None, f"第 {i+1} 个幻灯片缺少 'content' 字段"
    
    return True, plan, None


def handle_phase_complete(task: Task, phase: str, summary: str, live_container=None):
    """
    Handle phase completion and transition to the next phase.
    
    Args:
        task: The current task
        phase: The phase that was completed ('collecting', 'architect')
        summary: Summary from the completed phase
        live_container: Container for live updates
    """
    task_manager = st.session_state.task_manager
    
    if phase == "collecting":
        # Transition to Architect phase
        st.session_state.current_phase = "architect"
        
        if live_container:
            with live_container.container():
                st.info("📐 正在规划演示文稿结构...")
        
        # Run Architect agent
        run_architect_phase(task, summary, live_container)
        
    elif phase == "architect":
        # Read the presentation plan and show editor
        plan_path = Path(task.workspace_dir) / "slides" / "presentation_plan.json"
        
        if plan_path.exists():
            try:
                plan_content = plan_path.read_text(encoding='utf-8')
                st.session_state.pending_presentation_plan = plan_content
                st.session_state.show_plan_editor = True
                st.session_state.plan_editor_error = None
                st.session_state.current_phase = "editing_plan"
                
                if live_container:
                    with live_container.container():
                        st.info("📝 请检查并编辑演示文稿规划，然后点击确认继续...")
            except Exception as e:
                if live_container:
                    with live_container.container():
                        st.error(f"读取演示文稿规划失败: {e}")
        else:
            if live_container:
                with live_container.container():
                    st.error("未找到 presentation_plan.json 文件")


def confirm_and_start_generation(task: Task, plan_json: str):
    """
    Validate the edited plan and start slide generation in background.
    
    Args:
        task: The current task
        plan_json: The edited JSON string
    """
    # Validate the JSON
    is_valid, plan, error = validate_presentation_plan(plan_json)
    
    if not is_valid or plan is None:
        st.session_state.plan_editor_error = error
        return
    
    # Save the edited plan
    plan_path = Path(task.workspace_dir) / "slides" / "presentation_plan.json"
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding='utf-8')
    
    # IMPORTANT: Create slide framework SYNCHRONOUSLY before starting background thread
    # This creates manifest.json with all slides in "pending" status
    # so the grid view can immediately show all slides
    generator = create_slide_generator(task)
    if generator:
        try:
            generator.create_slide_framework(plan)
            print(f"Created slide framework with {len(plan.get('slides', []))} slides")
        except Exception as e:
            print(f"Error creating slide framework: {e}")
            st.session_state.plan_editor_error = f"创建幻灯片框架失败: {e}"
            return
    
    # Clear editor state and transition to designing phase
    st.session_state.pending_presentation_plan = None
    st.session_state.show_plan_editor = False
    st.session_state.plan_editor_error = None
    st.session_state.current_phase = "designing"
    st.session_state.slide_generation_in_progress = True
    
    # Capture configuration from session state before starting thread
    # (Thread cannot safely access session_state)
    api_key = st.session_state.api_key
    base_url = st.session_state.base_url
    model = st.session_state.model
    concurrency = st.session_state.slide_concurrency
    timeout = st.session_state.slide_timeout
    workspace_dir = task.workspace_dir
    
    # Start content generation in background thread
    # Note: slide framework is already created, this only generates content
    def run_generation():
        try:
            trigger_slide_generation_background(
                workspace_dir=workspace_dir,
                api_key=api_key,
                base_url=base_url,
                model=model,
                concurrency=concurrency,
                timeout=timeout,
                skip_framework=True  # Framework already created
            )
        except Exception as e:
            print(f"Background slide generation error: {e}")
    
    thread = threading.Thread(target=run_generation, daemon=True)
    thread.start()
    
    # Note: st.rerun() is called after this function returns


def trigger_slide_generation_background(
    workspace_dir: str,
    api_key: str,
    base_url: str,
    model: str,
    concurrency: int,
    timeout: float,
    skip_framework: bool = False
):
    """
    Run slide generation in background thread.
    Does not use any Streamlit components - only updates manifest.json.
    
    Args:
        workspace_dir: Path to the workspace directory
        api_key: OpenAI API key
        base_url: OpenAI base URL (optional)
        model: Model name
        concurrency: Number of concurrent slide generations
        timeout: Timeout per slide in seconds
        skip_framework: If True, skip creating framework (already created)
    """
    plan_path = Path(workspace_dir) / "slides" / "presentation_plan.json"
    
    if not plan_path.exists():
        print(f"Plan file not found: {plan_path}")
        return
    
    # Parse the plan
    plan = parse_presentation_plan(plan_path)
    if not plan:
        print("Failed to parse presentation plan")
        return
    
    # Create slide generator
    generator = SlideGenerator(
        api_key=api_key,
        workspace_dir=workspace_dir,
        model=model,
        base_url=base_url if base_url else None,
        concurrency=concurrency,
        task_timeout=timeout
    )
    
    slides_dir = Path(workspace_dir) / "slides"
    
    # Create framework only if not skipped
    if not skip_framework:
        try:
            generator.create_slide_framework(plan)
            print(f"Created slide framework in {slides_dir}")
        except Exception as e:
            print(f"Error creating framework: {e}")
            return
    
    def create_designer_agent(system_prompt: str) -> Agent:
        return Agent(
            api_key=api_key,
            workspace_dir=workspace_dir,
            model=model,
            base_url=base_url if base_url else None,
            system_prompt_override=system_prompt,
            include_image_tool=True  # Enable image generation for Designer agents
        )
    
    # Run concurrent generation
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        stats = loop.run_until_complete(
            generator.generate_slides_concurrent(
                plan=plan,
                slides_dir=slides_dir,
                create_agent_func=create_designer_agent
            )
        )
        
        loop.close()
        
        print(f"Slide generation complete: {stats}")
        
    except Exception as e:
        print(f"Error generating slides: {e}")
        import traceback
        traceback.print_exc()


def run_architect_phase(task: Task, collector_summary: str, live_container=None, max_json_retries: int = 3):
    """
    Run the Architect phase to create presentation_plan.json.
    
    Includes automatic JSON validation and retry loop - if the generated JSON
    is invalid, the agent will be asked to fix it.
    
    Args:
        task: The current task
        collector_summary: Summary from the information collection phase
        live_container: Container for live updates
        max_json_retries: Maximum number of JSON validation retries
    """
    # Get the existing agent (with conversation history)
    agent = get_or_create_agent(task)
    if agent is None:
        if live_container:
            with live_container.container():
                st.error("无法创建 Architect Agent")
        return
    
    # Load Architect prompt from the code directory (where app.py is located)
    code_dir = Path(__file__).parent.resolve()
    architect_prompt_path = code_dir / "Architect_prompt.md"
    
    if architect_prompt_path.exists():
        architect_prompt = architect_prompt_path.read_text(encoding='utf-8')
    else:
        if live_container:
            with live_container.container():
                st.error("未找到 Architect_prompt.md")
        return
    
    # Switch system prompt while keeping conversation history
    original_prompt = agent.system_prompt
    tool_definitions = agent.tools.get_tool_definitions_json()
    agent.system_prompt = f"{architect_prompt}\n\n{tool_definitions}"
    
    task_manager = st.session_state.task_manager
    
    # Create the task for Architect
    architect_task = f"""基于之前收集的信息，请创建演示文稿规划。

收集阶段摘要：
{collector_summary}

请执行以下步骤：
1. 分析收集到的信息
2. 规划幻灯片结构（8-15页）
3. 使用 write_file 写入 slides/presentation_plan.json
4. 完成后调用 phase_complete(phase="architect", summary="...")

确保创建 slides 目录（如果不存在）。
"""
    
    json_retry_count = 0
    plan_path = Path(task.workspace_dir) / "slides" / "presentation_plan.json"
    
    # Streaming display state
    current_streaming_text = ""
    live_events = []
    last_render_time = 0
    RENDER_THROTTLE_MS = 300
    
    def render_architect_output(force: bool = False):
        """Render the architect's streaming output."""
        nonlocal last_render_time
        
        if live_container is None:
            return
        
        current_time = time.time() * 1000
        if not force and (current_time - last_render_time) < RENDER_THROTTLE_MS:
            return
        
        last_render_time = current_time
        
        try:
            with live_container.container():
                # Show phase indicator
                st.info("📐 Architect Agent 正在规划演示文稿结构...")
                
                # Show completed events
                for evt in live_events:
                    render_chat_message(evt)
                
                # Show streaming text
                if current_streaming_text:
                    display_text = current_streaming_text
                    if len(display_text) > 2000:
                        display_text = display_text[-2000:] + "\n... (显示最后 2000 字符)"
                    
                    st.markdown(f"""
                    <div class="chat-message assistant-message">
                        <strong>🤖 Architect:</strong> <span style="color: #888;">(正在规划...)</span><br>
                        <pre style="white-space: pre-wrap; word-wrap: break-word;">{display_text}</pre>
                    </div>
                    """, unsafe_allow_html=True)
        except Exception:
            pass
    
    def validate_and_get_error() -> Optional[str]:
        """Validate the JSON file and return error message if invalid."""
        if not plan_path.exists():
            return None  # File doesn't exist yet, no validation needed
        
        try:
            content = plan_path.read_text(encoding='utf-8')
            is_valid, _, error = validate_presentation_plan(content)
            if not is_valid:
                return error
            return None  # Valid
        except Exception as e:
            return f"读取文件出错: {str(e)}"
    
    # Show initial message and render immediately
    if live_container:
        with live_container.container():
            st.info("📐 Architect Agent 正在规划演示文稿结构...")
            st.caption("⏳ 正在等待 AI 响应，这可能需要几秒钟...")
    
    # Add a small delay to allow Streamlit to render the initial message
    time.sleep(0.1)
    
    # Track if we've received any streaming content
    first_response_received = False
    
    # Run the agent
    try:
        for event in agent.run(architect_task, stream=True):
            # Update first response flag
            if not first_response_received:
                first_response_received = True
                # Clear the "waiting" message since we're now receiving content
            event_type = event.get("type")
            
            # Handle streaming events
            if event_type == "streaming_delta":
                current_streaming_text = event.get("accumulated", "")
                # Force render on first delta to clear "waiting" message
                render_architect_output(force=not first_response_received or len(current_streaming_text) < 100)
                continue
            
            elif event_type == "streaming_complete":
                content = event.get("content", "")
                if content:
                    task_manager.add_chat_message(task.id, {"type": "assistant_message", "content": content})
                    live_events.append({"type": "assistant_message", "content": content})
                current_streaming_text = ""
                render_architect_output(force=True)
                continue
            
            # Convert ToolCallInfo to dict for serialization
            if event_type in ["tool_call", "tool_result"]:
                tc = event.get("tool_call")
                if tc and not isinstance(tc, dict):
                    event = {
                        "type": event_type,
                        "tool_call": {
                            "id": tc.id,
                            "name": tc.name,
                            "arguments": tc.arguments,
                            "result": {
                                "success": tc.result.success if tc.result else False,
                                "data": tc.result.data if tc.result else None,
                                "error": tc.result.error if tc.result else None
                            } if tc.result else None
                        }
                    }
            
            # Save to history and display
            task_manager.add_chat_message(task.id, event)
            live_events.append(event)
            render_architect_output(force=True)
            
            # Check for phase_complete or write_file
            if event_type == "tool_result":
                tc = event.get("tool_call")
                if tc:
                    tc_name = tc.get("name") if isinstance(tc, dict) else tc.name
                    tc_result = tc.get("result") if isinstance(tc, dict) else tc.result
                    
                    if tc_name == "write_file":
                        # Check if presentation_plan.json was written
                        tc_args = tc.get("arguments") if isinstance(tc, dict) else tc.arguments
                        if tc_args:
                            files_written = tc_args.get("files", [])
                            for file_entry in files_written:
                                file_path = file_entry.get("path", "") if isinstance(file_entry, dict) else ""
                                if "presentation_plan.json" in file_path:
                                    st.session_state.preview_key += 1
                                    
                                    # Validate the JSON immediately after write
                                    validation_error = validate_and_get_error()
                                    
                                    if validation_error:
                                        json_retry_count += 1
                                        
                                        if live_container:
                                            with live_container.container():
                                                st.warning(f"⚠️ JSON 验证失败 (尝试 {json_retry_count}/{max_json_retries}): {validation_error[:200]}...")
                                        
                                        if json_retry_count >= max_json_retries:
                                            if live_container:
                                                with live_container.container():
                                                    st.error(f"❌ JSON 验证失败次数过多，请手动修复")
                                            # Still proceed to show editor with error
                                            handle_phase_complete(task, "architect", "", live_container)
                                            return
                                        
                                        # Send error back to agent for correction
                                        correction_task = f"""你写入的 presentation_plan.json 文件有错误，请修复后重新写入。

**错误信息:**
{validation_error}

**修复要求:**
1. 确保 JSON 格式正确（注意逗号、引号、括号配对）
2. 每个 slide 必须包含 id、title、content 三个字段
3. 如果 content 中有特殊字符，确保正确转义
4. 使用 write_file 写入修复后的完整 JSON

请立即修复并重新写入文件。
"""
                                        # Show retry message
                                        live_events.append({"type": "assistant_message", "content": f"🔄 正在修复 JSON 错误 (尝试 {json_retry_count}/{max_json_retries})..."})
                                        render_architect_output(force=True)
                                        
                                        # Continue the agent with correction task
                                        for retry_event in agent.run(correction_task, stream=True):
                                            retry_type = retry_event.get("type")
                                            
                                            # Handle streaming for retry
                                            if retry_type == "streaming_delta":
                                                current_streaming_text = retry_event.get("accumulated", "")
                                                render_architect_output(force=False)
                                                continue
                                            
                                            elif retry_type == "streaming_complete":
                                                r_content = retry_event.get("content", "")
                                                if r_content:
                                                    task_manager.add_chat_message(task.id, {"type": "assistant_message", "content": r_content})
                                                    live_events.append({"type": "assistant_message", "content": r_content})
                                                current_streaming_text = ""
                                                render_architect_output(force=True)
                                                continue
                                            
                                            # Convert ToolCallInfo
                                            if retry_type in ["tool_call", "tool_result"]:
                                                rtc = retry_event.get("tool_call")
                                                if rtc and not isinstance(rtc, dict):
                                                    retry_event = {
                                                        "type": retry_type,
                                                        "tool_call": {
                                                            "id": rtc.id,
                                                            "name": rtc.name,
                                                            "arguments": rtc.arguments,
                                                            "result": {
                                                                "success": rtc.result.success if rtc.result else False,
                                                                "data": rtc.result.data if rtc.result else None,
                                                                "error": rtc.result.error if rtc.result else None
                                                            } if rtc.result else None
                                                        }
                                                    }
                                            
                                            # Save to history and display
                                            task_manager.add_chat_message(task.id, retry_event)
                                            live_events.append(retry_event)
                                            render_architect_output(force=True)
                                            
                                            # Check if file was rewritten
                                            if retry_type == "tool_result":
                                                rtc = retry_event.get("tool_call")
                                                if rtc:
                                                    rtc_name = rtc.get("name") if isinstance(rtc, dict) else rtc.name
                                                    if rtc_name == "write_file":
                                                        rtc_args = rtc.get("arguments") if isinstance(rtc, dict) else rtc.arguments
                                                        if rtc_args:
                                                            r_files = rtc_args.get("files", [])
                                                            for r_file in r_files:
                                                                r_path = r_file.get("path", "") if isinstance(r_file, dict) else ""
                                                                if "presentation_plan.json" in r_path:
                                                                    st.session_state.preview_key += 1
                                                                    
                                                                    # Re-validate
                                                                    new_error = validate_and_get_error()
                                                                    if new_error is None:
                                                                        # Success! Proceed to editor
                                                                        if live_container:
                                                                            with live_container.container():
                                                                                st.success("✅ JSON 验证通过！")
                                                                        handle_phase_complete(task, "architect", "", live_container)
                                                                        return
                                                                    # Still error, will continue retry loop on next iteration
                                                    elif rtc_name == "phase_complete":
                                                        # Agent thinks it's done, but we need to verify
                                                        final_error = validate_and_get_error()
                                                        if final_error is None:
                                                            handle_phase_complete(task, "architect", "", live_container)
                                                            return
                                        continue  # Continue outer loop
                                    else:
                                        # JSON is valid, can proceed
                                        if live_container:
                                            with live_container.container():
                                                st.success("✅ JSON 验证通过！")
                    
                    elif tc_name == "phase_complete":
                        if tc_result:
                            result_data = tc_result.get("data") if isinstance(tc_result, dict) else (tc_result.data if hasattr(tc_result, 'data') else None)
                            if result_data and result_data.get("phase") == "architect":
                                # Validate before proceeding
                                validation_error = validate_and_get_error()
                                if validation_error and json_retry_count < max_json_retries:
                                    json_retry_count += 1
                                    # Send correction task
                                    correction_task = f"""phase_complete 被调用，但 JSON 验证失败。请先修复 JSON 错误。

**错误信息:**
{validation_error}

请使用 write_file 写入修复后的 presentation_plan.json，然后再调用 phase_complete。
"""
                                    # Show retry message
                                    live_events.append({"type": "assistant_message", "content": f"🔄 JSON 验证失败，正在修复..."})
                                    render_architect_output(force=True)
                                    
                                    for retry_event in agent.run(correction_task, stream=True):
                                        retry_type = retry_event.get("type")
                                        
                                        # Handle streaming
                                        if retry_type == "streaming_delta":
                                            current_streaming_text = retry_event.get("accumulated", "")
                                            render_architect_output(force=False)
                                            continue
                                        
                                        elif retry_type == "streaming_complete":
                                            r_content = retry_event.get("content", "")
                                            if r_content:
                                                task_manager.add_chat_message(task.id, {"type": "assistant_message", "content": r_content})
                                                live_events.append({"type": "assistant_message", "content": r_content})
                                            current_streaming_text = ""
                                            render_architect_output(force=True)
                                            continue
                                        
                                        # Save and display other events
                                        task_manager.add_chat_message(task.id, retry_event)
                                        live_events.append(retry_event)
                                        render_architect_output(force=True)
                                    continue
                                
                                # Trigger slide generation
                                handle_phase_complete(task, "architect", result_data.get("summary", ""), live_container)
                                break
    
    except Exception as e:
        if live_container:
            with live_container.container():
                st.error(f"Architect 阶段出错: {e}")
    
    finally:
        # Restore original prompt (optional, since agent is cached)
        pass


def trigger_slide_generation(task: Task, live_container=None):
    """
    Trigger the slide generation process after presentation_plan.json is written.
    
    This function:
    1. Reads the presentation_plan.json
    2. Creates empty slide templates
    3. Generates content for each slide concurrently
    """
    plan_path = Path(task.workspace_dir) / "slides" / "presentation_plan.json"
    
    if not plan_path.exists():
        if live_container:
            with live_container.container():
                st.error("未找到 presentation_plan.json")
        return
    
    # Parse the plan
    plan = parse_presentation_plan(plan_path)
    if not plan:
        if live_container:
            with live_container.container():
                st.error("无法解析 presentation_plan.json")
        return
    
    # Create slide generator
    generator = create_slide_generator(task)
    if not generator:
        if live_container:
            with live_container.container():
                st.error("无法创建 SlideGenerator")
        return
    
    slides_dir = Path(task.workspace_dir) / "slides"
    
    # Phase 2: Create framework
    if live_container:
        with live_container.container():
            st.info("📝 正在创建幻灯片框架...")
    
    try:
        generator.create_slide_framework(plan)
    except Exception as e:
        if live_container:
            with live_container.container():
                st.error(f"创建框架失败: {e}")
        return
    
    # Phase 3: Generate slides concurrently
    if live_container:
        with live_container.container():
            st.info("🎨 正在生成幻灯片内容...")
            progress_placeholder = st.empty()
    
    def create_designer_agent(system_prompt: str) -> Agent:
        return Agent(
            api_key=st.session_state.api_key,
            workspace_dir=task.workspace_dir,
            model=st.session_state.model,
            base_url=st.session_state.base_url if st.session_state.base_url else None,
            system_prompt_override=system_prompt,
            include_image_tool=True  # Enable image generation for Designer agents
        )
    
    # Run concurrent generation
    try:
        # Use asyncio to run the concurrent generation
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        stats = loop.run_until_complete(
            generator.generate_slides_concurrent(
                plan=plan,
                slides_dir=slides_dir,
                create_agent_func=create_designer_agent
            )
        )
        
        loop.close()
        
        # Show results
        if live_container:
            with live_container.container():
                if stats["failed"] == 0:
                    st.success(f"✅ 已生成 {stats['success']}/{stats['total']} 页幻灯片")
                else:
                    st.warning(
                        f"⚠️ 已生成 {stats['success']}/{stats['total']} 页，"
                        f"{stats['failed']} 页失败"
                    )
                    for err in stats.get("errors", []):
                        st.error(f"Slide {err['slide_id']}: {err['error']}")
        
        st.session_state.slide_generation_stats = stats
        st.session_state.preview_key += 1
        
    except Exception as e:
        if live_container:
            with live_container.container():
                st.error(f"生成幻灯片失败: {e}")


def regenerate_slide(task: Task, slide_index: int, feedback: str):
    """Regenerate a specific slide with user feedback."""
    slides_dir = get_slides_dir(task)
    if not slides_dir:
        st.error("未找到幻灯片目录")
        return
    
    # Get slide ID from manifest
    manifest_path = slides_dir / "manifest.json"
    if not manifest_path.exists():
        st.error("未找到 manifest.json")
        return
    
    try:
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        slides = manifest.get("slides", [])
        if slide_index >= len(slides):
            st.error("幻灯片索引无效")
            return
        
        slide_id = slides[slide_index].get("id")
    except Exception as e:
        st.error(f"读取 manifest 失败: {e}")
        return
    
    # Create generator and regenerate
    generator = create_slide_generator(task)
    if not generator:
        st.error("无法创建生成器")
        return
    
    def create_designer_agent(system_prompt: str) -> Agent:
        return Agent(
            api_key=st.session_state.api_key,
            workspace_dir=task.workspace_dir,
            model=st.session_state.model,
            base_url=st.session_state.base_url if st.session_state.base_url else None,
            system_prompt_override=system_prompt,
            include_image_tool=True  # Enable image generation for Designer agents
        )
    
    st.session_state.is_processing = True
    task_manager = st.session_state.task_manager
    
    try:
        for event in generator.regenerate_slide(
            slides_dir=slides_dir,
            slide_id=slide_id,
            user_feedback=feedback,
            create_agent_func=create_designer_agent
        ):
            event_type = event.get("type")
            
            if event_type == "error":
                st.error(event.get("error", "未知错误"))
            elif event_type == "task_completed":
                st.success("✅ 幻灯片已更新")
                st.session_state.preview_key += 1
    
    except Exception as e:
        st.error(f"重新生成失败: {e}")
    
    finally:
        st.session_state.is_processing = False
        st.rerun()


def refine_current_slide(task: Task, feedback: str, live_container=None):
    """Refine the currently selected slide with live streaming updates."""
    agent = get_or_create_agent(task)
    
    if agent is None:
        return
    
    refiner = SlideRefiner(agent)
    
    st.session_state.is_processing = True
    task_manager = st.session_state.task_manager
    
    # Track events for live display
    live_events = []
    current_streaming_text = ""
    
    # Flag to track if we should do a rerun
    should_rerun = True
    
    # Throttling for streaming updates to reduce WebSocket pressure
    last_render_time = 0
    RENDER_THROTTLE_MS = 300  # Only render every 300ms during streaming
    
    def render_live_events(force: bool = False):
        """Render all live events including streaming text.
        
        Args:
            force: If True, render regardless of throttle
        """
        nonlocal last_render_time
        
        if live_container is None:
            return
        
        # Apply throttling unless forced
        current_time = time.time() * 1000
        if not force and (current_time - last_render_time) < RENDER_THROTTLE_MS:
            return
        
        last_render_time = current_time
        
        try:
            with live_container.container():
                for evt in live_events:
                    render_chat_message(evt)
                
                if current_streaming_text:
                    # Truncate very long streaming text to reduce WebSocket payload
                    display_text = current_streaming_text
                    if len(display_text) > 2000:
                        display_text = display_text[-2000:] + "\n... (showing last 2000 chars)"
                    
                    st.markdown(f"""
                    <div class="chat-message assistant-message">
                        <strong>🤖 Assistant:</strong> <span style="color: #888;">(正在输入...)</span><br>
                        <pre style="white-space: pre-wrap; word-wrap: break-word;">{display_text}</pre>
                    </div>
                    """, unsafe_allow_html=True)
        except Exception:
            # Ignore rendering errors (e.g., WebSocket closed)
            # The task results are still saved to task_manager
            pass
    
    try:
        for event in refiner.refine_slide(
            task.html_file,
            task.selected_slide,
            feedback
        ):
            event_type = event.get("type")
            
            # Handle streaming events with throttling
            if event_type == "streaming_delta":
                current_streaming_text = event.get("accumulated", "")
                render_live_events(force=False)  # Throttled
                continue
            
            elif event_type == "streaming_complete":
                # Streaming finished, save the complete message to history
                complete_content = event.get("content", "")
                if complete_content:
                    # Create an assistant_message event for the complete response
                    assistant_event = {"type": "assistant_message", "content": complete_content}
                    task_manager.add_chat_message(task.id, assistant_event)
                    live_events.append(assistant_event)
                current_streaming_text = ""
                render_live_events(force=True)
                continue
            
            # Convert ToolCallInfo to dict for serialization
            if event_type in ["tool_call", "tool_result"]:
                tc = event.get("tool_call")
                if tc and not isinstance(tc, dict):
                    event = {
                        "type": event_type,
                        "tool_call": {
                            "id": tc.id,
                            "name": tc.name,
                            "arguments": tc.arguments,
                            "result": {
                                "success": tc.result.success if tc.result else False,
                                "data": tc.result.data if tc.result else None,
                                "error": tc.result.error if tc.result else None
                            } if tc.result else None
                        }
                    }
            
            # Add to task's chat history (this persists the result even if UI fails)
            task_manager.add_chat_message(task.id, event)
            live_events.append(event)
            render_live_events(force=True)  # Force render for non-streaming events
            
            if event_type == "tool_result":
                tc = event.get("tool_call")
                if tc:
                    tc_name = tc.get("name") if isinstance(tc, dict) else tc.name
                    if tc_name == "write_file":
                        st.session_state.preview_key += 1
    
    except Exception as e:
        # Check if it's a connection/WebSocket error that we can safely ignore
        error_str = str(e).lower()
        is_connection_error = any(keyword in error_str for keyword in [
            'websocket', 'connection', 'stream', 'closed', 'eof'
        ])
        
        if is_connection_error:
            # Connection was lost - results are already saved to task_manager
            # Don't try to render error or rerun since connection is gone
            should_rerun = False
        else:
            # Real error - record it
            try:
                error_event = {"type": "error", "error": str(e)}
                task_manager.add_chat_message(task.id, error_event)
                live_events.append(error_event)
                render_live_events(force=True)
            except Exception:
                # Ignore errors during error handling (connection may be closed)
                pass
    
    finally:
        st.session_state.is_processing = False
        
        # Try to clean up and rerun, but handle errors gracefully
        if should_rerun:
            try:
                # Small delay to let pending WebSocket messages drain
                time.sleep(0.1)
                
                if live_container:
                    live_container.empty()
                st.rerun()
            except Exception:
                # Rerun failed (e.g., WebSocket closed) - that's OK, state is saved
                pass


# ============================================================================
# Streaming Dialog Component
# ============================================================================

def render_streaming_dialog():
    """Render the floating streaming dialog for LLM responses."""
    if not st.session_state.get("show_streaming_dialog", False):
        return
    
    # Get the streaming content
    streaming_content = st.session_state.get("streaming_dialog_content", [])
    current_text = st.session_state.get("streaming_current_text", "")
    
    # Build the dialog HTML
    messages_html = ""
    for msg in streaming_content[-10:]:  # Show last 10 messages
        msg_type = msg.get("type", "")
        if msg_type == "user_message":
            messages_html += f'<div class="chat-msg user">{msg.get("content", "")}</div>'
        elif msg_type == "assistant_message":
            content = msg.get("content", "")
            if len(content) > 500:
                content = content[:500] + "..."
            messages_html += f'<div class="chat-msg assistant">{content}</div>'
        elif msg_type == "tool_call":
            tc = msg.get("tool_call", {})
            name = tc.get("name", "") if isinstance(tc, dict) else tc.name
            messages_html += f'<div class="chat-msg tool"><span class="tool-badge">🔧 {name}</span></div>'
        elif msg_type == "tool_result":
            tc = msg.get("tool_call", {})
            result = tc.get("result", {}) if isinstance(tc, dict) else tc.result
            success = result.get("success", False) if isinstance(result, dict) else (result.success if result else False)
            if success:
                messages_html += '<div class="chat-msg success">✅ 执行成功</div>'
            else:
                error = result.get("error", "") if isinstance(result, dict) else (result.error if result else "")
                messages_html += f'<div class="chat-msg error">❌ {error[:100]}</div>'
    
    # Add current streaming text
    if current_text:
        display_text = current_text[-800:] if len(current_text) > 800 else current_text
        messages_html += f'''
        <div class="chat-msg assistant" style="border-left-color: #2196f3;">
            <span style="color: #888; font-size: 11px;">正在输入...</span><br>
            <pre style="margin: 4px 0 0 0; white-space: pre-wrap; font-size: 12px;">{display_text}</pre>
        </div>
        '''
    
    dialog_html = f'''
    <div class="stream-dialog" id="streamDialog">
        <div class="stream-dialog-header">
            <span class="stream-dialog-title">🤖 AI 响应</span>
            <button class="stream-dialog-close" onclick="document.getElementById('streamDialog').style.display='none'">✕</button>
        </div>
        <div class="stream-dialog-body">
            {messages_html if messages_html else '<p style="color: #94a3b8; margin: 0;">等待响应...</p>'}
        </div>
    </div>
    '''
    
    st.markdown(dialog_html, unsafe_allow_html=True)


def render_left_panel():
    """Render the left panel with task management."""
    task_manager = st.session_state.task_manager
    tasks = task_manager.list_tasks()
    active_task = task_manager.get_active_task()
    
    # Section: Task Management
    st.markdown('<div class="side-title">任务管理</div>', unsafe_allow_html=True)
    
    # Task list header with new task button
    col1, col2 = st.columns([3, 2])
    with col1:
        st.markdown("**任务列表**")
    with col2:
        if st.button("＋ 新建任务", key="new_task_btn", use_container_width=True):
            st.session_state.show_new_task_dialog = True
            st.rerun()
    
    # New task dialog
    if st.session_state.show_new_task_dialog:
        with st.container():
            st.markdown("---")
            if st.session_state.copy_in_progress:
                st.info("⏳ 正在复制文件...")
            elif not st.session_state.pending_source_dir:
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("📂 选择目录", use_container_width=True, type="primary"):
                        handle_directory_selection()
                        st.rerun()
                with col2:
                    if st.button("取消", use_container_width=True):
                        st.session_state.show_new_task_dialog = False
                        st.rerun()
            else:
                source_dir = st.session_state.pending_source_dir
                st.caption(f"📁 {source_dir}")
                
                scan_result = st.session_state.pending_scan_result
                if scan_result:
                    st.caption(f"📊 {scan_result.total_files} 文件, {scan_result.total_size_mb:.1f} MB")
                
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("✅ 确认", use_container_width=True, type="primary"):
                        create_task_with_copy()
                        st.rerun()
                with col2:
                    if st.button("❌ 取消", use_container_width=True):
                        st.session_state.pending_source_dir = None
                        st.session_state.pending_pick_result = None
                        st.session_state.pending_scan_result = None
                        st.session_state.show_new_task_dialog = False
                        st.rerun()
            st.markdown("---")
    
    # Task list
    if not tasks:
        st.caption("暂无任务")
    else:
        for task in tasks:
            is_active = active_task and task.id == active_task.id
            
            col1, col2 = st.columns([5, 1])
            with col1:
                btn_type = "primary" if is_active else "secondary"
                icon = "✓" if is_active else "○"
                if st.button(
                    f"{icon} {task.name}",
                    key=f"task_{task.id}",
                    use_container_width=True,
                    type=btn_type
                ):
                    if not is_active:
                        task_manager.switch_task(task.id)
                        st.session_state.preview_key += 1
                        st.session_state.show_plan_editor = False
                        st.session_state.pending_presentation_plan = None
                        st.session_state.grid_expanded_slide = None
                        sync_phase_with_task()
                        st.rerun()
            
            with col2:
                if st.button("🗑", key=f"del_{task.id}"):
                    task_manager.delete_task(task.id)
                    if task.id in st.session_state.agents:
                        del st.session_state.agents[task.id]
                    st.rerun()
    
    st.markdown("---")
    
    # Section: Current Task Settings
    if active_task:
        st.markdown('<div class="side-title">当前任务设置</div>', unsafe_allow_html=True)
        
        # Task name
        new_name = st.text_input(
            "任务名称",
            value=active_task.name,
            key="left_task_name"
        )
        if new_name != active_task.name:
            task_manager.update_task(active_task.id, name=new_name)
        
        # HTML file path
        new_html = st.text_input(
            "HTML 文件路径",
            value=active_task.html_file,
            key="left_html_path",
            help="相对于工作目录"
        )
        if new_html != active_task.html_file:
            task_manager.update_task(active_task.id, html_file=new_html)
            st.session_state.preview_key += 1


def render_right_panel():
    """Render the right panel with main input area on top and streaming output below."""
    task = get_current_task()
    
    # Template definitions
    templates = {
        "年度总结": "请为公司年度总结生成 PPT：经营指标、亮点、团队成就、问题复盘、来年规划。建议 12-18 页。",
        "产品发布会": "新品发布会：愿景定位、用户痛点、功能演示、技术亮点、路线图、价格与计划、Q&A。",
        "项目汇报": "项目阶段汇报：目标、里程碑、当前进度、风险/对策、资源需求、下一步计划。",
        "商业计划书": "商业计划书：市场分析、商业模式、产品方案、竞争壁垒、财务预测、团队与融资。"
    }
    template_list = list(templates.items())
    
    # Check if a template was selected (before widget is rendered)
    selected_template_value = st.session_state.get("selected_template_value", "")
    if selected_template_value:
        st.session_state.selected_template_value = ""  # Clear it
    
    # ========== TOP SECTION: Input Area ==========
    # Headline
    st.markdown('<div class="headline">描述你的想法</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-headline">AI将帮助你生成完整的演示文稿</div>', unsafe_allow_html=True)
    
    # Main text area - use default value from template if selected
    default_value = selected_template_value if selected_template_value else ""
    user_idea = st.text_area(
        "your_idea",
        value=default_value,
        placeholder="例如：制作一份关于公司2024年度总结的PPT，包括业绩数据、团队成就和未来规划……",
        height=150,
        label_visibility="collapsed",
        key="main_idea_input"
    )
    
    # Button row: Generate button + Quick chips in one line
    col_btn, col_chip1, col_chip2, col_chip3, col_chip4 = st.columns([1.5, 1, 1, 1, 1])
    
    with col_btn:
        # Generate button - disabled if no input or processing
        can_generate = bool(user_idea.strip()) and not st.session_state.is_processing and task is not None
        
        if st.button(
            "🎨 生成PPT",
            type="primary",
            use_container_width=True,
            disabled=not can_generate
        ):
            if task and user_idea.strip():
                st.session_state.pending_generation_message = user_idea.strip()
    
    with col_chip1:
        if st.button(template_list[0][0], key="chip_0", use_container_width=True):
            st.session_state.selected_template_value = template_list[0][1]
            st.rerun()
    
    with col_chip2:
        if st.button(template_list[1][0], key="chip_1", use_container_width=True):
            st.session_state.selected_template_value = template_list[1][1]
            st.rerun()
    
    with col_chip3:
        if st.button(template_list[2][0], key="chip_2", use_container_width=True):
            st.session_state.selected_template_value = template_list[2][1]
            st.rerun()
    
    with col_chip4:
        if st.button(template_list[3][0], key="chip_3", use_container_width=True):
            st.session_state.selected_template_value = template_list[3][1]
            st.rerun()
    
    st.markdown("---")
    
    # ========== BOTTOM SECTION: Streaming Output Area ==========
    st.markdown("**🤖 AI 响应**")
    
    # Create a container for streaming output
    streaming_container = st.container()
    
    # If there's a pending generation, process it
    if st.session_state.get("pending_generation_message") and task:
        message = st.session_state.pending_generation_message
        st.session_state.pending_generation_message = None
        process_user_message_inline(task, message, streaming_container)
    
    # Show existing chat history or placeholder
    with streaming_container:
        if task and task.chat_history:
            # Show last few messages
            for event in task.chat_history[-6:]:
                render_inline_message(event)
        elif not st.session_state.is_processing:
            st.markdown(
                '<div style="color: #94a3b8; padding: 20px; text-align: center;">'
                '💬 输入您的想法并点击生成按钮，AI响应将在这里显示'
                '</div>',
                unsafe_allow_html=True
            )


def render_inline_message(event: dict):
    """Render a chat message inline (not in floating dialog)."""
    event_type = event.get("type")
    
    if event_type == "user_message":
        st.markdown(f'''
        <div class="chat-msg user">
            <strong>👤 您:</strong> {event.get("content", "")[:200]}{"..." if len(event.get("content", "")) > 200 else ""}
        </div>
        ''', unsafe_allow_html=True)
    
    elif event_type == "assistant_message":
        content = event.get("content", "")
        if len(content) > 300:
            content = content[:300] + "..."
        st.markdown(f'''
        <div class="chat-msg assistant">
            <strong>🤖 AI:</strong> {content}
        </div>
        ''', unsafe_allow_html=True)
    
    elif event_type == "tool_call":
        tc = event.get("tool_call", {})
        name = tc.get("name", "") if isinstance(tc, dict) else tc.name
        st.markdown(f'''
        <div class="chat-msg tool">
            <span class="tool-badge">🔧 {name}</span>
        </div>
        ''', unsafe_allow_html=True)
    
    elif event_type == "tool_result":
        tc = event.get("tool_call", {})
        result = tc.get("result", {}) if isinstance(tc, dict) else tc.result
        success = result.get("success", False) if isinstance(result, dict) else (result.success if result else False)
        if success:
            st.markdown('<div class="chat-msg success">✅ 执行成功</div>', unsafe_allow_html=True)
        else:
            error = result.get("error", "") if isinstance(result, dict) else (result.error if result else "")
            st.markdown(f'<div class="chat-msg error">❌ {error[:100]}</div>', unsafe_allow_html=True)
    
    elif event_type == "error":
        st.markdown(f'''
        <div class="chat-msg error">
            ❌ {event.get("error", "")}
        </div>
        ''', unsafe_allow_html=True)
    
    elif event_type == "task_completed":
        st.markdown(f'''
        <div class="chat-msg success">
            ✨ {event.get("result", "完成")}
        </div>
        ''', unsafe_allow_html=True)


def process_user_message_inline(task: Task, message: str, container):
    """Process user message and show streaming output inline in the container."""
    st.session_state.is_processing = True
    
    agent = get_or_create_agent(task)
    if agent is None:
        st.session_state.is_processing = False
        return
    
    task_manager = st.session_state.task_manager
    
    # Add user message
    user_event = {"type": "user_message", "content": message}
    task_manager.add_chat_message(task.id, user_event)
    
    # Track streaming state
    live_events = [user_event]
    current_streaming_text = ""
    last_render_time = 0
    RENDER_THROTTLE_MS = 200
    
    def render_live():
        """Render current streaming state."""
        nonlocal last_render_time
        current_time = time.time() * 1000
        if current_time - last_render_time < RENDER_THROTTLE_MS:
            return
        last_render_time = current_time
        
        try:
            with container:
                for evt in live_events[-8:]:
                    render_inline_message(evt)
                
                if current_streaming_text:
                    display_text = current_streaming_text[-500:] if len(current_streaming_text) > 500 else current_streaming_text
                    st.markdown(f'''
                    <div class="chat-msg assistant" style="border-left-color: #2196f3;">
                        <strong>🤖 AI:</strong> <span style="color: #888;">(正在生成...)</span><br>
                        <pre style="white-space: pre-wrap; margin: 4px 0 0 0; font-size: 12px;">{display_text}</pre>
                    </div>
                    ''', unsafe_allow_html=True)
        except:
            pass
    
    try:
        for event in agent.run(message, stream=True):
            event_type = event.get("type")
            
            if event_type == "streaming_delta":
                current_streaming_text = event.get("accumulated", "")
                render_live()
                continue
            
            elif event_type == "streaming_complete":
                content = event.get("content", "")
                if content:
                    assistant_event = {"type": "assistant_message", "content": content}
                    task_manager.add_chat_message(task.id, assistant_event)
                    live_events.append(assistant_event)
                current_streaming_text = ""
                render_live()
                continue
            
            # Convert ToolCallInfo to dict
            if event_type in ["tool_call", "tool_result"]:
                tc = event.get("tool_call")
                if tc and not isinstance(tc, dict):
                    event = {
                        "type": event_type,
                        "tool_call": {
                            "id": tc.id,
                            "name": tc.name,
                            "arguments": tc.arguments,
                            "result": {
                                "success": tc.result.success if tc.result else False,
                                "data": tc.result.data if tc.result else None,
                                "error": tc.result.error if tc.result else None
                            } if tc.result else None
                        }
                    }
            
            task_manager.add_chat_message(task.id, event)
            live_events.append(event)
            render_live()
            
            # Check for phase transitions
            if event_type == "tool_result":
                tc = event.get("tool_call")
                if tc:
                    tc_name = tc.get("name") if isinstance(tc, dict) else tc.name
                    if tc_name == "write_file":
                        st.session_state.preview_key += 1
                        tc_args = tc.get("arguments") if isinstance(tc, dict) else tc.arguments
                        if tc_args:
                            files_written = tc_args.get("files", [])
                            for file_entry in files_written:
                                file_path = file_entry.get("path", "") if isinstance(file_entry, dict) else ""
                                if "presentation_plan.json" in file_path:
                                    handle_phase_complete(task, "architect", "", None)
                    elif tc_name == "phase_complete":
                        tc_result = tc.get("result") if isinstance(tc, dict) else tc.result
                        if tc_result:
                            result_data = tc_result.get("data") if isinstance(tc_result, dict) else tc_result.data
                            if result_data and result_data.get("phase_complete"):
                                phase = result_data.get("phase", "")
                                summary = result_data.get("summary", "")
                                handle_phase_complete(task, phase, summary, None)
                                st.session_state.is_processing = False
                                break
            
            if not st.session_state.is_processing:
                break
    
    except Exception as e:
        error_event = {"type": "error", "error": str(e)}
        task_manager.add_chat_message(task.id, error_event)
        live_events.append(error_event)
    
    finally:
        st.session_state.is_processing = False
        st.rerun()


def process_user_message_with_dialog(task: Task, message: str):
    """Process user message and show results in streaming dialog."""
    st.session_state.is_processing = True
    
    agent = get_or_create_agent(task)
    if agent is None:
        st.session_state.is_processing = False
        return
    
    task_manager = st.session_state.task_manager
    
    # Add user message to dialog content
    user_event = {"type": "user_message", "content": message}
    task_manager.add_chat_message(task.id, user_event)
    st.session_state.streaming_dialog_content.append(user_event)
    
    try:
        for event in agent.run(message, stream=True):
            event_type = event.get("type")
            
            if event_type == "streaming_delta":
                st.session_state.streaming_current_text = event.get("accumulated", "")
                continue
            
            elif event_type == "streaming_complete":
                content = event.get("content", "")
                if content:
                    assistant_event = {"type": "assistant_message", "content": content}
                    task_manager.add_chat_message(task.id, assistant_event)
                    st.session_state.streaming_dialog_content.append(assistant_event)
                st.session_state.streaming_current_text = ""
                continue
            
            # Convert ToolCallInfo to dict
            if event_type in ["tool_call", "tool_result"]:
                tc = event.get("tool_call")
                if tc and not isinstance(tc, dict):
                    event = {
                        "type": event_type,
                        "tool_call": {
                            "id": tc.id,
                            "name": tc.name,
                            "arguments": tc.arguments,
                            "result": {
                                "success": tc.result.success if tc.result else False,
                                "data": tc.result.data if tc.result else None,
                                "error": tc.result.error if tc.result else None
                            } if tc.result else None
                        }
                    }
            
            task_manager.add_chat_message(task.id, event)
            st.session_state.streaming_dialog_content.append(event)
            
            # Check for phase transitions
            if event_type == "tool_result":
                tc = event.get("tool_call")
                if tc:
                    tc_name = tc.get("name") if isinstance(tc, dict) else tc.name
                    if tc_name == "write_file":
                        st.session_state.preview_key += 1
                        tc_args = tc.get("arguments") if isinstance(tc, dict) else tc.arguments
                        if tc_args:
                            files_written = tc_args.get("files", [])
                            for file_entry in files_written:
                                file_path = file_entry.get("path", "") if isinstance(file_entry, dict) else ""
                                if "presentation_plan.json" in file_path:
                                    handle_phase_complete(task, "architect", "", None)
                    elif tc_name == "phase_complete":
                        tc_result = tc.get("result") if isinstance(tc, dict) else tc.result
                        if tc_result:
                            result_data = tc_result.get("data") if isinstance(tc_result, dict) else tc_result.data
                            if result_data and result_data.get("phase_complete"):
                                phase = result_data.get("phase", "")
                                summary = result_data.get("summary", "")
                                handle_phase_complete(task, phase, summary, None)
                                st.session_state.is_processing = False
                                break
            
            if not st.session_state.is_processing:
                break
    
    except Exception as e:
        error_event = {"type": "error", "error": str(e)}
        task_manager.add_chat_message(task.id, error_event)
        st.session_state.streaming_dialog_content.append(error_event)
    
    finally:
        st.session_state.is_processing = False
        st.rerun()


# ============================================================================
# Main App
# ============================================================================

def main():
    """Main application entry point."""
    # Initialize session state
    init_session_state()
    
    # Sync phase with current task state
    sync_phase_with_task()
    
    # Get current phase
    current_phase = st.session_state.current_phase
    
    # Route based on phase
    if current_phase in ["designing", "completed"]:
        # Full-screen grid view for slide editing
        render_grid_view()
    
    elif current_phase == "editing_plan":
        # Plan editor view
        render_plan_editor()
    
    else:
        # Main collecting/input view - Apple style layout
        # Two-column layout: 25% left (narrow), 75% right (wide)
        col_left, col_right = st.columns([1, 3])
        
        with col_left:
            render_left_panel()
        
        with col_right:
            render_right_panel()
        
        # Footer
        st.markdown('''
        <div class="footer-text">
            <span>提示：内容会在本地保存，便于下次继续。</span>
            <a href="#" style="color: #64748b;">导出当前配置</a>
        </div>
        ''', unsafe_allow_html=True)
    
    # Render streaming dialog if active
    render_streaming_dialog()
    
    # Processing indicator toast
    if st.session_state.is_processing:
        st.toast("🔄 AI 正在工作...", icon="⏳")


if __name__ == "__main__":
    main()
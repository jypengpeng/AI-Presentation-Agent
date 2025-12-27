"""
Streamlit UI for the Autonomous Presentation Agent

Features:
- Left sidebar: API Key settings, task management, task settings
- Main area left: Chat log with highlighted tool calls
- Main area right: Real-time HTML preview
- Multi-task support with persistence
"""

import os
import json
import re
import shutil
import time
import asyncio
import threading
from datetime import datetime
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
    page_title="AI Presentation Agent",
    page_icon="🎨",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better styling
st.markdown("""
<style>
    /* Main container */
    .main .block-container {
        padding-top: 1rem;
        padding-bottom: 1rem;
    }
    
    /* Chat message styling */
    .chat-message {
        padding: 1rem;
        border-radius: 0.5rem;
        margin-bottom: 0.5rem;
    }
    
    .user-message {
        background-color: #e3f2fd;
        border-left: 4px solid #2196f3;
    }
    
    .assistant-message {
        background-color: #f5f5f5;
        border-left: 4px solid #4caf50;
    }
    
    .tool-call {
        background-color: #fff3e0;
        border-left: 4px solid #ff9800;
        font-family: monospace;
        font-size: 0.85rem;
    }
    
    .tool-result-success {
        background-color: #e8f5e9;
        border-left: 4px solid #4caf50;
        font-family: monospace;
        font-size: 0.85rem;
    }
    
    .tool-result-error {
        background-color: #ffebee;
        border-left: 4px solid #f44336;
        font-family: monospace;
        font-size: 0.85rem;
    }
    
    .error-message {
        background-color: #ffebee;
        border-left: 4px solid #f44336;
        padding: 1rem;
        border-radius: 0.5rem;
    }
    
    .completion-message {
        background-color: #e8f5e9;
        border-left: 4px solid #4caf50;
        padding: 1rem;
        border-radius: 0.5rem;
    }
    
    /* Sidebar styling */
    .sidebar .sidebar-content {
        padding: 1rem;
    }
    
    /* Preview iframe */
    .preview-container {
        border: 1px solid #ddd;
        border-radius: 0.5rem;
        overflow: hidden;
    }
    
    /* Tool name badge */
    .tool-badge {
        display: inline-block;
        background-color: #ff9800;
        color: white;
        padding: 0.2rem 0.5rem;
        border-radius: 0.25rem;
        font-weight: bold;
        margin-right: 0.5rem;
    }
    
    /* Task list styling */
    .task-item {
        padding: 0.5rem;
        border-radius: 0.25rem;
        margin-bottom: 0.25rem;
        cursor: pointer;
    }
    
    .task-item:hover {
        background-color: rgba(255, 255, 255, 0.1);
    }
    
    .task-item.active {
        background-color: rgba(33, 150, 243, 0.2);
        border-left: 3px solid #2196f3;
    }
    
    /* Grid view card styling */
    .slide-card {
        border: 1px solid #ddd;
        border-radius: 0.5rem;
        padding: 0.5rem;
        margin-bottom: 0.5rem;
        background-color: #fafafa;
        transition: all 0.2s ease;
    }
    
    .slide-card:hover {
        border-color: #2196f3;
        box-shadow: 0 2px 8px rgba(33, 150, 243, 0.2);
    }
    
    .slide-card.status-pending {
        border-left: 4px solid #9e9e9e;
    }
    
    .slide-card.status-generating {
        border-left: 4px solid #2196f3;
        animation: pulse 1.5s infinite;
    }
    
    .slide-card.status-completed {
        border-left: 4px solid #4caf50;
    }
    
    .slide-card.status-failed {
        border-left: 4px solid #f44336;
    }
    
    .slide-card.status-modified {
        border-left: 4px solid #ff9800;
    }
    
    @keyframes pulse {
        0% { opacity: 1; }
        50% { opacity: 0.7; }
        100% { opacity: 1; }
    }
    
    .slide-card-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 0.5rem;
    }
    
    .slide-card-title {
        font-weight: bold;
        font-size: 0.9rem;
        color: #333;
    }
    
    .slide-card-type {
        font-size: 0.75rem;
        color: #666;
        background-color: #e0e0e0;
        padding: 0.1rem 0.4rem;
        border-radius: 0.25rem;
    }
    
    .slide-card-preview {
        height: 120px;
        background-color: #f5f5f5;
        border-radius: 0.25rem;
        display: flex;
        align-items: center;
        justify-content: center;
        overflow: hidden;
    }
    
    .slide-card-preview iframe {
        width: 100%;
        height: 100%;
        border: none;
        pointer-events: none;
    }
    
    .status-icon {
        font-size: 1.2rem;
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


def apply_layout_changes_to_html(slide_id: str, selector: str, layout: dict, html_content: str) -> str:
    x = float(layout.get('x', 0) or 0)
    y = float(layout.get('y', 0) or 0)
    width = layout.get('width')
    height = layout.get('height')

    style_parts = [f"transform: translate({x}px, {y}px)"]
    if width is not None:
        try:
            style_parts.append(f"width: {float(width)}px")
        except Exception:
            pass
    if height is not None:
        try:
            style_parts.append(f"height: {float(height)}px")
        except Exception:
            pass

    style_str = '; '.join(style_parts)
    style_id = f"streamlit_layout_{slide_id}_{abs(hash(selector)) % 100000}"
    existing_style_pattern = rf'<style[^>]*id=["\']{style_id}["\'][^>]*>'
    style_tag = f'<style id="{style_id}">{selector} {{{style_str} !important; transform-origin: top left !important;}}</style>'

    if re.search(existing_style_pattern, html_content):
        html_content = re.sub(
            rf'<style[^>]*id=["\']{style_id}["\'][^>]*>.*?</style>',
            style_tag,
            html_content,
            flags=re.DOTALL
        )
    else:
        if '</head>' in html_content:
            html_content = html_content.replace('</head>', style_tag + '</head>')
        elif '</body>' in html_content:
            html_content = html_content.replace('</body>', style_tag + '</body>')
        else:
            html_content = style_tag + html_content

    return html_content


def inject_editing_support(html_content: str, slide_id: str, selected_selector: Optional[str] = None, enabled: bool = True) -> str:
    """在 HTML 中注入编辑支持，包括元素选择和锁定功能"""
    from datetime import datetime
    
    # 检查是否需要 Chart.js（如果内容中有图表）
    needs_chart_js = 'canvas' in html_content.lower() and ('chart' in html_content.lower() or 'Chart(' in html_content or 'new Chart' in html_content)
    chart_js_loaded = 'cdn.jsdelivr.net/npm/chart.js' in html_content or 'chart.js' in html_content.lower()
    
    # 如果需要 Chart.js 但还没有加载，添加它（必须在图表初始化脚本之前）
    if needs_chart_js and not chart_js_loaded:
        # 使用正确的 Chart.js CDN 链接，避免 source map 404 错误
        chart_js_script = '<script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>'
        # 查找第一个 <script> 标签，在它之前插入 Chart.js
        script_match = re.search(r'<script', html_content)
        if script_match:
            insert_pos = script_match.start()
            html_content = html_content[:insert_pos] + chart_js_script + html_content[insert_pos:]
        else:
            html_content = chart_js_script + html_content
    
    editing_script = f"""
    <!-- Interact.js 库 - 用于拖拽和调整大小 -->
    <script src="https://cdn.jsdelivr.net/npm/interactjs/dist/interact.min.js"></script>
    
    <style>
        .editable-element {{
            cursor: {'move' if enabled else 'default'} !important;
            transition: all 0.2s ease;
            border: 2px solid transparent;
            padding: 2px;
            margin: -2px;
            position: relative !important;
            user-select: none;
        }}
        .editable-element.resizing {{
            cursor: nwse-resize !important;
        }}
        .editable-element:hover {{
            border-color: #2196f3 !important;
            background-color: rgba(33, 150, 243, 0.1) !important;
        }}
        .editable-element.dragging {{
            opacity: 0.5;
            z-index: 1000;
        }}
    </style>
    <script>
    (function() {{
        const slideId = '{slide_id}';
        const layoutEnabled = {str(bool(enabled)).lower()};

        function disableAllInteractions() {{
            try {{
                if (typeof interact === 'undefined') return;
                document.querySelectorAll('.editable-element').forEach((el) => {{
                    try {{
                        interact(el).unset();
                    }} catch(e) {{
                        // ignore
                    }}
                }});
            }} catch(e) {{
                // ignore
            }}
        }}

        function emitLayout(target, selector) {{
            try {{
                console.log('[LAYOUT] emitLayout called:', {{ selector: selector, target: target.tagName }});
                const x = parseFloat(target.getAttribute('data-x')) || 0;
                const y = parseFloat(target.getAttribute('data-y')) || 0;
                const rect = target.getBoundingClientRect();
                const payload = {{
                    slide_id: slideId,
                    selector: selector,
                    x: x,
                    y: y,
                    width: Math.round(rect.width),
                    height: Math.round(rect.height),
                    ts: Date.now()
                }};
                console.log('[LAYOUT] Payload created:', payload);

                let sentToTop = false;
                let sentToParent = false;
                
                try {{
                    if (window.top && window.top !== window) {{
                        window.top.postMessage({{ type: 'layout_changed', data: payload }}, '*');
                        sentToTop = true;
                        console.log('[LAYOUT] ✅ Sent to window.top');
                    }}
                }} catch(e) {{
                    console.error('[LAYOUT] ❌ Failed to send to window.top:', e);
                }}

                try {{
                    if (window.parent && window.parent !== window) {{
                        window.parent.postMessage({{ type: 'layout_changed', data: payload }}, '*');
                        sentToParent = true;
                        console.log('[LAYOUT] ✅ Sent to window.parent');
                    }}
                }} catch(e) {{
                    console.error('[LAYOUT] ❌ Failed to send to window.parent:', e);
                }}
                
                if (!sentToTop && !sentToParent) {{
                    console.warn('[LAYOUT] ⚠️ Message not sent! window.top === window:', window.top === window, 'window.parent === window:', window.parent === window);
                }}
            }} catch(e) {{
                console.error('[LAYOUT] ❌ Error in emitLayout:', e);
            }}
        }}
        
        function generateSelector(element) {{
            if (element.id) {{
                return '#' + element.id;
            }}
            
            function getPath(el) {{
                const path = [];
                while (el && el.nodeType === 1) {{
                    let selector = el.tagName.toLowerCase();
                    
                    if (el.className && typeof el.className === 'string') {{
                        const classes = el.className.split(' ').filter(c => c && c !== 'editable-element' && c !== 'selected');
                        if (classes.length > 0) {{
                            selector += '.' + classes.join('.');
                        }}
                    }}
                    
                    const siblings = Array.from(el.parentElement ? el.parentElement.children : []);
                    const sameTagSiblings = siblings.filter(s => s.tagName === el.tagName);
                    const index = sameTagSiblings.indexOf(el);
                    
                    if (sameTagSiblings.length > 1) {{
                        selector += ':nth-of-type(' + (index + 1) + ')';
                    }}
                    
                    path.unshift(selector);
                    el = el.parentElement;
                    
                    if (path.length >= 5) break;
                }}
                return path.join(' > ');
            }}
            
            if (element.className && typeof element.className === 'string') {{
                const classes = element.className.split(' ').filter(c => c && c !== 'editable-element' && c !== 'selected');
                if (classes.length > 0) {{
                    const tagName = element.tagName.toLowerCase();
                    const siblings = Array.from(element.parentElement ? element.parentElement.children : []);
                    const sameTagSiblings = siblings.filter(s => s.tagName === element.tagName);
                    const index = sameTagSiblings.indexOf(element);
                    if (sameTagSiblings.length > 1) {{
                        return tagName + '.' + classes[0] + ':nth-of-type(' + (index + 1) + ')';
                    }} else {{
                        return tagName + '.' + classes[0];
                    }}
                }}
            }}
            
            const pathSelector = getPath(element);
            if (pathSelector) {{
                return pathSelector;
            }}
            
            const tagName = element.tagName.toLowerCase();
            const siblings = Array.from(element.parentElement ? element.parentElement.children : []);
            const sameTagSiblings = siblings.filter(s => s.tagName === element.tagName);
            const index = sameTagSiblings.indexOf(element);
            return tagName + ':nth-of-type(' + (index + 1) + ')';
        }}
        
        function makeEditable(element) {{
            if (element.classList.contains('editable-element')) return;
            
            element.classList.add('editable-element');
            const selector = generateSelector(element);
            element.setAttribute('data-selector', selector);
            
            if (!element.id && !element.getAttribute('data-element-id')) {{
                const elementId = 'elem_' + slideId + '_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
                element.setAttribute('data-element-id', elementId);
            }}
            
            // 添加点击选择功能
            element.addEventListener('click', function(e) {{
                // 如果正在编辑文字，不触发选择
                if (element.contentEditable === 'true') {{
                    return;
                }}
                e.stopPropagation();
                e.preventDefault();
                const elementId = element.id || element.getAttribute('data-element-id') || null;
                const tag = element.tagName.toLowerCase();
                const text = element.textContent || element.innerText || '';
                const styles = window.getComputedStyle(element);
                
                const selectedData = {{
                    slide_id: slideId,
                    selector: selector,
                    element_id: elementId,
                    tag: tag,
                    text: text.substring(0, 100),
                    styles: {{
                        fontFamily: styles.fontFamily,
                        fontSize: styles.fontSize,
                        color: styles.color,
                        backgroundColor: styles.backgroundColor,
                        fontWeight: styles.fontWeight,
                        textAlign: styles.textAlign
                    }}
                }};
                
                console.log('[EDIT] Element clicked:', selectedData);
                
                // 使用 postMessage 与父窗口通信（iframe 无法直接修改父窗口 URL）
                try {{
                    const message = {{
                        type: 'element_selected',
                        data: selectedData
                    }};
                    
                    if (window.top && window.top !== window) {{
                        window.top.postMessage(message, '*');
                        console.log('[EDIT] Sent message to window.top');
                    }} else if (window.parent && window.parent !== window) {{
                        window.parent.postMessage(message, '*');
                        console.log('[EDIT] Sent message to window.parent');
                    }} else {{
                        // 如果不在 iframe 中，直接设置 URL
                        const url = new URL(window.location.href);
                        url.searchParams.set('selected', JSON.stringify(selectedData));
                        url.searchParams.set('_t', Date.now().toString());
                        window.location.href = url.toString();
                    }}
                }} catch(e) {{
                    console.error('[EDIT] Failed to send message:', e);
                }}
            }}, true);
            
            // 添加双击编辑文字功能（仅在布局调整模式下）
            if (layoutEnabled) {{
                let doubleClickTimer = null;
                element.addEventListener('dblclick', function(e) {{
                    e.stopPropagation();
                    e.preventDefault();
                    
                    // 只允许文本元素编辑
                    const tag = element.tagName.toLowerCase();
                    const textElements = ['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'span', 'div', 'li', 'td', 'th', 'a', 'button', 'label'];
                    if (!textElements.includes(tag)) {{
                        return;
                    }}
                    
                    // 使元素可编辑
                    element.contentEditable = 'true';
                    element.style.outline = '2px solid #2196f3';
                    element.style.outlineOffset = '2px';
                    element.style.backgroundColor = 'rgba(33, 150, 243, 0.1)';
                    
                    // 聚焦并选中所有文字
                    element.focus();
                    if (window.getSelection) {{
                        const selection = window.getSelection();
                        const range = document.createRange();
                        range.selectNodeContents(element);
                        selection.removeAllRanges();
                        selection.addRange(range);
                    }}
                    
                    console.log('[EDIT] Element made editable:', selector);
                    
                    // 监听失去焦点事件，保存更改
                    function saveTextChange() {{
                        if (element.contentEditable === 'true') {{
                            const newText = element.textContent || element.innerText || '';
                            const elementId = element.id || element.getAttribute('data-element-id') || null;
                            
                            // 恢复不可编辑状态
                            element.contentEditable = 'false';
                            element.style.outline = '';
                            element.style.outlineOffset = '';
                            element.style.backgroundColor = '';
                            
                            // 发送文字更新消息
                            try {{
                                const message = {{
                                    type: 'text_changed',
                                    data: {{
                                        slide_id: slideId,
                                        selector: selector,
                                        element_id: elementId,
                                        new_text: newText
                                    }}
                                }};
                                
                                if (window.top && window.top !== window) {{
                                    window.top.postMessage(message, '*');
                                }} else if (window.parent && window.parent !== window) {{
                                    window.parent.postMessage(message, '*');
                                }}
                                console.log('[EDIT] Text changed, sent message:', newText.substring(0, 50));
                            }} catch(e) {{
                                console.error('[EDIT] Failed to send text change message:', e);
                            }}
                            
                            element.removeEventListener('blur', saveTextChange);
                            element.removeEventListener('keydown', handleKeyDown);
                        }}
                    }}
                    
                    // 处理回车键和ESC键
                    function handleKeyDown(e) {{
                        if (e.key === 'Enter' && !e.shiftKey) {{
                            e.preventDefault();
                            element.blur();
                        }} else if (e.key === 'Escape') {{
                            e.preventDefault();
                            element.textContent = element.getAttribute('data-original-text') || element.textContent;
                            element.blur();
                        }}
                    }}
                    
                    // 保存原始文字
                    element.setAttribute('data-original-text', element.textContent);
                    
                    // 添加事件监听器
                    element.addEventListener('blur', saveTextChange, {{ once: true }});
                    element.addEventListener('keydown', handleKeyDown);
                }});
            }}
            
            // 设置拖动和拉伸功能（等待 Interact.js 加载）
            function setupInteractForElement() {{
                console.log('[LAYOUT] setupInteractForElement called, layoutEnabled:', layoutEnabled, 'interact defined:', typeof interact !== 'undefined');
                if (!layoutEnabled) {{
                    console.log('[LAYOUT] ⚠️ layoutEnabled is false, skipping interact setup');
                    return; // 如果 layoutEnabled 为 false，不设置交互
                }}
                
                if (typeof interact !== 'undefined') {{
                    // Interact.js 已加载，立即设置
                    console.log('[LAYOUT] ✅ Setting up interact for element:', selector);
                    try {{
                        interact(element)
                            .draggable({{
                                allowFrom: null,
                                ignoreFrom: '.resize-handle',
                                onstart: function(event) {{
                                    console.log('[LAYOUT] 🎯 Drag started');
                                    event.target.classList.add('dragging');
                                }},
                                onmove: function(event) {{
                                    const target = event.target;
                                    const x = (parseFloat(target.getAttribute('data-x')) || 0) + event.dx;
                                    const y = (parseFloat(target.getAttribute('data-y')) || 0) + event.dy;
                                    target.style.transform = `translate(${{x}}px, ${{y}}px)`;
                                    target.setAttribute('data-x', x);
                                    target.setAttribute('data-y', y);
                                }},
                                onend: function(event) {{
                                    console.log('[LAYOUT] 🎯 Drag ended, calling emitLayout');
                                    event.target.classList.remove('dragging');
                                    emitLayout(event.target, selector);
                                }}
                            }})
                            .resizable({{
                                edges: {{ left: true, right: true, top: true, bottom: true }},
                                margin: 8,
                                listeners: {{
                                    start: function(event) {{
                                        event.target.classList.add('resizing');
                                    }},
                                    move: function(event) {{
                                        const target = event.target;
                                        let x = (parseFloat(target.getAttribute('data-x')) || 0);
                                        let y = (parseFloat(target.getAttribute('data-y')) || 0);
                                        target.style.width = event.rect.width + 'px';
                                        target.style.height = event.rect.height + 'px';
                                        x += event.deltaRect.left;
                                        y += event.deltaRect.top;
                                        target.style.transform = `translate(${{x}}px, ${{y}}px)`;
                                        target.setAttribute('data-x', x);
                                        target.setAttribute('data-y', y);
                                    }},
                                    end: function(event) {{
                                        console.log('[LAYOUT] 🎯 Resize ended, calling emitLayout');
                                        event.target.classList.remove('resizing');
                                        emitLayout(event.target, selector);
                                    }}
                                }},
                                modifiers: [
                                    interact.modifiers.restrictSize({{
                                        min: {{ width: 50, height: 20 }}
                                    }})
                                ]
                            }});
                        console.log('[EDIT] Interact.js setup for element:', selector);
                    }} catch(e) {{
                        console.error('[EDIT] Failed to setup interact:', e);
                    }}
                }} else {{
                    // Interact.js 还没加载，等待一下再试
                    setTimeout(setupInteractForElement, 50);
                }}
            }}
            
            // 立即尝试设置（如果 layoutEnabled 为 true）
            if (layoutEnabled) {{
                setupInteractForElement();
            }}
        }}
        
        function init() {{
            // 如果页面需要 Chart.js，等待它加载完成
            const needsChart = document.querySelector('canvas') && (document.querySelector('script[src*="chart"]') || document.body.innerHTML.includes('Chart(') || document.body.innerHTML.includes('new Chart'));
            if (needsChart && typeof Chart === 'undefined') {{
                // 等待 Chart.js 加载
                let attempts = 0;
                const checkChart = setInterval(function() {{
                    attempts++;
                    if (typeof Chart !== 'undefined' || attempts > 50) {{
                        clearInterval(checkChart);
                        if (attempts > 50) {{
                            console.warn('Chart.js not loaded after timeout');
                        }}
                        doInit();
                    }}
                }}, 100);
                return;
            }}
            
            doInit();
        }}
        
        function doInit() {{
            console.log('[EDIT] doInit called, layoutEnabled=' + layoutEnabled);
            console.log('[EDIT] interact available:', typeof interact !== 'undefined');
            
            const selectors = ['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'div', 'span', 'button', 'a', 'strong', 'em', 'small', 'li', 'ul', 'ol', 'img', 'svg', 'canvas'];
            let elementCount = 0;
            selectors.forEach(selector => {{
                document.querySelectorAll(selector).forEach(el => {{
                    if (el.closest('script') || el.closest('style') || el.closest('head')) return;
                    makeEditable(el);
                    elementCount++;
                }});
            }});
            console.log('[EDIT] Made ' + elementCount + ' elements editable');

            if (!layoutEnabled) {{
                console.log('[EDIT] layoutEnabled=false, disabling interactions');
                (function tryDisable(attempt) {{
                    try {{
                        if (typeof interact === 'undefined') {{
                            if (attempt < 20) setTimeout(() => tryDisable(attempt + 1), 50);
                            return;
                        }}
                        disableAllInteractions();
                        console.log('[EDIT] Interactions disabled');
                    }} catch(e) {{
                        console.error('[EDIT] Error disabling interactions:', e);
                    }}
                }})(0);
            }} else {{
                console.log('[EDIT] layoutEnabled=true, interactions should be enabled');
            }}
        }}
        
        // 延迟初始化，确保 Chart.js 和其他脚本先加载
        if (document.readyState === 'loading') {{
            document.addEventListener('DOMContentLoaded', function() {{
                setTimeout(init, 100);
            }});
        }} else {{
            setTimeout(init, 100);
        }}
    }})();
    </script>
    """
    
    if '</body>' in html_content:
        html_content = html_content.replace('</body>', editing_script + '</body>')
    else:
        html_content += editing_script
    
    return html_content


def apply_text_changes_to_html(slide_id: str, selector: str, new_text: str, html_content: str, element_id: str = None) -> str:
    """应用文字更改到 HTML 内容"""
    import html as html_module
    
    # 转义HTML特殊字符
    escaped_text = html_module.escape(new_text)
    
    if element_id:
        # 使用 element_id 查找元素（优先）
        element_id_pattern = rf'data-element-id=["\']{re.escape(element_id)}["\']'
        
        # 查找包含该 element_id 的开始标签
        start_tag_pattern = rf'<([^>]*{re.escape(element_id_pattern)}[^>]*)>'
        match = re.search(start_tag_pattern, html_content)
        
        if match:
            start_pos = match.start()
            start_tag = match.group(0)
            # 提取标签名
            tag_name_match = re.search(r'<(\w+)', start_tag)
            if tag_name_match:
                tag_name = tag_name_match.group(1)
                
                # 找到对应的结束标签
                # 从开始标签后开始查找
                search_start = match.end()
                depth = 1
                pos = search_start
                end_pos = -1
                
                while pos < len(html_content) and depth > 0:
                    # 查找下一个标签
                    next_open = html_content.find(f'<{tag_name}', pos)
                    next_close = html_content.find(f'</{tag_name}>', pos)
                    
                    if next_close == -1:
                        break
                    
                    if next_open != -1 and next_open < next_close:
                        # 找到嵌套的开始标签
                        depth += 1
                        pos = next_open + len(tag_name) + 1
                    else:
                        # 找到结束标签
                        depth -= 1
                        if depth == 0:
                            end_pos = next_close
                            break
                        pos = next_close + len(f'</{tag_name}>')
                
                if end_pos != -1:
                    # 替换标签内容
                    html_content = html_content[:match.end()] + escaped_text + html_content[end_pos:]
                    print(f"[TEXT] ✅ 使用 element_id 替换成功: {element_id}")
                    return html_content
    
    # 使用 selector 查找元素
    selector_pattern = rf'data-selector=["\']{re.escape(selector)}["\']'
    match = re.search(rf'<([^>]*{re.escape(selector_pattern)}[^>]*)>', html_content)
    
    if match:
        start_pos = match.start()
        start_tag = match.group(0)
        tag_name_match = re.search(r'<(\w+)', start_tag)
        if tag_name_match:
            tag_name = tag_name_match.group(1)
            
            # 找到对应的结束标签
            search_start = match.end()
            depth = 1
            pos = search_start
            end_pos = -1
            
            while pos < len(html_content) and depth > 0:
                next_open = html_content.find(f'<{tag_name}', pos)
                next_close = html_content.find(f'</{tag_name}>', pos)
                
                if next_close == -1:
                    break
                
                if next_open != -1 and next_open < next_close:
                    depth += 1
                    pos = next_open + len(tag_name) + 1
                else:
                    depth -= 1
                    if depth == 0:
                        end_pos = next_close
                        break
                    pos = next_close + len(f'</{tag_name}>')
            
            if end_pos != -1:
                html_content = html_content[:match.end()] + escaped_text + html_content[end_pos:]
                print(f"[TEXT] ✅ 使用 selector 替换成功: {selector}")
                return html_content
    
    print(f"[TEXT] ⚠️ 未找到匹配的元素，element_id={element_id}, selector={selector}")
    return html_content


def apply_element_style_changes_to_html(slide_id: str, selector: str, style_props: dict, html_content: str) -> str:
    style_parts = []
    if 'font_family' in style_props:
        style_parts.append(f"font-family: {style_props['font_family']}")
    if 'font_size' in style_props:
        style_parts.append(f"font-size: {style_props['font_size']}px")
    if 'color' in style_props:
        style_parts.append(f"color: {style_props['color']}")
    if 'background_color' in style_props:
        style_parts.append(f"background-color: {style_props['background_color']}")
    if 'pos_x' in style_props and 'pos_y' in style_props:
        style_parts.append("position: relative")
        style_parts.append(f"left: {style_props['pos_x']}%")
        style_parts.append(f"top: {style_props['pos_y']}%")
    if 'font_weight' in style_props:
        style_parts.append(f"font-weight: {style_props['font_weight']}")
    if 'text_align' in style_props:
        style_parts.append(f"text-align: {style_props['text_align']}")

    style_str = '; '.join(style_parts)
    element_id = style_props.get('element_id')
    final_selector = selector

    if element_id:
        element_id_pattern = rf'data-element-id=["\']{re.escape(element_id)}["\']'
        if re.search(element_id_pattern, html_content):
            def add_style_to_element_by_id(match):
                full_match = match.group(0)
                if 'style=' in full_match:
                    def update_style(m):
                        existing = m.group(1)
                        for prop in ['font-family', 'font-size', 'color', 'background-color', 'position', 'left', 'top', 'font-weight', 'text-align']:
                            existing = re.sub(rf'{prop}:\s*[^;]+;?', '', existing)
                        existing = existing.strip().rstrip(';').strip()
                        if existing:
                            new_style = f'{existing}; {style_str}'
                        else:
                            new_style = style_str
                        return f'style="{new_style}"'
                    return re.sub(r'style="([^"]*)"', update_style, full_match)
                return full_match.rstrip('>') + f' style="{style_str}">'

            html_content = re.sub(
                rf'(<[^>]*{element_id_pattern}[^>]*)',
                add_style_to_element_by_id,
                html_content
            )
            final_selector = f'[data-element-id="{element_id}"]'
        else:
            selector_pattern = rf'data-selector=["\']{re.escape(selector)}["\']'
            if re.search(selector_pattern, html_content):
                def add_element_id(match):
                    tag = match.group(0)
                    if 'data-element-id=' not in tag:
                        tag = tag.replace('>', f' data-element-id="{element_id}">')
                    return tag

                html_content = re.sub(
                    rf'(<[^>]*{selector_pattern}[^>]*)',
                    add_element_id,
                    html_content,
                    count=1
                )
            if re.search(element_id_pattern, html_content):
                final_selector = f'[data-element-id="{element_id}"]'
            else:
                final_selector = selector
    else:
        pattern = rf'data-selector=["\']{re.escape(selector)}["\']'
        if re.search(pattern, html_content):
            final_selector = f'[data-selector="{selector}"]'

    style_id = f"streamlit_style_{slide_id}_{abs(hash(selector)) % 100000}"
    existing_style_pattern = rf'<style[^>]*id=["\']{style_id}["\'][^>]*>'
    style_tag = f'<style id="{style_id}">{final_selector} {{{style_str} !important;}}</style>'

    if re.search(existing_style_pattern, html_content):
        html_content = re.sub(
            rf'<style[^>]*id=["\']{style_id}["\'][^>]*>.*?</style>',
            style_tag,
            html_content,
            flags=re.DOTALL
        )
    else:
        if '</head>' in html_content:
            html_content = html_content.replace('</head>', style_tag + '</head>')
        elif '</body>' in html_content:
            html_content = html_content.replace('</body>', style_tag + '</body>')
        else:
            html_content = style_tag + html_content

    return html_content


def apply_style_realtime(slide_id: str, selector: str, style_props: dict, manifest: dict, slides_dir: Path, element_id: str = None):
    """实时应用样式更改（不显示消息，静默更新）"""
    from datetime import datetime
    
    print(f"[STYLE] apply_style_realtime called: slide_id={slide_id}, selector={selector}, style_props={style_props}")
    
    history_key = f"style_history_{slide_id}_{selector}"
    if history_key not in st.session_state:
        st.session_state[history_key] = []

    draft_key = f"draft_html_{slide_id}"
    dirty_key = f"draft_dirty_{slide_id}"

    print(f"[STYLE] draft_key={draft_key}, dirty_key={dirty_key}")
    print(f"[STYLE] draft_key in session_state: {draft_key in st.session_state}")

    # 获取幻灯片文件名
    slides = manifest.get("slides", [])
    slide_meta = None
    for slide in slides:
        if slide.get("id") == slide_id:
            slide_meta = slide
            break
    
    if not slide_meta:
        print(f"[STYLE] ERROR: 未找到幻灯片: {slide_id}")
        return False
    
    slide_file = slides_dir / slide_meta.get("file", f"{slide_id}.html")
    print(f"[STYLE] slide_file: {slide_file}")

    base_html = None
    if draft_key in st.session_state and st.session_state.get(draft_key):
        base_html = st.session_state.get(draft_key)
        print(f"[STYLE] 从 session_state 获取 base_html，长度: {len(base_html)}")
    elif slide_file.exists():
        try:
            base_html = slide_file.read_text(encoding='utf-8')
            print(f"[STYLE] 从文件读取 base_html，长度: {len(base_html)}")
        except Exception as e:
            print(f"[STYLE] ERROR: 读取文件失败: {e}")
            base_html = None

    if base_html:
        history = st.session_state[history_key]
        history.append(base_html)
        if len(history) > 10:
            history.pop(0)
        st.session_state[history_key] = history
        print(f"[STYLE] 添加到历史记录，历史记录数量: {len(history)}")

    if element_id:
        style_props['element_id'] = element_id

    if base_html is None:
        print(f"[STYLE] ERROR: base_html 为空")
        return False

    print(f"[STYLE] 应用样式更改...")
    updated_html = apply_element_style_changes_to_html(slide_id, selector, style_props, base_html)
    print(f"[STYLE] 样式更改完成，updated_html 长度: {len(updated_html)}")
    
    st.session_state[draft_key] = updated_html
    # 不再设置 dirty_key，因为返回就撤回所有操作
    print(f"[STYLE] 设置 draft_key")
    
    return True


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

    draft_key = f"draft_html_{slide_id}"
    dirty_key = f"draft_dirty_{slide_id}"
    layout_active_key = f"layout_active_{slide_id}"
    desc_active_key = f"desc_active_{slide_id}"
    leave_confirm_key = f"leave_confirm_{slide_id}"
    leave_target_key = f"leave_target_{slide_id}"
    toast_key = f"toast_{slide_id}"
    scroll_target_key = f"scroll_target_{slide_id}"
    save_pending_key = f"layout_save_pending_{slide_id}"
    save_requested_ts_key = f"layout_save_requested_ts_{slide_id}"
    last_layout_ts_key = f"last_layout_ts_{slide_id}"
    leave_confirm_bridge_key = f"leave_confirm_bridge_{slide_id}"
    leave_confirm_nonce_key = f"leave_confirm_nonce_{slide_id}"
    toast_nonce_key = f"toast_nonce_{slide_id}"

    if layout_active_key not in st.session_state:
        st.session_state[layout_active_key] = False
    if desc_active_key not in st.session_state:
        st.session_state[desc_active_key] = False
    if leave_confirm_key not in st.session_state:
        st.session_state[leave_confirm_key] = False
    if toast_key not in st.session_state:
        st.session_state[toast_key] = ""
    if scroll_target_key not in st.session_state:
        st.session_state[scroll_target_key] = None
    if save_pending_key not in st.session_state:
        st.session_state[save_pending_key] = False
    if save_requested_ts_key not in st.session_state:
        st.session_state[save_requested_ts_key] = 0
    if last_layout_ts_key not in st.session_state:
        st.session_state[last_layout_ts_key] = 0
    if leave_confirm_bridge_key not in st.session_state:
        st.session_state[leave_confirm_bridge_key] = ""
    if leave_confirm_nonce_key not in st.session_state:
        st.session_state[leave_confirm_nonce_key] = 0
    if toast_nonce_key not in st.session_state:
        st.session_state[toast_nonce_key] = 0

    if st.session_state.get(toast_key):
        msg = str(st.session_state.get(toast_key))
        st.session_state[toast_key] = ""
        st.session_state[toast_nonce_key] = int(st.session_state.get(toast_nonce_key) or 0) + 1
        toast_nonce = int(st.session_state.get(toast_nonce_key) or 0)
        # 使用 st.toast 和 alert 双重提示
        st.toast(msg, icon="✅")
        st.markdown(
            f"""
<script>
(function(){{
  try{{
    const k = '__pptToastNonce_{slide_id}';
    const last = window[k] || 0;
    const cur = {toast_nonce};
    if (cur > last) {{
      window[k] = cur;
      setTimeout(function() {{
        alert({json.dumps(msg, ensure_ascii=False)});
      }}, 100);
    }}
  }}catch(e){{}}
}})();
</script>
""",
            unsafe_allow_html=True,
        )

    # 移除旧的确认对话框桥接逻辑，改用简单的按钮确认

    # 使用 postMessage 处理元素选择
    st.markdown(
        """
<script>
(function() {
  try {
    if (window.__pptLayoutBridgeHandler) {
      window.removeEventListener('message', window.__pptLayoutBridgeHandler, false);
    }
  } catch (e) {
    // ignore
  }

  window.__pptLayoutBridgeHandler = function(event) {
    try {
      const msg = event && event.data;
      if (!msg || typeof msg !== 'object') return;
      
      // Handle element selection - 直接通过 URL 参数传递
      if (msg.type === 'element_selected') {
        const selectedData = msg.data;
        try {
          const url = new URL(window.location.href);
          url.searchParams.set('selected', JSON.stringify(selectedData));
          url.searchParams.set('_t', Date.now().toString());
          window.history.replaceState({}, '', url);
          // 触发 Streamlit rerun
          setTimeout(() => {
            window.location.reload();
          }, 100);
        } catch (e) {
          console.error('Failed to update URL:', e);
        }
        return;
      }
      
      // Handle text changes - 通过 URL 参数传递
      if (msg.type === 'text_changed') {
        const textData = msg.data;
        try {
          const url = new URL(window.location.href);
          url.searchParams.set('text_change', JSON.stringify(textData));
          url.searchParams.set('_t', Date.now().toString());
          window.history.replaceState({}, '', url);
          // 触发 Streamlit rerun
          setTimeout(() => {
            window.location.reload();
          }, 100);
        } catch (e) {
          console.error('Failed to update URL for text change:', e);
        }
        return;
      }
      
    } catch (e) {
      console.error('Bridge handler error:', e);
    }
  };

  window.addEventListener('message', window.__pptLayoutBridgeHandler, false);
})();
</script>
        """,
        unsafe_allow_html=True,
    )
    
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

    # 移除 save_pending_key 相关逻辑，因为不再需要保存确认

    # 移除旧的确认对话框逻辑，改用简单的按钮确认
    
    # Header with back button
    if st.button("← 返回网格", use_container_width=False, key=f"back_btn_{slide_id}"):
        if st.session_state.slide_modification_in_progress:
            st.warning("正在应用修改，请稍后再试。")
            st.stop()
        
        # 直接撤回所有操作
        if draft_key in st.session_state:
            del st.session_state[draft_key]
        if dirty_key in st.session_state:
            del st.session_state[dirty_key]
        st.session_state[layout_active_key] = False
        st.session_state[desc_active_key] = False
        # 清除选中元素
        if st.session_state.get("selected_element") and st.session_state.selected_element.get("slide_id") == slide_id:
            st.session_state.selected_element = None
            st.session_state.grid_expanded_slide = None
            st.rerun()
    
    # Title and page number below the back button
    col1, col2 = st.columns([3, 1])
    with col1:
        st.subheader(f"📄 {slide_meta.get('title', 'Slide')}")
    with col2:
        st.caption(f"第 {slide_index + 1} / {len(slides)} 页")
    
    st.divider()
    
    # Left-right layout: preview on left, edit on right
    col_preview, col_edit = st.columns([7, 3])
    
    with col_preview:
        st.markdown("**预览** (点击元素进行选择)")
        slide_file = slide_meta.get("file", "")
        slide_path = slides_dir / slide_file
        
        if slide_path.exists():
            try:
                # 如果 draft_key 不存在，从文件读取
                # 如果存在，优先使用 session_state 中的内容（可能是未导出的修改）
                if draft_key not in st.session_state:
                    slide_content = slide_path.read_text(encoding='utf-8')
                    st.session_state[draft_key] = slide_content
                    print(f"[LOAD] 从文件加载: {slide_path}, 大小: {len(slide_content)} 字节")
                else:
                    slide_content = st.session_state.get(draft_key, "")
                    print(f"[LOAD] 使用 session_state 内容，大小: {len(slide_content)} 字节")
                    # 验证 session_state 中的内容是否与文件一致（用于调试）
                    file_content = slide_path.read_text(encoding='utf-8')
                    if slide_content != file_content:
                        print(f"[LOAD] 警告: session_state 内容与文件不一致！")
                        print(f"[LOAD] session_state 大小: {len(slide_content)} 字节")
                        print(f"[LOAD] 文件大小: {len(file_content)} 字节")
                
                # 重要：检查 URL 参数中是否有文字更改 - 必须在布局变化之前处理
                text_change_param = st.query_params.get("text_change")
                if text_change_param:
                    print(f"[TEXT] 🔍 检测到 URL 参数中的 text_change: {text_change_param[:100]}...")
                    try:
                        text_change_data = json.loads(text_change_param)
                        if isinstance(text_change_data, dict) and text_change_data.get("slide_id") == slide_id:
                            selector = text_change_data.get("selector")
                            new_text = text_change_data.get("new_text", "")
                            element_id = text_change_data.get("element_id")
                            print(f"[TEXT] 📦 解析后的 text_change_data: slide_id={slide_id}, selector={selector}, element_id={element_id}, new_text长度={len(new_text)}")
                            if selector and slide_content:
                                # 应用文字更改到当前内容
                                print(f"[TEXT] 🔧 准备应用文字更改，当前内容长度: {len(slide_content)}")
                                updated_html = apply_text_changes_to_html(slide_id, selector, new_text, slide_content, element_id)
                                print(f"[TEXT] 🔧 文字更改后内容长度: {len(updated_html)}")
                                st.session_state[draft_key] = updated_html
                                slide_content = updated_html  # 更新当前内容用于预览
                                print(f"[TEXT] ✅ 文字更改已应用并更新 draft_key")
                                # 清除 URL 参数
                                if "_t" in st.query_params:
                                    del st.query_params["_t"]
                                if "text_change" in st.query_params:
                                    del st.query_params["text_change"]
                                print(f"[TEXT] 🔄 清除 URL 参数，准备 rerun")
                                st.rerun()
                    except Exception as e:
                        print(f"[TEXT] ❌ Error processing text change: {e}")
                        import traceback
                        traceback.print_exc()
                        pass
                
                # 重要：检查 URL 参数中是否有布局变化 - 必须在加载内容后立即处理
                layout_param = st.query_params.get("layout")
                if layout_param:
                    print(f"[LAYOUT] 🔍 检测到 URL 参数中的 layout: {layout_param[:100]}...")
                    try:
                        layout_data_str = layout_param
                        layout_data = json.loads(layout_data_str)
                        print(f"[LAYOUT] 📦 解析后的 layout_data: slide_id={layout_data.get('slide_id')}, selector={layout_data.get('selector')}")
                        if isinstance(layout_data, dict) and layout_data.get("slide_id") == slide_id:
                            selector = layout_data.get("selector")
                            print(f"[LAYOUT] ✅ slide_id 匹配，准备应用布局变化")
                            if selector and slide_content:
                                # 应用布局变化到当前内容
                                updated_html = apply_layout_changes_to_html(slide_id, selector, layout_data, slide_content)
                                st.session_state[draft_key] = updated_html
                                slide_content = updated_html  # 更新当前内容用于预览
                                print(f"[LAYOUT] ✅ 布局变化已应用并更新 draft_key")
                                print(f"[LAYOUT] draft_key={draft_key}")
                                print(f"[LAYOUT] 更新前内容大小: {len(slide_content)} 字节")
                                print(f"[LAYOUT] 更新后内容大小: {len(updated_html)} 字节")
                                print(f"[LAYOUT] selector={selector}, x={layout_data.get('x')}, y={layout_data.get('y')}, width={layout_data.get('width')}, height={layout_data.get('height')}")
                                # 验证更新是否成功
                                if draft_key in st.session_state:
                                    verify_size = len(st.session_state.get(draft_key, ""))
                                    print(f"[LAYOUT] ✅ 验证: draft_key 中的内容大小: {verify_size} 字节")
                                else:
                                    print(f"[LAYOUT] ❌ 错误: draft_key 不存在于 session_state 中！")
                            else:
                                print(f"[LAYOUT] ⚠️ selector 或 slide_content 为空: selector={selector}, slide_content长度={len(slide_content) if slide_content else 0}")
                            
                            # 清除 URL 参数
                            if "_t" in st.query_params:
                                del st.query_params["_t"]
                            if "layout" in st.query_params:
                                del st.query_params["layout"]
                            print(f"[LAYOUT] 🔄 清除 URL 参数，准备 rerun")
                            st.rerun()
                        else:
                            print(f"[LAYOUT] ⚠️ slide_id 不匹配: 期望={slide_id}, 实际={layout_data.get('slide_id')}")
                    except Exception as e:
                        print(f"[LAYOUT] ❌ Error processing layout: {e}")
                        import traceback
                        traceback.print_exc()
                        pass
                else:
                    print(f"[LAYOUT] ℹ️ 没有检测到 URL 参数中的 layout")

                # 获取当前选中的元素
                selected_selector = None
                if (st.session_state.get("selected_element") and 
                    st.session_state.selected_element.get("slide_id") == slide_id):
                    selected_selector = st.session_state.selected_element.get("selector")

                # 注入编辑支持（包括元素选择和拖拽）
                # 只有在布局调整模式下才启用拖动和拉伸功能
                editing_enabled = bool(st.session_state.get(layout_active_key))
                print(f"[EDIT] 注入编辑支持，slide_id={slide_id}, enabled={editing_enabled}, selected_selector={selected_selector}, layout_active={st.session_state.get(layout_active_key)}")
                edited_content = inject_editing_support(slide_content, slide_id, selected_selector, enabled=editing_enabled)
                
                # 应用 iframe fixes
                preview_content = prepare_html_for_preview(edited_content, container_height=600)
                # 使用 scrolling=False，让 body 的 overflow-y: auto 处理滚动
                components.html(preview_content, height=600, scrolling=False)

                # 检查 URL 参数中是否有选中信息
                if st.query_params.get("selected"):
                    try:
                        selected_data_str = st.query_params["selected"]
                        selected_data = json.loads(selected_data_str)
                        if selected_data.get("slide_id") == slide_id:
                            current_selected = st.session_state.get("selected_element")
                            current_selector = current_selected.get("selector") if current_selected and current_selected.get("slide_id") == slide_id else None
                            current_element_id = current_selected.get("element_id") if current_selected and current_selected.get("slide_id") == slide_id else None
                            new_selector = selected_data.get("selector")
                            new_element_id = selected_data.get("element_id")
                            
                            if (current_selector != new_selector or 
                                current_element_id != new_element_id or 
                                current_selector is None):
                                st.session_state.selected_element = selected_data
                                if "_t" in st.query_params:
                                    del st.query_params["_t"]
                                if "selected" in st.query_params:
                                    del st.query_params["selected"]
                                st.rerun()
                    except Exception as e:
                        pass

                # 简化的提示
                if not selected_selector:
                    st.caption("👆 点击元素进行选择")
                else:
                    st.caption(f"✅ 已选择: {selected_selector}")
            except Exception as e:
                st.error(f"预览加载失败: {e}")
        else:
            st.warning("幻灯片文件不存在")
    
    with col_edit:
        scroll_target = st.session_state.get(scroll_target_key)
        if scroll_target:
            st.session_state[scroll_target_key] = None

        # 刷新选择按钮
        if st.button("🔄 刷新选择", key=f"refresh_selection_{slide_id}", use_container_width=True):
            st.rerun()
        
        st.divider()

        st.markdown("**布局调整**")
        if st.button("🧩 布局调整", key=f"enable_layout_{slide_id}", use_container_width=True, disabled=bool(st.session_state.get(layout_active_key))):
            st.session_state[layout_active_key] = True
            st.session_state[scroll_target_key] = f"layout_actions_{slide_id}"
            st.rerun()

        st.markdown(f"<div id='layout_actions_{slide_id}'></div>", unsafe_allow_html=True)
        if st.session_state.get(layout_active_key):
            st.caption("已开启：左侧可拖动/拉伸。")
            # 强制重新获取最新的 draft_content
            draft_content = st.session_state.get(draft_key)
            
            # 调试信息：显示 draft_key 状态
            if draft_key in st.session_state:
                content_size = len(st.session_state.get(draft_key, ""))
                st.caption(f"📝 草稿内容大小: {content_size} 字节")
            else:
                st.caption("⚠️ 没有草稿内容，将从文件读取")
            
            if draft_content:
                # 导出按钮（覆盖原文件）
                if st.button("📦 导出并覆盖原文件", key=f"export_layout_{slide_id}", use_container_width=True, type="primary"):
                    # 再次强制获取最新的 draft_content（防止按钮点击时的状态问题）
                    latest_draft = st.session_state.get(draft_key, "")
                    if not latest_draft:
                        latest_draft = draft_content
                    
                    # 构建文件路径
                    slide_file_name = slide_meta.get("file", f"{slide_id}.html")
                    slide_file_path = slides_dir / slide_file_name
                    
                    try:
                        # 确保文件路径正确
                        if not slide_file_path.parent.exists():
                            slide_file_path.parent.mkdir(parents=True, exist_ok=True)
                        
                        # 确保 draft_content 不为空
                        if not latest_draft:
                            st.error("❌ 没有可导出的内容，请先进行修改")
                            return
                        
                        # 使用最新的内容
                        draft_content = latest_draft
                        
                        # 写入文件（覆盖原文件）
                        slide_file_path.write_text(draft_content, encoding='utf-8')
                        
                        # 等待一小段时间确保写入完成
                        time.sleep(0.1)
                        
                        # 验证文件是否写入成功
                        if not slide_file_path.exists():
                            raise Exception(f"文件写入失败: {slide_file_path}")
                        
                        # 读取验证
                        verify_content = slide_file_path.read_text(encoding='utf-8')
                        if verify_content != draft_content:
                            time.sleep(0.1)
                            verify_content = slide_file_path.read_text(encoding='utf-8')
                            if verify_content != draft_content:
                                raise Exception(f"文件内容验证失败！")
                        
                        # 更新 manifest
                        for s in slides:
                            if s.get("id") == slide_id:
                                s["status"] = "modified"
                                break
                        manifest["updated_at"] = datetime.utcnow().isoformat() + "Z"
                        manifest_path = slides_dir / "manifest.json"
                        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
                        
                        # 重要：用新写入的文件内容更新 draft_key
                        st.session_state[draft_key] = draft_content
                        
                        # 清除其他状态
                        if dirty_key in st.session_state:
                            del st.session_state[dirty_key]
                        st.session_state[layout_active_key] = False
                        st.session_state[toast_key] = "导出成功，已覆盖原文件"
                        st.success(f"✅ 导出成功，已覆盖原文件！")
                        st.balloons()
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ 导出失败: {e}")
            
            if st.button("🗑️ 撤回修改", key=f"discard_layout_{slide_id}", use_container_width=True):
                if draft_key in st.session_state:
                    del st.session_state[draft_key]
                if dirty_key in st.session_state:
                    del st.session_state[dirty_key]
                st.session_state[layout_active_key] = False
                st.session_state[toast_key] = "撤回成功"
                st.success("✅ 撤回成功")
                st.rerun()
        else:
            st.caption("(未开启布局调整)")

        st.divider()

        st.markdown("**描述性修改**")
        if st.button("📝 描述性修改", key=f"enable_desc_{slide_id}", use_container_width=True, disabled=bool(st.session_state.get(desc_active_key))):
            st.session_state[desc_active_key] = True
            st.session_state[scroll_target_key] = f"desc_area_{slide_id}"
            st.rerun()

        st.markdown(f"<div id='desc_area_{slide_id}'></div>", unsafe_allow_html=True)
        if st.session_state.get(desc_active_key):
            modification_input = st.text_area(
            "请描述您想要的修改",
            placeholder="例如：将标题改为红色，添加一个柱状图...",
            height=150,
            key=f"modify_{slide_id}"
        )
        
            streaming_container = st.empty()
            if st.button(
                "🔄 应用修改",
                type="primary",
                use_container_width=True,
                disabled=st.session_state.slide_modification_in_progress
            ):
                if modification_input.strip():
                    # 应用修改并覆盖原文件
                    apply_slide_modification(task, slide_index, slide_id, modification_input.strip(), streaming_container, overwrite_file=True)
                    st.session_state[desc_active_key] = False
                    st.session_state[toast_key] = "修改已应用并覆盖原文件"
                    st.success("✅ 修改已应用并覆盖原文件")
                    st.balloons()
                    st.rerun()

            if st.button("❌ 取消", key=f"cancel_desc_{slide_id}", use_container_width=True):
                # 撤回描述性修改
                st.session_state[desc_active_key] = False
                st.session_state[toast_key] = "已取消描述性修改"
                st.success("✅ 已取消")
                st.rerun()
        else:
            st.caption("(未开启描述性修改)")

        st.divider()

        st.markdown("**✏️ 元素编辑器**")
        
        # 检查是否有选中的元素
        selected_element = st.session_state.get("selected_element")
        
        # 如果没有选中元素，显示提示
        if not selected_element:
            st.info("👆 点击左侧预览中的元素来选择并编辑")
        elif selected_element.get("slide_id") != slide_id:
            st.warning(f"⚠️ 当前选中的元素属于其他幻灯片")
            if st.button("❌ 清除选择", key=f"clear_mismatch_{slide_id}", use_container_width=True):
                st.session_state.selected_element = None
                st.rerun()
        elif selected_element and selected_element.get("slide_id") == slide_id:
            selector = selected_element.get("selector", "")
            element_id = selected_element.get("element_id", "")
            element_type = selected_element.get("tag", "")
            element_text = selected_element.get("text", "")[:30]
            
            # 获取元素的当前样式
            current_styles = selected_element.get("styles", {})
            
            st.success(f"✅ 已选择: `{element_type}`")
            if element_text:
                st.caption(f"文本: {element_text}...")
            st.caption("💡 可以直接拖拽元素移动位置，拖拽边缘调整大小")
            
            st.divider()
            
            # 元素编辑控件 - 实时样式编辑
            st.markdown("**🎨 样式编辑**")
            
            # 定义实时更新回调函数
            def update_style_realtime_callback(prop_name):
                """实时更新样式的回调函数"""
                def callback():
                    key = f"{prop_name}_{slide_id}_{selector}"
                    value = st.session_state.get(key)
                    if value is not None:
                        style_props = {prop_name: value}
                        if element_id:
                            style_props['element_id'] = element_id
                        apply_style_realtime(slide_id, selector, style_props, manifest, slides_dir, element_id)
                        st.rerun()
                return callback
            
            # 字体选择
            font_families = [
                "Arial", "Helvetica", "Times New Roman", "Courier New",
                "Verdana", "Georgia", "Palatino", "Garamond",
                "Comic Sans MS", "Trebuchet MS", "Impact",
                "Microsoft YaHei", "SimHei", "SimSun", "KaiTi",
                "PingFang SC", "Hiragino Sans GB", "STHeiti",
                "Roboto", "Open Sans", "Lato", "Montserrat"
            ]
            current_font = current_styles.get("fontFamily", "Arial")
            font_family_index = font_families.index(current_font) if current_font in font_families else 0
            font_family = st.selectbox(
                "字体",
                font_families,
                index=font_family_index,
                key=f"font_family_{slide_id}_{selector}",
                on_change=update_style_realtime_callback('font_family')
            )
            
            # 字体大小
            current_font_size = current_styles.get("fontSize", 48)
            font_size = st.slider(
                "字体大小 (px)",
                min_value=12,
                max_value=120,
                value=int(current_font_size),
                key=f"font_size_{slide_id}_{selector}",
                on_change=update_style_realtime_callback('font_size')
            )
            
            # 文字颜色
            current_color = current_styles.get("color", "#000000")
            if current_color.startswith("rgb"):
                current_color = "#000000"
            color_key = f"color_{slide_id}_{selector}"
            if color_key not in st.session_state:
                st.session_state[color_key] = current_color if current_color.startswith("#") else "#000000"
            
            def update_color():
                color_val = st.session_state.get(color_key)
                if color_val:
                    style_props = {'color': color_val}
                    if element_id:
                        style_props['element_id'] = element_id
                    apply_style_realtime(slide_id, selector, style_props, manifest, slides_dir, element_id)
                    st.rerun()
            
            color = st.color_picker(
                "文字颜色",
                value=st.session_state.get(color_key, current_color if current_color.startswith("#") else "#000000"),
                key=color_key,
                on_change=update_color
            )
            
            # 背景颜色
            current_bg = current_styles.get("backgroundColor", "transparent")
            if current_bg == "transparent" or current_bg == "rgba(0, 0, 0, 0)":
                current_bg = "#FFFFFF"
            elif not current_bg.startswith("#"):
                current_bg = "#FFFFFF"
            bg_color_key = f"bg_color_{slide_id}_{selector}"
            if bg_color_key not in st.session_state:
                st.session_state[bg_color_key] = current_bg if current_bg.startswith("#") else "#FFFFFF"
            
            def update_bg_color():
                bg_color_val = st.session_state.get(bg_color_key)
                if bg_color_val:
                    style_props = {'background_color': bg_color_val}
                    if element_id:
                        style_props['element_id'] = element_id
                    apply_style_realtime(slide_id, selector, style_props, manifest, slides_dir, element_id)
                    st.rerun()
            
            bg_color = st.color_picker(
                "背景颜色",
                value=st.session_state.get(bg_color_key, current_bg if current_bg.startswith("#") else "#FFFFFF"),
                key=bg_color_key,
                on_change=update_bg_color
            )
            
            # 字体粗细
            current_weight = current_styles.get("fontWeight", "normal")
            weight_options = ["normal", "bold", "lighter", "100", "200", "300", "400", "500", "600", "700", "800", "900"]
            weight_index = weight_options.index(current_weight) if current_weight in weight_options else 0
            font_weight = st.selectbox(
                "字体粗细",
                weight_options,
                index=weight_index,
                key=f"font_weight_{slide_id}_{selector}",
                on_change=update_style_realtime_callback('font_weight')
            )
            
            # 文本对齐
            current_align = current_styles.get("textAlign", "left")
            align_options = ["left", "center", "right", "justify"]
            align_index = align_options.index(current_align) if current_align in align_options else 0
            text_align = st.selectbox(
                "文本对齐",
                align_options,
                index=align_index,
                key=f"text_align_{slide_id}_{selector}",
                on_change=update_style_realtime_callback('text_align')
            )
            
            st.divider()
            
            # 导出按钮
            draft_content = st.session_state.get(draft_key)
            
            if draft_content:
                if st.button("📦 导出并覆盖原文件", key=f"export_slide_{slide_id}", use_container_width=True, type="primary"):
                    latest_draft = st.session_state.get(draft_key, "")
                    if not latest_draft:
                        latest_draft = draft_content
                    
                    slide_file_name = slide_meta.get("file", f"{slide_id}.html")
                    slide_file_path = slides_dir / slide_file_name
                    
                    try:
                        if not slide_file_path.parent.exists():
                            slide_file_path.parent.mkdir(parents=True, exist_ok=True)
                        
                        if not latest_draft:
                            st.error("❌ 没有可导出的内容，请先进行修改")
                            return
                        
                        draft_content = latest_draft
                        slide_file_path.write_text(draft_content, encoding='utf-8')
                        time.sleep(0.1)
                        
                        if not slide_file_path.exists():
                            raise Exception(f"文件写入失败: {slide_file_path}")
                        
                        verify_content = slide_file_path.read_text(encoding='utf-8')
                        if verify_content != draft_content:
                            time.sleep(0.1)
                            verify_content = slide_file_path.read_text(encoding='utf-8')
                            if verify_content != draft_content:
                                raise Exception(f"文件内容验证失败！")
                        
                        slides_list = manifest.get("slides", [])
                        for s in slides_list:
                            if s.get("id") == slide_id:
                                s["status"] = "modified"
                                break
                        
                        manifest["updated_at"] = datetime.utcnow().isoformat() + "Z"
                        manifest_path = slides_dir / "manifest.json"
                        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
                        
                        st.session_state[draft_key] = draft_content
                        
                        if dirty_key in st.session_state:
                            del st.session_state[dirty_key]
                        
                        st.session_state[toast_key] = "导出成功，已覆盖原文件"
                        st.success(f"✅ 导出成功，已覆盖原文件！")
                        st.balloons()
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ 导出失败: {e}")
            else:
                st.info("💡 请先进行样式修改")
            
            # 撤回按钮
            history_key = f"style_history_{slide_id}_{selector}"
            can_undo = history_key in st.session_state and len(st.session_state.get(history_key, [])) > 0
            
            if st.button("↩️ 撤回", key=f"undo_{slide_id}_{selector}", use_container_width=True, disabled=not can_undo):
                history = st.session_state.get(history_key, [])
                if history:
                    previous_html = history.pop()
                    st.session_state[history_key] = history
                    st.session_state[draft_key] = previous_html
                    st.session_state[toast_key] = "已撤回"
                    st.success("✅ 已撤回")
                    st.rerun()
            
            # 清除选择按钮
            if st.button("❌ 清除选择", key=f"clear_{slide_id}", use_container_width=True):
                st.session_state.selected_element = None
                st.rerun()

        if scroll_target:
            st.markdown(
                f"""
<script>
(function(){{
  try{{
    const el = document.getElementById('{scroll_target}');
    if (el) el.scrollIntoView({{behavior:'smooth', block:'start'}});
  }}catch(e){{}}
}})();
</script>
""",
                unsafe_allow_html=True,
            )
    
    st.divider()
    
    # Navigation buttons
    col1, col2, col3 = st.columns([1, 2, 1])
    with col1:
        if slide_index > 0:
            prev_slide = slides[slide_index - 1]
            if st.button("上一页", use_container_width=True):
                # 清理状态
                if draft_key in st.session_state:
                    del st.session_state[draft_key]
                if dirty_key in st.session_state:
                    del st.session_state[dirty_key]
                st.session_state[layout_active_key] = False
                st.session_state[desc_active_key] = False
                if st.session_state.get("selected_element") and st.session_state.selected_element.get("slide_id") == slide_id:
                    st.session_state.selected_element = None
                st.session_state.grid_expanded_slide = prev_slide.get("id")
                st.rerun()
    with col3:
        if slide_index < len(slides) - 1:
            next_slide = slides[slide_index + 1]
            if st.button("下一页", use_container_width=True):
                # 清理状态
                if draft_key in st.session_state:
                    del st.session_state[draft_key]
                if dirty_key in st.session_state:
                    del st.session_state[dirty_key]
                st.session_state[layout_active_key] = False
                st.session_state[desc_active_key] = False
                if st.session_state.get("selected_element") and st.session_state.selected_element.get("slide_id") == slide_id:
                    st.session_state.selected_element = None
                st.session_state.grid_expanded_slide = next_slide.get("id")
                st.rerun()


def apply_slide_modification(task: Task, slide_index: int, slide_id: str, feedback: str, streaming_container=None, overwrite_file=False):
    """Apply modification to a slide using the Designer agent with streaming output.
    
    Args:
        task: The current task
        slide_index: Index of the slide
        slide_id: ID of the slide
        feedback: User feedback/description
        streaming_container: Container for streaming output
        overwrite_file: If True, the modification will overwrite the original file (default: False, but regenerate_slide already does this)
    """
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
    
    # Header
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
    """Export multi-file slides to a single HTML file."""
    slides_dir = get_slides_dir(task)
    if not slides_dir:
        st.error("未找到幻灯片目录")
        return
    
    generator = create_slide_generator(task)
    if not generator:
        st.error("无法创建导出器")
        return
    
    try:
        output_path = generator.export_to_single_file(slides_dir)
        st.success(f"✅ 导出成功: {output_path}")
        
        # Update task html_file to point to exported file
        relative_path = output_path.relative_to(Path(task.workspace_dir))
        st.session_state.task_manager.update_task(task.id, html_file=str(relative_path))
        st.session_state.preview_key += 1
        st.rerun()
    except Exception as e:
        st.error(f"导出失败: {e}")


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
# Main App
# ============================================================================

def main():
    """Main application entry point."""
    # Render sidebar
    render_sidebar()
    
    # Sync phase with current task state (handles page refresh, etc.)
    sync_phase_with_task()
    
    # Main content area
    st.title("🎨 AI Presentation Agent")
    
    # Route based on current phase
    current_phase = st.session_state.current_phase
    
    if current_phase in ["designing", "completed"]:
        # Show grid view for slide monitoring and editing
        st.caption("幻灯片生成与编辑")
        render_grid_view()
    
    elif current_phase == "editing_plan":
        # Show plan editor
        st.caption("编辑演示文稿规划")
        render_plan_editor()
    
    else:
        # Show chat view for collecting and architect phases
        st.caption("使用 AI 创建数据驱动的 HTML 演示文稿")
        
        # Create two columns for chat and preview
        col1, col2 = st.columns([1, 1])
        
        with col1:
            render_chat_panel()
        
        with col2:
            render_preview_panel()
    
    # Processing indicator
    if st.session_state.is_processing:
        st.toast("🔄 Agent 正在工作...", icon="⏳")


if __name__ == "__main__":
    main()
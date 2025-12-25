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
import streamlit as st
import streamlit.components.v1 as components
from pathlib import Path
from dotenv import load_dotenv
from agent_core import Agent, SlideRefiner, ToolCallInfo
from task_manager import TaskManager, Task
from typing import Optional, List, Tuple
from directory_picker import pick_directory, is_valid_directory
from workspace_copier import WorkspaceCopier, ScanResult

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
    
    # Directory picker state
    if "pending_source_dir" not in st.session_state:
        st.session_state.pending_source_dir = None
    
    if "pending_scan_result" not in st.session_state:
        st.session_state.pending_scan_result = None
    
    if "show_size_warning" not in st.session_state:
        st.session_state.show_size_warning = False
    
    if "copy_in_progress" not in st.session_state:
        st.session_state.copy_in_progress = False
    
    # Sync confirmation state
    if "confirm_sync" not in st.session_state:
        st.session_state.confirm_sync = False


init_session_state()


# ============================================================================
# Helper Functions
# ============================================================================

def get_current_task() -> Optional[Task]:
    """Get the current active task."""
    return st.session_state.task_manager.get_active_task()


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
    """Handle the directory selection and copy process."""
    # Open directory picker
    selected_dir = pick_directory("选择工作目录")
    
    if selected_dir and is_valid_directory(selected_dir):
        st.session_state.pending_source_dir = selected_dir
        
        # Scan the directory
        copier = WorkspaceCopier()
        scan_result = copier.scan_directory(selected_dir)
        st.session_state.pending_scan_result = scan_result
        
        # Check if size warning is needed
        if copier.needs_size_warning(scan_result):
            st.session_state.show_size_warning = True
        # Don't auto-proceed, let user confirm after seeing the file list
    else:
        st.session_state.pending_source_dir = None
        st.session_state.pending_scan_result = None


def create_task_with_copy():
    """Create a new task and copy the workspace."""
    source_dir = st.session_state.pending_source_dir
    
    if not source_dir:
        return
    
    task_manager = st.session_state.task_manager
    
    # Create the task first (this generates the workspace path)
    task = task_manager.create_task(source_dir)
    
    # Now copy the files
    st.session_state.copy_in_progress = True
    
    try:
        copier = WorkspaceCopier()
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
            
            # Directory selected - show preview and confirm
            else:
                source_dir = st.session_state.pending_source_dir
                st.info(f"📁 已选择: {source_dir}")
                
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
                        f"⚠️ 目录较大 ({scan_result.total_size_mb:.1f} MB)，"
                        f"复制可能需要一些时间。"
                    )
                
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
                        st.session_state.pending_scan_result = None
                        st.session_state.show_size_warning = False
                        handle_directory_selection()
                        st.rerun()
                with col3:
                    if st.button("❌ 取消", use_container_width=True):
                        st.session_state.pending_source_dir = None
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

def render_preview_panel():
    """Render the HTML preview panel."""
    task = get_current_task()
    
    if not task:
        st.info("📄 选择任务后将显示预览")
        return
    
    st.subheader("🖼️ 预览")
    
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
            
            components.html(
                html_content,
                height=600,
                scrolling=True
            )
        except Exception as e:
            st.error(f"渲染预览时出错: {e}")
    
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
    
    # Main content area
    st.title("🎨 AI Presentation Agent")
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
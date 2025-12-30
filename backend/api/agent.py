"""Agent API routes for starting AI generation.

This module provides REST endpoints for:
- Starting the Agent generation process
- Checking Agent status
- Streaming Agent responses via WebSocket
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from config import get_settings, get_prompt_loader
from state.task_manager import TaskManager, TaskStatus
from state.manifest import ManifestManager
from core.agent import Agent
from workflow.phase_manager import Phase
from tools.base import ToolRegistry, BaseTool, ToolResult
from tools.file_tools import ReadFileTool, WriteFileTool, ListFilesTool
from tools.command_tools import ExecuteCommandTool
from tools.phase_tools import PhaseCompleteTool, TaskCompletedTool
from api.tasks import get_task_manager  # 使用统一的 TaskManager 实例


# Configure logging
logger = logging.getLogger(__name__)


router = APIRouter(prefix="/tasks/{task_id}/agent", tags=["agent"])


def create_task_registry(workspace_path: Path, phase_callback=None) -> ToolRegistry:
    """Create a tool registry with tools configured for the task workspace.
    
    Args:
        workspace_path: The workspace directory for the task
        phase_callback: Optional callback for phase_complete tool
        
    Returns:
        ToolRegistry with properly configured tools
    """
    logger.info(f"[Agent] Creating tool registry with workspace: {workspace_path}")
    logger.info(f"[Agent] Workspace resolved path: {workspace_path.resolve()}")
    logger.info(f"[Agent] Workspace exists: {workspace_path.exists()}")
    
    # List files in workspace for debugging
    if workspace_path.exists():
        all_files = list(workspace_path.rglob("*"))
        logger.info(f"[Agent] Files in workspace: {len(all_files)}")
        for f in all_files[:20]:  # Limit to first 20 files
            if f.is_file():
                logger.info(f"[Agent]   - {f.relative_to(workspace_path)}")
    else:
        logger.warning(f"[Agent] Workspace does not exist: {workspace_path}")
    
    registry = ToolRegistry()
    
    # Register file tools with the correct workspace
    registry.register(ReadFileTool(workspace_root=workspace_path))
    registry.register(WriteFileTool(workspace_root=workspace_path))
    registry.register(ListFilesTool(workspace_root=workspace_path))
    registry.register(ExecuteCommandTool(workspace_root=workspace_path))
    
    # Register phase tools
    registry.register(PhaseCompleteTool(phase_callback=phase_callback))
    registry.register(TaskCompletedTool())
    
    # Register inspect_csv_head tool (matches original agent_core.py)
    registry.register(InspectCsvHeadTool(workspace_root=workspace_path))
    
    return registry


class InspectCsvHeadTool(BaseTool):
    """Tool for inspecting CSV file headers and first rows."""
    
    def __init__(self, workspace_root: Optional[Path] = None):
        self.workspace_root = workspace_root or Path.cwd()
    
    @property
    def name(self) -> str:
        return "inspect_csv_head"
    
    @property
    def description(self) -> str:
        return "Inspect a CSV file by showing the first few rows as a Markdown table. Use this to understand CSV structure without reading the entire file."
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the CSV file (relative to workspace)"
                },
                "rows": {
                    "type": "integer",
                    "description": "Number of data rows to show (default: 5)",
                    "default": 5
                }
            },
            "required": ["path"]
        }
    
    async def execute(self, path: str, rows: int = 5, **kwargs) -> ToolResult:
        """Inspect CSV file."""
        import csv
        
        try:
            file_path = self.workspace_root / path
            
            if not file_path.exists():
                return ToolResult.failure(f"File not found: {path}")
            
            # Try using pandas first
            try:
                import pandas as pd
                df = pd.read_csv(file_path, nrows=rows)
                
                # Get total row count
                with open(file_path, 'r', encoding='utf-8') as f:
                    total_rows = sum(1 for _ in f) - 1  # Subtract header
                
                markdown = df.to_markdown(index=False)
                
                result = f"**File:** `{path}`\n"
                result += f"**Columns:** {len(df.columns)}\n"
                result += f"**Total rows:** {total_rows}\n"
                result += f"**Showing first {len(df)} rows:**\n\n"
                result += markdown
                
                return ToolResult.success(
                    result,
                    columns=list(df.columns),
                    total_rows=total_rows,
                    rows_shown=len(df)
                )
            except ImportError:
                # Fallback without pandas
                with open(file_path, 'r', encoding='utf-8', newline='') as f:
                    reader = csv.reader(f)
                    header = next(reader, None)
                    
                    if not header:
                        return ToolResult.failure("CSV file is empty")
                    
                    data_rows = []
                    for i, row in enumerate(reader):
                        if i >= rows:
                            break
                        data_rows.append(row)
                    
                    # Simple markdown table
                    result = "| " + " | ".join(header) + " |\n"
                    result += "|" + "|".join(["---"] * len(header)) + "|\n"
                    for row in data_rows:
                        result += "| " + " | ".join(row) + " |\n"
                    
                    return ToolResult.success(
                        result,
                        columns=header,
                        rows_shown=len(data_rows)
                    )
                    
        except Exception as e:
            return ToolResult.failure(f"Error reading CSV: {e}")


class RunAgentRequest(BaseModel):
    """Request to run agent with user message."""
    message: str
    phase: Optional[str] = None  # Optional phase override


class AgentRunResponse(BaseModel):
    """Response from agent run."""
    success: bool
    task_id: str
    message: str
    phase: str


# Store for running agent tasks
_agent_tasks: Dict[str, Dict[str, Any]] = {}


def get_agent_status(task_id: str) -> Dict[str, Any]:
    """Get status of agent task."""
    if task_id in _agent_tasks:
        return _agent_tasks[task_id]
    return {"status": "idle", "phase": None}


async def run_agent_task(
    task_id: str,
    user_message: str,
    phase: Optional[str] = None
):
    """Run agent task in background.
    
    This function runs the AI agent to process user input and generate
    the presentation plan.
    
    Key workflow:
    1. Collecting phase: Agent explores files, reads content, analyzes data
    2. When collecting completes via phase_complete(phase="collecting", summary="..."):
       - The summary is captured and passed to Architect phase
    3. Architect phase: Uses the collected information to create presentation plan
    """
    settings = get_settings()
    prompt_loader = get_prompt_loader()
    task_manager = get_task_manager()
    
    logger.info(f"[Agent] Starting agent task for {task_id}")
    logger.info(f"[Agent] Settings workspace_base: {settings.workspace_base}")
    
    # Update status
    _agent_tasks[task_id] = {
        "status": "running",
        "phase": phase or "collecting",
        "messages": [],
        "error": None
    }
    
    try:
        # Get the task
        task = task_manager.get_task(task_id)
        if not task:
            logger.error(f"[Agent] Task not found: {task_id}")
            _agent_tasks[task_id]["status"] = "error"
            _agent_tasks[task_id]["error"] = "Task not found"
            return
        
        # Determine which prompt to use based on phase
        current_phase = phase or task.phase.value
        logger.info(f"[Agent] Current phase: {current_phase}")
        
        if current_phase == "collecting":
            system_prompt = prompt_loader.load("system_prompt")
        elif current_phase in ["architect", "editing_plan"]:
            system_prompt = prompt_loader.load("Architect_prompt")
        else:
            system_prompt = prompt_loader.load("system_prompt")
        
        # Get workspace path - compare with TaskManager path
        workspace = settings.get_workspace_path(task_id)
        tm_workspace = task_manager.get_workspace_path(task_id)
        logger.info(f"[Agent] Settings workspace path: {workspace}")
        logger.info(f"[Agent] TaskManager workspace path: {tm_workspace}")
        logger.info(f"[Agent] Paths match: {workspace.resolve() == tm_workspace.resolve()}")
        
        workspace.mkdir(parents=True, exist_ok=True)
        
        # Create slides directory
        slides_dir = workspace / "slides"
        slides_dir.mkdir(parents=True, exist_ok=True)
        
        # Create task-specific tool registry
        task_registry = create_task_registry(workspace)
        
        # Create agent with task-specific registry
        agent = Agent(
            system_prompt=system_prompt,
            model=settings.openai_model,
            settings=settings,
            registry=task_registry
        )
        
        try:
            # Run the collecting agent
            response = await agent.chat(user_message, max_tool_rounds=20)
            
            _agent_tasks[task_id]["messages"].append({
                "role": "assistant",
                "content": response
            })
            
            # CRITICAL: Capture the collecting phase summary from agent.task_result
            # When phase_complete(phase="collecting", summary="...") is called,
            # the Agent class sets task_result to the summary value
            collecting_summary = ""
            if agent.task_completed and agent.task_result:
                collecting_summary = agent.task_result
                logger.info(f"[Agent] Captured collecting phase summary: {collecting_summary[:200]}...")
            
            # Check if presentation_plan.json was created
            slides_dir = workspace / "slides"
            plan_path = slides_dir / "presentation_plan.json"
            
            if plan_path.exists():
                # Update task phase
                task_manager.update_task(task_id, phase=Phase.EDITING_PLAN)
                _agent_tasks[task_id]["phase"] = "editing_plan"
                _agent_tasks[task_id]["status"] = "completed"
                _agent_tasks[task_id]["plan_ready"] = True
            else:
                # Plan not yet created, run architect phase
                architect_prompt = prompt_loader.load("Architect_prompt")
                
                # Create architect agent with same task registry
                architect_agent = Agent(
                    system_prompt=architect_prompt,
                    model=settings.architect_model,
                    settings=settings,
                    registry=task_registry
                )
                
                try:
                    # FIXED: Build the architect task with collected information
                    # Include both the original user message AND the summary from collecting phase
                    if collecting_summary:
                        # Use the collected information summary
                        architect_message = f"""基于之前收集的信息，创建演示文稿规划。

## 用户原始需求
{user_message}

## 信息收集阶段摘要
{collecting_summary}

## 任务要求
请基于以上收集到的信息，执行以下步骤：
1. 分析收集到的项目/数据信息
2. 规划幻灯片结构（8-15页）
3. 使用 write_file 工具将规划写入 slides/presentation_plan.json

**重要**: 直接使用收集阶段已经获取的信息，无需重新读取文件！

## 规划格式示例
{{
  "title": "演示文稿标题",
  "theme": {{ "primaryColor": "#171717", "accentColor": "#737373" }},
  "slides": [
    {{ "id": "slide_1", "title": "标题页", "content": "内容描述", "type": "title" }},
    {{ "id": "slide_2", "title": "目录", "content": "内容描述", "type": "toc" }}
  ]
}}
"""
                    else:
                        # Fallback: No summary available, use original behavior
                        logger.warning("[Agent] No collecting summary available, Architect will need to explore files")
                        architect_message = f"""基于用户的需求，创建演示文稿规划。

用户需求：
{user_message}

请执行以下步骤：
1. 首先使用 list_files 和 read_file 工具探索项目内容
2. 分析项目信息
3. 规划幻灯片结构（8-15页）
4. 使用 write_file 工具将规划写入 slides/presentation_plan.json

规划格式示例：
{{
  "title": "演示文稿标题",
  "theme": {{ "primaryColor": "#171717", "accentColor": "#737373" }},
  "slides": [
    {{ "id": "slide_1", "title": "标题页", "content": "内容描述", "type": "title" }},
    {{ "id": "slide_2", "title": "目录", "content": "内容描述", "type": "toc" }}
  ]
}}
"""
                    
                    _agent_tasks[task_id]["phase"] = "architect"
                    logger.info(f"[Agent] Starting Architect phase with {'collected summary' if collecting_summary else 'no summary (fallback)'}")
                    
                    architect_response = await architect_agent.chat(
                        architect_message,
                        max_tool_rounds=20
                    )
                    
                    _agent_tasks[task_id]["messages"].append({
                        "role": "architect",
                        "content": architect_response
                    })
                    
                    # Check again if plan was created
                    if plan_path.exists():
                        task_manager.update_task(task_id, phase=Phase.EDITING_PLAN)
                        _agent_tasks[task_id]["phase"] = "editing_plan"
                        _agent_tasks[task_id]["status"] = "completed"
                        _agent_tasks[task_id]["plan_ready"] = True
                    else:
                        _agent_tasks[task_id]["status"] = "completed"
                        _agent_tasks[task_id]["plan_ready"] = False
                        
                finally:
                    await architect_agent.close()
                    
        finally:
            await agent.close()
            
    except Exception as e:
        _agent_tasks[task_id]["status"] = "error"
        _agent_tasks[task_id]["error"] = str(e)
        import traceback
        traceback.print_exc()


@router.post("/run", response_model=AgentRunResponse)
async def start_agent(
    task_id: str,
    request: RunAgentRequest,
    background_tasks: BackgroundTasks,
    manager: TaskManager = Depends(get_task_manager)
):
    """Start the agent to process user message.
    
    This starts a background task that runs the AI agent to:
    1. Process the user's idea
    2. Create a presentation plan
    3. Save the plan to slides/presentation_plan.json
    """
    # Check if task exists
    task = manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Check if agent is already running
    current_status = get_agent_status(task_id)
    if current_status.get("status") == "running":
        raise HTTPException(
            status_code=409,
            detail="Agent is already running for this task"
        )
    
    # Save the idea to task metadata
    current_metadata = task.metadata or {}
    current_metadata["idea"] = request.message
    manager.update_task(task_id, metadata=current_metadata)
    
    # Start agent task in background
    background_tasks.add_task(
        run_agent_task,
        task_id,
        request.message,
        request.phase
    )
    
    return AgentRunResponse(
        success=True,
        task_id=task_id,
        message="Agent started",
        phase=request.phase or "collecting"
    )


@router.get("/status")
async def get_agent_status_endpoint(
    task_id: str,
    manager: TaskManager = Depends(get_task_manager)
) -> Dict[str, Any]:
    """Get the status of the agent for a task."""
    task = manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    status = get_agent_status(task_id)
    
    # Also check if plan exists
    settings = get_settings()
    workspace = settings.get_workspace_path(task_id)
    plan_path = workspace / "slides" / "presentation_plan.json"
    
    status["plan_exists"] = plan_path.exists()
    status["task_phase"] = task.phase.value
    
    return status


@router.websocket("/stream")
async def stream_agent(websocket: WebSocket, task_id: str):
    """WebSocket endpoint for streaming Agent responses.
    
    Messages from client:
    - {"type": "start", "message": "user message", "phase": "optional phase"}
    - {"type": "abort"} to cancel
    
    Messages to client:
    - {"type": "connected", "task_id": "..."}
    - {"type": "chunk", "content": "..."} for streaming content
    - {"type": "tool_call", "name": "...", "args": {...}}
    - {"type": "tool_result", "name": "...", "status": "...", "output": "..."}
    - {"type": "phase", "phase": "..."} for phase updates
    - {"type": "complete", "plan_ready": bool}
    - {"type": "error", "message": "..."}
    """
    await websocket.accept()
    
    settings = get_settings()
    prompt_loader = get_prompt_loader()
    task_manager = get_task_manager()
    
    # Verify task exists
    task = task_manager.get_task(task_id)
    if not task:
        await websocket.send_json({"type": "error", "message": "Task not found"})
        await websocket.close()
        return
    
    await websocket.send_json({"type": "connected", "task_id": task_id})
    
    agent = None
    architect_agent = None
    
    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type", "")
            
            if msg_type == "start":
                user_message = data.get("message", "")
                phase = data.get("phase")
                
                if not user_message:
                    await websocket.send_json({"type": "error", "message": "No message provided"})
                    continue
                
                # Get workspace and create registry
                workspace = settings.get_workspace_path(task_id)
                workspace.mkdir(parents=True, exist_ok=True)
                slides_dir = workspace / "slides"
                slides_dir.mkdir(parents=True, exist_ok=True)
                
                task_registry = create_task_registry(workspace)
                
                # Determine which prompt to use
                current_phase = phase or task.phase.value
                
                if current_phase == "collecting":
                    system_prompt = prompt_loader.load("system_prompt")
                elif current_phase in ["architect", "editing_plan"]:
                    system_prompt = prompt_loader.load("Architect_prompt")
                else:
                    system_prompt = prompt_loader.load("system_prompt")
                
                # Create agent
                agent = Agent(
                    system_prompt=system_prompt,
                    model=settings.openai_model,
                    settings=settings,
                    registry=task_registry
                )
                
                try:
                    # Stream the response for collecting phase
                    await websocket.send_json({"type": "phase", "phase": "collecting"})
                    
                    full_response = ""
                    async for chunk in agent.chat_stream(user_message, max_tool_rounds=20):
                        full_response += chunk
                        await websocket.send_json({"type": "chunk", "content": chunk})
                    
                    # CRITICAL: Capture the collecting phase summary from agent.task_result
                    # When phase_complete(phase="collecting", summary="...") is called,
                    # the Agent class sets task_result to the summary value
                    collecting_summary = ""
                    if agent.task_completed and agent.task_result:
                        collecting_summary = agent.task_result
                        logger.info(f"[WebSocket] Captured collecting phase summary: {collecting_summary[:200]}...")
                    
                    # Check if plan was created
                    plan_path = slides_dir / "presentation_plan.json"
                    
                    if plan_path.exists():
                        task_manager.update_task(task_id, phase=Phase.EDITING_PLAN)
                        await websocket.send_json({
                            "type": "complete",
                            "plan_ready": True,
                            "phase": "editing_plan"
                        })
                    else:
                        # Need to run architect phase
                        await websocket.send_json({"type": "phase", "phase": "architect"})
                        
                        architect_prompt = prompt_loader.load("Architect_prompt")
                        architect_agent = Agent(
                            system_prompt=architect_prompt,
                            model=settings.architect_model,
                            settings=settings,
                            registry=task_registry
                        )
                        
                        # FIXED: Build the architect task with collected information
                        # Include both the original user message AND the summary from collecting phase
                        if collecting_summary:
                            # Use the collected information summary
                            logger.info("[WebSocket] Starting Architect phase with collected summary")
                            architect_message = f"""基于之前收集的信息，创建演示文稿规划。

## 用户原始需求
{user_message}

## 信息收集阶段摘要
{collecting_summary}

## 任务要求
请基于以上收集到的信息，执行以下步骤：
1. 分析收集到的项目/数据信息
2. 规划幻灯片结构（8-15页）
3. 使用 write_file 工具将规划写入 slides/presentation_plan.json

**重要**: 直接使用收集阶段已经获取的信息，无需重新读取文件！

## 规划格式示例
{{
  "title": "演示文稿标题",
  "theme": {{ "primaryColor": "#171717", "accentColor": "#737373" }},
  "slides": [
    {{ "id": "slide_1", "title": "标题页", "content": "内容描述", "type": "title" }},
    {{ "id": "slide_2", "title": "目录", "content": "内容描述", "type": "toc" }}
  ]
}}
"""
                        else:
                            # Fallback: No summary available, use original behavior
                            logger.warning("[WebSocket] No collecting summary available, Architect will need to explore files")
                            architect_message = f"""基于用户的需求，创建演示文稿规划。

用户需求：
{user_message}

请执行以下步骤：
1. 首先使用 list_files 和 read_file 工具探索项目内容
2. 分析项目信息
3. 规划幻灯片结构（8-15页）
4. 使用 write_file 工具将规划写入 slides/presentation_plan.json

规划格式示例：
{{
  "title": "演示文稿标题",
  "theme": {{ "primaryColor": "#171717", "accentColor": "#737373" }},
  "slides": [
    {{ "id": "slide_1", "title": "标题页", "content": "内容描述", "type": "title" }},
    {{ "id": "slide_2", "title": "目录", "content": "内容描述", "type": "toc" }}
  ]
}}
"""
                        
                        async for chunk in architect_agent.chat_stream(architect_message, max_tool_rounds=20):
                            await websocket.send_json({"type": "chunk", "content": chunk})
                        
                        # Check again for plan
                        if plan_path.exists():
                            task_manager.update_task(task_id, phase=Phase.EDITING_PLAN)
                            await websocket.send_json({
                                "type": "complete",
                                "plan_ready": True,
                                "phase": "editing_plan"
                            })
                        else:
                            await websocket.send_json({
                                "type": "complete",
                                "plan_ready": False,
                                "phase": "collecting"
                            })
                        
                        if architect_agent:
                            await architect_agent.close()
                            architect_agent = None
                    
                    if agent:
                        await agent.close()
                        agent = None
                        
                except Exception as e:
                    await websocket.send_json({"type": "error", "message": str(e)})
                    import traceback
                    traceback.print_exc()
            
            elif msg_type == "abort":
                await websocket.send_json({"type": "aborted"})
                break
            
            elif msg_type == "ping":
                await websocket.send_json({"type": "pong"})
                
    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except:
            pass
    finally:
        if agent:
            await agent.close()
        if architect_agent:
            await architect_agent.close()
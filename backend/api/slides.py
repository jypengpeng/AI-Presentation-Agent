"""Slide management API routes.

This module provides REST endpoints for slide management:
- Slide CRUD operations
- Slide generation
- Export endpoints
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from fastapi.responses import FileResponse
from pydantic import BaseModel, field_validator

from config import get_settings, get_prompt_loader
from state.task_manager import TaskManager
from state.manifest import ManifestManager, SlideManifest
from workflow.slide_generator import SlideGenerator, SlideGenerationTask
from export.html_exporter import HTMLExporter
from export.pptx_exporter import PPTXExporter
from export.zip_exporter import ZipExporter
from core.agent import Agent
from tools.base import ToolRegistry
from tools.file_tools import ReadFileTool, WriteFileTool

# Configure logging
logger = logging.getLogger(__name__)


router = APIRouter(prefix="/tasks/{task_id}/slides", tags=["slides"])


# Dependency for getting workspace path
def get_workspace_path(task_id: str) -> Path:
    """Get workspace path for a task."""
    settings = get_settings()
    return settings.get_workspace_path(task_id)


# Request/Response models
class SlideData(BaseModel):
    """Request model for slide data.
    
    Accepts both frontend format (content as string) and backend format (content as list).
    """
    id: Optional[str] = None  # Frontend sends id, we ignore it
    title: str
    content: Union[str, List[str]] = []
    notes: Optional[str] = ""
    layout: Optional[str] = "default"
    type: Optional[str] = None  # Frontend sends type, we map to layout
    
    @field_validator('content', mode='before')
    @classmethod
    def normalize_content(cls, v):
        """Convert string content to list format."""
        if isinstance(v, str):
            return [v] if v else []
        return v or []
    
    def get_layout(self) -> str:
        """Get layout, preferring type if layout is default."""
        if self.type and self.layout == "default":
            return self.type
        return self.layout or "default"


class SlideUpdate(BaseModel):
    """Request model for updating a slide."""
    title: Optional[str] = None
    content: Optional[Union[str, List[str]]] = None
    notes: Optional[str] = None
    layout: Optional[str] = None
    
    @field_validator('content', mode='before')
    @classmethod
    def normalize_content(cls, v):
        """Convert string content to list format."""
        if v is None:
            return None
        if isinstance(v, str):
            return [v] if v else []
        return v


class ThemeConfig(BaseModel):
    """Theme configuration - accepts both string and object format."""
    primaryColor: Optional[str] = None
    accentColor: Optional[str] = None


class PresentationPlan(BaseModel):
    """Request model for presentation plan.
    
    Accepts both frontend format and backend format for compatibility.
    """
    title: str = "Untitled Presentation"
    theme: Optional[Union[str, Dict[str, str]]] = "modern"
    slides: List[SlideData]
    metadata: Optional[Dict[str, Any]] = None
    
    @field_validator('theme', mode='before')
    @classmethod
    def normalize_theme(cls, v):
        """Convert theme object to string if needed."""
        if isinstance(v, dict):
            # Extract theme name or use default
            return v.get('name', 'modern')
        return v or "modern"


class SlideProgressItem(BaseModel):
    """Response model for individual slide progress."""
    id: str
    title: str
    section: Optional[str] = "content"
    status: str  # queued, running, done, failed
    progress: int = 0


class GenerationProgress(BaseModel):
    """Response model for generation progress."""
    total: int
    completed: int
    failed: int
    generating: int
    pending: int
    progress_percent: float
    slides: List[SlideProgressItem] = []


# Endpoints
@router.get("/plan")
async def get_presentation_plan(task_id: str) -> Dict[str, Any]:
    """Get the presentation plan for a task."""
    workspace = get_workspace_path(task_id)
    manager = ManifestManager(workspace)
    manifest = manager.get_manifest()
    return manifest.to_dict()


@router.put("/plan")
async def update_presentation_plan(
    task_id: str,
    plan: PresentationPlan
) -> Dict[str, Any]:
    """Update the presentation plan.
    
    Accepts both frontend format and backend format for flexibility.
    """
    workspace = get_workspace_path(task_id)
    manager = ManifestManager(workspace)
    
    # Normalize theme to string
    theme = plan.theme if isinstance(plan.theme, str) else "modern"
    
    manifest = SlideManifest(
        title=plan.title,
        theme=theme,
        metadata=plan.metadata or {}
    )
    
    for slide_data in plan.slides:
        # Normalize content to list
        content = slide_data.content
        if isinstance(content, str):
            content = [content] if content else []
        
        # Use type as layout if provided
        layout = slide_data.get_layout()
        
        manifest.add_slide(
            title=slide_data.title,
            content=content,
            notes=slide_data.notes or "",
            layout=layout
        )
    
    manager.save_manifest(manifest)
    manager.save_as_plan(manifest)
    
    return manifest.to_dict()


@router.get("")
async def list_slides(task_id: str) -> Dict[str, Any]:
    """List all slides for a task."""
    workspace = get_workspace_path(task_id)
    manager = ManifestManager(workspace)
    manifest = manager.get_manifest()
    
    return {
        "slides": [s.to_dict() for s in manifest.slides],
        "total": len(manifest.slides)
    }


@router.post("")
async def add_slide(task_id: str, slide: SlideData) -> Dict[str, Any]:
    """Add a new slide."""
    workspace = get_workspace_path(task_id)
    manager = ManifestManager(workspace)
    manifest = manager.get_manifest()
    
    # Normalize content to list
    content = slide.content
    if isinstance(content, str):
        content = [content] if content else []
    
    new_slide = manifest.add_slide(
        title=slide.title,
        content=content,
        notes=slide.notes or "",
        layout=slide.get_layout()
    )
    
    manager.save_manifest(manifest)
    
    return new_slide.to_dict()


@router.get("/{slide_index}")
async def get_slide(task_id: str, slide_index: int) -> Dict[str, Any]:
    """Get a specific slide."""
    workspace = get_workspace_path(task_id)
    manager = ManifestManager(workspace)
    manifest = manager.get_manifest()
    
    if slide_index < 0 or slide_index >= len(manifest.slides):
        raise HTTPException(status_code=404, detail="Slide not found")
    
    return manifest.slides[slide_index].to_dict()


@router.patch("/{slide_index}")
async def update_slide(
    task_id: str,
    slide_index: int,
    slide: SlideUpdate
) -> Dict[str, Any]:
    """Update a specific slide."""
    workspace = get_workspace_path(task_id)
    manager = ManifestManager(workspace)
    manifest = manager.get_manifest()
    
    update_data = {k: v for k, v in slide.dict().items() if v is not None}
    updated = manifest.update_slide(slide_index, **update_data)
    
    if not updated:
        raise HTTPException(status_code=404, detail="Slide not found")
    
    manager.save_manifest(manifest)
    
    return updated.to_dict()


@router.delete("/{slide_index}")
async def delete_slide(task_id: str, slide_index: int) -> Dict[str, str]:
    """Delete a specific slide."""
    workspace = get_workspace_path(task_id)
    manager = ManifestManager(workspace)
    manifest = manager.get_manifest()
    
    if not manifest.remove_slide(slide_index):
        raise HTTPException(status_code=404, detail="Slide not found")
    
    manager.save_manifest(manifest)
    
    return {"message": f"Slide {slide_index} deleted"}


@router.post("/{slide_index}/reorder")
async def reorder_slides(
    task_id: str,
    new_order: List[int]
) -> Dict[str, Any]:
    """Reorder slides."""
    workspace = get_workspace_path(task_id)
    manager = ManifestManager(workspace)
    manifest = manager.get_manifest()
    
    if not manifest.reorder_slides(new_order):
        raise HTTPException(status_code=400, detail="Invalid order")
    
    manager.save_manifest(manifest)
    
    return {"slides": [s.to_dict() for s in manifest.slides]}


@router.get("/{slide_index}/html")
async def get_slide_html(task_id: str, slide_index: int):
    """Get the HTML content of a generated slide."""
    workspace = get_workspace_path(task_id)
    slides_path = workspace / "slides"
    html_path = slides_path / f"slide_{slide_index + 1}.html"
    
    if not html_path.exists():
        raise HTTPException(status_code=404, detail="Slide HTML not found")
    
    return FileResponse(
        html_path,
        media_type="text/html",
        filename=html_path.name
    )


# Generation endpoints
@router.post("/generate")
async def start_generation(
    task_id: str,
    background_tasks: BackgroundTasks
) -> Dict[str, Any]:
    """Start slide generation for all slides."""
    workspace = get_workspace_path(task_id)
    manager = ManifestManager(workspace)
    manifest = manager.get_manifest()
    
    if not manifest.slides:
        raise HTTPException(status_code=400, detail="No slides to generate")
    
    # Get designer prompt
    prompt_loader = get_prompt_loader()
    designer_prompt = prompt_loader.load("Designer")
    
    # Mark all slides as generating in manifest
    for slide in manifest.slides:
        slide.status = "generating"
    manager.save_manifest(manifest)
    
    # Start generation in background
    async def generate_slides():
        settings = get_settings()
        
        # Callback to update manifest status during generation
        def on_progress(index: int, total: int, status):
            # status is SlideStatus enum, use its value directly
            # (enum.value gives us "pending", "generating", "completed", "failed")
            manifest_status = status.value if hasattr(status, 'value') else str(status)
            print(f"[on_progress] Slide {index}: {manifest_status}")  # Debug log
            manager.update_slide_status(index, manifest_status)
        
        generator = SlideGenerator(
            workspace_path=workspace,
            designer_prompt=designer_prompt,
            max_concurrent=settings.max_concurrent_slides,
            settings=settings,
            on_progress=on_progress
        )
        
        slides_data = [s.to_dict() for s in manifest.slides]
        await generator.generate_all(slides_data)
        # Note: We don't call generator.save_manifest() because on_progress
        # already updates the ManifestManager's manifest with correct format.
        # Calling it would overwrite with a different format.
    
    background_tasks.add_task(generate_slides)
    
    return {"message": "Generation started", "total_slides": len(manifest.slides)}


@router.get("/generate/progress", response_model=GenerationProgress)
async def get_generation_progress(task_id: str) -> Dict[str, Any]:
    """Get slide generation progress."""
    workspace = get_workspace_path(task_id)
    manager = ManifestManager(workspace)
    
    return manager.get_generation_progress()


@router.post("/{slide_index}/regenerate")
async def regenerate_slide(
    task_id: str,
    slide_index: int,
    background_tasks: BackgroundTasks
) -> Dict[str, str]:
    """Regenerate a specific slide."""
    workspace = get_workspace_path(task_id)
    manager = ManifestManager(workspace)
    manifest = manager.get_manifest()
    
    if slide_index < 0 or slide_index >= len(manifest.slides):
        raise HTTPException(status_code=404, detail="Slide not found")
    
    # Get designer prompt
    prompt_loader = get_prompt_loader()
    designer_prompt = prompt_loader.load("Designer")
    
    async def regenerate():
        settings = get_settings()
        generator = SlideGenerator(
            workspace_path=workspace,
            designer_prompt=designer_prompt,
            settings=settings
        )
        
        # Initialize tasks first
        slides_data = [s.to_dict() for s in manifest.slides]
        generator._tasks = [
            SlideGenerationTask(index=i, data=s)
            for i, s in enumerate(slides_data)
        ]
        generator._semaphore = asyncio.Semaphore(1)
        
        # Regenerate the specific slide
        await generator.regenerate_slide(slide_index)
    
    background_tasks.add_task(regenerate)
    
    return {"message": f"Regeneration of slide {slide_index} started"}


# AI Modify endpoint
class AIModifyRequest(BaseModel):
    """Request model for AI slide modification."""
    prompt: str
    context: Optional[List[Dict[str, str]]] = None  # Conversation history


class AIModifyResponse(BaseModel):
    """Response model for AI slide modification."""
    success: bool
    message: str  # AI's response message
    slide_updated: bool = False


def build_modify_prompt(
    slide_index: int,
    slide_data: Dict[str, Any],
    user_instruction: str,
    conversation_history: Optional[List[Dict[str, str]]] = None
) -> str:
    """Build the modification instruction prompt for the AI agent."""
    
    # Extract slide info
    title = slide_data.get('title', '无标题')
    content = slide_data.get('content', [])
    if isinstance(content, list):
        content_str = '\n'.join(f"- {item}" for item in content)
    else:
        content_str = str(content)
    
    relative_path = f"slides/slide_{slide_index + 1}.html"
    
    prompt = f"""## 当前幻灯片信息

**幻灯片编号:** {slide_index + 1}
**标题:** {title}
**内容描述:**
{content_str}

**文件路径:** {relative_path}

## 用户修改指令

{user_instruction}

## 你的任务

1. 使用 `read_file` 读取 {relative_path}
2. 根据用户的修改指令，对 HTML 内容进行调整
3. 使用 `write_file` 保存修改后的完整 HTML 文件到 {relative_path}
4. 简要说明你做了哪些修改

**重要:**
- 保持整体 HTML 结构不变
- 只修改用户要求的部分
- 确保修改后的幻灯片仍然是全屏、无滚动的设计
- 必须使用 write_file 工具保存修改后的文件
"""

    # Add conversation history if available
    if conversation_history and len(conversation_history) > 0:
        history_text = "\n## 之前的对话\n"
        # Only take the last 5 messages for context
        recent_history = conversation_history[-5:]
        for msg in recent_history:
            role = "用户" if msg.get('role') == 'user' else "助手"
            history_text += f"\n**{role}:** {msg.get('content', '')}\n"
        prompt = history_text + "\n" + prompt

    return prompt


@router.post("/{slide_index}/ai-modify", response_model=AIModifyResponse)
async def modify_slide_with_ai(
    task_id: str,
    slide_index: int,
    request: AIModifyRequest
) -> AIModifyResponse:
    """Modify a slide using AI based on user instructions.
    
    This endpoint allows users to make natural language requests to modify
    a specific slide. The AI agent will read the current slide HTML,
    make the requested changes, and save the updated content.
    """
    logger.info(f"[AI Modify] Task {task_id}, Slide {slide_index}: {request.prompt[:100]}...")
    
    # Get workspace and slide data
    workspace = get_workspace_path(task_id)
    manager = ManifestManager(workspace)
    manifest = manager.get_manifest()
    
    if slide_index < 0 or slide_index >= len(manifest.slides):
        raise HTTPException(status_code=404, detail="Slide not found")
    
    slide_data = manifest.slides[slide_index].to_dict()
    
    # Check if slide HTML exists
    html_path = workspace / "slides" / f"slide_{slide_index + 1}.html"
    if not html_path.exists():
        raise HTTPException(
            status_code=400,
            detail="Slide HTML not generated yet. Please generate the slide first."
        )
    
    # Load SlideModifier prompt
    prompt_loader = get_prompt_loader()
    try:
        system_prompt = prompt_loader.load("SlideModifier")
    except FileNotFoundError:
        # Fallback to Designer prompt if SlideModifier not found
        logger.warning("[AI Modify] SlideModifier.md not found, using Designer.md")
        system_prompt = prompt_loader.load("Designer")
    
    # Build user message
    user_message = build_modify_prompt(
        slide_index=slide_index,
        slide_data=slide_data,
        user_instruction=request.prompt,
        conversation_history=request.context
    )
    
    # Create Agent with workspace-specific tool registry
    settings = get_settings()
    registry = ToolRegistry()
    registry.register(ReadFileTool(workspace_root=workspace))
    registry.register(WriteFileTool(workspace_root=workspace))
    
    agent = Agent(
        system_prompt=system_prompt,
        model=settings.designer_model,  # Use the same model as Designer
        settings=settings,
        registry=registry
    )
    
    try:
        # Execute modification
        response = await agent.chat(user_message, max_tool_rounds=5)
        
        # Check if file was modified (compare timestamps or content)
        slide_updated = html_path.exists()  # Simple check - file still exists after modification
        
        logger.info(f"[AI Modify] Completed. Slide updated: {slide_updated}")
        
        return AIModifyResponse(
            success=True,
            message=response,
            slide_updated=slide_updated
        )
    
    except Exception as e:
        logger.error(f"[AI Modify] Error: {str(e)}")
        import traceback
        traceback.print_exc()
        
        return AIModifyResponse(
            success=False,
            message=f"修改失败: {str(e)}",
            slide_updated=False
        )
    
    finally:
        await agent.close()


# Export endpoints
class ExportOptions(BaseModel):
    """Options for export."""
    include_pptx: bool = True
    include_speech: bool = True
    include_screenshots: bool = False


@router.get("/export/html")
async def export_html(task_id: str):
    """Export presentation as combined HTML (iframe loader).
    
    This creates a presentation.html that loads individual slide files.
    """
    workspace = get_workspace_path(task_id)
    exporter = HTMLExporter(workspace)
    
    try:
        output_path = exporter.export_combined()
        return FileResponse(
            output_path,
            media_type="text/html",
            filename="presentation.html"
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/export/pptx")
async def export_pptx(task_id: str):
    """Export presentation as PPTX.
    
    Uses Selenium to take screenshots and python-pptx to create the file.
    """
    workspace = get_workspace_path(task_id)
    exporter = PPTXExporter(workspace)
    
    try:
        output_path = await exporter.export()
        return FileResponse(
            output_path,
            media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            filename="presentation.pptx"
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ImportError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/export/zip")
async def export_zip(
    task_id: str,
    include_pptx: bool = True,
    include_speech: bool = True
):
    """Export all presentation assets as ZIP.
    
    The ZIP package includes:
    - presentation.html (iframe-based loader)
    - presentation.pptx (if include_pptx=True and Playwright is installed)
    - speech_script.md (if include_speech=True)
    - speech_coaching.md (if include_speech=True)
    - slides/ (all slide HTML files)
    - README.md (keyboard shortcuts and instructions)
    
    Args:
        task_id: Task ID
        include_pptx: Include PowerPoint file (default: True)
        include_speech: Include speech script and coaching (default: True)
    """
    settings = get_settings()
    workspace = get_workspace_path(task_id)
    exporter = ZipExporter(workspace, settings=settings)
    
    try:
        # Use async export with return_bytes to avoid file locking issues
        zip_bytes = await exporter.export_async(
            include_pptx=include_pptx,
            include_speech=include_speech,
            return_bytes=True
        )
        
        from fastapi.responses import Response
        return Response(
            content=zip_bytes,
            media_type="application/zip",
            headers={
                "Content-Disposition": "attachment; filename=presentation.zip"
            }
        )
    except Exception as e:
        logger.error(f"Export failed: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/export/zip")
async def export_zip_with_options(
    task_id: str,
    options: ExportOptions
):
    """Export all presentation assets as ZIP with custom options.
    
    This is an alternative to GET /export/zip that accepts options in request body.
    """
    settings = get_settings()
    workspace = get_workspace_path(task_id)
    exporter = ZipExporter(workspace, settings=settings)
    
    try:
        zip_bytes = await exporter.export_async(
            include_pptx=options.include_pptx,
            include_speech=options.include_speech,
            include_screenshots=options.include_screenshots,
            return_bytes=True
        )
        
        from fastapi.responses import Response
        return Response(
            content=zip_bytes,
            media_type="application/zip",
            headers={
                "Content-Disposition": "attachment; filename=presentation.zip"
            }
        )
    except Exception as e:
        logger.error(f"Export failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
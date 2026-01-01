"""Concurrent slide generation.

This module provides:
- SlideGenerationTask: Individual slide generation task
- SlideGenerator: Manages concurrent slide generation
"""

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from config import Settings, get_settings
from core.agent import Agent
from tools.base import ToolRegistry
from tools.file_tools import ReadFileTool, WriteFileTool, ListFilesTool


class SlideStatus(Enum):
    """Status of a slide generation task."""
    PENDING = "pending"
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"


# HTML template for slide files - matches original slide_generator.py
SLIDE_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Slide {slide_index} - {slide_title}</title>
    
    <!-- Google Fonts - Chinese support (fallback for environments without system fonts) -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@400;500;700&display=swap" rel="stylesheet">
    
    <!-- Tailwind CSS -->
    <script src="https://cdn.tailwindcss.com"></script>
    
    <!-- Chart.js -->
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    
    <!-- Professional Light Theme -->
    <style>
        html, body {{
            margin: 0;
            padding: 0;
            width: 100vw;
            height: 100vh;
            overflow: hidden;
            font-family: 'Noto Sans SC', 'WenQuanYi Zen Hei', 'Microsoft YaHei', 'Inter', 'SF Pro Display', -apple-system, BlinkMacSystemFont, sans-serif;
        }}
        
        .slide-container {{
            width: 100%;
            height: 100%;
        }}
    </style>
</head>
<body class="bg-white">
    <!-- Navigation Indicator -->
    <div class="fixed bottom-4 right-4 text-sm text-gray-400">
        {slide_index} / {total_slides}
    </div>
    
    <!-- Slide Content Container -->
    <div id="content" class="slide-container">
        <!-- Content will be injected by Designer -->
        <div class="h-full flex items-center justify-center text-gray-800">
            <div class="text-center">
                <div class="text-6xl mb-4">⏳</div>
                <div class="text-2xl">正在生成内容...</div>
            </div>
        </div>
    </div>
</body>
</html>
"""


@dataclass
class SlideGenerationTask:
    """Represents a single slide generation task.
    
    Attributes:
        index: Slide index (0-based)
        data: Slide data from presentation plan
        status: Current generation status
        html_content: Generated HTML content
        error: Error message if failed
        started_at: When generation started
        completed_at: When generation completed
    """
    index: int
    data: Dict[str, Any]
    status: SlideStatus = SlideStatus.PENDING
    html_content: Optional[str] = None
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    attempts: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "index": self.index,
            "title": self.data.get("title", f"Slide {self.index + 1}"),
            "status": self.status.value,
            "error": self.error,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "attempts": self.attempts,
        }


class SlideGenerator:
    """Manages concurrent slide generation.
    
    Provides:
    - Concurrent generation with configurable parallelism
    - Progress tracking
    - Retry logic
    - Result aggregation
    """
    
    def __init__(
        self,
        workspace_path: Path,
        designer_prompt: str,
        max_concurrent: int = 3,
        max_retries: int = 2,
        settings: Optional[Settings] = None,
        on_progress: Optional[Callable[[int, int, SlideStatus], None]] = None,
    ):
        """Initialize slide generator.
        
        Args:
            workspace_path: Path to task workspace
            designer_prompt: System prompt for Designer agent
            max_concurrent: Maximum concurrent generations
            max_retries: Maximum retry attempts per slide
            settings: Application settings
            on_progress: Callback for progress updates (index, total, status)
        """
        self.workspace_path = Path(workspace_path)
        self.designer_prompt = designer_prompt
        self.max_concurrent = max_concurrent
        self.max_retries = max_retries
        self.settings = settings or get_settings()
        self.on_progress = on_progress
        
        self._tasks: List[SlideGenerationTask] = []
        self._semaphore: asyncio.Semaphore = asyncio.Semaphore(max_concurrent)
    
    @property
    def slides_path(self) -> Path:
        """Get slides directory path."""
        return self.workspace_path / "slides"
    
    @property
    def tasks(self) -> List[SlideGenerationTask]:
        """Get all generation tasks."""
        return self._tasks.copy()
    
    def get_progress(self) -> Dict[str, Any]:
        """Get current generation progress."""
        total = len(self._tasks)
        completed = sum(1 for t in self._tasks if t.status == SlideStatus.COMPLETED)
        failed = sum(1 for t in self._tasks if t.status == SlideStatus.FAILED)
        generating = sum(1 for t in self._tasks if t.status == SlideStatus.GENERATING)
        pending = sum(1 for t in self._tasks if t.status == SlideStatus.PENDING)
        
        return {
            "total": total,
            "completed": completed,
            "failed": failed,
            "generating": generating,
            "pending": pending,
            "progress_percent": (completed / total * 100) if total > 0 else 0,
            "tasks": [t.to_dict() for t in self._tasks]
        }
    
    def _create_slide_templates(self, slides: List[Dict[str, Any]]) -> None:
        """Create empty HTML template files for all slides.
        
        This matches the original slide_generator.py behavior where
        templates are created first, then Designer fills in the content.
        """
        total_slides = len(slides)
        
        for i, slide in enumerate(slides):
            slide_title = slide.get("title", f"Slide {i + 1}")
            filename = f"slide_{i + 1}.html"
            filepath = self.slides_path / filename
            
            # Generate HTML from template
            html_content = SLIDE_TEMPLATE.format(
                slide_index=i + 1,
                slide_title=slide_title,
                total_slides=total_slides
            )
            
            filepath.write_text(html_content, encoding='utf-8')
    
    async def generate_all(
        self,
        slides: List[Dict[str, Any]],
        design_context: Optional[str] = None
    ) -> List[SlideGenerationTask]:
        """Generate all slides concurrently.
        
        Args:
            slides: List of slide data from presentation plan
            design_context: Additional context for design
            
        Returns:
            List of completed generation tasks
        """
        # Initialize tasks
        self._tasks = [
            SlideGenerationTask(index=i, data=slide)
            for i, slide in enumerate(slides)
        ]
        
        # Create slides directory
        self.slides_path.mkdir(parents=True, exist_ok=True)
        
        # Create empty HTML templates first (like original slide_generator.py)
        self._create_slide_templates(slides)
        
        # Update semaphore for concurrency control
        self._semaphore = asyncio.Semaphore(self.max_concurrent)
        
        # Generate all slides concurrently
        await asyncio.gather(*[
            self._generate_slide(task, design_context)
            for task in self._tasks
        ])
        
        return self._tasks
    
    async def _generate_slide(
        self,
        task: SlideGenerationTask,
        design_context: Optional[str] = None
    ) -> None:
        """Generate a single slide with retry logic."""
        async with self._semaphore:
            for attempt in range(self.max_retries + 1):
                task.attempts = attempt + 1
                task.status = SlideStatus.GENERATING
                task.started_at = datetime.now()
                
                if self.on_progress:
                    self.on_progress(task.index, len(self._tasks), task.status)
                
                try:
                    # _call_designer now returns the HTML that was written by the agent
                    html_content = await self._call_designer(task, design_context)
                    
                    # Note: The agent already wrote the file via write_file tool
                    # We just store the content reference for tracking
                    task.html_content = html_content
                    task.status = SlideStatus.COMPLETED
                    task.completed_at = datetime.now()
                    
                    if self.on_progress:
                        self.on_progress(task.index, len(self._tasks), task.status)
                    
                    return
                    
                except Exception as e:
                    task.error = str(e)
                    if attempt < self.max_retries:
                        await asyncio.sleep(1)  # Brief delay before retry
                    else:
                        task.status = SlideStatus.FAILED
                        task.completed_at = datetime.now()
                        
                        if self.on_progress:
                            self.on_progress(task.index, len(self._tasks), task.status)
    
    def _create_workspace_registry(self) -> ToolRegistry:
        """Create a ToolRegistry with tools configured for task workspace.
        
        This ensures file operations are relative to the task workspace,
        not the backend's working directory.
        """
        registry = ToolRegistry()
        
        # Register file tools with workspace_root set to task workspace
        registry.register(ReadFileTool(workspace_root=self.workspace_path))
        registry.register(WriteFileTool(workspace_root=self.workspace_path))
        registry.register(ListFilesTool(workspace_root=self.workspace_path))
        
        return registry
    
    async def _call_designer(
        self,
        task: SlideGenerationTask,
        design_context: Optional[str] = None
    ) -> str:
        """Call Designer agent to generate slide HTML.
        
        The Designer uses write_file tool to save HTML directly.
        After agent completes, we read the HTML from the file it created.
        """
        # Create registry with workspace-aware file tools
        workspace_registry = self._create_workspace_registry()
        
        agent = Agent(
            system_prompt=self.designer_prompt,
            model=self.settings.designer_model,
            settings=self.settings,
            registry=workspace_registry  # Use workspace-specific registry
        )
        
        try:
            # Build prompt - tell the designer the exact file path to use
            prompt = self._build_slide_prompt(task, design_context)
            
            # Run agent - it will use write_file to save HTML
            await agent.chat(prompt, execute_tools=True)
            
            # Read the HTML file that the agent created
            html_path = self.slides_path / f"slide_{task.index + 1}.html"
            if html_path.exists():
                html_content = html_path.read_text(encoding="utf-8")
                # Validate it's actually HTML and not just agent summary
                if html_content.strip().startswith("<!DOCTYPE") or html_content.strip().startswith("<html"):
                    return html_content
                elif "<div" in html_content and "class=" in html_content:
                    # It might be partial HTML (just the content div), wrap it
                    return self._wrap_html_content(html_content, task)
                else:
                    # File contains non-HTML content (like agent summary)
                    return self._generate_error_html(task, f"File contains invalid HTML content")
            else:
                # Fallback: if file wasn't created, return error HTML
                return self._generate_error_html(task, "Designer did not create the slide file")
            
        finally:
            await agent.close()
    
    def _wrap_html_content(self, content: str, task: SlideGenerationTask) -> str:
        """Wrap partial HTML content in a complete HTML document."""
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=1920, height=1080">
    <title>{task.data.get('title', f'Slide {task.index + 1}')}</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body {{
            margin: 0;
            width: 1920px;
            height: 1080px;
            overflow: hidden;
        }}
        .slide-container {{
            width: 100%;
            height: 100%;
            padding: 40px;
            box-sizing: border-box;
        }}
    </style>
</head>
<body>
    <div id="content" class="slide-container">
        {content}
    </div>
</body>
</html>"""
    
    def _generate_error_html(self, task: SlideGenerationTask, error_msg: str) -> str:
        """Generate an error HTML page."""
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=1920, height=1080">
    <title>Error - Slide {task.index + 1}</title>
    <style>
        body {{
            margin: 0;
            padding: 40px;
            width: 1920px;
            height: 1080px;
            box-sizing: border-box;
            font-family: Arial, sans-serif;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            background: #fef2f2;
            color: #991b1b;
        }}
        h1 {{ font-size: 48px; margin-bottom: 20px; }}
        p {{ font-size: 24px; }}
    </style>
</head>
<body>
    <h1>⚠️ Generation Error</h1>
    <p>{error_msg}</p>
    <p>Slide: {task.data.get('title', f'Slide {task.index + 1}')}</p>
</body>
</html>"""
    
    def _build_slide_prompt(
        self,
        task: SlideGenerationTask,
        design_context: Optional[str] = None
    ) -> str:
        """Build the prompt for slide generation.
        
        Matches the original slide_generator.py create_designer_task() behavior.
        Designer should READ the existing template file and REPLACE the content div.
        """
        slide_data = task.data
        slide_id = f"slide_{task.index + 1}"
        relative_path = f"slides/{slide_id}.html"
        
        # Build content description
        content_parts = []
        if slide_data.get("title"):
            content_parts.append(f"**标题:** {slide_data['title']}")
        
        if slide_data.get("content"):
            content = slide_data['content']
            if isinstance(content, list):
                content_str = "\n".join(f"- {item}" for item in content)
            else:
                content_str = str(content)
            content_parts.append(f"**内容:**\n{content_str}")
        
        if slide_data.get("notes"):
            content_parts.append(f"**演讲备注:** {slide_data['notes']}")
        
        if slide_data.get("layout"):
            content_parts.append(f"**布局建议:** {slide_data['layout']}")
        
        if design_context:
            content_parts.append(f"**设计上下文:** {design_context}")
        
        content_description = "\n\n".join(content_parts)
        
        # Match original create_designer_task() format
        return f"""请为幻灯片 {slide_id} 设计并生成专业的 HTML 内容。

**你的任务：**
根据以下内容描述，创建一个信息密度高、视觉效果专业的幻灯片。

{content_description}

**重要步骤（必须严格按顺序执行）：**
1. 首先使用 `read_file` 工具读取当前文件：{relative_path}
2. 分析内容描述，识别其中的数据点、关系、层次结构
3. 选择合适的视觉组件（卡片、图表、引用框等）来呈现内容
4. 使用 `write_file` 工具写入完整的 HTML 文件到：{relative_path}

**⚠️ 重要：你必须使用 write_file 工具来保存文件！**
- 不要只在回复中输出 HTML 代码
- 必须调用 write_file 工具，参数格式：{{"path": "{relative_path}", "content": "完整的HTML内容"}}
- 替换 `<div id="content" class="slide-container">` 内部的占位符内容
- 保留 HTML 文件的整体结构（包括 head 中的 Tailwind 和 Chart.js 引用）

**设计原则：**
- 页面必须是全屏幻灯片，不能有滚动
- 使用浅色背景（白色/灰色）
- 信息密度要高，不要浪费空间
- 使用彩色边框卡片、徽章、引用框等专业组件
- 参考系统提示中的组件库

**输出文件路径：** {relative_path}
"""
    
    def _extract_html(self, response: str) -> str:
        """Extract HTML content from agent response."""
        import re
        
        # Try to find HTML in code blocks
        code_block_pattern = r'```(?:html)?\s*(<!DOCTYPE html>.*?</html>)\s*```'
        match = re.search(code_block_pattern, response, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()
        
        # Try to find raw HTML
        html_pattern = r'(<!DOCTYPE html>.*?</html>)'
        match = re.search(html_pattern, response, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()
        
        # If no HTML found, wrap response in basic HTML
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=1920, height=1080">
    <title>Slide</title>
    <style>
        body {{
            margin: 0;
            padding: 40px;
            width: 1920px;
            height: 1080px;
            box-sizing: border-box;
            font-family: Arial, sans-serif;
        }}
    </style>
</head>
<body>
    {response}
</body>
</html>"""
    
    async def regenerate_slide(
        self,
        index: int,
        design_context: Optional[str] = None
    ) -> SlideGenerationTask:
        """Regenerate a specific slide.
        
        Args:
            index: Slide index to regenerate
            design_context: Additional context for design
            
        Returns:
            Updated generation task
        """
        if index < 0 or index >= len(self._tasks):
            raise ValueError(f"Invalid slide index: {index}")
        
        task = self._tasks[index]
        task.status = SlideStatus.PENDING
        task.error = None
        
        await self._generate_slide(task, design_context)
        
        return task
    
    def save_manifest(self) -> None:
        """Save generation manifest."""
        manifest = {
            "generated_at": datetime.now().isoformat(),
            "total_slides": len(self._tasks),
            "slides": [
                {
                    "index": t.index,
                    "title": t.data.get("title", f"Slide {t.index + 1}"),
                    "status": t.status.value,
                    "file": f"slide_{t.index + 1}.html" if t.status == SlideStatus.COMPLETED else None
                }
                for t in self._tasks
            ]
        }
        
        manifest_path = self.slides_path / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
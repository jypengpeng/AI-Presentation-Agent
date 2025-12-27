"""
Slide Generator Module

This module implements the multi-phase slide generation workflow:
1. Phase 1: Architect - Content planning (outputs presentation_plan.json)
2. Phase 2: Framework - Create empty HTML templates
3. Phase 3: Designer - Concurrent content generation for each slide
4. Phase 4: Export - Merge into single HTML file

Key Design:
- Architect inherits the main Agent's conversation history
- Designer creates new Agent instances for each slide (parallel processing)
"""

import os
import json
import asyncio
import re
import zipfile
from pathlib import Path
from typing import Optional, Callable, Any, Generator
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import logging

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================================
# Enums and Data Classes
# ============================================================================

class SlideStatus(Enum):
    """Status of a slide in the generation process"""
    PENDING = "pending"
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"
    MODIFIED = "modified"


class SlideType(Enum):
    """Types of slides supported"""
    TITLE = "title"
    SECTION_HEADER = "section_header"
    BULLET_LIST = "bullet_list"
    SPLIT_CONTENT_CHART = "split_content_chart"
    BIG_STAT = "big_stat"
    GRID_CARDS = "grid_cards"


@dataclass
class SlideData:
    """Data for a single slide - simplified for creative freedom"""
    id: str
    title: str
    content: str  # Rich content description for the Designer


@dataclass
class ThemeData:
    """Theme configuration for the presentation - light theme default"""
    color_palette: str = "Professional Light"
    background_class: str = "bg-white"
    text_primary: str = "text-gray-800"
    text_accent: str = "text-blue-600"
    font_family: str = "Inter, sans-serif"


@dataclass
class PresentationPlan:
    """Complete presentation plan from Architect"""
    theme: ThemeData
    slides: list  # List of SlideData


@dataclass
class ManifestSlide:
    """Slide entry in manifest.json"""
    id: str
    file: str
    type: str
    title: str
    status: str = "pending"
    generated_at: Optional[str] = None


@dataclass
class Manifest:
    """Manifest file structure"""
    version: str = "1.0"
    created_at: str = ""
    updated_at: str = ""
    theme: dict = field(default_factory=dict)
    slides: list = field(default_factory=list)
    total_slides: int = 0
    completed_slides: int = 0


@dataclass
class RetryConfig:
    """Configuration for retry mechanism"""
    max_retries: int = 3
    base_delay: float = 1.0  # seconds
    max_delay: float = 30.0
    exponential_base: float = 2.0
    task_timeout: float = 120.0  # seconds per slide generation


@dataclass
class GenerationResult:
    """Result of slide generation"""
    success: bool
    slide_id: str
    error: Optional[str] = None
    retry_count: int = 0


# ============================================================================
# HTML Template
# ============================================================================

SLIDE_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Slide {slide_index} - {slide_title}</title>
    
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
            font-family: 'Inter', 'SF Pro Display', -apple-system, BlinkMacSystemFont, sans-serif;
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
    
    <!-- Navigation Script -->
    <script>
        const SLIDE_CONFIG = {{
            currentIndex: {slide_index},
            totalSlides: {total_slides},
            prevSlide: {prev_slide_path},
            nextSlide: {next_slide_path}
        }};
        
        document.addEventListener('keydown', (e) => {{
            if (e.key === 'ArrowLeft' && SLIDE_CONFIG.prevSlide) {{
                window.location.href = SLIDE_CONFIG.prevSlide;
            }} else if ((e.key === 'ArrowRight' || e.key === ' ' || e.key === 'Enter') && SLIDE_CONFIG.nextSlide) {{
                window.location.href = SLIDE_CONFIG.nextSlide;
            }}
        }});
    </script>
</body>
</html>
"""


# ============================================================================
# Exported Single File Template (iframe-based loader)
# ============================================================================

EXPORTED_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        html, body {{
            width: 100vw;
            height: 100vh;
            overflow: hidden;
            font-family: 'Inter', 'SF Pro Display', -apple-system, BlinkMacSystemFont, sans-serif;
            background: white;
        }}
        
        #slide-frame {{
            width: 100%;
            height: 100%;
            border: none;
            background: white;
        }}
        
        #slide-indicator {{
            position: fixed;
            bottom: 16px;
            right: 16px;
            color: #9ca3af;
            font-size: 14px;
            font-weight: 400;
            z-index: 1000;
            pointer-events: none;
        }}
        
        #loading {{
            position: fixed;
            inset: 0;
            display: flex;
            align-items: center;
            justify-content: center;
            background: white;
            z-index: 999;
            transition: opacity 0.3s;
        }}
        
        #loading.hidden {{
            opacity: 0;
            pointer-events: none;
        }}
        
        .spinner {{
            width: 40px;
            height: 40px;
            border: 3px solid #e5e7eb;
            border-top-color: #3b82f6;
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
        }}
        
        @keyframes spin {{
            to {{ transform: rotate(360deg); }}
        }}
    </style>
</head>
<body>
    <!-- Loading indicator -->
    <div id="loading">
        <div class="spinner"></div>
    </div>
    
    <!-- Slide iframe -->
    <iframe id="slide-frame" src=""></iframe>
    
    <!-- Slide indicator -->
    <div id="slide-indicator">1 / {total_slides}</div>
    
    <script>
        // Slide configuration
        const slides = {slides_json};
        const totalSlides = slides.length;
        let currentSlideIndex = 0;
        
        // DOM elements
        const frame = document.getElementById('slide-frame');
        const indicator = document.getElementById('slide-indicator');
        const loading = document.getElementById('loading');
        
        // Load a slide
        function loadSlide(index) {{
            if (index < 0 || index >= totalSlides) return;
            
            loading.classList.remove('hidden');
            currentSlideIndex = index;
            
            // Update iframe src
            frame.src = slides[index].file;
            
            // Update indicator
            indicator.textContent = `${{index + 1}} / ${{totalSlides}}`;
        }}
        
        // Navigation functions
        function nextSlide() {{
            if (currentSlideIndex < totalSlides - 1) {{
                loadSlide(currentSlideIndex + 1);
            }}
        }}
        
        function prevSlide() {{
            if (currentSlideIndex > 0) {{
                loadSlide(currentSlideIndex - 1);
            }}
        }}
        
        // Toggle fullscreen
        function toggleFullscreen() {{
            if (!document.fullscreenElement) {{
                document.documentElement.requestFullscreen().catch(err => {{
                    console.log('Fullscreen error:', err);
                }});
            }} else {{
                document.exitFullscreen();
            }}
        }}
        
        // Keyboard navigation
        document.addEventListener('keydown', (e) => {{
            if (e.key === 'ArrowRight' || e.key === ' ') {{
                e.preventDefault();
                nextSlide();
            }} else if (e.key === 'ArrowLeft') {{
                e.preventDefault();
                prevSlide();
            }} else if (e.key === 'Enter' || e.key === 'F' || e.key === 'f') {{
                e.preventDefault();
                toggleFullscreen();
            }} else if (e.key === 'Home') {{
                e.preventDefault();
                loadSlide(0);
            }} else if (e.key === 'End') {{
                e.preventDefault();
                loadSlide(totalSlides - 1);
            }} else if (e.key === 'Escape' && document.fullscreenElement) {{
                // Escape is handled by browser for fullscreen exit
            }}
        }});
        
        // Hide loading when iframe loads
        frame.addEventListener('load', () => {{
            loading.classList.add('hidden');
        }});
        
        // Initialize - load first slide
        loadSlide(0);
    </script>
</body>
</html>
"""


# ============================================================================
# SlideGenerator Class
# ============================================================================

class SlideGenerator:
    """
    Coordinates the multi-phase slide generation workflow.
    
    This class manages:
    1. Switching the main Agent to Architect role (preserving conversation history)
    2. Creating empty HTML templates based on the plan
    3. Spawning Designer Agents for concurrent slide generation
    4. Exporting to a single HTML file
    """
    
    def __init__(
        self,
        api_key: str,
        workspace_dir: str,
        model: str = "gpt-4o",
        base_url: Optional[str] = None,
        concurrency: int = 0,  # 0 = unlimited
        task_timeout: float = 120.0,  # seconds per slide
        on_progress: Optional[Callable[[str, int, int], None]] = None,
        on_slide_complete: Optional[Callable[[str, bool], None]] = None
    ):
        """
        Initialize the SlideGenerator.
        
        Args:
            api_key: OpenAI API key
            workspace_dir: Root directory for file operations
            model: Model to use for generation
            base_url: Optional custom API base URL
            concurrency: Max concurrent slide generations (0 = unlimited)
            task_timeout: Timeout per slide generation in seconds
            on_progress: Callback(phase, current, total) for progress updates
            on_slide_complete: Callback(slide_id, success) when a slide is done
        """
        self.api_key = api_key
        self.workspace_dir = Path(workspace_dir).resolve()
        self.model = model
        self.base_url = base_url
        self.concurrency = concurrency
        self.on_progress = on_progress
        self.on_slide_complete = on_slide_complete
        
        # Load prompts
        self.architect_prompt = self._load_prompt("Architect_prompt.md")
        self.designer_prompt = self._load_prompt("Designer.md")
        
        # Retry configuration with custom timeout
        self.retry_config = RetryConfig(task_timeout=task_timeout)
    
    def _load_prompt(self, filename: str) -> str:
        """Load a prompt file from the project directory (where slide_generator.py is located).
        
        Note: We load from the project root, not the task workspace directory,
        because the workspace is the user's project being analyzed.
        """
        # Load from the code directory (where slide_generator.py is located)
        code_dir = Path(__file__).parent.resolve()
        prompt_path = code_dir / filename
        
        if prompt_path.exists():
            logger.info(f"[PROMPT] Loading prompt: {prompt_path}")
            return prompt_path.read_text(encoding='utf-8')
        else:
            logger.error(f"[PROMPT] Prompt file not found: {prompt_path}")
            return ""
    
    # =========================================================================
    # Phase 1: Architect - Content Planning
    # =========================================================================
    
    def build_architect_prompt(self, agent_tools_json: str) -> str:
        """
        Build the complete Architect system prompt.
        
        Args:
            agent_tools_json: Tool definitions from AgentTools.get_tool_definitions_json()
        
        Returns:
            Complete system prompt for Architect role
        """
        return f"""{self.architect_prompt}

{agent_tools_json}
"""
    
    def create_architect_task(self, user_request: str) -> str:
        """
        Create the task instruction for Architect.
        
        Args:
            user_request: The user's original request
        
        Returns:
            Task instruction string
        """
        return f"""基于你之前收集的所有信息，现在请为用户创建演示文稿规划。

用户请求：{user_request}

请根据之前的分析结果，输出 presentation_plan.json 文件。
如果信息不足，可以使用工具进行补充探索。

**重要规则：**
1. 输出必须是纯 JSON 格式，不要包含 markdown 代码块
2. 文件路径：slides/presentation_plan.json
3. 使用 write_file 工具写入文件
4. **内容要详尽**：每个 slide 的 content 字段需要包含所有相关信息

**JSON Schema（极简结构）：**
{{
  "title": "演示文稿标题",
  "slides": [
    {{
      "id": "slide_1",
      "title": "幻灯片标题",
      "content": "详细的内容描述，包括所有数据点、公式、对比、引用等。Designer 会根据这个内容自由设计视觉布局。不要省略任何重要信息。"
    }}
  ]
}}

**Content 字段示例：**
"content": "Success Index 设计 - 一个衡量游戏成功的综合指标：

公式：Success Index = W₁×normalize(Positive Rate) + W₂×normalize(log(Total Reviews)) + W₃×normalize(Avg Playtime) + W₄×normalize(Owner Count)

四个维度及权重：
1. 游戏质量 (30%) - 好评率 - 直接反映玩家认可度
2. 市场影响力 (35%) - log(评论数) - 反映曝光度和讨论度
3. 玩家参与度 (20%) - 平均游戏时长 - 反映留存和粘性
4. 商业表现 (15%) - 拥有者数量 - 直接反映销售成功

核心洞察：市场影响力权重最高(35%)，因为评论数同时反映购买量和玩家活跃度。

引用：'成功不能仅由销售额定义——必须从质量、影响力、参与度和商业维度综合评估'"
"""
    
    # =========================================================================
    # Phase 2: Framework - Create Empty Templates
    # =========================================================================
    
    def create_slide_framework(self, plan: dict) -> Path:
        """
        Create the slide framework: empty HTML templates and manifest.json.
        
        Args:
            plan: The presentation plan from Architect (parsed JSON)
        
        Returns:
            Path to the slides directory
        """
        slides_dir = self.workspace_dir / "slides"
        slides_dir.mkdir(parents=True, exist_ok=True)
        
        slides = plan.get("slides", [])
        presentation_title = plan.get("title", "Presentation")
        
        # Create manifest
        manifest = {
            "version": "1.0",
            "created_at": datetime.utcnow().isoformat() + "Z",
            "updated_at": datetime.utcnow().isoformat() + "Z",
            "title": presentation_title,
            "slides": [],
            "total_slides": len(slides),
            "completed_slides": 0
        }
        
        # Create each slide HTML
        for i, slide in enumerate(slides):
            slide_id = slide.get("id", f"slide_{i + 1}")
            slide_title = slide.get("title", f"Slide {i + 1}")
            
            # File name
            filename = f"{slide_id}.html"
            filepath = slides_dir / filename
            
            # Navigation paths
            prev_path = f'"{slides[i - 1].get("id", f"slide_{i}")}.html"' if i > 0 else "null"
            next_path = f'"{slides[i + 1].get("id", f"slide_{i + 2}")}.html"' if i < len(slides) - 1 else "null"
            
            # Generate HTML from template (simplified - no theme variables)
            html_content = SLIDE_TEMPLATE.format(
                slide_index=i + 1,
                slide_title=slide_title,
                total_slides=len(slides),
                prev_slide_path=prev_path,
                next_slide_path=next_path
            )
            
            filepath.write_text(html_content, encoding='utf-8')
            logger.info(f"Created slide template: {filepath}")
            
            # Add to manifest
            manifest["slides"].append({
                "id": slide_id,
                "file": filename,
                "title": slide_title,
                "content": slide.get("content", ""),
                "status": "pending",
                "generated_at": None
            })
        
        # Write manifest
        manifest_path = slides_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
        logger.info(f"Created manifest: {manifest_path}")
        
        # Also save the original plan
        plan_path = slides_dir / "presentation_plan.json"
        plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding='utf-8')
        
        return slides_dir
    
    # =========================================================================
    # Phase 3: Designer - Content Generation
    # =========================================================================
    
    def build_designer_prompt(self, slide_data: dict, agent_tools_json: str) -> str:
        """
        Build the complete Designer system prompt for a specific slide.
        
        Args:
            slide_data: The slide's data from the plan (id, title, content)
            agent_tools_json: Tool definitions (should include generate_image for Designer)
        
        Returns:
            Complete system prompt for Designer role
        """
        return f"""{self.designer_prompt}

## Current Slide Data

**Slide ID:** {slide_data.get('id', 'unknown')}
**Title:** {slide_data.get('title', 'Untitled')}

**Content to Display:**
{slide_data.get('content', 'No content provided')}

---

{agent_tools_json}
"""
    
    def create_designer_task(self, slide_id: str, relative_path: str) -> str:
        """
        Create the task instruction for Designer.
        
        Args:
            slide_id: The slide ID
            relative_path: Relative path to the slide HTML file (e.g., "slides/slide_1.html")
        
        Returns:
            Task instruction string
        """
        return f"""请为幻灯片 {slide_id} 设计并生成专业的 HTML 内容。

**你的任务：**
根据系统提示中提供的 slide 标题和内容描述，创建一个信息密度高、视觉效果专业的幻灯片。

**重要步骤：**
1. 首先使用 read_file 工具读取当前文件：{relative_path}
2. 分析内容描述，识别其中的数据点、关系、层次结构
3. 选择合适的视觉组件（卡片、图表、引用框等）来呈现内容
4. 生成 HTML 内容替换 `<div id="content">` 内的占位符
5. 使用 write_file 工具将完整的 HTML 写回文件

**设计原则：**
- 使用浅色背景（白色/灰色）
- 信息密度要高，不要浪费空间
- 使用彩色边框卡片、徽章、引用框等专业组件
- 参考系统提示中的组件库
- 保持文件的 HTML 结构完整，只替换 `<div id="content" class="slide-container">` 内部的内容

**输出文件路径：** {relative_path}

完成后不要调用 task_completed，直接结束即可。
"""
    
    async def generate_slides_concurrent(
        self,
        plan: dict,
        slides_dir: Path,
        create_agent_func: Callable
    ) -> dict:
        """
        Generate all slides concurrently.
        
        Args:
            plan: The presentation plan
            slides_dir: Directory containing slide templates
            create_agent_func: Function to create a new Agent instance
                              signature: (system_prompt: str) -> Agent
        
        Returns:
            Statistics dict with success/failure counts
        """
        slides = plan.get("slides", [])
        
        # Semaphore for concurrency control
        if self.concurrency > 0:
            semaphore = asyncio.Semaphore(self.concurrency)
        else:
            semaphore = asyncio.Semaphore(len(slides))  # Effectively unlimited
        
        results = []
        total_slides = len(slides)
        completed_count = 0
        
        logger.info(f"Starting concurrent generation of {total_slides} slides (concurrency={self.concurrency or 'unlimited'})")
        
        async def generate_with_semaphore(slide_data: dict, index: int):
            nonlocal completed_count
            slide_id = slide_data.get("id", f"slide_{index + 1}")
            
            async with semaphore:
                logger.info(f"[{slide_id}] Acquired semaphore, starting generation...")
                
                try:
                    # Wrap with timeout to prevent indefinite hanging
                    result = await asyncio.wait_for(
                        self._generate_single_slide_with_retry(
                            slide_data=slide_data,
                            slides_dir=slides_dir,
                            create_agent_func=create_agent_func,
                            index=index
                        ),
                        timeout=self.retry_config.task_timeout
                    )
                    
                    completed_count += 1
                    logger.info(f"[{slide_id}] Generation completed ({completed_count}/{total_slides})")
                    return result
                    
                except asyncio.TimeoutError:
                    completed_count += 1
                    logger.error(f"[{slide_id}] Generation TIMEOUT after {self.retry_config.task_timeout}s ({completed_count}/{total_slides})")
                    # 立即更新 manifest 状态
                    self._update_manifest_status(slides_dir, slide_id, "failed")
                    return GenerationResult(
                        success=False,
                        slide_id=slide_id,
                        error=f"Generation timeout after {self.retry_config.task_timeout} seconds",
                        retry_count=self.retry_config.max_retries
                    )
                except Exception as e:
                    completed_count += 1
                    logger.error(f"[{slide_id}] Generation FAILED with exception: {e} ({completed_count}/{total_slides})")
                    # 立即更新 manifest 状态
                    self._update_manifest_status(slides_dir, slide_id, "failed")
                    return GenerationResult(
                        success=False,
                        slide_id=slide_id,
                        error=str(e),
                        retry_count=0
                    )
        
        # Create tasks for all slides
        tasks = [
            generate_with_semaphore(slide, i)
            for i, slide in enumerate(slides)
        ]
        
        logger.info(f"Created {len(tasks)} generation tasks, waiting for completion...")
        
        # Run concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        logger.info(f"All tasks completed. Processing results...")
        
        # Process results
        stats = {
            "total": len(slides),
            "success": 0,
            "failed": 0,
            "errors": []
        }
        
        for i, result in enumerate(results):
            slide_id = slides[i].get("id", f"slide_{i + 1}")
            
            if isinstance(result, Exception):
                stats["failed"] += 1
                stats["errors"].append({
                    "slide_id": slide_id,
                    "error": str(result)
                })
                # 状态已在 generate_with_semaphore 中更新，这里只做记录
                logger.error(f"[{slide_id}] Result: Exception - {result}")
            elif isinstance(result, GenerationResult):
                if result.success:
                    stats["success"] += 1
                    # 状态已在 _generate_single_slide_with_retry 中立即更新
                    logger.info(f"[{slide_id}] Result: SUCCESS (retries={result.retry_count})")
                else:
                    stats["failed"] += 1
                    stats["errors"].append({
                        "slide_id": slide_id,
                        "error": result.error
                    })
                    # 状态已在 _generate_single_slide_with_retry 中立即更新
                    logger.error(f"[{slide_id}] Result: FAILED - {result.error}")
            else:
                # Unexpected result type
                stats["failed"] += 1
                stats["errors"].append({
                    "slide_id": slide_id,
                    "error": f"Unexpected result type: {type(result)}"
                })
                # 确保异常情况也更新状态
                self._update_manifest_status(slides_dir, slide_id, "failed")
                logger.error(f"[{slide_id}] Result: UNEXPECTED TYPE - {type(result)}")
        
        logger.info(f"Generation complete: {stats['success']}/{stats['total']} success, {stats['failed']} failed")
        
        return stats
    
    async def _generate_single_slide_with_retry(
        self,
        slide_data: dict,
        slides_dir: Path,
        create_agent_func: Callable,
        index: int
    ) -> GenerationResult:
        """
        Generate a single slide with retry logic.
        
        Uses exponential backoff: 1s -> 2s -> 4s
        """
        slide_id = slide_data.get("id", f"slide_{index + 1}")
        # Use relative path for write_file tool (relative to workspace)
        relative_path = f"slides/{slide_id}.html"
        absolute_path = slides_dir / f"{slide_id}.html"
        
        last_error = None
        
        for attempt in range(self.retry_config.max_retries):
            try:
                logger.debug(f"[{slide_id}] Attempt {attempt + 1}/{self.retry_config.max_retries}")
                
                # Update manifest to generating
                self._update_manifest_status(slides_dir, slide_id, "generating")
                
                # Create a new Designer agent with image generation capability
                from agent_core import Agent
                
                logger.debug(f"[{slide_id}] Creating temp agent for tool definitions...")
                
                # Get tool definitions with generate_image enabled (Designer-only tool)
                temp_agent = Agent(
                    api_key=self.api_key,
                    workspace_dir=str(self.workspace_dir),
                    model=self.model,
                    base_url=self.base_url,
                    include_image_tool=True  # Enable image generation for Designer
                )
                tools_json = temp_agent.tools.get_tool_definitions_json()
                
                logger.debug(f"[{slide_id}] Building designer prompt...")
                designer_prompt = self.build_designer_prompt(slide_data, tools_json)
                designer_agent = create_agent_func(designer_prompt)
                
                # Use relative path for the task
                task = self.create_designer_task(slide_id, relative_path)
                
                logger.debug(f"[{slide_id}] Calling designer_agent.run_sync() in thread pool...")
                
                # Run the agent in a thread pool to avoid blocking the event loop
                # This is critical for true concurrency - run_sync is blocking
                result = await asyncio.to_thread(designer_agent.run_sync, task)
                
                logger.debug(f"[{slide_id}] run_sync() returned: success={result.get('success')}")
                
                if result.get("success"):
                    # Verify that the file was actually updated (not just the placeholder)
                    if absolute_path.exists():
                        content = absolute_path.read_text(encoding='utf-8')
                        if '正在生成内容' in content or 'Content will be injected here' in content:
                            last_error = "File not updated - still contains placeholder content"
                            logger.warning(f"[{slide_id}] Agent returned success but file still has placeholder content")
                            continue  # Retry
                    
                    logger.info(f"[{slide_id}] Successfully generated on attempt {attempt + 1}")
                    
                    # 立即更新 manifest 状态，使 UI 能实时显示进度
                    self._update_manifest_status(slides_dir, slide_id, "completed")
                    
                    if self.on_slide_complete:
                        self.on_slide_complete(slide_id, True)
                    
                    return GenerationResult(
                        success=True,
                        slide_id=slide_id,
                        retry_count=attempt
                    )
                else:
                    last_error = result.get("error", "Unknown error")
                    logger.warning(f"[{slide_id}] Generation failed (attempt {attempt + 1}/{self.retry_config.max_retries}): {last_error}")
            
            except Exception as e:
                last_error = str(e)
                logger.warning(f"[{slide_id}] Exception on attempt {attempt + 1}/{self.retry_config.max_retries}: {e}")
            
            # Wait before retry (exponential backoff)
            if attempt < self.retry_config.max_retries - 1:
                delay = min(
                    self.retry_config.base_delay * (self.retry_config.exponential_base ** attempt),
                    self.retry_config.max_delay
                )
                logger.debug(f"[{slide_id}] Waiting {delay}s before retry...")
                await asyncio.sleep(delay)
        
        # All retries exhausted - 立即更新 manifest 状态
        self._update_manifest_status(slides_dir, slide_id, "failed")
        
        if self.on_slide_complete:
            self.on_slide_complete(slide_id, False)
        
        return GenerationResult(
            success=False,
            slide_id=slide_id,
            error=last_error,
            retry_count=self.retry_config.max_retries
        )
    
    def _update_manifest_status(self, slides_dir: Path, slide_id: str, status: str):
        """Update the status of a slide in manifest.json."""
        manifest_path = slides_dir / "manifest.json"
        
        if not manifest_path.exists():
            return
        
        try:
            manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
            
            for slide in manifest.get("slides", []):
                if slide.get("id") == slide_id:
                    slide["status"] = status
                    if status == "completed":
                        slide["generated_at"] = datetime.utcnow().isoformat() + "Z"
                    break
            
            # Update counts
            manifest["completed_slides"] = sum(
                1 for s in manifest.get("slides", [])
                if s.get("status") == "completed"
            )
            manifest["updated_at"] = datetime.utcnow().isoformat() + "Z"
            
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
        
        except Exception as e:
            logger.error(f"Failed to update manifest: {e}")
    
    # =========================================================================
    # Phase 4: Export - Merge to Single File
    # =========================================================================
    
    def export_to_single_file(self, slides_dir: Path, output_path: Optional[Path] = None, slides_path_prefix: str = "../slides/") -> Path:
        """
        Create a presentation loader that dynamically loads slide HTML files via iframe.
        
        This approach preserves all CSS, JS, and content from individual slides,
        avoiding the issues with content extraction and merging.
        
        Args:
            slides_dir: Directory containing slide HTML files
            output_path: Optional output path (default: exported/presentation.html)
            slides_path_prefix: Prefix for slide file paths (default: "../slides/" for exported folder)
        
        Returns:
            Path to the exported file
        """
        if output_path is None:
            export_dir = self.workspace_dir / "exported"
            export_dir.mkdir(parents=True, exist_ok=True)
            output_path = export_dir / "presentation.html"
        
        # Read manifest
        manifest_path = slides_dir / "manifest.json"
        if not manifest_path.exists():
            raise FileNotFoundError(f"Manifest not found: {manifest_path}")
        
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        slides_meta = manifest.get("slides", [])
        
        # Build slides array for JavaScript
        slides_json = json.dumps([
            {
                "id": slide.get("id", f"slide_{i+1}"),
                "title": slide.get("title", f"Slide {i+1}"),
                "file": f"{slides_path_prefix}{slide.get('file', f'slide_{i+1}.html')}"
            }
            for i, slide in enumerate(slides_meta)
        ], ensure_ascii=False)
        
        # Get title from manifest
        title = manifest.get("title", slides_meta[0].get("title", "Presentation") if slides_meta else "Presentation")
        
        # Generate exported HTML
        exported_html = EXPORTED_HTML_TEMPLATE.format(
            title=title,
            slides_json=slides_json,
            total_slides=len(slides_meta)
        )
        
        output_path.write_text(exported_html, encoding='utf-8')
        logger.info(f"Exported presentation to: {output_path}")
        
        return output_path
    
    def create_zip_package(self, slides_dir: Path, output_path: Optional[Path] = None) -> Path:
        """
        Create a ZIP package containing the presentation and all slides.
        
        The ZIP structure:
        - presentation.html (main file to open)
        - slides/ (all slide HTML files)
        - README.md (keyboard shortcuts guide)
        
        Args:
            slides_dir: Directory containing slide HTML files
            output_path: Optional output path for the ZIP file
        
        Returns:
            Path to the created ZIP file
        """
        import tempfile
        
        export_dir = self.workspace_dir / "exported"
        export_dir.mkdir(parents=True, exist_ok=True)
        
        # Determine output path
        if output_path is None:
            output_path = export_dir / "presentation.zip"
        
        # Read manifest for title
        manifest_path = slides_dir / "manifest.json"
        title = "Presentation"
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
                title = manifest.get("title", "Presentation")
            except:
                pass
        
        # Generate presentation.html with correct paths for ZIP structure
        # In ZIP: presentation.html and slides/ are in the same directory
        # So we use "slides/" instead of "../slides/"
        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as tmp:
            tmp_path = Path(tmp.name)
        
        self.export_to_single_file(slides_dir, output_path=tmp_path, slides_path_prefix="slides/")
        
        # Create README content
        readme_content = f"""# {title}

## 使用说明

打开 `presentation.html` 文件即可开始演示。

## 键盘快捷键

| 按键 | 功能 |
|------|------|
| ← | 上一页 |
| → | 下一页 |
| 空格 | 下一页 |
| Enter | 切换全屏 |
| F | 切换全屏 |
| Esc | 退出全屏 |
| Home | 跳到第一页 |
| End | 跳到最后一页 |

## 文件结构

```
├── presentation.html    # 主文件，打开此文件开始演示
├── slides/              # 幻灯片文件目录
│   ├── slide_1.html
│   ├── slide_2.html
│   └── ...
└── README.md            # 本说明文件
```

## 注意事项

- 请确保 `slides` 文件夹与 `presentation.html` 在同一目录下
- 建议使用现代浏览器（Chrome、Firefox、Edge）打开
- 如需编辑单个幻灯片，可直接修改 `slides` 文件夹中的 HTML 文件
"""
        
        # Create ZIP file
        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            # Add presentation.html (with correct paths for ZIP structure)
            zf.write(tmp_path, 'presentation.html')
            
            # Add README.md
            zf.writestr('README.md', readme_content)
            
            # Add all files from slides directory
            for file_path in slides_dir.iterdir():
                if file_path.is_file():
                    arcname = f'slides/{file_path.name}'
                    zf.write(file_path, arcname)
        
        # Clean up temp file
        try:
            tmp_path.unlink()
        except:
            pass
        
        logger.info(f"Created ZIP package: {output_path}")
        
        return output_path
    
    # =========================================================================
    # Single Slide Modification
    # =========================================================================
    
    def regenerate_slide(
        self,
        slides_dir: Path,
        slide_id: str,
        user_feedback: Optional[str] = None,
        create_agent_func: Optional[Callable] = None
    ) -> Generator[dict, None, None]:
        """
        Regenerate a single slide, optionally with user feedback.
        
        Args:
            slides_dir: Directory containing slide files
            slide_id: ID of the slide to regenerate
            user_feedback: Optional user feedback for modification
            create_agent_func: Function to create a new Agent
        
        Yields:
            Events from the agent
        """
        # Read the plan
        plan_path = slides_dir / "presentation_plan.json"
        if not plan_path.exists():
            yield {"type": "error", "error": f"Plan not found: {plan_path}"}
            return
        
        plan = json.loads(plan_path.read_text(encoding='utf-8'))
        
        # Find the slide
        slide_data = None
        for slide in plan.get("slides", []):
            if slide.get("id") == slide_id:
                slide_data = slide
                break
        
        if not slide_data:
            yield {"type": "error", "error": f"Slide not found: {slide_id}"}
            return
        
        # Read current slide content
        relative_path = f"slides/{slide_id}.html"
        absolute_path = slides_dir / f"{slide_id}.html"
        current_content = ""
        if absolute_path.exists():
            current_content = absolute_path.read_text(encoding='utf-8')
        
        # Build the task with feedback
        if user_feedback:
            task = f"""请修改这个幻灯片的内容。

**用户反馈：**
{user_feedback}

**原始内容描述：**
{slide_data.get('content', 'N/A')}

**当前 HTML 内容：**
```html
{current_content}
```

请根据用户反馈修改内容，使用 write_file 更新文件：{relative_path}
只需要替换 `<div id="content">` 标签内的内容。
"""
        else:
            task = self.create_designer_task(slide_id, relative_path)
        
        # Create and run Designer agent with image generation capability
        if create_agent_func:
            from agent_core import Agent
            temp_agent = Agent(
                api_key=self.api_key,
                workspace_dir=str(self.workspace_dir),
                model=self.model,
                base_url=self.base_url,
                include_image_tool=True  # Enable image generation for Designer
            )
            tools_json = temp_agent.tools.get_tool_definitions_json()
            
            designer_prompt = self.build_designer_prompt(slide_data, tools_json)
            designer_agent = create_agent_func(designer_prompt)
            
            for event in designer_agent.run(task):
                yield event
                
                if event.get("type") == "tool_result":
                    tc = event.get("tool_call")
                    if tc:
                        tc_name = tc.name if hasattr(tc, 'name') else tc.get("name", "")
                        if tc_name == "write_file":
                            self._update_manifest_status(slides_dir, slide_id, "modified")


# ============================================================================
# Utility Functions
# ============================================================================

def parse_presentation_plan(plan_path: Path) -> Optional[dict]:
    """
    Parse and validate a presentation plan JSON file.
    
    Args:
        plan_path: Path to the presentation_plan.json file
    
    Returns:
        Parsed plan dict or None if invalid
    """
    if not plan_path.exists():
        return None
    
    try:
        plan = json.loads(plan_path.read_text(encoding='utf-8'))
        
        # Basic validation
        if "slides" not in plan:
            logger.error("Plan missing 'slides' key")
            return None
        
        if not isinstance(plan["slides"], list):
            logger.error("'slides' must be a list")
            return None
        
        if len(plan["slides"]) == 0:
            logger.error("'slides' list is empty")
            return None
        
        return plan
    
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse plan JSON: {e}")
        return None


def get_slide_status_summary(slides_dir: Path) -> dict:
    """
    Get a summary of slide generation status.
    
    Args:
        slides_dir: Directory containing slides
    
    Returns:
        Status summary dict
    """
    manifest_path = slides_dir / "manifest.json"
    
    if not manifest_path.exists():
        return {"error": "Manifest not found"}
    
    try:
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        
        status_counts = {
            "pending": 0,
            "generating": 0,
            "completed": 0,
            "failed": 0,
            "modified": 0
        }
        
        for slide in manifest.get("slides", []):
            status = slide.get("status", "pending")
            if status in status_counts:
                status_counts[status] += 1
        
        return {
            "total": manifest.get("total_slides", 0),
            "completed": manifest.get("completed_slides", 0),
            **status_counts
        }
    
    except Exception as e:
        return {"error": str(e)}
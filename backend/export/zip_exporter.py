"""ZIP package export functionality.

This module provides:
- ZipExporter: Package all presentation assets into a ZIP file
"""

import asyncio
import io
import json
import logging
import zipfile
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Union

from config import Settings, get_settings

logger = logging.getLogger(__name__)


class ZipExporter:
    """Packages presentation assets into a ZIP file.
    
    Includes:
    - HTML slides
    - Combined presentation (iframe loader)
    - PPTX file (via screenshots)
    - Speech scripts and coaching
    - Presentation plan
    - README with keyboard shortcuts
    """
    
    def __init__(
        self,
        workspace_path: Path,
        settings: Optional[Settings] = None
    ):
        """Initialize exporter.
        
        Args:
            workspace_path: Path to task workspace
            settings: Application settings
        """
        self.workspace_path = Path(workspace_path)
        self.slides_path = self.workspace_path / "slides"
        self.settings = settings or get_settings()
    
    def _get_manifest(self) -> Optional[dict]:
        """Read and return the manifest.json file."""
        manifest_path = self.slides_path / "manifest.json"
        if not manifest_path.exists():
            return None
        try:
            return json.loads(manifest_path.read_text(encoding='utf-8'))
        except Exception:
            return None
    
    async def _generate_pptx(self) -> Optional[Path]:
        """Generate PPTX file using PPTXExporter.
        
        Returns:
            Path to PPTX file, or None if failed
        """
        try:
            from export.pptx_exporter import PPTXExporter
            
            exporter = PPTXExporter(self.workspace_path)
            pptx_path = await exporter.export()
            return pptx_path
        except ImportError as e:
            logger.warning(f"PPTX export dependencies not available: {e}")
            return None
        except Exception as e:
            logger.error(f"Error generating PPTX: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _get_screenshot_paths(self) -> List[Path]:
        """Get existing screenshot paths.
        
        Returns:
            List of screenshot file paths
        """
        screenshots_path = self.workspace_path / "screenshots"
        if not screenshots_path.exists():
            return []
        
        import re
        paths = list(screenshots_path.glob("slide_*.png"))
        paths.sort(key=lambda p: int(re.search(r'slide_(\d+)', p.stem).group(1)) if re.search(r'slide_(\d+)', p.stem) else 0)
        return paths
    
    def _generate_speech_materials(
        self
    ) -> tuple[Optional[str], Optional[str]]:
        """Generate speech script and coaching.
        
        Returns:
            Tuple of (speech_script, speech_coaching) or (None, None) if failed
        """
        try:
            from export.speech_generator import SpeechGenerator
        except ImportError:
            logger.warning("SpeechGenerator not available")
            return None, None
        
        # Check if API key is configured (SpeechGenerator reads from .env via settings)
        if not self.settings.openai_api_key:
            logger.warning("OPENAI_API_KEY not configured in .env, skipping speech generation")
            return None, None
        
        try:
            # SpeechGenerator reads configuration from .env via get_settings()
            generator = SpeechGenerator(settings=self.settings)
            
            speech_script = generator.generate_speech_script(self.slides_path)
            speech_coaching = None
            
            if speech_script:
                speech_coaching = generator.generate_speech_coaching(speech_script)
            
            return speech_script, speech_coaching
        except Exception as e:
            logger.error(f"Error generating speech materials: {e}")
            return None, None
    
    def _generate_readme(
        self,
        title: str,
        has_pptx: bool = False,
        has_speech: bool = False,
        has_coaching: bool = False
    ) -> str:
        """Generate README content for the ZIP package."""
        pptx_note = ""
        if has_pptx:
            pptx_note = "├── presentation.pptx    # PowerPoint 版本\n"
        
        speech_note = ""
        if has_speech:
            speech_note = "├── speech_script.md     # 演讲稿\n"
        if has_coaching:
            speech_note += "├── speech_coaching.md   # 演讲指导\n"
        
        return f"""# {title}

## 使用说明

打开 `presentation.html` 文件即可开始演示。
{"也可以使用 `presentation.pptx` 在 PowerPoint 中打开。" if has_pptx else ""}

{"## 演讲辅助材料" if has_speech else ""}
{"- `speech_script.md` - 完整的演讲稿，包含每页幻灯片的演讲内容和时间估算" if has_speech else ""}
{"- `speech_coaching.md` - 演讲技巧指导，帮助您更好地完成演讲" if has_coaching else ""}

## 键盘快捷键 (HTML 版本)

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
{pptx_note}{speech_note}├── slides/              # 幻灯片文件目录
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
    
    def export(
        self,
        output_path: Optional[Path] = None,
        include_html: bool = True,
        include_pptx: bool = True,
        include_screenshots: bool = True,
        include_plan: bool = True,
        include_speech: bool = True,
        return_bytes: bool = False
    ) -> Union[Path, bytes]:
        """Export all assets as a ZIP file (sync wrapper).
        
        This is a synchronous wrapper around export_async.
        """
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        return loop.run_until_complete(
            self.export_async(
                output_path=output_path,
                include_html=include_html,
                include_pptx=include_pptx,
                include_screenshots=include_screenshots,
                include_plan=include_plan,
                include_speech=include_speech,
                return_bytes=return_bytes
            )
        )
    
    async def export_async(
        self,
        output_path: Optional[Path] = None,
        include_html: bool = True,
        include_pptx: bool = True,
        include_screenshots: bool = True,
        include_plan: bool = True,
        include_speech: bool = True,
        return_bytes: bool = False
    ) -> Union[Path, bytes]:
        """Export all assets as a ZIP file.
        
        Args:
            output_path: Output ZIP file path
            include_html: Include HTML slides and combined presentation
            include_pptx: Include PPTX file (requires Playwright)
            include_screenshots: Include screenshots
            include_plan: Include presentation plan
            include_speech: Include speech script and coaching
            return_bytes: If True, return ZIP as bytes instead of saving to file
            
        Returns:
            Path to exported ZIP file, or bytes if return_bytes=True
        """
        from export.html_exporter import HTMLExporter
        import tempfile
        
        # Read manifest for title
        manifest = self._get_manifest()
        title = "Presentation"
        if manifest:
            title = manifest.get("title", "Presentation")
        
        # Create a temporary directory for building the package
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            
            # Generate presentation.html with correct paths for ZIP structure
            html_path = None
            if include_html:
                try:
                    html_exporter = HTMLExporter(self.workspace_path)
                    html_path = tmp_path / "presentation.html"
                    html_exporter.export_combined(
                        output_path=html_path,
                        title=title,
                        slides_path_prefix="slides/"
                    )
                except Exception as e:
                    logger.warning(f"Failed to generate HTML: {e}")
            
            # Generate PPTX if requested (uses Playwright for screenshots)
            pptx_path = None
            if include_pptx:
                try:
                    logger.info("Generating PPTX with screenshots...")
                    generated_pptx = await self._generate_pptx()
                    if generated_pptx and generated_pptx.exists():
                        # Copy to temp directory
                        pptx_path = tmp_path / "presentation.pptx"
                        import shutil
                        shutil.copy2(generated_pptx, pptx_path)
                        logger.info(f"PPTX generated: {pptx_path}")
                except Exception as e:
                    logger.warning(f"Failed to generate PPTX: {e}")
                    import traceback
                    traceback.print_exc()
            
            # Get screenshot paths for inclusion
            screenshot_paths = self._get_screenshot_paths() if include_screenshots else []
            
            # Generate speech materials if requested
            speech_script = None
            speech_coaching = None
            if include_speech:
                try:
                    logger.info("Generating speech materials...")
                    speech_script, speech_coaching = self._generate_speech_materials()
                except Exception as e:
                    logger.warning(f"Failed to generate speech materials: {e}")
            
            # Generate README content
            readme_content = self._generate_readme(
                title=title,
                has_pptx=pptx_path is not None and pptx_path.exists() if pptx_path else False,
                has_speech=speech_script is not None,
                has_coaching=speech_coaching is not None
            )
            
            # Create ZIP
            if return_bytes:
                # Create ZIP in memory
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
                    self._write_zip_contents(
                        zf,
                        html_path=html_path,
                        pptx_path=pptx_path,
                        speech_script=speech_script,
                        speech_coaching=speech_coaching,
                        readme_content=readme_content,
                        include_screenshots=include_screenshots,
                        screenshot_paths=screenshot_paths,
                        include_plan=include_plan
                    )
                
                zip_buffer.seek(0)
                logger.info("Created ZIP package in memory")
                return zip_buffer.getvalue()
            else:
                # Create ZIP to file
                if output_path is None:
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    output_path = self.workspace_path / f"presentation_{timestamp}.zip"
                
                output_path = Path(output_path)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                
                with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                    self._write_zip_contents(
                        zf,
                        html_path=html_path,
                        pptx_path=pptx_path,
                        speech_script=speech_script,
                        speech_coaching=speech_coaching,
                        readme_content=readme_content,
                        include_screenshots=include_screenshots,
                        screenshot_paths=screenshot_paths,
                        include_plan=include_plan
                    )
                
                logger.info(f"Created ZIP package: {output_path}")
                return output_path
    
    def _write_zip_contents(
        self,
        zf: zipfile.ZipFile,
        html_path: Optional[Path],
        pptx_path: Optional[Path],
        speech_script: Optional[str],
        speech_coaching: Optional[str],
        readme_content: str,
        include_screenshots: bool,
        screenshot_paths: List[Path],
        include_plan: bool
    ) -> None:
        """Write all contents to the ZIP file."""
        # Add presentation.html
        if html_path and html_path.exists():
            zf.write(html_path, 'presentation.html')
        
        # Add presentation.pptx if generated
        if pptx_path and pptx_path.exists():
            zf.write(pptx_path, 'presentation.pptx')
        
        # Add speech materials if generated
        if speech_script:
            zf.writestr('speech_script.md', speech_script)
        if speech_coaching:
            zf.writestr('speech_coaching.md', speech_coaching)
        
        # Add README.md
        zf.writestr('README.md', readme_content)
        
        # Add all files from slides directory
        if self.slides_path.exists():
            for file_path in self.slides_path.iterdir():
                if file_path.is_file():
                    arcname = f'slides/{file_path.name}'
                    zf.write(file_path, arcname)
        
        # Add screenshots if requested
        if include_screenshots and screenshot_paths:
            for screenshot_path in screenshot_paths:
                if screenshot_path.exists():
                    arcname = f'screenshots/{screenshot_path.name}'
                    zf.write(screenshot_path, arcname)
        
        # Add presentation plan if requested
        if include_plan:
            plan_path = self.slides_path / "presentation_plan.json"
            if plan_path.exists():
                zf.write(plan_path, "presentation_plan.json")
    
    def get_export_size_estimate(self) -> int:
        """Estimate total export size in bytes."""
        total = 0
        
        paths_to_check = [
            ("slides", "*.html"),
            ("slides", "*.json"),
            ("screenshots", "*.png"),
            (".", "*.pptx"),
            (".", "*.html"),
        ]
        
        for subdir, pattern in paths_to_check:
            path = self.workspace_path / subdir
            if path.exists():
                for f in path.glob(pattern):
                    total += f.stat().st_size
        
        return total
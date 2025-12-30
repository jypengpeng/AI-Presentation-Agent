"""PPTX export functionality.

This module provides:
- PPTXExporter: Convert HTML slides to PowerPoint format
"""

import asyncio
import re
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional


class PPTXExporter:
    """Exports slides as a PowerPoint presentation.
    
    Features:
    - Converts HTML slides to PPTX
    - Takes screenshots of HTML for slide images
    - Adds speaker notes
    """
    
    def __init__(self, workspace_path: Path):
        """Initialize exporter.
        
        Args:
            workspace_path: Path to task workspace
        """
        self.workspace_path = Path(workspace_path)
        self.slides_path = self.workspace_path / "slides"
        self.screenshots_path = self.workspace_path / "screenshots"
    
    def get_slide_files(self) -> List[Path]:
        """Get list of slide HTML files in order."""
        if not self.slides_path.exists():
            return []
        
        files = list(self.slides_path.glob("slide_*.html"))
        
        def get_slide_num(path: Path) -> int:
            match = re.search(r'slide_(\d+)\.html', path.name)
            return int(match.group(1)) if match else 0
        
        return sorted(files, key=get_slide_num)
    
    async def take_screenshots(self) -> List[Path]:
        """Take screenshots of all slides using Playwright.
        
        Returns:
            List of screenshot paths
        """
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            raise ImportError(
                "Playwright not installed. Run: pip install playwright && playwright install"
            )
        
        slides = self.get_slide_files()
        if not slides:
            return []
        
        self.screenshots_path.mkdir(parents=True, exist_ok=True)
        screenshot_paths = []
        
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page(
                viewport={"width": 1920, "height": 1080}
            )
            
            for slide_path in slides:
                screenshot_path = self.screenshots_path / f"{slide_path.stem}.png"
                
                file_url = f"file://{slide_path.resolve()}"
                await page.goto(file_url, wait_until="networkidle")
                await page.screenshot(path=str(screenshot_path))
                
                screenshot_paths.append(screenshot_path)
            
            await browser.close()
        
        return screenshot_paths
    
    async def export(
        self,
        output_path: Optional[Path] = None,
        title: str = "Presentation",
        take_screenshots: bool = True
    ) -> Path:
        """Export slides as PPTX.
        
        Args:
            output_path: Output file path
            title: Presentation title
            take_screenshots: Whether to take screenshots for slides
            
        Returns:
            Path to exported PPTX file
        """
        try:
            from pptx import Presentation
            from pptx.util import Inches, Pt
        except ImportError:
            raise ImportError(
                "python-pptx not installed. Run: pip install python-pptx"
            )
        
        if output_path is None:
            output_path = self.workspace_path / "presentation.pptx"
        
        slides = self.get_slide_files()
        if not slides:
            raise ValueError("No slides found to export")
        
        # Take screenshots if needed
        if take_screenshots:
            screenshot_paths = await self.take_screenshots()
        else:
            screenshot_paths = list(self.screenshots_path.glob("slide_*.png"))
            screenshot_paths.sort(key=lambda p: int(re.search(r'slide_(\d+)', p.stem).group(1)))
        
        # Create presentation
        prs = Presentation()
        prs.slide_width = Inches(13.333)  # 16:9 widescreen
        prs.slide_height = Inches(7.5)
        
        # Get blank layout
        blank_layout = prs.slide_layouts[6]  # Blank layout
        
        for i, slide_path in enumerate(slides):
            slide = prs.slides.add_slide(blank_layout)
            
            # Add screenshot as background if available
            if i < len(screenshot_paths) and screenshot_paths[i].exists():
                slide.shapes.add_picture(
                    str(screenshot_paths[i]),
                    Inches(0), Inches(0),
                    width=Inches(13.333), height=Inches(7.5)
                )
            
            # Add speaker notes if available
            notes = self._extract_notes(slide_path)
            if notes:
                notes_slide = slide.notes_slide
                notes_slide.notes_text_frame.text = notes
        
        # Save presentation
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        prs.save(str(output_path))
        
        return output_path
    
    def _extract_notes(self, slide_path: Path) -> str:
        """Extract speaker notes from slide HTML.
        
        Looks for notes in data attributes or comments.
        """
        content = slide_path.read_text(encoding="utf-8")
        
        # Try to find notes in data attribute
        match = re.search(r'data-notes="([^"]*)"', content)
        if match:
            return match.group(1)
        
        # Try to find notes in HTML comment
        match = re.search(r'<!--\s*notes:\s*(.*?)\s*-->', content, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()
        
        return ""
    
    def export_sync(
        self,
        output_path: Optional[Path] = None,
        title: str = "Presentation"
    ) -> Path:
        """Synchronous wrapper for export."""
        return asyncio.run(self.export(output_path, title))
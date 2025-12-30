"""ZIP package export functionality.

This module provides:
- ZipExporter: Package all presentation assets into a ZIP file
"""

import json
import zipfile
from datetime import datetime
from pathlib import Path
from typing import List, Optional


class ZipExporter:
    """Packages presentation assets into a ZIP file.
    
    Includes:
    - HTML slides
    - Combined presentation
    - PPTX file
    - Screenshots
    - Speech scripts and audio
    - Presentation plan
    """
    
    def __init__(self, workspace_path: Path):
        """Initialize exporter.
        
        Args:
            workspace_path: Path to task workspace
        """
        self.workspace_path = Path(workspace_path)
    
    def export(
        self,
        output_path: Optional[Path] = None,
        include_html: bool = True,
        include_pptx: bool = True,
        include_screenshots: bool = True,
        include_plan: bool = True
    ) -> Path:
        """Export all assets as a ZIP file.
        
        Args:
            output_path: Output ZIP file path
            include_html: Include HTML slides
            include_pptx: Include PPTX file
            include_screenshots: Include screenshots
            include_plan: Include presentation plan
            
        Returns:
            Path to exported ZIP file
        """
        if output_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = self.workspace_path / f"presentation_{timestamp}.zip"
        
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            # Add manifest
            manifest = self._create_manifest()
            zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
            
            if include_html:
                self._add_html_files(zf)
            
            if include_pptx:
                self._add_pptx_file(zf)
            
            if include_screenshots:
                self._add_screenshots(zf)
            
            if include_plan:
                self._add_plan_file(zf)
        
        return output_path
    
    def _create_manifest(self) -> dict:
        """Create export manifest."""
        return {
            "exported_at": datetime.now().isoformat(),
            "workspace": str(self.workspace_path),
            "contents": {
                "html_slides": self._list_files("slides", "*.html"),
                "pptx": self._list_files(".", "*.pptx"),
                "screenshots": self._list_files("screenshots", "*.png"),
            }
        }
    
    def _list_files(self, subdir: str, pattern: str) -> List[str]:
        """List files in a subdirectory matching pattern."""
        path = self.workspace_path / subdir
        if not path.exists():
            return []
        return [f.name for f in path.glob(pattern)]
    
    def _add_html_files(self, zf: zipfile.ZipFile) -> None:
        """Add HTML slides to ZIP."""
        slides_path = self.workspace_path / "slides"
        if not slides_path.exists():
            return
        
        for html_file in slides_path.glob("*.html"):
            arcname = f"slides/{html_file.name}"
            zf.write(html_file, arcname)
        
        # Add combined presentation if exists
        combined = self.workspace_path / "presentation.html"
        if combined.exists():
            zf.write(combined, "presentation.html")
    
    def _add_pptx_file(self, zf: zipfile.ZipFile) -> None:
        """Add PPTX file to ZIP."""
        pptx_files = list(self.workspace_path.glob("*.pptx"))
        for pptx_file in pptx_files:
            zf.write(pptx_file, pptx_file.name)
    
    def _add_screenshots(self, zf: zipfile.ZipFile) -> None:
        """Add screenshots to ZIP."""
        screenshots_path = self.workspace_path / "screenshots"
        if not screenshots_path.exists():
            return
        
        for img_file in screenshots_path.glob("*.png"):
            arcname = f"screenshots/{img_file.name}"
            zf.write(img_file, arcname)
    
    def _add_plan_file(self, zf: zipfile.ZipFile) -> None:
        """Add presentation plan to ZIP."""
        plan_path = self.workspace_path / "slides" / "presentation_plan.json"
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
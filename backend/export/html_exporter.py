"""HTML export functionality.

This module provides:
- HTMLExporter: Combine slides into single HTML presentation using iframe loader
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional


# Exported Single File Template (iframe-based loader)
# This approach preserves all CSS, JS, and content from individual slides
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


class HTMLExporter:
    """Exports slides as a combined HTML presentation.
    
    Features:
    - Creates iframe-based presentation loader
    - Preserves all CSS, JS, and content from individual slides
    - Adds navigation controls with keyboard support
    - Supports fullscreen mode
    """
    
    def __init__(self, workspace_path: Path):
        """Initialize exporter.
        
        Args:
            workspace_path: Path to task workspace
        """
        self.workspace_path = Path(workspace_path)
        self.slides_path = self.workspace_path / "slides"
    
    def get_slide_files(self) -> List[Path]:
        """Get list of slide HTML files in order."""
        if not self.slides_path.exists():
            return []
        
        files = list(self.slides_path.glob("slide_*.html"))
        
        # Sort by slide number
        def get_slide_num(path: Path) -> int:
            match = re.search(r'slide_(\d+)\.html', path.name)
            return int(match.group(1)) if match else 0
        
        return sorted(files, key=get_slide_num)
    
    def get_manifest(self) -> Optional[Dict[str, Any]]:
        """Read and return the manifest.json file."""
        manifest_path = self.slides_path / "manifest.json"
        if not manifest_path.exists():
            return None
        try:
            return json.loads(manifest_path.read_text(encoding='utf-8'))
        except Exception:
            return None
    
    def export_combined(
        self,
        output_path: Optional[Path] = None,
        title: str = "Presentation",
        slides_path_prefix: str = "slides/"
    ) -> Path:
        """Export all slides as a combined HTML file using iframe loader.
        
        This approach preserves all CSS, JS, and content from individual slides,
        avoiding the issues with content extraction and merging.
        
        Args:
            output_path: Output file path (default: workspace/presentation.html)
            title: Presentation title
            slides_path_prefix: Prefix for slide file paths (default: "slides/")
            
        Returns:
            Path to exported file
        """
        if output_path is None:
            output_path = self.workspace_path / "presentation.html"
        
        # Read manifest
        manifest = self.get_manifest()
        if not manifest:
            # Fallback to file-based detection
            slides = self.get_slide_files()
            if not slides:
                raise ValueError("No slides found to export")
            slides_meta = [
                {"id": f"slide_{i+1}", "title": f"Slide {i+1}", "file": slide.name}
                for i, slide in enumerate(slides)
            ]
            title = "Presentation"
        else:
            slides_meta = manifest.get("slides", [])
            if not slides_meta:
                raise ValueError("No slides found in manifest")
            title = manifest.get("title", title)
        
        # Build slides array for JavaScript
        slides_json = json.dumps([
            {
                "id": slide.get("id", f"slide_{i+1}"),
                "title": slide.get("title", f"Slide {i+1}"),
                "file": f"{slides_path_prefix}{slide.get('file', f'slide_{i+1}.html')}"
            }
            for i, slide in enumerate(slides_meta)
        ], ensure_ascii=False)
        
        # Generate exported HTML
        exported_html = EXPORTED_HTML_TEMPLATE.format(
            title=title,
            slides_json=slides_json,
            total_slides=len(slides_meta)
        )
        
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(exported_html, encoding="utf-8")
        
        return output_path
    
    def export_index(
        self,
        output_path: Optional[Path] = None,
        title: str = "Presentation"
    ) -> Path:
        """Export an index page linking to all slides.
        
        Args:
            output_path: Output file path (default: workspace/slides/index.html)
            title: Presentation title
            
        Returns:
            Path to exported file
        """
        if output_path is None:
            output_path = self.slides_path / "index.html"
        
        # Try to get slides from manifest first
        manifest = self.get_manifest()
        if manifest:
            slides_meta = manifest.get("slides", [])
            title = manifest.get("title", title)
        else:
            # Fallback to file detection
            slides = self.get_slide_files()
            if not slides:
                raise ValueError("No slides found to export")
            slides_meta = [
                {"id": f"slide_{i+1}", "title": f"Slide {i+1}", "file": slide.name}
                for i, slide in enumerate(slides)
            ]
        
        if not slides_meta:
            raise ValueError("No slides found to export")
        
        # Generate index HTML
        slide_links = []
        for i, slide in enumerate(slides_meta, 1):
            slide_title = slide.get("title", f"Slide {i}")
            slide_file = slide.get("file", f"slide_{i}.html")
            slide_links.append(f"""
                <a href="{slide_file}" class="slide-link">
                    <span class="slide-number">{i}</span>
                    <span class="slide-name">{slide_title}</span>
                </a>
            """)
        
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} - Index</title>
    <style>
        body {{
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
        }}
        h1 {{
            color: #333;
            border-bottom: 2px solid #007bff;
            padding-bottom: 10px;
        }}
        .slides-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
            gap: 15px;
            margin-top: 20px;
        }}
        .slide-link {{
            display: flex;
            align-items: center;
            padding: 15px;
            background: white;
            border-radius: 8px;
            text-decoration: none;
            color: #333;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            transition: transform 0.2s, box-shadow 0.2s;
        }}
        .slide-link:hover {{
            transform: translateY(-2px);
            box-shadow: 0 4px 8px rgba(0,0,0,0.15);
        }}
        .slide-number {{
            width: 40px;
            height: 40px;
            background: #007bff;
            color: white;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: bold;
            margin-right: 12px;
        }}
        .slide-name {{
            flex: 1;
        }}
        .open-presentation {{
            display: inline-block;
            margin-top: 20px;
            padding: 12px 24px;
            background: #007bff;
            color: white;
            text-decoration: none;
            border-radius: 8px;
            font-weight: 600;
        }}
        .open-presentation:hover {{
            background: #0056b3;
        }}
    </style>
</head>
<body>
    <h1>{title}</h1>
    <p>Total slides: {len(slides_meta)}</p>
    <a href="../presentation.html" class="open-presentation">▶ Open Presentation</a>
    <div class="slides-grid">
        {"".join(slide_links)}
    </div>
</body>
</html>"""
        
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(html, encoding="utf-8")
        
        return output_path
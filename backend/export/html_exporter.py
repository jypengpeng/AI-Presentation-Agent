"""HTML export functionality.

This module provides:
- HTMLExporter: Combine slides into single HTML presentation
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional


class HTMLExporter:
    """Exports slides as a combined HTML presentation.
    
    Features:
    - Combines multiple slide HTML files
    - Adds navigation controls
    - Supports keyboard navigation
    - Generates index page
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
    
    def export_combined(
        self,
        output_path: Optional[Path] = None,
        title: str = "Presentation"
    ) -> Path:
        """Export all slides as a combined HTML file.
        
        Args:
            output_path: Output file path (default: workspace/presentation.html)
            title: Presentation title
            
        Returns:
            Path to exported file
        """
        if output_path is None:
            output_path = self.workspace_path / "presentation.html"
        
        slides = self.get_slide_files()
        
        if not slides:
            raise ValueError("No slides found to export")
        
        # Read all slide contents
        slide_contents = []
        for slide_path in slides:
            content = slide_path.read_text(encoding="utf-8")
            # Extract body content
            body_content = self._extract_body(content)
            slide_contents.append(body_content)
        
        # Generate combined HTML
        html = self._generate_combined_html(slide_contents, title)
        
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(html, encoding="utf-8")
        
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
        
        slides = self.get_slide_files()
        
        if not slides:
            raise ValueError("No slides found to export")
        
        # Generate index HTML
        slide_links = []
        for i, slide_path in enumerate(slides, 1):
            slide_links.append(f"""
                <a href="{slide_path.name}" class="slide-link">
                    <span class="slide-number">{i}</span>
                    <span class="slide-name">{slide_path.stem}</span>
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
            font-family: Arial, sans-serif;
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
    </style>
</head>
<body>
    <h1>{title}</h1>
    <p>Total slides: {len(slides)}</p>
    <div class="slides-grid">
        {"".join(slide_links)}
    </div>
</body>
</html>"""
        
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(html, encoding="utf-8")
        
        return output_path
    
    def _extract_body(self, html: str) -> str:
        """Extract body content from HTML."""
        # Try to find body content
        match = re.search(r'<body[^>]*>(.*?)</body>', html, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return html
    
    def _extract_styles(self, html: str) -> str:
        """Extract style tags from HTML."""
        styles = []
        for match in re.finditer(r'<style[^>]*>(.*?)</style>', html, re.DOTALL | re.IGNORECASE):
            styles.append(match.group(1))
        return "\n".join(styles)
    
    def _generate_combined_html(
        self,
        slide_contents: List[str],
        title: str
    ) -> str:
        """Generate combined presentation HTML."""
        slides_html = []
        for i, content in enumerate(slide_contents):
            slides_html.append(f"""
                <div class="slide" id="slide-{i+1}" data-slide="{i+1}">
                    {content}
                </div>
            """)
        
        return f"""<!DOCTYPE html>
<html lang="en">
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
        
        body {{
            background: #1a1a1a;
            overflow: hidden;
            font-family: Arial, sans-serif;
        }}
        
        .slide-container {{
            width: 100vw;
            height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
        }}
        
        .slide {{
            width: 1920px;
            height: 1080px;
            background: white;
            display: none;
            transform-origin: center;
        }}
        
        .slide.active {{
            display: block;
        }}
        
        .controls {{
            position: fixed;
            bottom: 20px;
            left: 50%;
            transform: translateX(-50%);
            display: flex;
            gap: 10px;
            z-index: 1000;
        }}
        
        .controls button {{
            padding: 10px 20px;
            font-size: 16px;
            cursor: pointer;
            border: none;
            border-radius: 5px;
            background: #007bff;
            color: white;
            transition: background 0.2s;
        }}
        
        .controls button:hover {{
            background: #0056b3;
        }}
        
        .controls button:disabled {{
            background: #ccc;
            cursor: not-allowed;
        }}
        
        .slide-counter {{
            position: fixed;
            bottom: 20px;
            right: 20px;
            color: white;
            font-size: 14px;
            z-index: 1000;
        }}
        
        /* Responsive scaling */
        @media (max-width: 1920px) {{
            .slide {{
                transform: scale(calc(100vw / 1920));
            }}
        }}
        
        @media (max-height: 1080px) {{
            .slide {{
                transform: scale(min(calc(100vw / 1920), calc(100vh / 1080)));
            }}
        }}
    </style>
</head>
<body>
    <div class="slide-container">
        {"".join(slides_html)}
    </div>
    
    <div class="controls">
        <button id="prev-btn" onclick="prevSlide()">← Previous</button>
        <button id="next-btn" onclick="nextSlide()">Next →</button>
    </div>
    
    <div class="slide-counter">
        <span id="current-slide">1</span> / <span id="total-slides">{len(slide_contents)}</span>
    </div>
    
    <script>
        let currentSlide = 1;
        const totalSlides = {len(slide_contents)};
        
        function showSlide(n) {{
            const slides = document.querySelectorAll('.slide');
            
            if (n < 1) n = 1;
            if (n > totalSlides) n = totalSlides;
            
            currentSlide = n;
            
            slides.forEach(slide => slide.classList.remove('active'));
            slides[n - 1].classList.add('active');
            
            document.getElementById('current-slide').textContent = n;
            document.getElementById('prev-btn').disabled = n === 1;
            document.getElementById('next-btn').disabled = n === totalSlides;
        }}
        
        function nextSlide() {{
            showSlide(currentSlide + 1);
        }}
        
        function prevSlide() {{
            showSlide(currentSlide - 1);
        }}
        
        // Keyboard navigation
        document.addEventListener('keydown', (e) => {{
            if (e.key === 'ArrowRight' || e.key === ' ') {{
                nextSlide();
            }} else if (e.key === 'ArrowLeft') {{
                prevSlide();
            }} else if (e.key === 'Home') {{
                showSlide(1);
            }} else if (e.key === 'End') {{
                showSlide(totalSlides);
            }}
        }});
        
        // Initialize
        showSlide(1);
    </script>
</body>
</html>"""
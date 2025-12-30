"""Image generation tools.

This module provides tools for image generation:
- GenerateImageTool: Generate images using AI models
"""

import base64
import httpx
from pathlib import Path
from typing import Any, Dict, Optional

from tools.base import BaseTool, ToolResult, register_tool


@register_tool
class GenerateImageTool(BaseTool):
    """Tool for generating images using AI."""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        api_base: str = "https://api.openai.com/v1",
        model: str = "dall-e-3",
        workspace_root: Optional[Path] = None
    ):
        self.api_key = api_key
        self.api_base = api_base.rstrip("/")
        self.model = model
        self.workspace_root = workspace_root or Path.cwd()
    
    @property
    def name(self) -> str:
        return "generate_image"
    
    @property
    def description(self) -> str:
        return "Generate an image based on a text prompt and save it to a file."
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Text description of the image to generate"
                },
                "output_path": {
                    "type": "string",
                    "description": "Path to save the generated image"
                },
                "size": {
                    "type": "string",
                    "description": "Image size (1024x1024, 1024x1792, 1792x1024)",
                    "default": "1024x1024"
                },
                "quality": {
                    "type": "string",
                    "description": "Image quality (standard or hd)",
                    "default": "standard"
                },
                "style": {
                    "type": "string",
                    "description": "Image style (vivid or natural)",
                    "default": "vivid"
                }
            },
            "required": ["prompt", "output_path"]
        }
    
    async def execute(
        self,
        prompt: str,
        output_path: str,
        size: str = "1024x1024",
        quality: str = "standard",
        style: str = "vivid",
        **kwargs
    ) -> ToolResult:
        """Generate an image and save it."""
        try:
            if not self.api_key:
                return ToolResult.failure("Image API key not configured")
            
            # Validate size
            valid_sizes = ["1024x1024", "1024x1792", "1792x1024"]
            if size not in valid_sizes:
                return ToolResult.failure(
                    f"Invalid size. Must be one of: {valid_sizes}"
                )
            
            # Resolve output path
            save_path = self._resolve_path(output_path)
            save_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Generate image via API
            async with httpx.AsyncClient(timeout=120) as client:
                response = await client.post(
                    f"{self.api_base}/images/generations",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "n": 1,
                        "size": size,
                        "quality": quality,
                        "style": style,
                        "response_format": "b64_json"
                    }
                )
                
                if response.status_code != 200:
                    error_detail = response.text
                    return ToolResult.failure(
                        f"Image generation failed: {response.status_code} - {error_detail}"
                    )
                
                data = response.json()
                
                if "data" not in data or len(data["data"]) == 0:
                    return ToolResult.failure("No image data in response")
                
                # Decode and save image
                image_b64 = data["data"][0]["b64_json"]
                image_bytes = base64.b64decode(image_b64)
                
                save_path.write_bytes(image_bytes)
                
                # Get revised prompt if available
                revised_prompt = data["data"][0].get("revised_prompt", prompt)
                
                return ToolResult.success(
                    f"Image saved to {output_path}",
                    path=str(save_path),
                    size=size,
                    prompt=prompt,
                    revised_prompt=revised_prompt
                )
                
        except httpx.TimeoutException:
            return ToolResult.failure("Image generation timed out")
        except Exception as e:
            return ToolResult.failure(f"Error generating image: {e}")
    
    def _resolve_path(self, path: str) -> Path:
        """Resolve path relative to workspace root."""
        path_obj = Path(path)
        if path_obj.is_absolute():
            return path_obj
        return self.workspace_root / path


@register_tool
class TakeScreenshotTool(BaseTool):
    """Tool for taking screenshots of HTML files using Playwright."""
    
    def __init__(self, workspace_root: Optional[Path] = None):
        self.workspace_root = workspace_root or Path.cwd()
    
    @property
    def name(self) -> str:
        return "take_screenshot"
    
    @property
    def description(self) -> str:
        return "Take a screenshot of an HTML file and save it as PNG."
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "html_path": {
                    "type": "string",
                    "description": "Path to the HTML file to screenshot"
                },
                "output_path": {
                    "type": "string",
                    "description": "Path to save the screenshot PNG"
                },
                "width": {
                    "type": "integer",
                    "description": "Viewport width in pixels",
                    "default": 1920
                },
                "height": {
                    "type": "integer",
                    "description": "Viewport height in pixels",
                    "default": 1080
                }
            },
            "required": ["html_path", "output_path"]
        }
    
    async def execute(
        self,
        html_path: str,
        output_path: str,
        width: int = 1920,
        height: int = 1080,
        **kwargs
    ) -> ToolResult:
        """Take a screenshot of an HTML file."""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return ToolResult.failure(
                "Playwright not installed. Run: pip install playwright && playwright install"
            )
        
        try:
            html_file = self._resolve_path(html_path)
            save_path = self._resolve_path(output_path)
            
            if not html_file.exists():
                return ToolResult.failure(f"HTML file not found: {html_path}")
            
            save_path.parent.mkdir(parents=True, exist_ok=True)
            
            async with async_playwright() as p:
                browser = await p.chromium.launch()
                page = await browser.new_page(
                    viewport={"width": width, "height": height}
                )
                
                # Load HTML file
                file_url = f"file://{html_file.resolve()}"
                await page.goto(file_url, wait_until="networkidle")
                
                # Take screenshot
                await page.screenshot(path=str(save_path), full_page=False)
                
                await browser.close()
            
            return ToolResult.success(
                f"Screenshot saved to {output_path}",
                path=str(save_path),
                width=width,
                height=height
            )
            
        except Exception as e:
            return ToolResult.failure(f"Error taking screenshot: {e}")
    
    def _resolve_path(self, path: str) -> Path:
        """Resolve path relative to workspace root."""
        path_obj = Path(path)
        if path_obj.is_absolute():
            return path_obj
        return self.workspace_root / path
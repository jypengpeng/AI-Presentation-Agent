"""Speech script and coaching generation.

This module provides:
- SpeechGenerator: Generate speech scripts and coaching advice from slides
"""

import json
import re
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from config import Settings

logger = logging.getLogger(__name__)


class SpeechGenerator:
    """Generates speech scripts and coaching advice for presentations.
    
    Features:
    - Generate speech scripts based on slide content
    - Generate coaching advice for presentation delivery
    - Uses OpenAI API for generation
    - Reads configuration from .env via Settings
    """
    
    def __init__(
        self,
        settings: Optional["Settings"] = None
    ):
        """Initialize speech generator.
        
        Args:
            settings: Application settings (loaded from .env).
                      If None, will be loaded automatically.
        """
        from config import get_settings
        self.settings = settings or get_settings()
    
    def _create_client(self):
        """Create an OpenAI client with extended timeouts."""
        try:
            from openai import OpenAI
            import httpx
            import os
            
            # Read timeout settings from environment variables
            connect_timeout = float(os.environ.get("OPENAI_CONNECT_TIMEOUT", "30"))
            read_timeout = float(os.environ.get("OPENAI_READ_TIMEOUT", "600"))
            
            # Create custom httpx client with extended timeouts
            http_client = httpx.Client(
                timeout=httpx.Timeout(
                    connect=connect_timeout,
                    read=read_timeout,
                    write=30.0,
                    pool=30.0
                )
            )
            
            # Get configuration from settings (loaded from .env)
            api_key = self.settings.openai_api_key
            base_url = self.settings.openai_api_base
            
            if not api_key:
                raise RuntimeError("OPENAI_API_KEY not configured in .env")
            
            client_kwargs = {
                "api_key": api_key,
                "http_client": http_client,
                "timeout": read_timeout
            }
            
            # Only set base_url if it's not the default OpenAI URL
            if base_url and base_url != "https://api.openai.com/v1":
                client_kwargs["base_url"] = base_url
            
            return OpenAI(**client_kwargs)
        except ImportError:
            logger.error("OpenAI library not installed")
            raise RuntimeError("OpenAI library not installed. Run: pip install openai")
    
    def _extract_text_from_html(self, html_content: str) -> str:
        """Extract visible text content from HTML."""
        # Remove script and style elements
        content = re.sub(r'<script[^>]*>.*?</script>', '', html_content, flags=re.DOTALL | re.IGNORECASE)
        content = re.sub(r'<style[^>]*>.*?</style>', '', content, flags=re.DOTALL | re.IGNORECASE)
        
        # Remove HTML comments
        content = re.sub(r'<!--.*?-->', '', content, flags=re.DOTALL)
        
        # Remove HTML tags but keep content
        content = re.sub(r'<[^>]+>', ' ', content)
        
        # Clean up whitespace
        content = re.sub(r'\s+', ' ', content)
        content = content.strip()
        
        return content
    
    def _load_slides_content(self, slides_dir: Path) -> List[Dict[str, Any]]:
        """Load content from all slide HTML files.
        
        Args:
            slides_dir: Directory containing slide HTML files
            
        Returns:
            List of slide content dictionaries
        """
        # Read manifest to get slides
        manifest_path = slides_dir / "manifest.json"
        if not manifest_path.exists():
            logger.warning("Manifest not found, skipping speech generation")
            return []
        
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        slides_meta = manifest.get("slides", [])
        
        slides_content = []
        for i, slide_meta in enumerate(slides_meta):
            slide_file = slide_meta.get("file", f"slide_{i+1}.html")
            slide_path = slides_dir / slide_file
            
            if not slide_path.exists():
                continue
            
            html_content = slide_path.read_text(encoding='utf-8')
            text_content = self._extract_text_from_html(html_content)
            slides_content.append({
                "number": i + 1,
                "title": slide_meta.get("title", f"Slide {i+1}"),
                "html": html_content[:3000],  # Limit HTML for context
                "text": text_content[:2000]   # Limit text
            })
        
        return slides_content
    
    def generate_speech_script(
        self,
        slides_dir: Path
    ) -> Optional[str]:
        """Generate a speech script based on all slide contents.
        
        Args:
            slides_dir: Directory containing slide HTML files
        
        Returns:
            Generated speech script as markdown string, or None if failed
        """
        slides_content = self._load_slides_content(slides_dir)
        
        if not slides_content:
            logger.warning("No slides found, skipping speech generation")
            return None
        
        # Build slides text
        slides_text = []
        for slide in slides_content:
            slides_text.append(f"""
=== 第 {slide['number']} 页幻灯片: {slide['title']} ===
内容概要：
{slide['text']}
""")
        
        all_slides_text = "\n".join(slides_text)
        
        prompt = f"""你是一位专业的演讲稿撰写专家。我将向你提供一份演示文稿的所有幻灯片内容，请你根据这些内容撰写一份完整的演讲稿。

要求：
1. 演讲稿应该流畅自然，适合口头表达
2. 每一页幻灯片都应该有对应的演讲内容
3. 包含适当的过渡语句，让整个演讲连贯
4. 语气应该专业但不失亲和力
5. 在关键数据或观点处添加强调
6. 估计每页幻灯片的演讲时间，并在演讲稿中标注
7. 使用中文撰写

以下是所有幻灯片的内容：

{all_slides_text}

请根据以上内容，撰写完整的演讲稿。格式如下：

# 演讲稿

## 开场白
[开场内容]

## 第1页：[幻灯片标题]
[演讲时间：约X分钟]
[演讲内容]

## 第2页：[幻灯片标题]
...

## 结语
[结束语]

---
总预计演讲时间：X分钟
"""
        
        try:
            client = self._create_client()
            
            logger.info("Generating speech script...")
            response = client.chat.completions.create(
                model=self.settings.openai_model,
                messages=[
                    {"role": "system", "content": "你是一位专业的演讲稿撰写专家，擅长将PPT内容转化为生动的演讲稿。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=4096
            )
            
            speech_script = response.choices[0].message.content
            if speech_script:
                logger.info("Speech script generated successfully")
                return speech_script
            else:
                logger.warning("Empty speech script returned")
                return None
                
        except Exception as e:
            logger.warning(f"Failed to generate speech script: {e}")
            return None
    
    def generate_speech_coaching(
        self,
        speech_script: str
    ) -> Optional[str]:
        """Generate coaching advice for delivering the speech.
        
        Args:
            speech_script: The generated speech script
        
        Returns:
            Coaching advice as markdown string, or None if failed
        """
        prompt = f"""你是一位经验丰富且耐心的演讲导师，专门帮助演讲者提升演讲技巧。

以下是一份演讲稿：

{speech_script}

请作为演讲导师，提供详细的指导，帮助演讲者更好地完成这次演讲。请包括以下方面：

## 1. 整体演讲策略
- 核心信息是什么？如何确保观众记住它？
- 建议的演讲风格和语调

## 2. 开场技巧
- 如何在前30秒抓住观众注意力
- 开场的肢体语言和眼神交流建议

## 3. 每页幻灯片的演讲技巧
针对每一页幻灯片，提供：
- 重点强调的内容
- 建议的手势或动作
- 如何与观众互动
- 语速和停顿的建议
- 可能需要注意的难点

## 4. 过渡和节奏
- 页面之间如何自然过渡
- 如何控制整体节奏
- 什么时候可以稍作停顿让观众消化信息

## 5. 结尾技巧
- 如何有力地收尾
- 如何处理Q&A环节

## 6. 紧张情绪管理
- 演讲前的准备建议
- 如果忘词或出错如何应对

## 7. 练习建议
- 推荐的练习方法
- 练习时需要注意的要点

请用鼓励和支持的语气来给出建议，让演讲者感到自信。
"""
        
        try:
            client = self._create_client()
            
            logger.info("Generating speech coaching...")
            response = client.chat.completions.create(
                model=self.settings.openai_model,
                messages=[
                    {"role": "system", "content": "你是一位经验丰富且耐心的演讲导师，专门帮助演讲者提升演讲技巧。你总是给予鼓励和建设性的建议。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=4096
            )
            
            coaching = response.choices[0].message.content
            if coaching:
                logger.info("Speech coaching generated successfully")
                return coaching
            else:
                logger.warning("Empty coaching returned")
                return None
                
        except Exception as e:
            logger.warning(f"Failed to generate speech coaching: {e}")
            return None
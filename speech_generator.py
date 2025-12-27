#!/usr/bin/env python3
"""
Speech Generator Script

This script reads all slide_x.html files from a directory,
sends them to a LLM to generate a presentation speech script,
and then sends the speech to the LLM again to get coaching advice.

Usage:
    python speech_generator.py [slides_directory]
    
If no directory is specified, it will look for slides in the current directory.
"""

import os
import re
import sys
import glob
import io
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv
from openai import OpenAI
import httpx

# Load environment variables
load_dotenv()

# Fix Windows console encoding for UTF-8 output
if sys.platform == 'win32':
    # Set stdout to use UTF-8 encoding
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')


def get_openai_client() -> OpenAI:
    """
    Create and return an OpenAI client configured from environment variables.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    base_url = os.environ.get("OPENAI_BASE_URL")
    
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable is required")
    
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
    
    client_kwargs = {
        "api_key": api_key,
        "http_client": http_client,
        "timeout": read_timeout
    }
    
    if base_url:
        client_kwargs["base_url"] = base_url
    
    return OpenAI(**client_kwargs)


def get_model_name() -> str:
    """Get the model name from environment variables."""
    return os.environ.get("OPENAI_MODEL", "gpt-4o")


def find_slide_files(directory: str) -> list[str]:
    """
    Find all slide_x.html files in the specified directory.
    
    Args:
        directory: Path to the directory containing slide files
        
    Returns:
        List of file paths sorted by slide number
    """
    pattern = os.path.join(directory, "slide_*.html")
    files = glob.glob(pattern)
    
    # Sort by slide number
    def extract_number(filepath: str) -> int:
        match = re.search(r'slide_(\d+)\.html', filepath)
        return int(match.group(1)) if match else 0
    
    return sorted(files, key=extract_number)


def read_slide_content(filepath: str) -> tuple[int, str]:
    """
    Read the content of a slide file.
    
    Args:
        filepath: Path to the slide file
        
    Returns:
        Tuple of (slide_number, content)
    """
    match = re.search(r'slide_(\d+)\.html', filepath)
    slide_number = int(match.group(1)) if match else 0
    
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    return slide_number, content


def extract_text_from_html(html_content: str) -> str:
    """
    Extract visible text content from HTML.
    
    This is a simple extraction that removes HTML tags and scripts.
    For more complex HTML, consider using BeautifulSoup.
    
    Args:
        html_content: Raw HTML content
        
    Returns:
        Extracted text content
    """
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


def generate_speech_script(client: OpenAI, model: str, slides_content: list[tuple[int, str, str]]) -> str:
    """
    Generate a presentation speech script based on slide contents.
    
    Args:
        client: OpenAI client
        model: Model name to use
        slides_content: List of (slide_number, html_content, text_content) tuples
        
    Returns:
        Generated speech script
    """
    # Build the prompt with all slides
    slides_text = []
    for slide_num, html_content, text_content in slides_content:
        slides_text.append(f"""
=== 第 {slide_num} 页幻灯片 ===
HTML内容概要：
{text_content[:2000]}  # Limit each slide to 2000 chars to avoid context length issues

完整HTML代码（用于理解布局和设计）：
```html
{html_content[:3000]}  # Include some HTML for context
```
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

    print("正在生成演讲稿...")
    print("-" * 50)
    
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "你是一位专业的演讲稿撰写专家，擅长将PPT内容转化为生动的演讲稿。"},
            {"role": "user", "content": prompt}
        ],
        temperature=0.7,
        max_tokens=4096
    )
    
    speech_script = response.choices[0].message.content
    if speech_script is None:
        raise ValueError("模型未返回有效的演讲稿内容")
    return speech_script


def get_speech_coaching(client: OpenAI, model: str, speech_script: str) -> str:
    """
    Get coaching advice for delivering the speech.
    
    Args:
        client: OpenAI client
        model: Model name to use
        speech_script: The generated speech script
        
    Returns:
        Coaching advice
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

    print("\n正在获取演讲指导...")
    print("-" * 50)
    
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "你是一位经验丰富且耐心的演讲导师，专门帮助演讲者提升演讲技巧。你总是给予鼓励和建设性的建议。"},
            {"role": "user", "content": prompt}
        ],
        temperature=0.7,
        max_tokens=4096
    )
    
    coaching = response.choices[0].message.content
    if coaching is None:
        raise ValueError("模型未返回有效的演讲指导内容")
    return coaching


def save_output(content: str, filepath: str):
    """Save content to a file."""
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"已保存到: {filepath}")


def main():
    """Main function to run the speech generator."""
    # Get slides directory from command line or use current directory
    if len(sys.argv) > 1:
        slides_dir = sys.argv[1]
    else:
        slides_dir = "."
    
    # Check if directory exists
    if not os.path.isdir(slides_dir):
        print(f"错误: 目录不存在: {slides_dir}")
        sys.exit(1)
    
    # Find slide files
    slide_files = find_slide_files(slides_dir)
    
    if not slide_files:
        print(f"错误: 在 {slides_dir} 中没有找到 slide_*.html 文件")
        sys.exit(1)
    
    print(f"找到 {len(slide_files)} 个幻灯片文件:")
    for f in slide_files:
        print(f"  - {os.path.basename(f)}")
    print()
    
    # Read all slide contents
    slides_content = []
    for filepath in slide_files:
        slide_num, html_content = read_slide_content(filepath)
        text_content = extract_text_from_html(html_content)
        slides_content.append((slide_num, html_content, text_content))
        print(f"已读取第 {slide_num} 页幻灯片 ({len(text_content)} 字符)")
    
    print()
    
    # Initialize OpenAI client
    try:
        client = get_openai_client()
        model = get_model_name()
        print(f"使用模型: {model}")
        print()
    except ValueError as e:
        print(f"错误: {e}")
        print("请确保在 .env 文件中设置了 OPENAI_API_KEY")
        sys.exit(1)
    
    # Generate speech script
    speech_script = generate_speech_script(client, model, slides_content)
    
    print("\n" + "=" * 60)
    print("生成的演讲稿：")
    print("=" * 60)
    print(speech_script)
    
    # Save speech script
    output_dir = Path(slides_dir)
    speech_path = output_dir / "speech_script.md"
    save_output(speech_script, str(speech_path))
    
    # Get coaching advice
    coaching = get_speech_coaching(client, model, speech_script)
    
    print("\n" + "=" * 60)
    print("演讲指导：")
    print("=" * 60)
    print(coaching)
    
    # Save coaching advice
    coaching_path = output_dir / "speech_coaching.md"
    save_output(coaching, str(coaching_path))
    
    print("\n" + "=" * 60)
    print("完成！")
    print(f"演讲稿已保存到: {speech_path}")
    print(f"演讲指导已保存到: {coaching_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()
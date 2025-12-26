"""
Image Generation Module

This module provides image generation functionality using AI APIs.
Can be used as a standalone script or integrated as an Agent tool.

Usage as standalone:
    python gen_image.py "your prompt here"
    
Usage as module:
    from gen_image import generate_image
    result = generate_image("a beautiful sunset", save_path="output.png")
"""

import requests
import json
import re
import base64
import time
import sys
import os
from pathlib import Path
from typing import Optional, Dict, Any
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()


def get_config() -> Dict[str, str]:
    """
    Get image generation API configuration from environment variables.
    
    Returns:
        Dict with api_url, api_key, and model_id
    """
    api_base = os.getenv("IMAGE_API_URL", "https://your-api-domain.com/v1")
    return {
        "api_url": api_base.rstrip("/") + "/chat/completions",
        "api_key": os.getenv("IMAGE_API_KEY", ""),
        "model_id": os.getenv("IMAGE_MODEL_ID", "gemini-3-pro-image")
    }


def generate_image(
    prompt: str,
    save_path: Optional[str] = None,
    timeout: int = 120
) -> Dict[str, Any]:
    """
    Generate an image using AI API.
    
    This function is designed to be used as an Agent tool. It returns a structured
    result dict that can be easily processed by the agent framework.
    
    Args:
        prompt: The text prompt describing the image to generate
        save_path: Optional path to save the generated image.
                   If None, image is returned as base64 only.
        timeout: Request timeout in seconds (default: 120)
        
    Returns:
        Dict with the following structure:
        - success: bool - Whether the generation was successful
        - base64: str - The base64-encoded image data (on success)
        - format: str - Image format (e.g., 'png', 'jpg')
        - file_path: str - Path where image was saved (if save_path provided)
        - error: str - Error message (on failure)
        
    Example:
        >>> result = generate_image("a cat wearing a hat")
        >>> if result["success"]:
        ...     print(f"Image format: {result['format']}")
        ...     # Use result["base64"] for the image data
        ... else:
        ...     print(f"Error: {result['error']}")
    """
    # Validate prompt
    if not prompt or not prompt.strip():
        return {
            "success": False,
            "error": "Prompt is required and cannot be empty"
        }
    
    # Get configuration
    config = get_config()
    
    if not config["api_key"]:
        return {
            "success": False,
            "error": "IMAGE_API_KEY is not configured in .env file"
        }
    
    # Prepare request
    headers = {
        "Authorization": f"Bearer {config['api_key']}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": config["model_id"],
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "stream": False,
        "temperature": 0.7
    }
    
    try:
        # Make API request
        response = requests.post(
            config["api_url"],
            headers=headers,
            json=payload,
            timeout=timeout
        )
        
        # Check for HTTP errors
        if response.status_code != 200:
            return {
                "success": False,
                "error": f"API returned status {response.status_code}: {response.text[:500]}"
            }
        
        # Parse JSON response
        try:
            res_json = response.json()
        except json.JSONDecodeError as e:
            return {
                "success": False,
                "error": f"Invalid JSON response: {str(e)}"
            }
        
        # Extract content from response
        try:
            content = res_json['choices'][0]['message']['content']
        except (KeyError, IndexError, TypeError) as e:
            return {
                "success": False,
                "error": f"Unexpected response structure: {str(e)}"
            }
        
        # Extract base64 image data using regex
        pattern = r'!\[.*?\]\s*\((data:image\/(\w+);base64,([a-zA-Z0-9+/=]+))\)'
        match = re.search(pattern, content)
        
        if not match:
            # Try alternative pattern without markdown wrapper
            alt_pattern = r'data:image\/(\w+);base64,([a-zA-Z0-9+/=]+)'
            alt_match = re.search(alt_pattern, content)
            
            if alt_match:
                file_ext = alt_match.group(1)
                base64_str = alt_match.group(2)
            else:
                return {
                    "success": False,
                    "error": f"No image data found in response. Content preview: {content[:300]}..."
                }
        else:
            file_ext = match.group(2)
            base64_str = match.group(3)
        
        # Normalize file extension
        if file_ext == 'jpeg':
            file_ext = 'jpg'
        
        result = {
            "success": True,
            "base64": base64_str,
            "format": file_ext
        }
        
        # Save image if path is provided
        if save_path:
            try:
                # Decode base64
                img_data = base64.b64decode(base64_str)
                
                # Ensure directory exists
                save_path_obj = Path(save_path)
                save_path_obj.parent.mkdir(parents=True, exist_ok=True)
                
                # Write file
                with open(save_path_obj, 'wb') as f:
                    f.write(img_data)
                
                result["file_path"] = str(save_path_obj)
                
            except Exception as e:
                # Image generated successfully but failed to save
                result["save_error"] = f"Failed to save image: {str(e)}"
        
        return result
        
    except requests.Timeout:
        return {
            "success": False,
            "error": f"Request timed out after {timeout} seconds"
        }
    except requests.RequestException as e:
        return {
            "success": False,
            "error": f"Network error: {str(e)}"
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Unexpected error: {str(e)}"
        }


def generate_image_tool(prompt: str, save_path: str, timeout: int = 120) -> Dict[str, Any]:
    """
    Simplified version for Agent tool usage.
    
    This function is designed specifically for agent integration:
    - Always requires a save_path (no base64 in response to save tokens)
    - Returns only essential information
    - Designed to be wrapped by AgentTools with path validation
    
    Args:
        prompt: The text prompt describing the image to generate
        save_path: Path to save the generated image (required)
        timeout: Request timeout in seconds (default: 120)
        
    Returns:
        Dict with the following structure:
        - success: bool - Whether the generation was successful
        - file_path: str - Path where image was saved (on success)
        - format: str - Image format (e.g., 'png', 'jpg') (on success)
        - error: str - Error message (on failure)
        
    Example:
        >>> result = generate_image_tool("a cat wearing a hat", "images/cat.png")
        >>> if result["success"]:
        ...     print(f"Image saved to: {result['file_path']}")
        ... else:
        ...     print(f"Error: {result['error']}")
    """
    if not save_path:
        return {
            "success": False,
            "error": "save_path is required for agent tool usage"
        }
    
    # Call the main generate_image function
    result = generate_image(prompt, save_path=save_path, timeout=timeout)
    
    if result["success"]:
        # Return only essential info (no base64 to save tokens)
        return {
            "success": True,
            "file_path": result.get("file_path", save_path),
            "format": result["format"]
        }
    else:
        return {
            "success": False,
            "error": result["error"]
        }


def run_cli():
    """
    Command-line interface for image generation.
    Maintains backward compatibility with the original script behavior.
    """
    if len(sys.argv) < 2:
        print("Error: No prompt provided. Usage: python gen_image.py 'your prompt here'")
        sys.exit(1)
    
    prompt_text = sys.argv[1]
    
    # Optional: get save path from second argument
    save_path = sys.argv[2] if len(sys.argv) > 2 else None
    
    # If no save path provided, generate a default filename
    if not save_path:
        timestamp = int(time.time())
        save_path = f"output_{timestamp}.png"
    
    print(f"Generating image for prompt: {prompt_text[:50]}...")
    
    result = generate_image(prompt_text, save_path=save_path)
    
    if result["success"]:
        print(f"Success! Image format: {result['format']}")
        if "file_path" in result:
            print(f"Saved to: {result['file_path']}")
        if "save_error" in result:
            print(f"Warning: {result['save_error']}")
        # Print base64 for backward compatibility (can be piped to other tools)
        print(result["base64"])
    else:
        print(f"Error: {result['error']}")
        sys.exit(1)


if __name__ == "__main__":
    run_cli()
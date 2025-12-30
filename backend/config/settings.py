"""Settings and configuration management.

This module handles all environment variables and configuration settings
using pydantic-settings for type safety and validation.
"""

import os
import logging
from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


# Configure logging
logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # OpenAI API Configuration
    openai_api_key: str = Field(default="", description="OpenAI API Key")
    openai_api_base: str = Field(
        default="https://api.openai.com/v1",
        description="OpenAI API Base URL"
    )
    openai_model: str = Field(
        default="gpt-4o",
        description="Default OpenAI model"
    )
    architect_model: str = Field(
        default="gpt-4o",
        description="Model for Architect agent"
    )
    designer_model: str = Field(
        default="gpt-4o",
        description="Model for Designer agent"
    )
    
    # Image Generation
    image_api_key: str = Field(default="", description="Image API Key")
    image_api_base: str = Field(
        default="https://api.openai.com/v1",
        description="Image API Base URL"
    )
    image_model: str = Field(
        default="dall-e-3",
        description="Image generation model"
    )
    
    # Directory Configuration
    workspace_base: Path = Field(
        default=Path("./tasks"),
        description="Base directory for task workspaces"
    )
    prompts_dir: Path = Field(
        default=Path("./prompts"),
        description="Directory containing prompt files"
    )
    
    @field_validator('workspace_base', 'prompts_dir', mode='after')
    @classmethod
    def resolve_to_absolute(cls, v: Path) -> Path:
        """Ensure paths are absolute."""
        resolved = v.resolve()
        logger.info(f"[Settings] Resolved path: {v} -> {resolved}")
        return resolved
    
    # Slide Generation
    max_concurrent_slides: int = Field(
        default=3,
        description="Maximum concurrent slide generation"
    )
    slide_generation_timeout: int = Field(
        default=120,
        description="Timeout for slide generation in seconds"
    )
    
    # Server Configuration
    host: str = Field(default="0.0.0.0", description="Server host")
    port: int = Field(default=8000, description="Server port")
    debug: bool = Field(default=False, description="Debug mode")
    
    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "extra": "ignore",
    }
    
    def get_workspace_path(self, task_id: str) -> Path:
        """Get workspace path for a specific task."""
        return self.workspace_base / f"task_{task_id}" / "workspace"
    
    def get_slides_path(self, task_id: str) -> Path:
        """Get slides directory path for a specific task."""
        return self.get_workspace_path(task_id) / "slides"
    
    def get_prompt_path(self, prompt_name: str) -> Path:
        """Get path to a specific prompt file."""
        return self.prompts_dir / prompt_name


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance (singleton pattern)."""
    return Settings()


def init_directories(settings: Optional[Settings] = None) -> None:
    """Initialize required directories."""
    if settings is None:
        settings = get_settings()
    
    settings.workspace_base.mkdir(parents=True, exist_ok=True)
    settings.prompts_dir.mkdir(parents=True, exist_ok=True)
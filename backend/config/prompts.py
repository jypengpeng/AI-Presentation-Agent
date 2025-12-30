"""Prompt loading and management.

This module handles loading and caching of prompt templates
from files and provides methods for prompt formatting.
"""

import re
from functools import lru_cache
from pathlib import Path
from typing import Optional, Dict, Any

from config.settings import get_settings


class PromptLoader:
    """Handles loading and caching of prompt templates."""
    
    def __init__(self, prompts_dir: Optional[Path] = None):
        """Initialize prompt loader.
        
        Args:
            prompts_dir: Directory containing prompt files.
                        Defaults to settings.prompts_dir.
        """
        if prompts_dir is None:
            prompts_dir = get_settings().prompts_dir
        self.prompts_dir = Path(prompts_dir)
        self._cache: Dict[str, str] = {}
    
    def load(self, prompt_name: str) -> str:
        """Load a prompt template from file.
        
        Args:
            prompt_name: Name of the prompt file (with or without extension)
            
        Returns:
            The prompt content as a string
            
        Raises:
            FileNotFoundError: If the prompt file doesn't exist
        """
        if prompt_name in self._cache:
            return self._cache[prompt_name]
        
        # Try with common extensions
        extensions = ["", ".txt", ".md"]
        prompt_path = None
        
        for ext in extensions:
            candidate = self.prompts_dir / f"{prompt_name}{ext}"
            if candidate.exists():
                prompt_path = candidate
                break
        
        if prompt_path is None:
            raise FileNotFoundError(
                f"Prompt '{prompt_name}' not found in {self.prompts_dir}"
            )
        
        content = prompt_path.read_text(encoding="utf-8")
        self._cache[prompt_name] = content
        return content
    
    def format(
        self,
        prompt_name: str,
        **kwargs: Any
    ) -> str:
        """Load and format a prompt template with variables.
        
        Uses Python's str.format() for simple substitution.
        
        Args:
            prompt_name: Name of the prompt file
            **kwargs: Variables to substitute in the template
            
        Returns:
            Formatted prompt string
        """
        template = self.load(prompt_name)
        
        # Support both {var} and {{var}} formats
        # First replace {{ }} with a placeholder
        template = template.replace("{{", "<<<DOUBLE_OPEN>>>")
        template = template.replace("}}", "<<<DOUBLE_CLOSE>>>")
        
        # Format with kwargs
        try:
            result = template.format(**kwargs)
        except KeyError as e:
            # If a variable is missing, leave it as is
            result = template
            for key, value in kwargs.items():
                result = result.replace(f"{{{key}}}", str(value))
        
        # Restore double braces
        result = result.replace("<<<DOUBLE_OPEN>>>", "{")
        result = result.replace("<<<DOUBLE_CLOSE>>>", "}")
        
        return result
    
    def clear_cache(self) -> None:
        """Clear the prompt cache."""
        self._cache.clear()
    
    def reload(self, prompt_name: str) -> str:
        """Reload a prompt from file, bypassing cache.
        
        Args:
            prompt_name: Name of the prompt file
            
        Returns:
            The prompt content
        """
        if prompt_name in self._cache:
            del self._cache[prompt_name]
        return self.load(prompt_name)


@lru_cache()
def get_prompt_loader() -> PromptLoader:
    """Get cached prompt loader instance."""
    return PromptLoader()


# Convenience functions for common prompts
def get_system_prompt() -> str:
    """Get the default system prompt."""
    return get_prompt_loader().load("system_prompt")


def get_architect_prompt() -> str:
    """Get the Architect agent prompt."""
    return get_prompt_loader().load("Architect_prompt")


def get_designer_prompt() -> str:
    """Get the Designer agent prompt."""
    return get_prompt_loader().load("Designer")


def get_phase_prompt(phase: str) -> str:
    """Get prompt for a specific workflow phase.
    
    Args:
        phase: The workflow phase name
        
    Returns:
        The phase-specific prompt
    """
    phase_prompts = {
        "collecting": "system_prompt",
        "architect": "Architect_prompt",
        "editing_plan": "Architect_prompt",
        "designing": "Designer",
        "completed": "system_prompt",
    }
    
    prompt_name = phase_prompts.get(phase, "system_prompt")
    return get_prompt_loader().load(prompt_name)
"""Tools module for AI Presentation Agent.

This module provides a modular, extensible tool system with:
- Base tool class for consistent interface
- Tool registry for dynamic tool discovery
- Individual tool implementations
"""

from tools.base import BaseTool, ToolRegistry, ToolResult, tool_registry
from tools.file_tools import ReadFileTool, WriteFileTool, ListFilesTool
from tools.command_tools import ExecuteCommandTool
from tools.image_tools import GenerateImageTool
from tools.phase_tools import TransitionPhaseTool, GenerateSlideTool

__all__ = [
    "BaseTool",
    "ToolRegistry",
    "ToolResult",
    "tool_registry",
    "ReadFileTool",
    "WriteFileTool",
    "ListFilesTool",
    "ExecuteCommandTool",
    "GenerateImageTool",
    "TransitionPhaseTool",
    "GenerateSlideTool",
]
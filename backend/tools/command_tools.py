"""Command execution tools.

This module provides tools for executing system commands:
- ExecuteCommandTool: Execute shell commands safely
"""

import asyncio
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from tools.base import BaseTool, ToolResult, register_tool


@register_tool
class ExecuteCommandTool(BaseTool):
    """Tool for executing shell commands."""
    
    def __init__(
        self, 
        workspace_root: Optional[Path] = None,
        timeout: int = 120,
        allowed_commands: Optional[list] = None
    ):
        self.workspace_root = workspace_root or Path.cwd()
        self.timeout = timeout
        self.allowed_commands = allowed_commands  # None means all allowed
    
    @property
    def name(self) -> str:
        return "execute_command"
    
    @property
    def description(self) -> str:
        return "Execute a shell command and return its output. Use with caution."
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The command to execute"
                },
                "cwd": {
                    "type": "string",
                    "description": "Working directory for command execution (default: workspace root)"
                },
                "timeout": {
                    "type": "integer",
                    "description": f"Command timeout in seconds (default: {self.timeout})"
                }
            },
            "required": ["command"]
        }
    
    async def execute(
        self,
        command: str,
        cwd: Optional[str] = None,
        timeout: Optional[int] = None,
        **kwargs
    ) -> ToolResult:
        """Execute a shell command."""
        try:
            # Validate command if whitelist is provided
            if self.allowed_commands is not None:
                cmd_name = command.split()[0] if command else ""
                if cmd_name not in self.allowed_commands:
                    return ToolResult.failure(
                        f"Command '{cmd_name}' is not in the allowed list"
                    )
            
            # Resolve working directory
            work_dir = self._resolve_path(cwd) if cwd else self.workspace_root
            
            if not work_dir.exists():
                return ToolResult.failure(
                    f"Working directory does not exist: {work_dir}"
                )
            
            # Use specified timeout or default
            cmd_timeout = timeout or self.timeout
            
            # Determine shell based on OS
            if sys.platform == "win32":
                shell = True
            else:
                shell = True
            
            # Run command asynchronously
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(work_dir),
                shell=shell
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=cmd_timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                return ToolResult.failure(
                    f"Command timed out after {cmd_timeout} seconds",
                    command=command
                )
            
            # Decode output
            stdout_str = stdout.decode('utf-8', errors='replace')
            stderr_str = stderr.decode('utf-8', errors='replace')
            
            # Combine output
            output_parts = []
            if stdout_str.strip():
                output_parts.append(stdout_str.strip())
            if stderr_str.strip():
                output_parts.append(f"[stderr]\n{stderr_str.strip()}")
            
            output = "\n".join(output_parts) if output_parts else "(no output)"
            
            if process.returncode == 0:
                return ToolResult.success(
                    output,
                    command=command,
                    return_code=process.returncode,
                    cwd=str(work_dir)
                )
            else:
                return ToolResult.failure(
                    f"Command failed with exit code {process.returncode}:\n{output}",
                    command=command,
                    return_code=process.returncode
                )
                
        except Exception as e:
            return ToolResult.failure(f"Error executing command: {e}")
    
    def _resolve_path(self, path: str) -> Path:
        """Resolve path relative to workspace root."""
        path_obj = Path(path)
        if path_obj.is_absolute():
            return path_obj
        return self.workspace_root / path


@register_tool  
class PythonExecuteTool(BaseTool):
    """Tool for executing Python code."""
    
    def __init__(self, workspace_root: Optional[Path] = None):
        self.workspace_root = workspace_root or Path.cwd()
    
    @property
    def name(self) -> str:
        return "python_execute"
    
    @property
    def description(self) -> str:
        return "Execute Python code and return the result."
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "The Python code to execute"
                }
            },
            "required": ["code"]
        }
    
    async def execute(self, code: str, **kwargs) -> ToolResult:
        """Execute Python code."""
        try:
            # Create a restricted globals dict
            restricted_globals = {
                "__builtins__": {
                    "print": print,
                    "len": len,
                    "range": range,
                    "str": str,
                    "int": int,
                    "float": float,
                    "bool": bool,
                    "list": list,
                    "dict": dict,
                    "set": set,
                    "tuple": tuple,
                    "sorted": sorted,
                    "enumerate": enumerate,
                    "zip": zip,
                    "map": map,
                    "filter": filter,
                    "sum": sum,
                    "min": min,
                    "max": max,
                    "abs": abs,
                    "round": round,
                    "isinstance": isinstance,
                    "type": type,
                }
            }
            
            # Capture output
            import io
            from contextlib import redirect_stdout, redirect_stderr
            
            stdout_capture = io.StringIO()
            stderr_capture = io.StringIO()
            
            result = None
            
            with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
                # Try to evaluate as expression first
                try:
                    result = eval(code, restricted_globals)
                except SyntaxError:
                    # If not an expression, execute as statements
                    exec(code, restricted_globals)
            
            stdout_str = stdout_capture.getvalue()
            stderr_str = stderr_capture.getvalue()
            
            output_parts = []
            if result is not None:
                output_parts.append(f"Result: {result}")
            if stdout_str:
                output_parts.append(stdout_str)
            if stderr_str:
                output_parts.append(f"[stderr]\n{stderr_str}")
            
            output = "\n".join(output_parts) if output_parts else "(no output)"
            
            return ToolResult.success(output)
            
        except Exception as e:
            return ToolResult.failure(f"Python execution error: {e}")
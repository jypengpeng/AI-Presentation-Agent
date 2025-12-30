"""File operation tools.

This module provides tools for file system operations:
- ReadFileTool: Read file contents
- WriteFileTool: Write content to files
- ListFilesTool: List directory contents
"""

import os
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from tools.base import BaseTool, ToolResult, register_tool


# Configure logging
logger = logging.getLogger(__name__)


@register_tool
class ReadFileTool(BaseTool):
    """Tool for reading file contents.
    
    Supports both 'path' (string) and 'paths' (array) parameter formats
    to be compatible with original agent_core.py.
    """
    
    def __init__(self, workspace_root: Optional[Path] = None):
        self.workspace_root = workspace_root or Path.cwd()
    
    @property
    def name(self) -> str:
        return "read_file"
    
    @property
    def description(self) -> str:
        return "Read the contents of one or more files. Returns file content with line numbers."
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of file paths to read (relative to workspace)"
                },
                "path": {
                    "type": "string",
                    "description": "Single file path (alternative to 'paths')"
                },
                "encoding": {
                    "type": "string",
                    "description": "File encoding (default: utf-8)",
                    "default": "utf-8"
                }
            },
            "required": []
        }
    
    async def execute(
        self,
        paths: Optional[List[str]] = None,
        path: Optional[str] = None,
        encoding: str = "utf-8",
        **kwargs
    ) -> ToolResult:
        """Read file contents.
        
        Supports both 'paths' array and 'path' string parameters.
        """
        # Support both 'paths' array and 'path' string
        if paths:
            files_to_read = paths
        elif path:
            files_to_read = [path]
        else:
            return ToolResult.failure("Either 'path' or 'paths' parameter is required")
        
        all_results = []
        success_count = 0
        fail_count = 0
        
        for file_path_str in files_to_read:
            try:
                file_path = self._resolve_path(file_path_str)
                
                if not file_path.exists():
                    all_results.append(f"[{file_path_str}] File not found")
                    fail_count += 1
                    continue
                
                if not file_path.is_file():
                    all_results.append(f"[{file_path_str}] Not a file")
                    fail_count += 1
                    continue
                
                # Check if file is within workspace
                if not self._is_within_workspace(file_path):
                    all_results.append(f"[{file_path_str}] Access denied: outside workspace")
                    fail_count += 1
                    continue
                
                content = file_path.read_text(encoding=encoding)
                
                # Add line numbers for reference
                lines = content.split('\n')
                numbered_lines = [
                    f"{i+1:4d} | {line}"
                    for i, line in enumerate(lines)
                ]
                numbered_content = '\n'.join(numbered_lines)
                
                if len(files_to_read) > 1:
                    all_results.append(f"=== {file_path_str} ({len(lines)} lines) ===\n{numbered_content}")
                else:
                    all_results.append(numbered_content)
                
                success_count += 1
                
            except UnicodeDecodeError as e:
                all_results.append(f"[{file_path_str}] Decode error: {e}")
                fail_count += 1
            except Exception as e:
                all_results.append(f"[{file_path_str}] Error: {e}")
                fail_count += 1
        
        output = "\n\n".join(all_results)
        
        return ToolResult.success(
            output,
            success_count=success_count,
            fail_count=fail_count,
            total_count=len(files_to_read)
        )
    
    def _resolve_path(self, path: str) -> Path:
        """Resolve path relative to workspace root."""
        path_obj = Path(path)
        if path_obj.is_absolute():
            return path_obj
        return self.workspace_root / path
    
    def _is_within_workspace(self, path: Path) -> bool:
        """Check if path is within the workspace."""
        try:
            path.resolve().relative_to(self.workspace_root.resolve())
            return True
        except ValueError:
            return False


@register_tool
class WriteFileTool(BaseTool):
    """Tool for writing content to files."""
    
    def __init__(self, workspace_root: Optional[Path] = None):
        self.workspace_root = workspace_root or Path.cwd()
    
    @property
    def name(self) -> str:
        return "write_file"
    
    @property
    def description(self) -> str:
        return "Write content to a file. Creates the file if it doesn't exist, or overwrites if it does."
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The path to the file to write (relative to workspace)"
                },
                "content": {
                    "type": "string",
                    "description": "The content to write to the file"
                },
                "encoding": {
                    "type": "string",
                    "description": "File encoding (default: utf-8)",
                    "default": "utf-8"
                },
                "create_dirs": {
                    "type": "boolean",
                    "description": "Create parent directories if they don't exist",
                    "default": True
                }
            },
            "required": ["path", "content"]
        }
    
    async def execute(
        self, 
        path: str, 
        content: str, 
        encoding: str = "utf-8",
        create_dirs: bool = True,
        **kwargs
    ) -> ToolResult:
        """Write content to file."""
        try:
            file_path = self._resolve_path(path)
            
            # Check if file is within workspace
            if not self._is_within_workspace(file_path):
                return ToolResult.failure(
                    f"Access denied: {path} is outside workspace"
                )
            
            # Create parent directories if needed
            if create_dirs:
                file_path.parent.mkdir(parents=True, exist_ok=True)
            elif not file_path.parent.exists():
                return ToolResult.failure(
                    f"Parent directory does not exist: {file_path.parent}"
                )
            
            # Check if file exists (for metadata)
            existed = file_path.exists()
            
            # Write content
            file_path.write_text(content, encoding=encoding)
            
            return ToolResult.success(
                f"Successfully wrote {len(content)} bytes to {path}",
                path=str(file_path),
                size=len(content),
                created=not existed
            )
            
        except Exception as e:
            return ToolResult.failure(f"Error writing file: {e}")
    
    def _resolve_path(self, path: str) -> Path:
        """Resolve path relative to workspace root."""
        path_obj = Path(path)
        if path_obj.is_absolute():
            return path_obj
        return self.workspace_root / path
    
    def _is_within_workspace(self, path: Path) -> bool:
        """Check if path is within the workspace."""
        try:
            path.resolve().relative_to(self.workspace_root.resolve())
            return True
        except ValueError:
            return False


@register_tool
class ListFilesTool(BaseTool):
    """Tool for listing directory contents.
    
    Supports both 'path' (string) and 'paths' (array) parameter formats
    to be compatible with original agent_core.py.
    """
    
    def __init__(self, workspace_root: Optional[Path] = None):
        self.workspace_root = workspace_root or Path.cwd()
    
    @property
    def name(self) -> str:
        return "list_files"
    
    @property
    def description(self) -> str:
        return "List files and directories in one or more paths."
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of directory paths to list (relative to workspace). Use ['.'] for root."
                },
                "path": {
                    "type": "string",
                    "description": "Single directory path (alternative to 'paths')",
                    "default": "."
                },
                "recursive": {
                    "type": "boolean",
                    "description": "Whether to list files recursively",
                    "default": False
                },
                "include_hidden": {
                    "type": "boolean",
                    "description": "Whether to include hidden files (starting with .)",
                    "default": False
                },
                "pattern": {
                    "type": "string",
                    "description": "Glob pattern to filter files (e.g., '*.py')"
                }
            },
            "required": []
        }
    
    async def execute(
        self,
        paths: Optional[List[str]] = None,
        path: str = ".",
        recursive: bool = False,
        include_hidden: bool = False,
        pattern: Optional[str] = None,
        **kwargs
    ) -> ToolResult:
        """List directory contents.
        
        Supports both 'paths' array and 'path' string parameters.
        """
        # Support both 'paths' array and 'path' string
        dirs_to_list = paths if paths else [path]
        
        logger.info(f"[ListFiles] workspace_root: {self.workspace_root}")
        logger.info(f"[ListFiles] workspace_root resolved: {self.workspace_root.resolve()}")
        logger.info(f"[ListFiles] Listing dirs: {dirs_to_list}")
        
        all_results = []
        total_files = 0
        total_dirs = 0
        
        for dir_path_str in dirs_to_list:
            try:
                dir_path = self._resolve_path(dir_path_str)
                logger.info(f"[ListFiles] Resolved '{dir_path_str}' -> {dir_path}")
                logger.info(f"[ListFiles] Dir exists: {dir_path.exists()}, is_dir: {dir_path.is_dir() if dir_path.exists() else 'N/A'}")
                
                if not dir_path.exists():
                    logger.warning(f"[ListFiles] Directory not found: {dir_path}")
                    all_results.append(f"[{dir_path_str}] Directory not found")
                    continue
                
                if not dir_path.is_dir():
                    all_results.append(f"[{dir_path_str}] Not a directory")
                    continue
                
                # Check if directory is within workspace
                if not self._is_within_workspace(dir_path):
                    all_results.append(f"[{dir_path_str}] Access denied: outside workspace")
                    continue
                
                files: List[str] = []
                
                if recursive:
                    if pattern:
                        items = dir_path.rglob(pattern)
                    else:
                        items = dir_path.rglob("*")
                else:
                    if pattern:
                        items = dir_path.glob(pattern)
                    else:
                        items = dir_path.iterdir()
                
                for item in sorted(items):
                    rel_path = item.relative_to(dir_path)
                    name = str(rel_path)
                    
                    # Skip hidden files if not included
                    if not include_hidden:
                        if any(part.startswith('.') for part in rel_path.parts):
                            continue
                    
                    # Add indicator for directories
                    if item.is_dir():
                        name += "/"
                        total_dirs += 1
                    else:
                        total_files += 1
                    
                    files.append(name)
                
                logger.info(f"[ListFiles] Found {len(files)} items in {dir_path_str}")
                
                if len(dirs_to_list) > 1:
                    all_results.append(f"[{dir_path_str}]\n" + "\n".join(files) if files else f"[{dir_path_str}] (empty)")
                else:
                    all_results.append("\n".join(files) if files else "(empty directory)")
                
            except Exception as e:
                logger.error(f"[ListFiles] Error listing {dir_path_str}: {e}")
                all_results.append(f"[{dir_path_str}] Error: {e}")
        
        output = "\n\n".join(all_results)
        logger.info(f"[ListFiles] Total: {total_files} files, {total_dirs} dirs")
        
        return ToolResult.success(
            output,
            total_files=total_files,
            total_dirs=total_dirs,
            paths_count=len(dirs_to_list),
            recursive=recursive
        )
    
    def _resolve_path(self, path: str) -> Path:
        """Resolve path relative to workspace root."""
        path_obj = Path(path)
        if path_obj.is_absolute():
            return path_obj
        return self.workspace_root / path
    
    def _is_within_workspace(self, path: Path) -> bool:
        """Check if path is within the workspace."""
        try:
            path.resolve().relative_to(self.workspace_root.resolve())
            return True
        except ValueError:
            return False
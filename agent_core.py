"""
Agent Core Module

This module implements the Autonomous Agent with JSON boundary marker tool calling.
Instead of using native OpenAI/Claude tool_call API, we use text-based tool calls
wrapped in <<<TOOL_CALL>>> / <<<END_TOOL_CALL>>> markers.

This approach is more compatible with proxies and different API providers.
"""

import os
import json
import re
import subprocess
import fnmatch
import logging
from pathlib import Path
from typing import Optional, Callable, Generator, Any
from dataclasses import dataclass, field
from openai import OpenAI

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================================
# JSON Boundary Marker Tool Calling Constants
# ============================================================================

TOOL_CALL_START = '<<<TOOL_CALL>>>'
TOOL_CALL_END = '<<<END_TOOL_CALL>>>'


# ============================================================================
# JSON Tool Call Parsing Functions
# ============================================================================

def parse_json_tool_calls(text: str) -> tuple[list[dict], list[str]]:
    """
    Parse all JSON tool calls from text using boundary markers.
    
    Format:
    <<<TOOL_CALL>>>
    {"tool": "tool_name", "parameters": {...}}
    <<<END_TOOL_CALL>>>
    
    Returns:
        Tuple of (parsed_tool_calls, parse_errors)
        - parsed_tool_calls: List of parsed tool calls with 'tool' and 'parameters' keys
        - parse_errors: List of error messages for failed parses
    """
    results = []
    errors = []
    
    # Match <<<TOOL_CALL>>> ... <<<END_TOOL_CALL>>> blocks
    pattern = re.compile(
        re.escape(TOOL_CALL_START) + r'\s*([\s\S]*?)\s*' + re.escape(TOOL_CALL_END),
        re.MULTILINE
    )
    
    for match in pattern.finditer(text):
        try:
            json_str = match.group(1).strip()
            parsed = json.loads(json_str)
            
            # Validate tool call format
            if isinstance(parsed, dict) and 'tool' in parsed and isinstance(parsed['tool'], str):
                results.append({
                    'tool': parsed['tool'],
                    'parameters': parsed.get('parameters', {})
                })
                logger.debug(f"[PARSE_TOOL] Parsed tool call: {parsed['tool']}")
            else:
                error_msg = f"Invalid tool call format: missing 'tool' key or not a dict"
                errors.append(error_msg)
                logger.warning(f"[PARSE_TOOL] {error_msg}")
        except json.JSONDecodeError as e:
            error_msg = f"JSON parse error: {e}"
            errors.append(error_msg)
            logger.warning(f"[PARSE_TOOL] Failed to parse JSON tool call: {e}")
    
    return results, errors


def has_tool_call_start(text: str) -> bool:
    """Check if text contains a tool call start marker."""
    return TOOL_CALL_START in text


def has_complete_tool_block(text: str) -> bool:
    """Check if all tool call blocks are complete."""
    start_count = text.count(TOOL_CALL_START)
    end_count = text.count(TOOL_CALL_END)
    return start_count > 0 and end_count >= start_count


def extract_text_without_tool_calls(text: str) -> str:
    """
    Extract text content, removing tool call blocks.
    
    Returns the text with all tool call blocks removed.
    """
    pattern = re.compile(
        re.escape(TOOL_CALL_START) + r'\s*[\s\S]*?\s*' + re.escape(TOOL_CALL_END),
        re.MULTILINE
    )
    result = pattern.sub('', text).strip()
    return result


# ============================================================================
# Tool Result Data Classes
# ============================================================================

@dataclass
class ToolResult:
    """Result of a tool execution"""
    success: bool
    data: Optional[Any] = None
    error: Optional[str] = None


@dataclass
class FileEntry:
    """A file or directory entry"""
    name: str
    type: str  # 'file' or 'directory'


@dataclass
class ListFilesResult:
    """Result of list_files operation"""
    path: str
    entries: list[FileEntry] = field(default_factory=list)
    file_count: int = 0
    dir_count: int = 0
    success: bool = True
    error: Optional[str] = None


@dataclass
class ReadFileResult:
    """Result of read_file operation"""
    path: str
    success: bool = True
    content: Optional[str] = None
    line_count: int = 0
    total_lines: int = 0  # Total lines in the original file
    truncated: bool = False  # Whether the file was truncated
    error: Optional[str] = None


@dataclass
class WriteFileResult:
    """Result of write_file operation"""
    path: str
    success: bool = True
    action: Optional[str] = None  # 'created', 'modified', 'unchanged'
    error: Optional[str] = None


@dataclass
class ExecuteCommandResult:
    """Result of execute_command operation"""
    command: str
    cwd: str
    exit_code: Optional[int] = None
    stdout: str = ""
    stderr: str = ""
    success: bool = True
    error: Optional[str] = None
    killed: bool = False


# ============================================================================
# File Truncation Constants
# ============================================================================

# Data file extensions that should be truncated more aggressively (50 lines max)
DATA_FILE_EXTENSIONS = {
    '.csv', '.tsv', '.json', '.jsonl', '.ndjson',
    '.log', '.logs',
    '.xml', '.yaml', '.yml',
    '.sql', '.sqlite', '.db',
    '.parquet', '.arrow', '.feather',
    '.dat', '.data', '.txt'  # Common data file extensions
}

# Maximum lines for data files
DATA_FILE_MAX_LINES = 50

# Maximum lines for other text files
DEFAULT_MAX_LINES = 500

# Warning message appended when file is truncated
TRUNCATION_WARNING = "\n[System]: File truncated. Please write a Python script to process the data instead of reading it directly."


# ============================================================================
# Agent Tools Class
# ============================================================================

class AgentTools:
    """
    A collection of tools that the Agent can use to interact with the file system
    and execute commands.
    """
    
    # Default patterns to ignore when listing files
    DEFAULT_IGNORED = ['.git', '__pycache__', 'node_modules', '.venv', 'venv', '.idea', '.vscode']
    
    def __init__(self, workspace_dir: str, ignore_patterns: Optional[list[str]] = None):
        """
        Initialize the AgentTools.
        
        Args:
            workspace_dir: The root directory for all file operations
            ignore_patterns: List of patterns to ignore when listing files
        """
        self.workspace_dir = Path(workspace_dir).resolve()
        self.ignore_patterns = ignore_patterns or self.DEFAULT_IGNORED
        
    def _should_ignore(self, name: str) -> bool:
        """Check if a file/directory should be ignored based on patterns."""
        for pattern in self.ignore_patterns:
            if pattern.startswith('*') and len(pattern) > 1:
                # *.ext matching
                if name.endswith(pattern[1:]):
                    return True
            elif pattern.endswith('*') and len(pattern) > 1:
                # prefix* matching
                if name.startswith(pattern[:-1]):
                    return True
            else:
                # exact match
                if name == pattern:
                    return True
        return False
    
    def _resolve_path(self, path: str) -> Path:
        """Resolve a path relative to the workspace directory."""
        if not path or path == '.':
            return self.workspace_dir
        
        resolved = (self.workspace_dir / path).resolve()
        
        # Security check: ensure path is within workspace
        try:
            resolved.relative_to(self.workspace_dir)
        except ValueError:
            raise ValueError(f"Path '{path}' is outside the workspace directory")
        
        return resolved
    
    # =========================================================================
    # list_files
    # =========================================================================
    
    def list_files(self, paths: list[str], recursive: bool = False) -> ToolResult:
        """
        List files and directories in the specified paths.
        
        Args:
            paths: List of directory paths to list (relative to workspace)
            recursive: Whether to list files recursively
            
        Returns:
            ToolResult containing ListFilesResult for each path
        """
        if not paths:
            paths = ['.']
            
        results = []
        total_files = 0
        total_dirs = 0
        
        for dir_path in paths:
            try:
                resolved_path = self._resolve_path(dir_path)
                
                if not resolved_path.exists():
                    results.append(ListFilesResult(
                        path=dir_path,
                        success=False,
                        error=f"Directory not found: {dir_path}"
                    ))
                    continue
                    
                if not resolved_path.is_dir():
                    results.append(ListFilesResult(
                        path=dir_path,
                        success=False,
                        error=f"Not a directory: {dir_path}"
                    ))
                    continue
                
                entries = []
                
                if recursive:
                    entries = self._list_recursive(resolved_path, "")
                else:
                    entries = self._list_top_level(resolved_path)
                
                # Sort: directories first, then files, alphabetically within each group
                entries.sort(key=lambda e: (e.type != 'directory', e.name.lower()))
                
                file_count = sum(1 for e in entries if e.type == 'file')
                dir_count = sum(1 for e in entries if e.type == 'directory')
                
                results.append(ListFilesResult(
                    path=dir_path,
                    entries=entries,
                    file_count=file_count,
                    dir_count=dir_count,
                    success=True
                ))
                
                total_files += file_count
                total_dirs += dir_count
                
            except Exception as e:
                results.append(ListFilesResult(
                    path=dir_path,
                    success=False,
                    error=str(e)
                ))
        
        all_success = all(r.success for r in results)
        
        return ToolResult(
            success=all_success,
            data={
                'results': [self._result_to_dict(r) for r in results],
                'total_files': total_files,
                'total_dirs': total_dirs,
                'total_paths': len(paths),
                'recursive': recursive
            },
            error=None if all_success else "Some directories failed to list"
        )
    
    def _list_top_level(self, dir_path: Path) -> list[FileEntry]:
        """List only top-level entries in a directory."""
        entries = []
        
        for item in dir_path.iterdir():
            if self._should_ignore(item.name):
                continue
                
            if item.is_dir():
                entries.append(FileEntry(name=item.name + '/', type='directory'))
            elif item.is_file():
                entries.append(FileEntry(name=item.name, type='file'))
                
        return entries
    
    def _list_recursive(self, dir_path: Path, base_path: str) -> list[FileEntry]:
        """Recursively list all entries in a directory."""
        entries = []
        
        try:
            for item in dir_path.iterdir():
                if self._should_ignore(item.name):
                    continue
                    
                relative_path = f"{base_path}/{item.name}" if base_path else item.name
                
                if item.is_dir():
                    entries.append(FileEntry(name=relative_path + '/', type='directory'))
                    # Recurse into subdirectory
                    entries.extend(self._list_recursive(item, relative_path))
                elif item.is_file():
                    entries.append(FileEntry(name=relative_path, type='file'))
        except PermissionError:
            pass  # Skip directories we can't access
            
        return entries
    
    def _result_to_dict(self, result: ListFilesResult) -> dict:
        """Convert a ListFilesResult to a dictionary."""
        return {
            'path': result.path,
            'entries': [{'name': e.name, 'type': e.type} for e in result.entries],
            'file_count': result.file_count,
            'dir_count': result.dir_count,
            'success': result.success,
            'error': result.error
        }
    
    # =========================================================================
    # read_file
    # =========================================================================
    
    def read_file(self, paths: list[str]) -> ToolResult:
        """
        Read the contents of one or more files.
        
        Text files are returned with line numbers prefixed (e.g., "   1 | code here").
        
        Args:
            paths: List of file paths to read (relative to workspace)
            
        Returns:
            ToolResult containing ReadFileResult for each file
        """
        if not paths:
            return ToolResult(success=False, error="paths is required")
            
        results = []
        success_count = 0
        fail_count = 0
        
        for file_path in paths:
            result = self._read_single_file(file_path)
            results.append(result)
            
            if result.success:
                success_count += 1
            else:
                fail_count += 1
        
        all_success = fail_count == 0
        
        return ToolResult(
            success=all_success,
            data={
                'results': [self._read_result_to_dict(r) for r in results],
                'success_count': success_count,
                'fail_count': fail_count,
                'total_count': len(paths)
            },
            error=None if all_success else f"{fail_count} files failed to read"
        )
    
    def _read_single_file(self, file_path: str) -> ReadFileResult:
        """Read a single file and return its contents with line numbers.
        
        Implements smart truncation logic:
        - Data files (.csv, .json, .log, etc.): max 50 lines
        - Other text files: max 500 lines
        - Appends warning message if truncated
        """
        try:
            resolved_path = self._resolve_path(file_path)
            
            if not resolved_path.exists():
                return ReadFileResult(
                    path=file_path,
                    success=False,
                    error=f"File not found: {file_path}"
                )
                
            if not resolved_path.is_file():
                return ReadFileResult(
                    path=file_path,
                    success=False,
                    error=f"Not a file: {file_path}"
                )
            
            # Check if it's a binary file
            if self._is_binary_file(resolved_path):
                return ReadFileResult(
                    path=file_path,
                    success=False,
                    error=f"Cannot read binary file: {file_path}"
                )
            
            # Read file content
            content = resolved_path.read_text(encoding='utf-8')
            lines = content.split('\n')
            total_lines = len(lines)
            
            # Determine max lines based on file extension
            file_ext = resolved_path.suffix.lower()
            is_data_file = file_ext in DATA_FILE_EXTENSIONS
            max_lines = DATA_FILE_MAX_LINES if is_data_file else DEFAULT_MAX_LINES
            
            # Apply truncation if needed
            truncated = False
            if total_lines > max_lines:
                lines = lines[:max_lines]
                truncated = True
                logger.info(f"[TRUNCATE] File '{file_path}' truncated from {total_lines} to {max_lines} lines (data_file={is_data_file})")
            
            # Add line numbers
            max_line_num_width = len(str(total_lines))  # Use total lines for consistent width
            numbered_lines = [
                f"{str(i + 1).rjust(max_line_num_width)} | {line}"
                for i, line in enumerate(lines)
            ]
            
            # Build final content
            final_content = '\n'.join(numbered_lines)
            
            # Append truncation warning if truncated
            if truncated:
                final_content += TRUNCATION_WARNING
            
            return ReadFileResult(
                path=file_path,
                success=True,
                content=final_content,
                line_count=len(lines),
                total_lines=total_lines,
                truncated=truncated
            )
            
        except UnicodeDecodeError:
            return ReadFileResult(
                path=file_path,
                success=False,
                error=f"Cannot decode file (not UTF-8): {file_path}"
            )
        except Exception as e:
            return ReadFileResult(
                path=file_path,
                success=False,
                error=str(e)
            )
    
    def _is_binary_file(self, path: Path) -> bool:
        """Check if a file is binary by looking at its extension and content."""
        binary_extensions = {
            '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.ico', '.webp',
            '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
            '.zip', '.tar', '.gz', '.rar', '.7z',
            '.exe', '.dll', '.so', '.dylib',
            '.pyc', '.pyo', '.class',
            '.mp3', '.mp4', '.avi', '.mkv', '.wav', '.flac',
            '.ttf', '.otf', '.woff', '.woff2'
        }
        
        if path.suffix.lower() in binary_extensions:
            return True
        
        # Check first bytes for binary content
        try:
            with open(path, 'rb') as f:
                chunk = f.read(1024)
                if b'\x00' in chunk:
                    return True
        except:
            pass
            
        return False
    
    def _read_result_to_dict(self, result: ReadFileResult) -> dict:
        """Convert a ReadFileResult to a dictionary."""
        return {
            'path': result.path,
            'success': result.success,
            'content': result.content,
            'line_count': result.line_count,
            'total_lines': result.total_lines,
            'truncated': result.truncated,
            'error': result.error
        }
    
    # =========================================================================
    # inspect_csv_head - Inspect CSV file headers and first rows
    # =========================================================================
    
    def inspect_csv_head(self, path: str, rows: int = 5) -> ToolResult:
        """
        Inspect the first few rows of a CSV file and return as Markdown table.
        
        Uses pandas for robust CSV parsing. Falls back to manual parsing if
        pandas is not available.
        
        Args:
            path: Path to the CSV file (relative to workspace)
            rows: Number of data rows to show (default: 5)
            
        Returns:
            ToolResult containing the Markdown table representation
        """
        try:
            resolved_path = self._resolve_path(path)
            
            if not resolved_path.exists():
                return ToolResult(success=False, error=f"File not found: {path}")
            
            if not resolved_path.is_file():
                return ToolResult(success=False, error=f"Not a file: {path}")
            
            # Try using pandas first
            try:
                import pandas as pd
                
                # Read only the first few rows for efficiency
                df = pd.read_csv(resolved_path, nrows=rows)
                
                # Get total row count (approximate for large files)
                try:
                    with open(resolved_path, 'r', encoding='utf-8') as f:
                        total_rows = sum(1 for _ in f) - 1  # Subtract header
                except:
                    total_rows = "unknown"
                
                # Convert to markdown table
                markdown_table = df.to_markdown(index=False)
                
                # Add metadata
                result = f"**File:** `{path}`\n"
                result += f"**Columns:** {len(df.columns)}\n"
                result += f"**Total rows:** {total_rows}\n"
                result += f"**Showing first {len(df)} rows:**\n\n"
                result += markdown_table
                
                return ToolResult(
                    success=True,
                    data={
                        'path': path,
                        'columns': list(df.columns),
                        'column_count': len(df.columns),
                        'total_rows': total_rows,
                        'rows_shown': len(df),
                        'markdown': result,
                        'dtypes': {col: str(dtype) for col, dtype in df.dtypes.items()}
                    }
                )
                
            except ImportError:
                # Fallback: manual CSV parsing
                return self._inspect_csv_head_fallback(resolved_path, path, rows)
                
        except Exception as e:
            return ToolResult(success=False, error=f"Error reading CSV: {str(e)}")
    
    def _inspect_csv_head_fallback(self, resolved_path: Path, path: str, rows: int) -> ToolResult:
        """Fallback CSV inspection without pandas."""
        import csv
        
        try:
            with open(resolved_path, 'r', encoding='utf-8', newline='') as f:
                reader = csv.reader(f)
                
                # Read header
                try:
                    header = next(reader)
                except StopIteration:
                    return ToolResult(success=False, error="CSV file is empty")
                
                # Read data rows
                data_rows = []
                for i, row in enumerate(reader):
                    if i >= rows:
                        break
                    data_rows.append(row)
                
                # Count remaining rows
                remaining = sum(1 for _ in reader)
                total_rows = len(data_rows) + remaining
            
            # Build markdown table
            if not header:
                return ToolResult(success=False, error="CSV file has no columns")
            
            # Calculate column widths
            col_widths = [len(str(h)) for h in header]
            for row in data_rows:
                for i, cell in enumerate(row):
                    if i < len(col_widths):
                        col_widths[i] = max(col_widths[i], len(str(cell)))
            
            # Build table
            def format_row(row):
                cells = [str(cell).ljust(col_widths[i]) if i < len(col_widths) else str(cell)
                        for i, cell in enumerate(row)]
                return "| " + " | ".join(cells) + " |"
            
            header_line = format_row(header)
            separator = "|" + "|".join(["-" * (w + 2) for w in col_widths]) + "|"
            data_lines = [format_row(row) for row in data_rows]
            
            markdown_table = "\n".join([header_line, separator] + data_lines)
            
            result = f"**File:** `{path}`\n"
            result += f"**Columns:** {len(header)}\n"
            result += f"**Total rows:** {total_rows}\n"
            result += f"**Showing first {len(data_rows)} rows:**\n\n"
            result += markdown_table
            
            return ToolResult(
                success=True,
                data={
                    'path': path,
                    'columns': header,
                    'column_count': len(header),
                    'total_rows': total_rows,
                    'rows_shown': len(data_rows),
                    'markdown': result
                }
            )
            
        except Exception as e:
            return ToolResult(success=False, error=f"Error parsing CSV: {str(e)}")
    
    # =========================================================================
    # write_file
    # =========================================================================
    
    def write_file(self, files: list[dict]) -> ToolResult:
        """
        Write content to one or more files.
        
        Args:
            files: List of dicts with 'path' and 'content' keys
            
        Returns:
            ToolResult containing WriteFileResult for each file
        """
        if not files:
            return ToolResult(success=False, error="files is required")
            
        results = []
        success_count = 0
        fail_count = 0
        created_count = 0
        modified_count = 0
        unchanged_count = 0
        
        for file_entry in files:
            file_path = file_entry.get('path')
            content = file_entry.get('content', '')
            
            if not file_path:
                results.append(WriteFileResult(
                    path='',
                    success=False,
                    error="path is required"
                ))
                fail_count += 1
                continue
            
            result = self._write_single_file(file_path, content)
            results.append(result)
            
            if result.success:
                success_count += 1
                if result.action == 'created':
                    created_count += 1
                elif result.action == 'modified':
                    modified_count += 1
                elif result.action == 'unchanged':
                    unchanged_count += 1
            else:
                fail_count += 1
        
        all_success = fail_count == 0
        
        return ToolResult(
            success=all_success,
            data={
                'results': [self._write_result_to_dict(r) for r in results],
                'success_count': success_count,
                'fail_count': fail_count,
                'created_count': created_count,
                'modified_count': modified_count,
                'unchanged_count': unchanged_count,
                'total_count': len(files)
            },
            error=None if all_success else f"{fail_count} files failed to write"
        )
    
    def _write_single_file(self, file_path: str, content: str) -> WriteFileResult:
        """Write content to a single file."""
        try:
            resolved_path = self._resolve_path(file_path)
            
            # Check if file exists and content is the same
            file_exists = resolved_path.exists()
            if file_exists:
                try:
                    existing_content = resolved_path.read_text(encoding='utf-8')
                    if existing_content == content:
                        return WriteFileResult(
                            path=file_path,
                            success=True,
                            action='unchanged'
                        )
                except:
                    pass
            
            # Create parent directories if needed
            resolved_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Write the file
            resolved_path.write_text(content, encoding='utf-8')
            
            return WriteFileResult(
                path=file_path,
                success=True,
                action='modified' if file_exists else 'created'
            )
            
        except Exception as e:
            return WriteFileResult(
                path=file_path,
                success=False,
                error=str(e)
            )
    
    def _write_result_to_dict(self, result: WriteFileResult) -> dict:
        """Convert a WriteFileResult to a dictionary."""
        return {
            'path': result.path,
            'success': result.success,
            'action': result.action,
            'error': result.error
        }
    
    # =========================================================================
    # execute_command
    # =========================================================================
    
    def execute_command(
        self,
        command: str,
        cwd: Optional[str] = None,
        timeout: int = 60000
    ) -> ToolResult:
        """
        Execute a shell command and capture its output.
        
        Args:
            command: The command to execute
            cwd: Working directory (relative to workspace), defaults to workspace root
            timeout: Timeout in milliseconds (default 60000 = 60 seconds)
            
        Returns:
            ToolResult containing ExecuteCommandResult
        """
        if not command:
            return ToolResult(success=False, error="command is required")
        
        # Resolve working directory
        try:
            if cwd:
                working_dir = self._resolve_path(cwd)
            else:
                working_dir = self.workspace_dir
                
            if not working_dir.exists():
                return ToolResult(
                    success=False,
                    error=f"Working directory not found: {cwd}"
                )
        except ValueError as e:
            return ToolResult(success=False, error=str(e))
        
        # Convert timeout from milliseconds to seconds
        timeout_seconds = timeout / 1000 if timeout > 0 else None
        
        try:
            # Determine the shell to use based on OS
            if os.name == 'nt':  # Windows
                # Use cmd.exe with chcp 65001 for UTF-8 encoding
                shell_cmd = f'chcp 65001 >nul && {command}'
                process = subprocess.Popen(
                    shell_cmd,
                    shell=True,
                    cwd=str(working_dir),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding='utf-8',
                    errors='replace'
                )
            else:  # Unix-like
                process = subprocess.Popen(
                    command,
                    shell=True,
                    cwd=str(working_dir),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding='utf-8',
                    errors='replace'
                )
            
            try:
                stdout, stderr = process.communicate(timeout=timeout_seconds)
                exit_code = process.returncode
                killed = False
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate()
                exit_code = -1
                killed = True
                stderr = f"Command timed out after {timeout}ms\n{stderr}"
            
            success = exit_code == 0
            
            result = ExecuteCommandResult(
                command=command,
                cwd=str(working_dir),
                exit_code=exit_code,
                stdout=stdout,
                stderr=stderr,
                success=success,
                killed=killed
            )
            
            return ToolResult(
                success=success,
                data=self._exec_result_to_dict(result),
                error=None if success else f"Command exited with code {exit_code}"
            )
            
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"Failed to execute command: {str(e)}"
            )
    
    def _exec_result_to_dict(self, result: ExecuteCommandResult) -> dict:
        """Convert an ExecuteCommandResult to a dictionary."""
        return {
            'command': result.command,
            'cwd': result.cwd,
            'exit_code': result.exit_code,
            'stdout': result.stdout,
            'stderr': result.stderr,
            'success': result.success,
            'killed': result.killed,
            'output': result.stdout + ('\n' + result.stderr if result.stderr else '')
        }
    
    # =========================================================================
    # task_completed
    # =========================================================================
    
    def task_completed(self, result: str) -> ToolResult:
        """
        Signal that the task has been completed.
        
        Args:
            result: Description of what was accomplished
            
        Returns:
            ToolResult indicating completion
        """
        return ToolResult(
            success=True,
            data={
                'completed': True,
                'result': result
            }
        )
    
    # =========================================================================
    # Tool Definitions for JSON Boundary Marker Format
    # =========================================================================
    
    def get_tool_definitions_json(self) -> str:
        """
        Get the tool definitions in JSON boundary marker format for system prompt.
        
        Returns:
            Tool descriptions and usage instructions as text
        """
        tools = [
            {
                "name": "list_files",
                "description": "List files and subdirectories in one or more directories. Useful for exploring the project structure.",
                "parameters": {
                    "paths": {
                        "type": "string[]",
                        "required": True,
                        "description": "List of directory paths to list (relative to workspace root). Use '.' for the root directory."
                    },
                    "recursive": {
                        "type": "boolean",
                        "required": False,
                        "description": "Whether to list subdirectories recursively. Default is false."
                    }
                },
                "example": {
                    "tool": "list_files",
                    "parameters": {"paths": ["."], "recursive": True}
                }
            },
            {
                "name": "read_file",
                "description": "Read the content of one or more files. Returns text files with line number prefixes (e.g., '  1 | code here'). The line numbers are for reference only and not part of the actual file content.",
                "parameters": {
                    "paths": {
                        "type": "string[]",
                        "required": True,
                        "description": "List of file paths to read (relative to workspace root)"
                    }
                },
                "example": {
                    "tool": "read_file",
                    "parameters": {"paths": ["src/main.py", "config.json"]}
                }
            },
            {
                "name": "write_file",
                "description": "Write content to one or more files. Creates parent directories automatically if they don't exist. Files are written with UTF-8 encoding.",
                "parameters": {
                    "files": {
                        "type": "array of {path: string, content: string}",
                        "required": True,
                        "description": "List of files to write, each with path and content"
                    }
                },
                "example": {
                    "tool": "write_file",
                    "parameters": {
                        "files": [{"path": "output.txt", "content": "Hello, World!"}]
                    }
                }
            },
            {
                "name": "execute_command",
                "description": f"Execute a shell command and return the output (stdout and stderr). Use this to run Python scripts, install packages, or perform other system operations. Working directory defaults to the workspace root ({self.workspace_dir}).",
                "parameters": {
                    "command": {
                        "type": "string",
                        "required": True,
                        "description": "The shell command to execute"
                    },
                    "cwd": {
                        "type": "string",
                        "required": False,
                        "description": "Working directory (relative to workspace root). Defaults to workspace root."
                    },
                    "timeout": {
                        "type": "integer",
                        "required": False,
                        "description": "Timeout in milliseconds. Default is 60000 (60 seconds). Use 0 for no timeout."
                    }
                },
                "example": {
                    "tool": "execute_command",
                    "parameters": {"command": "python script.py"}
                }
            },
            {
                "name": "task_completed",
                "description": "Signal that the assigned task has been completed. Use this when you have finished all required work and want to present the final result to the user.",
                "parameters": {
                    "result": {
                        "type": "string",
                        "required": True,
                        "description": "A summary of what was accomplished and any relevant information about the completed work."
                    }
                },
                "example": {
                    "tool": "task_completed",
                    "parameters": {"result": "Successfully created the presentation with 5 slides."}
                }
            },
            {
                "name": "inspect_csv_head",
                "description": "Inspect a CSV file by showing the first few rows as a Markdown table. Use this to understand the structure and content of CSV data files without loading the entire file. This is more efficient than read_file for CSV files.",
                "parameters": {
                    "path": {
                        "type": "string",
                        "required": True,
                        "description": "Path to the CSV file (relative to workspace root)"
                    },
                    "rows": {
                        "type": "integer",
                        "required": False,
                        "description": "Number of data rows to show (default: 5)"
                    }
                },
                "example": {
                    "tool": "inspect_csv_head",
                    "parameters": {"path": "data/sales.csv", "rows": 10}
                }
            }
        ]
        
        # Build tool descriptions
        tool_descriptions = []
        for tool in tools:
            params_desc = []
            for param_name, param_info in tool["parameters"].items():
                req = "[required]" if param_info.get("required") else "[optional]"
                params_desc.append(f"    - {param_name} ({param_info['type']}) {req}: {param_info['description']}")
            
            tool_descriptions.append(f"""### {tool['name']}
{tool['description']}

Parameters:
{chr(10).join(params_desc)}

Example:
```json
{json.dumps(tool['example'], indent=2)}
```""")
        
        return f"""## Available Tools

{chr(10).join(tool_descriptions)}

---

## How to Use Tools

When you need to use a tool, output a JSON object wrapped in special boundary markers:

{TOOL_CALL_START}
{{"tool": "tool_name", "parameters": {{...}}}}
{TOOL_CALL_END}

You can call multiple tools by outputting multiple tool blocks:

{TOOL_CALL_START}
{{"tool": "read_file", "parameters": {{"paths": ["file1.txt", "file2.txt"]}}}}
{TOOL_CALL_END}

{TOOL_CALL_START}
{{"tool": "write_file", "parameters": {{"files": [{{"path": "output.txt", "content": "Hello!"}}]}}}}
{TOOL_CALL_END}

**Important:**
- Each tool call must be wrapped in {TOOL_CALL_START} and {TOOL_CALL_END} markers
- The content between markers must be a valid JSON object
- Use proper JSON syntax (double quotes for strings, no trailing commas)
- After each tool call, wait for the result before proceeding
- The boundary markers ensure that any code blocks in parameters won't interfere with parsing"""
    
    def execute_tool(self, tool_name: str, arguments: dict) -> ToolResult:
        """
        Execute a tool by name with the given arguments.
        
        Args:
            tool_name: Name of the tool to execute
            arguments: Tool arguments as a dictionary
            
        Returns:
            ToolResult from the tool execution
        """
        tool_handlers = {
            'list_files': lambda args: self.list_files(
                paths=args.get('paths', ['.']),
                recursive=args.get('recursive', False)
            ),
            'read_file': lambda args: self.read_file(
                paths=args.get('paths', [])
            ),
            'write_file': lambda args: self.write_file(
                files=args.get('files', [])
            ),
            'execute_command': lambda args: self.execute_command(
                command=args.get('command', ''),
                cwd=args.get('cwd'),
                timeout=args.get('timeout', 60000)
            ),
            'task_completed': lambda args: self.task_completed(
                result=args.get('result', '')
            ),
            'inspect_csv_head': lambda args: self.inspect_csv_head(
                path=args.get('path', ''),
                rows=args.get('rows', 5)
            )
        }
        
        handler = tool_handlers.get(tool_name)
        if not handler:
            return ToolResult(success=False, error=f"Unknown tool: {tool_name}")
        
        try:
            return handler(arguments)
        except Exception as e:
            return ToolResult(success=False, error=f"Tool execution error: {str(e)}")


# ============================================================================
# Agent Message Classes
# ============================================================================

@dataclass
class AgentMessage:
    """A message in the agent conversation"""
    role: str  # 'system', 'user', 'assistant', 'tool'
    content: Optional[str] = None
    tool_calls: Optional[list] = None
    tool_call_id: Optional[str] = None
    name: Optional[str] = None  # For tool messages


@dataclass
class ToolCallInfo:
    """Information about a tool call for UI display"""
    id: str
    name: str
    arguments: dict
    result: Optional[ToolResult] = None


# ============================================================================
# Agent Class
# ============================================================================

class Agent:
    """
    Autonomous Agent that uses OpenAI's Function Calling API
    to execute tasks using a set of tools.
    """
    
    def __init__(
        self,
        api_key: str,
        workspace_dir: str,
        system_prompt_path: str = "system_prompt.txt",
        model: str = "gpt-4o",
        base_url: Optional[str] = None,
        on_tool_call: Optional[Callable[[ToolCallInfo], None]] = None,
        on_message: Optional[Callable[[str, str], None]] = None,
        enable_thinking: Optional[bool] = None
    ):
        """
        Initialize the Agent.
        
        Args:
            api_key: OpenAI API key
            workspace_dir: Root directory for file operations
            system_prompt_path: Path to the system prompt file
            model: OpenAI model to use (default: gpt-4o)
            base_url: Optional custom API base URL
            on_tool_call: Callback when a tool is called (for UI updates)
            on_message: Callback when agent sends a message (role, content)
            enable_thinking: Whether to enable extended thinking for Claude models.
                           None = auto-detect (disabled for proxies/custom base_url)
                           True = force enable
                           False = force disable
        """
        self.model = model
        self.workspace_dir = Path(workspace_dir).resolve()
        self.on_tool_call = on_tool_call
        self.on_message = on_message
        self.base_url = base_url
        
        # Extended thinking configuration
        # Default: disabled for custom base_url (proxy), enabled for direct Anthropic API
        if enable_thinking is None:
            # Auto-detect: disable for proxies since they often don't support thinking properly
            self.enable_thinking = False  # Default to disabled - proxies typically don't support it
            logger.info(f"[THINKING] Auto-detect: Extended thinking disabled (custom base_url or proxy detected)")
        else:
            self.enable_thinking = enable_thinking
            logger.info(f"[THINKING] Explicitly set to: {enable_thinking}")
        
        # Track if we've detected thinking support at runtime
        self._thinking_supported = None  # None = unknown, True/False after first response
        
        # Initialize OpenAI client
        client_kwargs = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url
        self.client = OpenAI(**client_kwargs)
        
        # Initialize tools
        self.tools = AgentTools(workspace_dir)
        
        # Load system prompt and append tool definitions
        base_prompt = self._load_system_prompt(system_prompt_path)
        tool_definitions = self.tools.get_tool_definitions_json()
        self.system_prompt = f"{base_prompt}\n\n{tool_definitions}"
        
        # Conversation history
        self.messages: list[dict] = []
        
        # Task completion flag
        self.task_completed = False
        self.task_result = None
    
    def _is_claude_model(self) -> bool:
        """Check if the current model is a Claude model."""
        model_lower = self.model.lower()
        return 'claude' in model_lower or 'anthropic' in model_lower
    
    def _get_extra_body(self) -> Optional[dict]:
        """
        Get extra body parameters for the API request.
        
        For Claude models with extended thinking enabled, we need to:
        1. Enable thinking mode with a budget
        2. Ensure assistant messages in history start with thinking blocks
        """
        if self._is_claude_model() and self.enable_thinking:
            # Check if we've detected that thinking is not supported
            if self._thinking_supported is False:
                logger.info(f"[THINKING] Skipping thinking - not supported by this API/proxy")
                return None
            
            # Enable thinking with a reasonable budget
            extra_body = {
                "thinking": {
                    "type": "enabled",
                    "budget_tokens": 10000  # Allow up to 10k tokens for thinking
                }
            }
            logger.debug(f"[CLAUDE] Extra body for thinking: {json.dumps(extra_body, indent=2)}")
            return extra_body
        return None
    
    def _format_message_for_claude(self, message: dict) -> dict:
        """
        Format a message for Claude's extended thinking requirements.
        
        When thinking is enabled, assistant messages must start with thinking blocks.
        This ensures proper conversation history format.
        """
        if message.get("role") != "assistant":
            return message
        
        # Check if this message already has thinking content
        content = message.get("content")
        
        # If content is a string, convert to proper format
        if isinstance(content, str):
            # For Claude, we need to wrap in content blocks
            # But since we don't have thinking for this message, we'll handle it
            return message
        
        # If content is already a list of content blocks, check for thinking
        if isinstance(content, list):
            has_thinking = any(
                isinstance(block, dict) and block.get("type") in ["thinking", "redacted_thinking"]
                for block in content
            )
            if has_thinking:
                return message
        
        return message
    
    def _build_claude_messages(self, messages: list[dict]) -> list[dict]:
        """
        Build messages list formatted for Claude's extended thinking.
        
        Ensures that assistant messages properly include thinking blocks
        when present in the conversation history.
        """
        formatted = []
        for msg in messages:
            formatted.append(self._format_message_for_claude(msg))
        return formatted
    
    def _parse_claude_response(self, message) -> tuple[list, Optional[str], list]:
        """
        Parse Claude's response to extract thinking blocks, text content, and tool calls.
        
        Returns:
            (thinking_blocks, text_content, tool_calls)
            - thinking_blocks: List of complete thinking block dicts (with type, thinking, signature)
            - text_content: The text response content
            - tool_calls: List of tool calls
        """
        thinking_blocks = []
        text_content = None
        tool_calls = []
        
        logger.debug(f"[PARSE] Parsing response message type: {type(message)}")
        logger.debug(f"[PARSE] Message attributes: {dir(message)}")
        
        # Log raw message content
        if hasattr(message, 'content'):
            logger.debug(f"[PARSE] Message content type: {type(message.content)}")
            if isinstance(message.content, list):
                logger.debug(f"[PARSE] Message content blocks count: {len(message.content)}")
                for i, block in enumerate(message.content):
                    block_info = {
                        "type": getattr(block, 'type', 'unknown'),
                        "attributes": dir(block) if hasattr(block, '__dict__') else str(block)
                    }
                    logger.debug(f"[PARSE] Block {i}: {json.dumps(block_info, default=str)}")
            else:
                content_preview = str(message.content)[:200] if message.content else "None"
                logger.debug(f"[PARSE] Message content (string): {content_preview}...")
        
        # Check if the response has content blocks (Claude format)
        if hasattr(message, 'content') and isinstance(message.content, list):
            for block in message.content:
                if hasattr(block, 'type'):
                    logger.debug(f"[PARSE] Processing block type: {block.type}")
                    if block.type == 'thinking':
                        # Preserve the complete thinking block with signature
                        thinking_block = {
                            "type": "thinking",
                            "thinking": getattr(block, 'thinking', '')
                        }
                        # Include signature if present (critical for Claude API)
                        if hasattr(block, 'signature') and block.signature:
                            thinking_block["signature"] = block.signature
                            logger.debug(f"[PARSE] Thinking block has signature: {block.signature[:50]}...")
                        else:
                            logger.warning(f"[PARSE] Thinking block MISSING signature!")
                        thinking_blocks.append(thinking_block)
                        logger.debug(f"[PARSE] Added thinking block, thinking preview: {thinking_block['thinking'][:100]}...")
                    elif block.type == 'redacted_thinking':
                        # Preserve redacted thinking blocks as-is
                        redacted_block = {
                            "type": "redacted_thinking",
                            "data": getattr(block, 'data', '')
                        }
                        thinking_blocks.append(redacted_block)
                        logger.debug(f"[PARSE] Added redacted_thinking block")
                    elif block.type == 'text':
                        text_content = getattr(block, 'text', None)
                        logger.debug(f"[PARSE] Text content: {text_content[:100] if text_content else 'None'}...")
                    elif block.type == 'tool_use':
                        # Convert to tool_call format
                        tool_calls.append({
                            "id": getattr(block, 'id', ''),
                            "type": "function",
                            "function": {
                                "name": getattr(block, 'name', ''),
                                "arguments": json.dumps(getattr(block, 'input', {}))
                            }
                        })
                        logger.debug(f"[PARSE] Added tool_use: {getattr(block, 'name', '')}")
        
        # Fallback to standard OpenAI format
        if text_content is None and hasattr(message, 'content') and isinstance(message.content, str):
            text_content = message.content
            logger.debug(f"[PARSE] Fallback to string content")
        
        if not tool_calls and hasattr(message, 'tool_calls') and message.tool_calls:
            tool_calls = message.tool_calls
            logger.debug(f"[PARSE] Fallback to tool_calls attribute, count: {len(tool_calls)}")
        
        logger.info(f"[PARSE] Result: {len(thinking_blocks)} thinking blocks, text={text_content is not None}, {len(tool_calls)} tool_calls")
        return thinking_blocks, text_content, tool_calls
    
    def _create_assistant_message_with_thinking(
        self,
        thinking_blocks: list,
        content: Optional[str],
        tool_calls: Optional[list]
    ) -> dict:
        """
        Create an assistant message that includes thinking blocks for Claude.
        
        When extended thinking is enabled, assistant messages must start with
        thinking blocks before any text or tool_use content.
        
        Args:
            thinking_blocks: List of complete thinking block dicts (with type, thinking, signature)
            content: Text content
            tool_calls: Tool calls to include
        """
        logger.debug(f"[CREATE_MSG] Creating assistant message: thinking_blocks={len(thinking_blocks)}, content={content is not None}, tool_calls={len(tool_calls) if tool_calls else 0}")
        
        # Check if this is Claude with thinking enabled AND we have thinking blocks
        use_claude_format = self._is_claude_model() and self.enable_thinking and thinking_blocks
        
        if not use_claude_format:
            # Standard OpenAI format for:
            # - Non-Claude models
            # - Claude without thinking enabled
            # - Claude with thinking but no thinking blocks returned (proxy doesn't support it)
            msg = {"role": "assistant", "content": content}
            if tool_calls:
                msg["tool_calls"] = [
                    {
                        "id": tc.id if hasattr(tc, 'id') else tc.get("id", ""),
                        "type": "function",
                        "function": {
                            "name": tc.function.name if hasattr(tc, 'function') else tc.get("function", {}).get("name", ""),
                            "arguments": tc.function.arguments if hasattr(tc, 'function') else tc.get("function", {}).get("arguments", "{}")
                        }
                    }
                    for tc in tool_calls
                ]
            logger.debug(f"[CREATE_MSG] OpenAI format (thinking_blocks={len(thinking_blocks)}): {json.dumps(msg, default=str)[:500]}...")
            return msg
        
        # For Claude with extended thinking AND we have thinking blocks, build content blocks
        content_blocks = []
        
        # Thinking blocks must come first - include complete blocks with signatures
        for i, thinking_block in enumerate(thinking_blocks):
            # Add the complete thinking block (includes signature if present)
            content_blocks.append(thinking_block)
            has_sig = "signature" in thinking_block
            logger.debug(f"[CREATE_MSG] Added thinking block {i}, has_signature={has_sig}")
        
        # Then text content
        if content:
            content_blocks.append({
                "type": "text",
                "text": content
            })
            logger.debug(f"[CREATE_MSG] Added text block")
        
        # Then tool_use blocks
        if tool_calls:
            for tc in tool_calls:
                tc_id = tc.id if hasattr(tc, 'id') else tc.get("id", "")
                tc_name = tc.function.name if hasattr(tc, 'function') else tc.get("function", {}).get("name", "")
                tc_args = tc.function.arguments if hasattr(tc, 'function') else tc.get("function", {}).get("arguments", "{}")
                
                content_blocks.append({
                    "type": "tool_use",
                    "id": tc_id,
                    "name": tc_name,
                    "input": json.loads(tc_args) if isinstance(tc_args, str) else tc_args
                })
                logger.debug(f"[CREATE_MSG] Added tool_use block: {tc_name}")
        
        result_msg = {
            "role": "assistant",
            "content": content_blocks if content_blocks else content
        }
        
        # Log the structure of content blocks
        if content_blocks:
            block_summary = [{"type": b.get("type"), "has_signature": "signature" in b if b.get("type") == "thinking" else None} for b in content_blocks]
            logger.info(f"[CREATE_MSG] Claude format content blocks: {json.dumps(block_summary)}")
        
        return result_msg
    
    def _create_tool_result_message(self, tool_call_id: str, result: str) -> dict:
        """
        Create a tool result message in the appropriate format.
        
        For Claude, use content blocks format. For others, use standard format.
        
        Note: For Claude, when there are multiple tool results, they should be
        combined into a single user message. Use _create_combined_tool_results_message
        for that purpose.
        """
        if self._is_claude_model():
            return {
                "role": "user",
                "content": [{
                    "type": "tool_result",
                    "tool_use_id": tool_call_id,
                    "content": result
                }]
            }
        else:
            return {
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": result
            }
    
    def _create_combined_tool_results_message(self, tool_results: list[tuple[str, str]]) -> list[dict]:
        """
        Create tool result messages, combining them appropriately for the model.
        
        For Claude: All tool results are combined into a SINGLE user message.
        Claude API requires that each tool_use block has a corresponding tool_result
        in the IMMEDIATELY NEXT message.
        
        For OpenAI: Each tool result is a separate tool message.
        
        Args:
            tool_results: List of (tool_call_id, result_content) tuples
            
        Returns:
            List of message dicts (single message for Claude, multiple for OpenAI)
        """
        if not tool_results:
            return []
        
        if self._is_claude_model():
            # Claude: Combine all tool results into ONE user message
            content_blocks = []
            for tool_call_id, result_content in tool_results:
                content_blocks.append({
                    "type": "tool_result",
                    "tool_use_id": tool_call_id,
                    "content": result_content
                })
            
            logger.debug(f"[TOOL_RESULTS] Created combined Claude message with {len(content_blocks)} tool_result blocks")
            return [{
                "role": "user",
                "content": content_blocks
            }]
        else:
            # OpenAI: Each tool result is a separate message
            messages = []
            for tool_call_id, result_content in tool_results:
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": result_content
                })
            logger.debug(f"[TOOL_RESULTS] Created {len(messages)} separate OpenAI tool messages")
            return messages
        
    def _load_system_prompt(self, path: str) -> str:
        """Load the system prompt from a file."""
        prompt_path = self.workspace_dir / path
        
        if prompt_path.exists():
            return prompt_path.read_text(encoding='utf-8')
        else:
            # Default system prompt if file not found
            return """You are an autonomous AI agent that helps users create data-driven HTML presentations.

You have access to the following tools:
- list_files: List files and directories
- read_file: Read file contents
- write_file: Write content to files
- execute_command: Execute shell commands
- task_completed: Signal task completion

Follow these guidelines:
1. Analyze the user's request carefully
2. Break down complex tasks into smaller steps
3. Use tools to explore the project and understand the context
4. Write clean, well-structured code
5. Test your work by executing relevant commands
6. If you encounter errors, analyze them and fix the issues
7. Signal completion when the task is done

Always explain what you're doing and why."""

    def reset(self):
        """Reset the agent state for a new conversation."""
        self.messages = []
        self.task_completed = False
        self.task_result = None
    
    def _add_message(self, message: dict):
        """Add a message to the conversation history."""
        self.messages.append(message)
    
    def run(self, user_message: str, max_iterations: int = 50, stream: bool = True) -> Generator[dict, None, None]:
        """
        Run the agent with a user message.
        
        This is a generator that yields events as the agent processes the request.
        
        Args:
            user_message: The user's request
            max_iterations: Maximum number of tool-call iterations (safety limit)
            stream: Whether to use streaming API calls (default: True)
            
        Yields:
            Events with type and data:
            - {'type': 'user_message', 'content': str}
            - {'type': 'assistant_message', 'content': str}
            - {'type': 'streaming_delta', 'delta': str, 'accumulated': str}  # New: streaming text updates
            - {'type': 'streaming_complete', 'content': str}  # New: streaming finished
            - {'type': 'tool_call', 'tool_call': ToolCallInfo}
            - {'type': 'tool_result', 'tool_call': ToolCallInfo}
            - {'type': 'task_completed', 'result': str}
            - {'type': 'error', 'error': str}
        """
        # Reset task completion flag
        self.task_completed = False
        self.task_result = None
        
        # Build messages for API call
        api_messages = [
            {"role": "system", "content": self.system_prompt}
        ]
        
        # Add conversation history
        api_messages.extend(self.messages)
        
        # Add user message
        user_msg = {"role": "user", "content": user_message}
        self._add_message(user_msg)
        api_messages.append(user_msg)
        
        yield {"type": "user_message", "content": user_message}
        
        iteration = 0
        
        while not self.task_completed and iteration < max_iterations:
            iteration += 1
            
            try:
                # Build API call parameters - NO native tools, we use text-based tool calling
                api_params = {
                    "model": self.model,
                    "messages": api_messages,
                    "stream": stream
                }
                
                # Add extra body for Claude models (enable thinking)
                extra_body = self._get_extra_body()
                if extra_body:
                    api_params["extra_body"] = extra_body
                
                # Log the messages being sent (summarized)
                logger.info(f"[API] Sending request to model: {self.model} (stream={stream})")
                logger.debug(f"[API] Message count: {len(api_messages)}")
                for i, msg in enumerate(api_messages):
                    role = msg.get("role", "unknown")
                    content = msg.get("content")
                    if isinstance(content, list):
                        block_types = [b.get("type", "unknown") for b in content if isinstance(b, dict)]
                        logger.debug(f"[API] Message {i} ({role}): content_blocks={block_types}")
                    else:
                        preview = str(content)[:100] if content else "None"
                        logger.debug(f"[API] Message {i} ({role}): {preview}...")
                
                # Call API
                logger.info(f"[API] Calling API (JSON boundary marker mode, stream={stream})...")
                
                if stream:
                    # Streaming mode
                    full_text_content = ""
                    thinking_blocks = []
                    current_thinking = ""
                    in_thinking_block = False
                    
                    response_stream = self.client.chat.completions.create(**api_params)
                    
                    for chunk in response_stream:
                        if not chunk.choices:
                            continue
                        
                        delta = chunk.choices[0].delta
                        
                        # Handle content delta
                        if hasattr(delta, 'content') and delta.content:
                            content_delta = delta.content
                            full_text_content += content_delta
                            
                            # Yield streaming delta event for UI updates
                            yield {
                                "type": "streaming_delta",
                                "delta": content_delta,
                                "accumulated": full_text_content
                            }
                    
                    # Streaming complete
                    if full_text_content:
                        yield {
                            "type": "streaming_complete",
                            "content": full_text_content
                        }
                    
                    logger.info(f"[API] Streaming complete, total length: {len(full_text_content)}")
                    
                else:
                    # Non-streaming mode (original behavior)
                    response = self.client.chat.completions.create(**api_params)
                    logger.info(f"[API] Response received")
                    
                    assistant_message = response.choices[0].message
                    logger.debug(f"[API] Response message type: {type(assistant_message)}")
                    
                    # Get the full text content from response
                    full_text_content = None
                    thinking_blocks = []
                    
                    # Handle different response formats
                    if hasattr(assistant_message, 'content'):
                        if isinstance(assistant_message.content, list):
                            # Claude format with content blocks
                            for block in assistant_message.content:
                                if hasattr(block, 'type'):
                                    if block.type == 'thinking':
                                        thinking_block = {
                                            "type": "thinking",
                                            "thinking": getattr(block, 'thinking', '')
                                        }
                                        if hasattr(block, 'signature') and block.signature:
                                            thinking_block["signature"] = block.signature
                                        thinking_blocks.append(thinking_block)
                                    elif block.type == 'text':
                                        full_text_content = getattr(block, 'text', '')
                        else:
                            # String content (OpenAI format)
                            full_text_content = assistant_message.content
                    
                    # Detect if thinking is supported by this API/proxy
                    if self.enable_thinking and self._thinking_supported is None:
                        if thinking_blocks:
                            self._thinking_supported = True
                            logger.info(f"[THINKING] Detected: API supports extended thinking (got {len(thinking_blocks)} thinking blocks)")
                        else:
                            self._thinking_supported = False
                            self.enable_thinking = False  # Disable for future requests
                            logger.warning(f"[THINKING] Detected: API/proxy does NOT support extended thinking. Disabling thinking mode.")
                
                # Parse JSON boundary marker tool calls from text
                tool_calls = []
                parse_errors = []
                has_tool_markers = False
                
                if full_text_content:
                    has_tool_markers = has_tool_call_start(full_text_content)
                    tool_calls, parse_errors = parse_json_tool_calls(full_text_content)
                    logger.debug(f"[PARSE_TOOL] Parsed {len(tool_calls)} tool call(s) from text, {len(parse_errors)} error(s)")
                
                # Handle case where tool markers exist but parsing failed
                if has_tool_markers and not tool_calls and parse_errors:
                    logger.warning(f"[AGENT] Tool call markers found but parsing failed: {parse_errors}")
                    
                    # Add assistant message to history
                    assistant_msg_dict = {"role": "assistant", "content": full_text_content}
                    self._add_message(assistant_msg_dict)
                    api_messages.append(assistant_msg_dict)
                    
                    # Send error feedback to let the agent retry with correct format
                    error_feedback = (
                        f"工具调用格式错误，无法解析。错误信息：{'; '.join(parse_errors)}\n\n"
                        f"请使用正确的JSON格式重试。确保：\n"
                        f"1. JSON语法正确（使用双引号，无尾随逗号）\n"
                        f"2. 字符串中的特殊字符正确转义\n"
                        f"3. 工具调用格式为：{TOOL_CALL_START}\n"
                        f'   {{"tool": "tool_name", "parameters": {{...}}}}\n'
                        f"   {TOOL_CALL_END}"
                    )
                    
                    error_msg = {"role": "user", "content": error_feedback}
                    self._add_message(error_msg)
                    api_messages.append(error_msg)
                    
                    # Yield error notification to UI
                    yield {"type": "assistant_message", "content": f"⚠️ 工具调用解析失败，正在重试..."}
                    
                    # Continue to next iteration to let agent retry
                    continue
                
                # Check if the assistant wants to use tools
                if tool_calls:
                    # Add assistant message to history (the full text including tool call markers)
                    assistant_msg_dict = {"role": "assistant", "content": full_text_content}
                    self._add_message(assistant_msg_dict)
                    api_messages.append(assistant_msg_dict)
                    
                    # Get text without tool call blocks for display
                    display_text = extract_text_without_tool_calls(full_text_content) if full_text_content else ""
                    if display_text and not stream:
                        # Only yield assistant_message if not streaming (streaming already sent deltas)
                        yield {"type": "assistant_message", "content": display_text}
                    
                    # Process each tool call
                    tool_call_infos = []
                    tool_results_text_parts = []  # Build tool results as text
                    
                    for i, tool_call in enumerate(tool_calls):
                        tool_name = tool_call['tool']
                        arguments = tool_call['parameters']
                        tool_id = f"call_{iteration}_{i}"  # Generate a simple ID
                        
                        # Create tool call info for UI
                        tool_call_info = ToolCallInfo(
                            id=tool_id,
                            name=tool_name,
                            arguments=arguments
                        )
                        
                        yield {"type": "tool_call", "tool_call": tool_call_info}
                        
                        # Execute the tool
                        result = self.tools.execute_tool(tool_name, arguments)
                        tool_call_info.result = result
                        
                        # Check for task completion
                        if tool_name == "task_completed" and result.success:
                            self.task_completed = True
                            self.task_result = arguments.get('result', '')
                        
                        # Build tool result text
                        result_content = json.dumps(result.data if result.data else {"error": result.error}, indent=2)
                        tool_results_text_parts.append(f'Tool result for "{tool_name}":\n{result_content}')
                        tool_call_infos.append(tool_call_info)
                    
                    # Add all tool results as a single user message (text format)
                    if tool_results_text_parts:
                        tool_results_message = {
                            "role": "user",
                            "content": "\n\n".join(tool_results_text_parts)
                        }
                        self._add_message(tool_results_message)
                        api_messages.append(tool_results_message)
                    
                    logger.info(f"[TOOL_RESULTS] Added {len(tool_call_infos)} tool results as text message")
                    
                    # Now yield tool results and call callbacks
                    for tool_call_info in tool_call_infos:
                        yield {"type": "tool_result", "tool_call": tool_call_info}
                        
                        # Callback for UI
                        if self.on_tool_call:
                            self.on_tool_call(tool_call_info)
                
                else:
                    # No tool calls - just a regular response
                    content = full_text_content
                    assistant_msg_dict = {"role": "assistant", "content": content}
                    self._add_message(assistant_msg_dict)
                    api_messages.append(assistant_msg_dict)
                    
                    if content and not stream:
                        # Only yield assistant_message if not streaming (streaming already sent deltas)
                        yield {"type": "assistant_message", "content": content}
                        
                        if self.on_message:
                            self.on_message("assistant", content)
                    
                    # If no tool calls and no task_completed, treat this as implicit completion
                    # The agent has finished its work but didn't explicitly call task_completed
                    logger.info(f"[AGENT] No tool calls in response - treating as implicit task completion")
                    self.task_completed = True
                    self.task_result = content if content else "任务已完成"
                    break
                    
            except Exception as e:
                yield {"type": "error", "error": str(e)}
                break
        
        if self.task_completed:
            yield {"type": "task_completed", "result": self.task_result}
        elif iteration >= max_iterations:
            yield {"type": "error", "error": f"Maximum iterations ({max_iterations}) reached"}
    
    def run_sync(self, user_message: str, max_iterations: int = 50) -> dict:
        """
        Run the agent synchronously and return the final result.
        
        Args:
            user_message: The user's request
            max_iterations: Maximum number of tool-call iterations
            
        Returns:
            Final result dict with 'success', 'result' or 'error'
        """
        events = list(self.run(user_message, max_iterations))
        
        if not events:
            return {"success": False, "error": "No events generated"}
        
        last_event = events[-1]
        
        if last_event["type"] == "task_completed":
            return {"success": True, "result": last_event["result"]}
        elif last_event["type"] == "error":
            return {"success": False, "error": last_event["error"]}
        elif last_event["type"] == "assistant_message":
            return {"success": True, "result": last_event["content"]}
        else:
            return {"success": True, "result": "Task processing completed"}


# ============================================================================
# Slide Refinement Helper
# ============================================================================

class SlideRefiner:
    """
    Helper class for refining individual slides in an HTML presentation.
    """
    
    def __init__(self, agent: Agent):
        """
        Initialize the SlideRefiner.
        
        Args:
            agent: The Agent instance to use for refinement
        """
        self.agent = agent
    
    def extract_slide(self, html_path: str, slide_index: int) -> Optional[str]:
        """
        Extract a single slide's HTML from the presentation.
        
        Args:
            html_path: Path to the HTML file
            slide_index: 0-based index of the slide to extract
            
        Returns:
            The HTML content of the slide, or None if not found
        """
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            # Fallback to regex if BeautifulSoup is not available
            return self._extract_slide_regex(html_path, slide_index)
        
        full_path = self.agent.workspace_dir / html_path
        if not full_path.exists():
            return None
        
        html_content = full_path.read_text(encoding='utf-8')
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Common slide container patterns
        slides = soup.find_all(['section', 'div'], class_=lambda c: c and 'slide' in c.lower() if c else False)
        
        if not slides:
            # Try finding by id pattern
            slides = soup.find_all(['section', 'div'], id=lambda i: i and 'slide' in i.lower() if i else False)
        
        if not slides:
            # Try finding all sections (reveal.js style)
            slides = soup.find_all('section')
        
        if slide_index < 0 or slide_index >= len(slides):
            return None
        
        return str(slides[slide_index])
    
    def _extract_slide_regex(self, html_path: str, slide_index: int) -> Optional[str]:
        """Extract slide using regex (fallback when BeautifulSoup is not available)."""
        import re
        
        full_path = self.agent.workspace_dir / html_path
        if not full_path.exists():
            return None
        
        html_content = full_path.read_text(encoding='utf-8')
        
        # Pattern to match slide sections
        pattern = r'<section[^>]*>.*?</section>'
        matches = re.findall(pattern, html_content, re.DOTALL)
        
        if slide_index < 0 or slide_index >= len(matches):
            return None
        
        return matches[slide_index]
    
    def refine_slide(
        self,
        html_path: str,
        slide_index: int,
        user_feedback: str
    ) -> Generator[dict, None, None]:
        """
        Refine a specific slide based on user feedback.
        
        Args:
            html_path: Path to the HTML file
            slide_index: 0-based index of the slide to refine
            user_feedback: User's modification request
            
        Yields:
            Events from the agent's refinement process
        """
        # Extract the current slide code
        slide_code = self.extract_slide(html_path, slide_index)
        
        if not slide_code:
            yield {
                "type": "error",
                "error": f"Could not extract slide {slide_index + 1} from {html_path}"
            }
            return
        
        # Construct the refinement prompt
        refinement_prompt = f"""用户希望修改第 {slide_index + 1} 页幻灯片。

这是该页原本的代码：
```html
{slide_code}
```

用户的修改意见：{user_feedback}

请遵循 system_prompt 中的 Tailwind/Chart.js 规范，修改这一页幻灯片。
请直接使用 write_file 工具将修改后的完整 HTML 文件写入 {html_path}。
注意保持其他幻灯片不变，只修改第 {slide_index + 1} 页的内容。"""
        
        # Run the agent with the refinement prompt
        yield from self.agent.run(refinement_prompt)


# ============================================================================
# Convenience Functions
# ============================================================================

def create_agent(
    api_key: str,
    workspace_dir: str = ".",
    system_prompt_path: str = "system_prompt.txt",
    model: str = "gpt-4o",
    base_url: Optional[str] = None
) -> Agent:
    """
    Create and return a configured Agent instance.
    
    Args:
        api_key: OpenAI API key
        workspace_dir: Root directory for file operations
        system_prompt_path: Path to the system prompt file
        model: OpenAI model to use
        base_url: Optional custom API base URL
        
    Returns:
        Configured Agent instance
    """
    return Agent(
        api_key=api_key,
        workspace_dir=workspace_dir,
        system_prompt_path=system_prompt_path,
        model=model,
        base_url=base_url
    )


if __name__ == "__main__":
    # Simple test
    import sys
    
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("Please set OPENAI_API_KEY environment variable")
        sys.exit(1)
    
    agent = create_agent(api_key, workspace_dir=".")
    
    print("Agent initialized. Enter a task (or 'quit' to exit):")
    
    while True:
        try:
            user_input = input("\n> ").strip()
            if user_input.lower() in ('quit', 'exit', 'q'):
                break
            
            if not user_input:
                continue
            
            print("\n" + "="*50)
            
            for event in agent.run(user_input):
                event_type = event["type"]
                
                if event_type == "assistant_message":
                    print(f"\n🤖 Assistant: {event['content']}")
                elif event_type == "tool_call":
                    tc = event["tool_call"]
                    print(f"\n🔧 Calling {tc.name}({json.dumps(tc.arguments, indent=2)})")
                elif event_type == "tool_result":
                    tc = event["tool_call"]
                    status = "✅" if tc.result.success else "❌"
                    print(f"{status} Result: {json.dumps(tc.result.data, indent=2) if tc.result.data else tc.result.error}")
                elif event_type == "task_completed":
                    print(f"\n✨ Task Completed: {event['result']}")
                elif event_type == "error":
                    print(f"\n❌ Error: {event['error']}")
            
            print("\n" + "="*50)
            
        except KeyboardInterrupt:
            print("\nInterrupted")
            break
        except Exception as e:
            print(f"\nError: {e}")
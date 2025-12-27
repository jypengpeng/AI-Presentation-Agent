"""
Workspace Copier Module

Handles copying directories while respecting .gitignore rules.
Provides size calculation and progress tracking for large directories.
"""

import os
import shutil
import fnmatch
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional, Set, Callable


@dataclass
class CopyResult:
    """Result of a copy operation."""
    success: bool
    files_copied: int = 0
    dirs_created: int = 0
    total_size_bytes: int = 0
    skipped_files: int = 0
    error: Optional[str] = None
    
    @property
    def total_size_mb(self) -> float:
        """Get total size in megabytes."""
        return self.total_size_bytes / (1024 * 1024)


@dataclass
class ScanResult:
    """Result of scanning a directory or file list."""
    total_files: int = 0
    total_dirs: int = 0
    total_size_bytes: int = 0
    skipped_by_ignore: int = 0
    files_to_copy: List[str] = field(default_factory=list)
    # Base directory for relative paths
    base_dir: str = ""
    
    @property
    def total_size_mb(self) -> float:
        """Get total size in megabytes."""
        return self.total_size_bytes / (1024 * 1024)


class GitIgnoreParser:
    """
    Parse and match against .gitignore patterns.
    
    Supports basic gitignore patterns:
    - Simple file/directory names
    - Wildcards (* and ?)
    - Directory-only patterns (ending with /)
    - Negation patterns (starting with !)
    - Comments (starting with #)
    """
    
    # Default patterns to always ignore (commonly large or unnecessary)
    DEFAULT_IGNORE = [
        '.git/',
        'node_modules/',
        '.git',
        'node_modules',
    ]
    
    def __init__(self, gitignore_path: Optional[str] = None):
        """
        Initialize the parser.
        
        Args:
            gitignore_path: Path to the .gitignore file
        """
        self.patterns: List[str] = []
        self.negation_patterns: List[str] = []
        
        # Add default ignore patterns
        self.patterns.extend(self.DEFAULT_IGNORE)
        
        # Parse gitignore file if provided
        if gitignore_path and os.path.isfile(gitignore_path):
            self._parse_file(gitignore_path)
    
    def _parse_file(self, filepath: str):
        """Parse a .gitignore file."""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    
                    # Skip empty lines and comments
                    if not line or line.startswith('#'):
                        continue
                    
                    # Handle negation patterns
                    if line.startswith('!'):
                        self.negation_patterns.append(line[1:])
                    else:
                        self.patterns.append(line)
        except Exception as e:
            print(f"Warning: Could not parse gitignore file: {e}")
    
    def _match_pattern(self, pattern: str, path: str, is_dir: bool) -> bool:
        """
        Check if a path matches a gitignore pattern.
        
        Args:
            pattern: The gitignore pattern
            path: The relative path to check
            is_dir: Whether the path is a directory
            
        Returns:
            True if the path matches the pattern
        """
        # Handle directory-only patterns
        if pattern.endswith('/'):
            if not is_dir:
                return False
            pattern = pattern[:-1]
        
        # Normalize path separators
        path = path.replace('\\', '/')
        pattern = pattern.replace('\\', '/')
        
        # Get the basename for simple patterns
        basename = os.path.basename(path)
        
        # Check if pattern contains path separator
        if '/' in pattern:
            # Match against full path
            if pattern.startswith('/'):
                # Anchored to root
                return fnmatch.fnmatch(path, pattern[1:])
            else:
                # Can match anywhere in path
                return fnmatch.fnmatch(path, pattern) or fnmatch.fnmatch(path, f"*/{pattern}")
        else:
            # Match against basename only
            return fnmatch.fnmatch(basename, pattern)
    
    def should_ignore(self, relative_path: str, is_dir: bool = False) -> bool:
        """
        Check if a path should be ignored.
        
        Args:
            relative_path: Path relative to the repository root
            is_dir: Whether the path is a directory
            
        Returns:
            True if the path should be ignored
        """
        # Check negation patterns first (they take precedence)
        for pattern in self.negation_patterns:
            if self._match_pattern(pattern, relative_path, is_dir):
                return False
        
        # Check ignore patterns
        for pattern in self.patterns:
            if self._match_pattern(pattern, relative_path, is_dir):
                return True
        
        return False


class WorkspaceCopier:
    """
    Copy a directory while respecting .gitignore rules.
    
    Features:
    - Parse and apply .gitignore patterns
    - Calculate total size before copying
    - Provide progress callbacks
    - Skip ignored files/directories
    """
    
    DEFAULT_SIZE_WARNING_MB = 100  # Warn if over 100MB
    
    def __init__(
        self,
        gitignore_path: Optional[str] = None,
        size_warning_mb: float = DEFAULT_SIZE_WARNING_MB
    ):
        """
        Initialize the copier.
        
        Args:
            gitignore_path: Path to the .gitignore file (uses project root by default)
            size_warning_mb: Size threshold for warnings in MB
        """
        if gitignore_path is None:
            # Use the project's .gitignore
            project_root = Path(__file__).parent
            gitignore_path = str(project_root / ".gitignore")
        
        self.parser = GitIgnoreParser(gitignore_path)
        self.size_warning_bytes = int(size_warning_mb * 1024 * 1024)
    
    def scan_files(
        self,
        file_paths: List[str],
        base_dir: str,
        progress_callback: Optional[Callable[[str], None]] = None
    ) -> ScanResult:
        """
        Scan a list of specific files and calculate what would be copied.
        
        Args:
            file_paths: List of absolute file paths to scan
            base_dir: Base directory for calculating relative paths
            progress_callback: Optional callback for progress updates
            
        Returns:
            ScanResult with details about files to copy
        """
        result = ScanResult()
        result.base_dir = base_dir
        base_path = Path(base_dir).resolve()
        
        for file_path in file_paths:
            abs_path = Path(file_path).resolve()
            
            if not abs_path.is_file():
                result.skipped_by_ignore += 1
                continue
            
            # Calculate relative path from base directory
            try:
                rel_path = str(abs_path.relative_to(base_path))
            except ValueError:
                # File is not under base_dir, use just the filename
                rel_path = abs_path.name
            
            # Check if file should be ignored
            if self.parser.should_ignore(rel_path, is_dir=False):
                result.skipped_by_ignore += 1
                continue
            
            try:
                file_size = os.path.getsize(abs_path)
                result.total_size_bytes += file_size
                result.total_files += 1
                result.files_to_copy.append(rel_path)
                
                if progress_callback:
                    progress_callback(f"Scanning: {rel_path}")
                    
            except OSError:
                result.skipped_by_ignore += 1
        
        return result
    
    def scan_directory(
        self,
        source_dir: str,
        progress_callback: Optional[Callable[[str], None]] = None
    ) -> ScanResult:
        """
        Scan a directory and calculate what would be copied.
        
        Args:
            source_dir: The source directory to scan
            progress_callback: Optional callback for progress updates
            
        Returns:
            ScanResult with details about files to copy
        """
        result = ScanResult()
        source_path = Path(source_dir).resolve()
        result.base_dir = str(source_path)
        
        if not source_path.is_dir():
            return result
        
        for root, dirs, files in os.walk(source_dir):
            # Calculate relative path from source
            rel_root = os.path.relpath(root, source_dir)
            if rel_root == '.':
                rel_root = ''
            
            # Filter directories (modify in place to skip ignored dirs)
            dirs_to_remove = []
            for d in dirs:
                rel_path = os.path.join(rel_root, d) if rel_root else d
                if self.parser.should_ignore(rel_path, is_dir=True):
                    dirs_to_remove.append(d)
                    result.skipped_by_ignore += 1
            
            for d in dirs_to_remove:
                dirs.remove(d)
            
            result.total_dirs += len(dirs)
            
            # Process files
            for f in files:
                rel_path = os.path.join(rel_root, f) if rel_root else f
                full_path = os.path.join(root, f)
                
                if self.parser.should_ignore(rel_path, is_dir=False):
                    result.skipped_by_ignore += 1
                    continue
                
                try:
                    file_size = os.path.getsize(full_path)
                    result.total_size_bytes += file_size
                    result.total_files += 1
                    result.files_to_copy.append(rel_path)
                    
                    if progress_callback:
                        progress_callback(f"Scanning: {rel_path}")
                        
                except OSError:
                    # Skip files we can't access
                    result.skipped_by_ignore += 1
        
        return result
    
    def copy_files(
        self,
        file_paths: List[str],
        base_dir: str,
        target_dir: str,
        progress_callback: Optional[Callable[[str, int, int], None]] = None
    ) -> CopyResult:
        """
        Copy a list of specific files to the target location.
        
        Args:
            file_paths: List of absolute file paths to copy
            base_dir: Base directory for calculating relative paths
            target_dir: The target directory (will be created if needed)
            progress_callback: Optional callback(current_file, current_count, total_count)
            
        Returns:
            CopyResult with details about the copy operation
        """
        result = CopyResult(success=False)
        
        base_path = Path(base_dir).resolve()
        target_path = Path(target_dir).resolve()
        
        try:
            # First, scan to get the list of files
            scan_result = self.scan_files(file_paths, base_dir)
            total_files = scan_result.total_files
            
            # Create target directory
            target_path.mkdir(parents=True, exist_ok=True)
            result.dirs_created = 1
            
            # Copy files
            for idx, rel_path in enumerate(scan_result.files_to_copy):
                src_file = base_path / rel_path
                dst_file = target_path / rel_path
                
                # Create parent directories
                dst_file.parent.mkdir(parents=True, exist_ok=True)
                
                # Copy file
                try:
                    shutil.copy2(src_file, dst_file)
                    result.files_copied += 1
                    result.total_size_bytes += os.path.getsize(src_file)
                    
                    if progress_callback:
                        progress_callback(rel_path, idx + 1, total_files)
                        
                except Exception as e:
                    print(f"Warning: Could not copy {rel_path}: {e}")
                    result.skipped_files += 1
            
            result.success = True
            
        except Exception as e:
            result.error = str(e)
            result.success = False
        
        return result
    
    def copy_directory(
        self,
        source_dir: str,
        target_dir: str,
        progress_callback: Optional[Callable[[str, int, int], None]] = None
    ) -> CopyResult:
        """
        Copy a directory to the target location.
        
        Args:
            source_dir: The source directory to copy
            target_dir: The target directory (will be created if needed)
            progress_callback: Optional callback(current_file, current_count, total_count)
            
        Returns:
            CopyResult with details about the copy operation
        """
        result = CopyResult(success=False)
        
        source_path = Path(source_dir).resolve()
        target_path = Path(target_dir).resolve()
        
        if not source_path.is_dir():
            result.error = f"Source directory does not exist: {source_dir}"
            return result
        
        try:
            # First, scan to get the list of files
            scan_result = self.scan_directory(source_dir)
            total_files = scan_result.total_files
            
            # Create target directory
            target_path.mkdir(parents=True, exist_ok=True)
            result.dirs_created = 1
            
            # Copy files
            for idx, rel_path in enumerate(scan_result.files_to_copy):
                src_file = source_path / rel_path
                dst_file = target_path / rel_path
                
                # Create parent directories
                dst_file.parent.mkdir(parents=True, exist_ok=True)
                
                # Copy file
                try:
                    shutil.copy2(src_file, dst_file)
                    result.files_copied += 1
                    result.total_size_bytes += os.path.getsize(src_file)
                    
                    if progress_callback:
                        progress_callback(rel_path, idx + 1, total_files)
                        
                except Exception as e:
                    print(f"Warning: Could not copy {rel_path}: {e}")
                    result.skipped_files += 1
            
            result.success = True
            
        except Exception as e:
            result.error = str(e)
            result.success = False
        
        return result
    
    def needs_size_warning(self, scan_result: ScanResult) -> bool:
        """Check if the scan result warrants a size warning."""
        return scan_result.total_size_bytes > self.size_warning_bytes
    
    def get_size_warning_message(self, scan_result: ScanResult) -> str:
        """Get a warning message about the directory size."""
        return (
            f"目录大小为 {scan_result.total_size_mb:.1f} MB "
            f"({scan_result.total_files} 个文件)，"
            f"超过了 {self.size_warning_bytes / (1024*1024):.0f} MB 的警告阈值。\n"
            f"复制可能需要一些时间，是否继续？"
        )


def copy_workspace(
    source_dir: str,
    target_dir: str,
    gitignore_path: Optional[str] = None,
    progress_callback: Optional[Callable[[str, int, int], None]] = None
) -> CopyResult:
    """
    Convenience function to copy a workspace.
    
    Args:
        source_dir: Source directory
        target_dir: Target directory
        gitignore_path: Path to .gitignore file
        progress_callback: Progress callback
        
    Returns:
        CopyResult
    """
    copier = WorkspaceCopier(gitignore_path)
    return copier.copy_directory(source_dir, target_dir, progress_callback)


if __name__ == "__main__":
    # Test the workspace copier
    import tempfile
    
    print("Testing GitIgnoreParser...")
    
    # Create a test gitignore
    with tempfile.NamedTemporaryFile(mode='w', suffix='.gitignore', delete=False) as f:
        f.write("# Test gitignore\n")
        f.write("*.pyc\n")
        f.write("__pycache__/\n")
        f.write(".env\n")
        f.write("node_modules/\n")
        gitignore_path = f.name
    
    try:
        parser = GitIgnoreParser(gitignore_path)
        
        # Test patterns
        tests = [
            ("test.pyc", False, True),
            ("test.py", False, False),
            ("__pycache__", True, True),
            ("src/__pycache__", True, True),
            (".env", False, True),
            (".env.example", False, False),
            ("node_modules", True, True),
            (".git", True, True),
        ]
        
        print("\nPattern matching tests:")
        for path, is_dir, expected in tests:
            result = parser.should_ignore(path, is_dir)
            status = "PASS" if result == expected else "FAIL"
            print(f"  [{status}] {path} (is_dir={is_dir}): {result} (expected {expected})")
        
    finally:
        os.unlink(gitignore_path)
    
    print("\nWorkspaceCopier test complete!")
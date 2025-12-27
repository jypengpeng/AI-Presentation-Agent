"""
Directory and File Picker Module

Provides cross-platform file and directory selection dialogs.
On Windows, uses PowerShell to show file browser dialogs.
On other platforms, falls back to tkinter.
"""

import os
import sys
import platform
import subprocess
import threading
from typing import Optional, List, Union, Tuple
from dataclasses import dataclass


@dataclass
class PickResult:
    """Result of a file/directory pick operation."""
    # Whether the user selected files or a directory
    is_files: bool
    # If is_files is True, this contains the list of selected file paths
    # If is_files is False, this contains a single directory path
    paths: List[str]
    # The common parent directory of all selected files (or the directory itself)
    base_dir: str
    
    @property
    def is_directory(self) -> bool:
        """Returns True if a directory was selected."""
        return not self.is_files
    
    @property
    def directory(self) -> Optional[str]:
        """Returns the directory path if a directory was selected."""
        if not self.is_files and self.paths:
            return self.paths[0]
        return None
    
    @property
    def files(self) -> List[str]:
        """Returns the list of file paths if files were selected."""
        if self.is_files:
            return self.paths
        return []
    
    @property
    def relative_files(self) -> List[str]:
        """Returns file paths relative to the base directory."""
        if self.is_files and self.base_dir:
            return [os.path.relpath(f, self.base_dir) for f in self.paths]
        return []


def pick_files_windows_powershell(
    title: str = "选择文件",
    initial_dir: Optional[str] = None,
    multiselect: bool = True
) -> Optional[List[str]]:
    """
    Open a Windows file selection dialog using PowerShell.
    
    Args:
        title: The title of the dialog window
        initial_dir: The initial directory to open
        multiselect: Whether to allow selecting multiple files
        
    Returns:
        List of selected file paths, or None if cancelled
    """
    try:
        # Escape the initial directory for PowerShell
        if initial_dir:
            init_dir_escaped = initial_dir.replace("'", "''").replace('"', '""')
        else:
            init_dir_escaped = os.path.expanduser("~").replace("'", "''").replace('"', '""')
        
        multiselect_str = "$true" if multiselect else "$false"
        
        # PowerShell script using OpenFileDialog
        ps_script = '''
Add-Type -AssemblyName System.Windows.Forms
[System.Windows.Forms.Application]::EnableVisualStyles()

$dialog = New-Object System.Windows.Forms.OpenFileDialog
$dialog.Title = "''' + title + '''"
$dialog.InitialDirectory = "''' + init_dir_escaped + '''"
$dialog.Multiselect = ''' + multiselect_str + '''
$dialog.CheckFileExists = $true
$dialog.CheckPathExists = $true

$result = $dialog.ShowDialog()
if ($result -eq [System.Windows.Forms.DialogResult]::OK) {
    # Output each selected file on a separate line
    foreach ($file in $dialog.FileNames) {
        Write-Output $file
    }
} else {
    Write-Output ""
}
'''
        
        # Run PowerShell with window creation flags
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
            capture_output=True,
            text=True,
            startupinfo=startupinfo
        )
        
        if result.returncode == 0 and result.stdout.strip():
            # Parse the output - each file is on a separate line
            files = [line.strip() for line in result.stdout.strip().split('\n') if line.strip()]
            # Verify all files exist
            valid_files = [f for f in files if os.path.isfile(f)]
            if valid_files:
                return valid_files
        
        return None
        
    except Exception as e:
        print(f"PowerShell file dialog error: {e}", file=sys.stderr)
        return None


def pick_files_or_directory_windows_powershell(
    title: str = "选择文件或目录",
    initial_dir: Optional[str] = None
) -> Optional[PickResult]:
    """
    Open a Windows file selection dialog that allows selecting files or a directory.
    
    If user selects actual files, returns those files.
    If user clicks "选择此文件夹" (the folder selection button), returns the directory.
    
    Args:
        title: The title of the dialog window
        initial_dir: The initial directory to open
        
    Returns:
        PickResult with selected files or directory, or None if cancelled
    """
    try:
        # Escape the initial directory for PowerShell
        if initial_dir:
            init_dir_escaped = initial_dir.replace("'", "''").replace('"', '""')
        else:
            init_dir_escaped = os.path.expanduser("~").replace("'", "''").replace('"', '""')
        
        # PowerShell script that returns both the selected files and directory info
        # Uses a special marker to distinguish between file selection and folder selection
        ps_script = '''
Add-Type -AssemblyName System.Windows.Forms
[System.Windows.Forms.Application]::EnableVisualStyles()

$dialog = New-Object System.Windows.Forms.OpenFileDialog
$dialog.Title = "''' + title + '''"
$dialog.InitialDirectory = "''' + init_dir_escaped + '''"
$dialog.Multiselect = $true
$dialog.ValidateNames = $false
$dialog.CheckFileExists = $false
$dialog.CheckPathExists = $true
$dialog.FileName = "选择此文件夹"

$result = $dialog.ShowDialog()
if ($result -eq [System.Windows.Forms.DialogResult]::OK) {
    $selectedPath = $dialog.FileName
    $directory = [System.IO.Path]::GetDirectoryName($selectedPath)
    $fileName = [System.IO.Path]::GetFileName($selectedPath)
    
    # Check if user clicked "选择此文件夹" or selected actual files
    if ($fileName -eq "选择此文件夹") {
        # User selected the folder
        Write-Output "DIR:$directory"
    } else {
        # User selected actual file(s)
        Write-Output "FILES:"
        foreach ($file in $dialog.FileNames) {
            if ([System.IO.File]::Exists($file)) {
                Write-Output $file
            }
        }
    }
} else {
    Write-Output ""
}
'''
        
        # Run PowerShell with window creation flags
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
            capture_output=True,
            text=True,
            startupinfo=startupinfo
        )
        
        if result.returncode == 0 and result.stdout.strip():
            lines = result.stdout.strip().split('\n')
            first_line = lines[0].strip()
            
            if first_line.startswith("DIR:"):
                # User selected a directory
                dir_path = first_line[4:].strip()
                if dir_path and os.path.isdir(dir_path):
                    return PickResult(
                        is_files=False,
                        paths=[os.path.normpath(dir_path)],
                        base_dir=os.path.normpath(dir_path)
                    )
            
            elif first_line == "FILES:":
                # User selected files
                files = [line.strip() for line in lines[1:] if line.strip() and os.path.isfile(line.strip())]
                if files:
                    # Calculate common base directory
                    normalized_files = [os.path.normpath(f) for f in files]
                    base_dir = os.path.dirname(normalized_files[0])
                    # If multiple files, find common parent
                    if len(normalized_files) > 1:
                        base_dir = os.path.commonpath(normalized_files)
                        # commonpath might return a file path if files are in same dir
                        if not os.path.isdir(base_dir):
                            base_dir = os.path.dirname(base_dir)
                    
                    return PickResult(
                        is_files=True,
                        paths=normalized_files,
                        base_dir=base_dir
                    )
        
        return None
        
    except Exception as e:
        print(f"PowerShell dialog error: {e}", file=sys.stderr)
        return None


def pick_directory_windows_powershell(title: str = "选择目录", initial_dir: Optional[str] = None) -> Optional[str]:
    """
    Open a Windows directory selection dialog using PowerShell.
    
    This uses OpenFileDialog which shows files, allowing users to see
    what's in each folder before selecting it.
    
    The trick: We set FileName to "选择此文件夹", and when user clicks Open,
    we get the directory path from the dialog.
    
    Args:
        title: The title of the dialog window
        initial_dir: The initial directory to open
        
    Returns:
        The selected directory path, or None if cancelled
    """
    try:
        # Escape the initial directory for PowerShell
        if initial_dir:
            init_dir_escaped = initial_dir.replace("'", "''").replace('"', '""')
        else:
            init_dir_escaped = os.path.expanduser("~").replace("'", "''").replace('"', '""')
        
        # PowerShell script using OpenFileDialog
        # User can see files in each folder, then click "Open" to select that folder
        ps_script = '''
Add-Type -AssemblyName System.Windows.Forms
[System.Windows.Forms.Application]::EnableVisualStyles()

$dialog = New-Object System.Windows.Forms.OpenFileDialog
$dialog.Title = "''' + title + '''"
$dialog.InitialDirectory = "''' + init_dir_escaped + '''"
$dialog.ValidateNames = $false
$dialog.CheckFileExists = $false
$dialog.CheckPathExists = $true
$dialog.FileName = "选择此文件夹"

$result = $dialog.ShowDialog()
if ($result -eq [System.Windows.Forms.DialogResult]::OK) {
    $selectedPath = [System.IO.Path]::GetDirectoryName($dialog.FileName)
    Write-Output $selectedPath
} else {
    Write-Output ""
}
'''
        
        # Run PowerShell with window creation flags
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
            capture_output=True,
            text=True,
            startupinfo=startupinfo
        )
        
        if result.returncode == 0 and result.stdout.strip():
            path = result.stdout.strip()
            if path and os.path.isdir(path):
                return os.path.normpath(path)
        
        return None
        
    except Exception as e:
        print(f"PowerShell dialog error: {e}", file=sys.stderr)
        return None


def pick_directory_tkinter(title: str = "选择目录", initial_dir: Optional[str] = None) -> Optional[str]:
    """
    Open a directory selection dialog using tkinter.
    
    Note: This dialog does not show files, only folders.
    
    Args:
        title: The title of the dialog window
        initial_dir: The initial directory to open
        
    Returns:
        The selected directory path, or None if cancelled
    """
    result: dict[str, Optional[str]] = {"path": None}
    
    def run_dialog():
        """Run the dialog in a way that works with Streamlit."""
        try:
            import tkinter as tk
            from tkinter import filedialog
            
            # Create a root window and hide it
            root = tk.Tk()
            root.withdraw()
            
            # Make sure the dialog appears on top
            root.attributes('-topmost', True)
            
            # Set initial directory
            if initial_dir and os.path.isdir(initial_dir):
                init_dir = initial_dir
            else:
                init_dir = os.path.expanduser("~")
            
            # Open the directory selection dialog
            selected = filedialog.askdirectory(
                title=title,
                initialdir=init_dir,
                mustexist=True
            )
            
            if selected:
                result["path"] = os.path.normpath(selected)
            
            # Clean up
            root.destroy()
            
        except Exception as e:
            print(f"Error in directory picker: {e}", file=sys.stderr)
            result["path"] = None
    
    # Run dialog - tkinter needs to be in the main thread on some systems
    if threading.current_thread() is threading.main_thread():
        run_dialog()
    else:
        dialog_thread = threading.Thread(target=run_dialog)
        dialog_thread.start()
        dialog_thread.join(timeout=300)
    
    return result["path"]


def pick_files_tkinter(
    title: str = "选择文件",
    initial_dir: Optional[str] = None,
    multiselect: bool = True
) -> Optional[List[str]]:
    """
    Open a file selection dialog using tkinter.
    
    Args:
        title: The title of the dialog window
        initial_dir: The initial directory to open
        multiselect: Whether to allow selecting multiple files
        
    Returns:
        List of selected file paths, or None if cancelled
    """
    result: dict[str, Optional[List[str]]] = {"files": None}
    
    def run_dialog():
        """Run the dialog in a way that works with Streamlit."""
        try:
            import tkinter as tk
            from tkinter import filedialog
            
            # Create a root window and hide it
            root = tk.Tk()
            root.withdraw()
            
            # Make sure the dialog appears on top
            root.attributes('-topmost', True)
            
            # Set initial directory
            if initial_dir and os.path.isdir(initial_dir):
                init_dir = initial_dir
            else:
                init_dir = os.path.expanduser("~")
            
            if multiselect:
                # Open multiple file selection dialog
                selected = filedialog.askopenfilenames(
                    title=title,
                    initialdir=init_dir
                )
                if selected:
                    result["files"] = [os.path.normpath(f) for f in selected]
            else:
                # Open single file selection dialog
                selected = filedialog.askopenfilename(
                    title=title,
                    initialdir=init_dir
                )
                if selected:
                    result["files"] = [os.path.normpath(selected)]
            
            # Clean up
            root.destroy()
            
        except Exception as e:
            print(f"Error in file picker: {e}", file=sys.stderr)
            result["files"] = None
    
    # Run dialog
    if threading.current_thread() is threading.main_thread():
        run_dialog()
    else:
        dialog_thread = threading.Thread(target=run_dialog)
        dialog_thread.start()
        dialog_thread.join(timeout=300)
    
    return result["files"]


def pick_directory(title: str = "选择目录", initial_dir: Optional[str] = None) -> Optional[str]:
    """
    Open a directory selection dialog and return the selected path.
    
    On Windows, tries to use IFileOpenDialog which shows files.
    Falls back to tkinter on other platforms or if COM fails.
    
    Args:
        title: The title of the dialog window
        initial_dir: The initial directory to open (defaults to user's home)
        
    Returns:
        The selected directory path, or None if cancelled
    """
    if initial_dir is None:
        initial_dir = os.path.expanduser("~")
    
    # Try Windows PowerShell dialog first (shows files)
    if platform.system() == "Windows":
        result = pick_directory_windows_powershell(title, initial_dir)
        if result is not None:
            return result
    
    # Fall back to tkinter
    return pick_directory_tkinter(title, initial_dir)


def pick_files_or_directory(
    title: str = "选择文件或目录",
    initial_dir: Optional[str] = None
) -> Optional[PickResult]:
    """
    Open a file/directory selection dialog.
    
    User can either:
    - Select one or more files (returns PickResult with is_files=True)
    - Click "选择此文件夹" to select the current directory (returns PickResult with is_files=False)
    
    On Windows, uses PowerShell for a unified dialog.
    On other platforms, falls back to tkinter directory selection.
    
    Args:
        title: The title of the dialog window
        initial_dir: The initial directory to open (defaults to user's home)
        
    Returns:
        PickResult with selected files or directory, or None if cancelled
    """
    if initial_dir is None:
        initial_dir = os.path.expanduser("~")
    
    # Try Windows PowerShell dialog first
    if platform.system() == "Windows":
        result = pick_files_or_directory_windows_powershell(title, initial_dir)
        if result is not None:
            return result
    
    # Fall back to tkinter directory selection
    # (tkinter doesn't have a combined file/directory picker)
    dir_path = pick_directory_tkinter(title, initial_dir)
    if dir_path:
        return PickResult(
            is_files=False,
            paths=[dir_path],
            base_dir=dir_path
        )
    
    return None


def pick_files(
    title: str = "选择文件",
    initial_dir: Optional[str] = None,
    multiselect: bool = True
) -> Optional[List[str]]:
    """
    Open a file selection dialog.
    
    Args:
        title: The title of the dialog window
        initial_dir: The initial directory to open (defaults to user's home)
        multiselect: Whether to allow selecting multiple files
        
    Returns:
        List of selected file paths, or None if cancelled
    """
    if initial_dir is None:
        initial_dir = os.path.expanduser("~")
    
    # Try Windows PowerShell dialog first
    if platform.system() == "Windows":
        result = pick_files_windows_powershell(title, initial_dir, multiselect)
        if result is not None:
            return result
    
    # Fall back to tkinter
    return pick_files_tkinter(title, initial_dir, multiselect)


def is_valid_directory(path: str) -> bool:
    """
    Check if the given path is a valid, accessible directory.
    
    Args:
        path: The path to check
        
    Returns:
        True if the path is a valid directory
    """
    if not path:
        return False
    
    try:
        return os.path.isdir(path) and os.access(path, os.R_OK)
    except Exception:
        return False


def get_directory_info(path: str) -> dict:
    """
    Get basic information about a directory.
    
    Args:
        path: The directory path
        
    Returns:
        Dictionary with directory information
    """
    if not is_valid_directory(path):
        return {
            "valid": False,
            "error": "Invalid or inaccessible directory"
        }
    
    try:
        # Count files and subdirectories (non-recursive, quick check)
        items = os.listdir(path)
        files = sum(1 for item in items if os.path.isfile(os.path.join(path, item)))
        dirs = sum(1 for item in items if os.path.isdir(os.path.join(path, item)))
        
        return {
            "valid": True,
            "path": os.path.normpath(path),
            "name": os.path.basename(path) or path,
            "files_count": files,
            "dirs_count": dirs,
            "total_items": len(items)
        }
    except Exception as e:
        return {
            "valid": False,
            "error": str(e)
        }


if __name__ == "__main__":
    # Test the file/directory picker
    print("Testing file/directory picker...")
    print("You can select files or click '选择此文件夹' to select the directory.\n")
    
    result = pick_files_or_directory("选择文件或目录")
    
    if result:
        if result.is_files:
            print(f"Selected {len(result.files)} file(s):")
            for f in result.files:
                print(f"  - {f}")
            print(f"\nBase directory: {result.base_dir}")
            print(f"Relative paths: {result.relative_files}")
        else:
            dir_path = result.directory
            print(f"Selected directory: {dir_path}")
            if dir_path:
                info = get_directory_info(dir_path)
                print(f"Info: {info}")
    else:
        print("Selection cancelled")
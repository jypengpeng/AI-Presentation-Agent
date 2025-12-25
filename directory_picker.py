"""
Directory Picker Module

Provides a cross-platform directory selection dialog.
On Windows, uses PowerShell to show a folder browser that displays files.
On other platforms, falls back to tkinter.
"""

import os
import sys
import platform
import subprocess
import threading
from typing import Optional


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
    # Test the directory picker
    print("Testing directory picker...")
    
    selected = pick_directory("Select a test directory")
    
    if selected:
        print(f"Selected: {selected}")
        info = get_directory_info(selected)
        print(f"Info: {info}")
    else:
        print("Selection cancelled")
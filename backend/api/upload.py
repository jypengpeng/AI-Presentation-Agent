"""File upload API routes.

This module provides endpoints for uploading files and directories
while preserving the original tree structure.

Features:
- Single file upload
- Multiple file upload with directory structure
- Directory upload (files with relative paths)
"""

import os
import shutil
import logging
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Depends
from pydantic import BaseModel

from state.task_manager import TaskManager
from api.tasks import get_task_manager


# Configure logging
logger = logging.getLogger(__name__)


router = APIRouter(prefix="/upload", tags=["upload"])


class UploadResult(BaseModel):
    """Response model for upload results."""
    success: bool
    task_id: str
    files_uploaded: int
    total_size_bytes: int
    message: str


class FileInfo(BaseModel):
    """Information about an uploaded file."""
    path: str
    size: int


class UploadSummary(BaseModel):
    """Summary of uploaded files for a task."""
    task_id: str
    total_files: int
    total_size_bytes: int
    files: List[FileInfo]


def sanitize_path(path: str) -> str:
    """
    Sanitize a file path to prevent directory traversal attacks.
    
    Args:
        path: The relative file path
        
    Returns:
        Sanitized path
    """
    # Normalize the path
    path = path.replace("\\", "/")
    
    # Remove leading slashes and dots
    while path.startswith("/") or path.startswith("./"):
        path = path.lstrip("/").lstrip("./")
    
    # Remove any ".." components
    parts = path.split("/")
    safe_parts = [p for p in parts if p and p != ".."]
    
    return "/".join(safe_parts)


def get_workspace_path(task_id: str, manager: TaskManager) -> Path:
    """
    Get the workspace path for a task.
    
    Args:
        task_id: The task ID
        manager: TaskManager instance
        
    Returns:
        Path to the task's workspace directory
        
    Raises:
        HTTPException: If task not found
    """
    task = manager.get_task(task_id)
    if not task:
        logger.error(f"[Upload] Task not found: {task_id}")
        raise HTTPException(status_code=404, detail="Task not found")
    
    workspace = manager.get_workspace_path(task_id)
    logger.info(f"[Upload] Task {task_id} workspace path: {workspace} (resolved: {workspace.resolve()})")
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


@router.post("/{task_id}/files", response_model=UploadResult)
async def upload_files(
    task_id: str,
    files: List[UploadFile] = File(...),
    paths: Optional[str] = Form(None),
    manager: TaskManager = Depends(get_task_manager)
) -> UploadResult:
    """
    Upload multiple files to a task's workspace.
    
    This endpoint supports:
    - Simple file uploads (files will be placed in workspace root)
    - Structured uploads with relative paths (preserves directory structure)
    
    Args:
        task_id: Target task ID
        files: List of files to upload
        paths: Optional JSON array of relative paths corresponding to each file
               If provided, files will be placed at these relative paths
               Format: '["dir1/file1.txt", "dir2/subdir/file2.txt"]'
        
    Returns:
        UploadResult with upload statistics
    """
    import json
    
    logger.info(f"[Upload] Starting upload for task {task_id}, {len(files)} files")
    logger.info(f"[Upload] Paths parameter: {paths}")
    
    workspace = get_workspace_path(task_id, manager)
    logger.info(f"[Upload] Using workspace: {workspace}")
    
    # Parse relative paths if provided
    relative_paths: List[str] = []
    if paths:
        try:
            parsed_paths = json.loads(paths)
            if not isinstance(parsed_paths, list):
                raise HTTPException(
                    status_code=400,
                    detail="Paths must be a JSON array"
                )
            relative_paths = parsed_paths
            if len(relative_paths) != len(files):
                raise HTTPException(
                    status_code=400,
                    detail=f"Number of paths ({len(relative_paths)}) must match number of files ({len(files)})"
                )
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=400,
                detail="Invalid JSON format for paths parameter"
            )
    
    total_size = 0
    files_uploaded = 0
    
    for i, file in enumerate(files):
        try:
            # Determine target path
            if relative_paths and i < len(relative_paths):
                # Use provided relative path
                rel_path = sanitize_path(relative_paths[i])
            else:
                # Use original filename
                rel_path = sanitize_path(file.filename or f"file_{i}")
            
            target_path = workspace / rel_path
            logger.info(f"[Upload] File {i}: {file.filename} -> {target_path}")
            
            # Create parent directories if needed
            target_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Write file content
            content = await file.read()
            target_path.write_bytes(content)
            
            total_size += len(content)
            files_uploaded += 1
            logger.info(f"[Upload] Successfully wrote {len(content)} bytes to {target_path}")
            
        except Exception as e:
            # Continue with other files even if one fails
            logger.error(f"[Upload] Error uploading file {file.filename}: {e}")
            continue
    
    logger.info(f"[Upload] Complete: {files_uploaded} files, {total_size} bytes to workspace {workspace}")
    
    # List files in workspace for debugging
    if workspace.exists():
        all_files = list(workspace.rglob("*"))
        logger.info(f"[Upload] Files in workspace after upload: {len(all_files)}")
        for f in all_files[:20]:  # Limit to first 20 files
            logger.info(f"[Upload]   - {f.relative_to(workspace)}")
    
    return UploadResult(
        success=files_uploaded > 0,
        task_id=task_id,
        files_uploaded=files_uploaded,
        total_size_bytes=total_size,
        message=f"Successfully uploaded {files_uploaded} file(s)"
    )


@router.post("/{task_id}/directory", response_model=UploadResult)
async def upload_directory(
    task_id: str,
    files: List[UploadFile] = File(...),
    base_path: str = Form(""),
    manager: TaskManager = Depends(get_task_manager)
) -> UploadResult:
    """
    Upload files as a directory structure.
    
    Each file should have its webkitRelativePath set (from directory input).
    The frontend should pass the relative paths in the file's filename field.
    
    Args:
        task_id: Target task ID
        files: List of files from directory selection
        base_path: Optional base path to prepend to all files
        
    Returns:
        UploadResult with upload statistics
    """
    workspace = get_workspace_path(task_id, manager)
    
    # Add base path if provided
    base = sanitize_path(base_path) if base_path else ""
    
    total_size = 0
    files_uploaded = 0
    
    for file in files:
        try:
            # The filename should contain the relative path from frontend
            filename = file.filename or ""
            
            # Sanitize and combine with base path
            rel_path = sanitize_path(filename)
            if base:
                rel_path = f"{base}/{rel_path}"
            
            if not rel_path:
                continue
            
            target_path = workspace / rel_path
            
            # Create parent directories if needed
            target_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Write file content
            content = await file.read()
            target_path.write_bytes(content)
            
            total_size += len(content)
            files_uploaded += 1
            
        except Exception as e:
            print(f"Error uploading file {file.filename}: {e}")
            continue
    
    return UploadResult(
        success=files_uploaded > 0,
        task_id=task_id,
        files_uploaded=files_uploaded,
        total_size_bytes=total_size,
        message=f"Successfully uploaded {files_uploaded} file(s) with directory structure"
    )


@router.get("/{task_id}/files", response_model=UploadSummary)
async def list_uploaded_files(
    task_id: str,
    manager: TaskManager = Depends(get_task_manager)
) -> UploadSummary:
    """
    List all files in a task's workspace.
    
    Args:
        task_id: Task ID
        
    Returns:
        UploadSummary with file list and statistics
    """
    workspace = get_workspace_path(task_id, manager)
    
    files: List[FileInfo] = []
    total_size = 0
    
    if workspace.exists():
        for file_path in workspace.rglob("*"):
            if file_path.is_file():
                rel_path = file_path.relative_to(workspace)
                size = file_path.stat().st_size
                files.append(FileInfo(
                    path=str(rel_path).replace("\\", "/"),
                    size=size
                ))
                total_size += size
    
    return UploadSummary(
        task_id=task_id,
        total_files=len(files),
        total_size_bytes=total_size,
        files=files
    )


@router.delete("/{task_id}/files")
async def clear_workspace(
    task_id: str,
    manager: TaskManager = Depends(get_task_manager)
) -> dict:
    """
    Clear all files in a task's workspace.
    
    Args:
        task_id: Task ID
        
    Returns:
        Success message
    """
    workspace = get_workspace_path(task_id, manager)
    
    if workspace.exists():
        # Clear contents but keep the directory
        for item in workspace.iterdir():
            if item.is_file():
                item.unlink()
            elif item.is_dir():
                shutil.rmtree(item)
    
    return {"message": f"Workspace for task {task_id} cleared"}


@router.delete("/{task_id}/files/{file_path:path}")
async def delete_file(
    task_id: str,
    file_path: str,
    manager: TaskManager = Depends(get_task_manager)
) -> dict:
    """
    Delete a specific file from the workspace.
    
    Args:
        task_id: Task ID
        file_path: Relative path to the file
        
    Returns:
        Success message
    """
    workspace = get_workspace_path(task_id, manager)
    
    # Sanitize path
    safe_path = sanitize_path(file_path)
    target = workspace / safe_path
    
    # Ensure the target is within workspace
    try:
        target.resolve().relative_to(workspace.resolve())
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid file path")
    
    if not target.exists():
        raise HTTPException(status_code=404, detail="File not found")
    
    if target.is_file():
        target.unlink()
    elif target.is_dir():
        shutil.rmtree(target)
    
    return {"message": f"Deleted {file_path}"}
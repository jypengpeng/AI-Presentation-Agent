"""Task management API routes.

This module provides REST endpoints for task management:
- Create, read, update, delete tasks
- Task listing and filtering
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from state.task_manager import TaskManager, TaskState, TaskStatus
from workflow.phase_manager import Phase


router = APIRouter(prefix="/tasks", tags=["tasks"])

# Dependency for TaskManager
_task_manager: Optional[TaskManager] = None


def get_task_manager() -> TaskManager:
    """Get or create task manager instance."""
    global _task_manager
    if _task_manager is None:
        _task_manager = TaskManager()
    return _task_manager


# Request/Response models
class TaskCreate(BaseModel):
    """Request model for creating a task."""
    name: str
    metadata: Optional[Dict[str, Any]] = None


class TaskUpdate(BaseModel):
    """Request model for updating a task."""
    name: Optional[str] = None
    status: Optional[str] = None
    phase: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class TaskResponse(BaseModel):
    """Response model for task data."""
    id: str
    name: str
    status: str
    phase: str
    created_at: str
    updated_at: str
    metadata: Dict[str, Any]
    slide_count: int
    completed_slides: int

    class Config:
        from_attributes = True


class TaskListResponse(BaseModel):
    """Response model for task list."""
    tasks: List[TaskResponse]
    total: int


# Endpoints
@router.post("", response_model=TaskResponse)
async def create_task(
    task_data: TaskCreate,
    manager: TaskManager = Depends(get_task_manager)
) -> Dict[str, Any]:
    """Create a new task."""
    task = manager.create_task(
        name=task_data.name,
        metadata=task_data.metadata
    )
    return task.to_dict()


@router.get("", response_model=TaskListResponse)
async def list_tasks(
    status: Optional[str] = None,
    phase: Optional[str] = None,
    manager: TaskManager = Depends(get_task_manager)
) -> Dict[str, Any]:
    """List all tasks with optional filtering."""
    task_status = TaskStatus(status) if status else None
    task_phase = Phase(phase) if phase else None
    
    tasks = manager.get_all_tasks(status=task_status, phase=task_phase)
    
    return {
        "tasks": [t.to_dict() for t in tasks],
        "total": len(tasks)
    }


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: str,
    manager: TaskManager = Depends(get_task_manager)
) -> Dict[str, Any]:
    """Get a task by ID."""
    task = manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task.to_dict()


@router.get("/{task_id}/summary")
async def get_task_summary(
    task_id: str,
    manager: TaskManager = Depends(get_task_manager)
) -> Dict[str, Any]:
    """Get task summary including file counts."""
    summary = manager.get_task_summary(task_id)
    if not summary:
        raise HTTPException(status_code=404, detail="Task not found")
    return summary


@router.patch("/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: str,
    task_data: TaskUpdate,
    manager: TaskManager = Depends(get_task_manager)
) -> Dict[str, Any]:
    """Update a task."""
    update_fields = {}
    
    if task_data.name is not None:
        update_fields["name"] = task_data.name
    
    if task_data.status is not None:
        update_fields["status"] = TaskStatus(task_data.status)
    
    if task_data.phase is not None:
        update_fields["phase"] = Phase(task_data.phase)
    
    if task_data.metadata is not None:
        update_fields["metadata"] = task_data.metadata
    
    task = manager.update_task(task_id, **update_fields)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return task.to_dict()


@router.delete("/{task_id}")
async def delete_task(
    task_id: str,
    delete_files: bool = True,
    manager: TaskManager = Depends(get_task_manager)
) -> Dict[str, str]:
    """Delete a task."""
    success = manager.delete_task(task_id, delete_files=delete_files)
    if not success:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return {"message": f"Task {task_id} deleted successfully"}


@router.post("/{task_id}/archive")
async def archive_task(
    task_id: str,
    manager: TaskManager = Depends(get_task_manager)
) -> Dict[str, Any]:
    """Archive a task."""
    task = manager.archive_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return task.to_dict()


@router.post("/{task_id}/transition")
async def transition_phase(
    task_id: str,
    target_phase: str,
    manager: TaskManager = Depends(get_task_manager)
) -> Dict[str, Any]:
    """Transition task to a new phase."""
    try:
        phase = Phase(target_phase)
    except ValueError:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid phase: {target_phase}"
        )
    
    task = manager.update_task(task_id, phase=phase)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return task.to_dict()
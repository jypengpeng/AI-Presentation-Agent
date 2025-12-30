"""Task lifecycle management.

This module provides:
- TaskState: Dataclass representing task state
- TaskStatus: Enum for task status
- TaskManager: Manages task creation, loading, and persistence
"""

import json
import os
import shutil
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import Settings, get_settings
from workflow.phase_manager import Phase


class TaskStatus(Enum):
    """Status of a task."""
    ACTIVE = "active"
    COMPLETED = "completed"
    ARCHIVED = "archived"
    FAILED = "failed"


@dataclass
class TaskState:
    """Represents the state of a presentation task.
    
    Attributes:
        id: Unique task identifier
        name: Task name/title
        status: Current task status
        phase: Current workflow phase
        created_at: Creation timestamp
        updated_at: Last update timestamp
        metadata: Additional task metadata
        slide_count: Number of slides
        completed_slides: Number of completed slides
    """
    id: str
    name: str
    status: TaskStatus = TaskStatus.ACTIVE
    phase: Phase = Phase.COLLECTING
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    slide_count: int = 0
    completed_slides: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "name": self.name,
            "status": self.status.value,
            "phase": self.phase.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "metadata": self.metadata,
            "slide_count": self.slide_count,
            "completed_slides": self.completed_slides,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskState":
        """Create from dictionary."""
        return cls(
            id=data["id"],
            name=data["name"],
            status=TaskStatus(data["status"]),
            phase=Phase(data["phase"]),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            metadata=data.get("metadata", {}),
            slide_count=data.get("slide_count", 0),
            completed_slides=data.get("completed_slides", 0),
        )
    
    def update(self, **kwargs) -> None:
        """Update task state."""
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
        self.updated_at = datetime.now()


class TaskManager:
    """Manages task lifecycle and persistence.
    
    Provides:
    - Task creation and deletion
    - Task state loading and saving
    - Task listing and querying
    - Workspace directory management
    """
    
    def __init__(self, settings: Optional[Settings] = None):
        """Initialize task manager.
        
        Args:
            settings: Application settings
        """
        self.settings = settings or get_settings()
        self.base_path = self.settings.workspace_base
        self.base_path.mkdir(parents=True, exist_ok=True)
        
        self._tasks: Dict[str, TaskState] = {}
        self._load_all_tasks()
    
    def _load_all_tasks(self) -> None:
        """Load all existing tasks from disk."""
        if not self.base_path.exists():
            return
        
        for task_dir in self.base_path.iterdir():
            if task_dir.is_dir() and task_dir.name.startswith("task_"):
                state_file = task_dir / "task_state.json"
                if state_file.exists():
                    try:
                        data = json.loads(state_file.read_text(encoding="utf-8"))
                        task = TaskState.from_dict(data)
                        self._tasks[task.id] = task
                    except (json.JSONDecodeError, KeyError):
                        continue
    
    def create_task(
        self,
        name: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> TaskState:
        """Create a new task.
        
        Args:
            name: Task name
            metadata: Additional metadata
            
        Returns:
            Created task state
        """
        task_id = uuid.uuid4().hex[:8]
        
        task = TaskState(
            id=task_id,
            name=name,
            metadata=metadata or {}
        )
        
        # Create task directory structure
        task_path = self._get_task_path(task_id)
        workspace_path = task_path / "workspace"
        slides_path = workspace_path / "slides"
        
        task_path.mkdir(parents=True, exist_ok=True)
        workspace_path.mkdir(exist_ok=True)
        slides_path.mkdir(exist_ok=True)
        
        # Save task state
        self._tasks[task_id] = task
        self._save_task(task)
        
        return task
    
    def get_task(self, task_id: str) -> Optional[TaskState]:
        """Get a task by ID."""
        return self._tasks.get(task_id)
    
    def get_all_tasks(
        self,
        status: Optional[TaskStatus] = None,
        phase: Optional[Phase] = None
    ) -> List[TaskState]:
        """Get all tasks, optionally filtered.
        
        Args:
            status: Filter by status
            phase: Filter by phase
            
        Returns:
            List of matching tasks
        """
        tasks = list(self._tasks.values())
        
        if status:
            tasks = [t for t in tasks if t.status == status]
        
        if phase:
            tasks = [t for t in tasks if t.phase == phase]
        
        # Sort by updated_at descending
        tasks.sort(key=lambda t: t.updated_at, reverse=True)
        
        return tasks
    
    def update_task(
        self,
        task_id: str,
        **kwargs
    ) -> Optional[TaskState]:
        """Update a task's state.
        
        Args:
            task_id: Task ID
            **kwargs: Fields to update
            
        Returns:
            Updated task state, or None if not found
        """
        task = self._tasks.get(task_id)
        if not task:
            return None
        
        task.update(**kwargs)
        self._save_task(task)
        
        return task
    
    def delete_task(self, task_id: str, delete_files: bool = True) -> bool:
        """Delete a task.
        
        Args:
            task_id: Task ID
            delete_files: Also delete task files
            
        Returns:
            True if deleted, False if not found
        """
        if task_id not in self._tasks:
            return False
        
        del self._tasks[task_id]
        
        if delete_files:
            task_path = self._get_task_path(task_id)
            if task_path.exists():
                shutil.rmtree(task_path)
        
        return True
    
    def archive_task(self, task_id: str) -> Optional[TaskState]:
        """Archive a task."""
        return self.update_task(task_id, status=TaskStatus.ARCHIVED)
    
    def get_workspace_path(self, task_id: str) -> Path:
        """Get workspace path for a task."""
        return self._get_task_path(task_id) / "workspace"
    
    def get_slides_path(self, task_id: str) -> Path:
        """Get slides path for a task."""
        return self.get_workspace_path(task_id) / "slides"
    
    def _get_task_path(self, task_id: str) -> Path:
        """Get task directory path."""
        return self.base_path / f"task_{task_id}"
    
    def _save_task(self, task: TaskState) -> None:
        """Save task state to disk."""
        task_path = self._get_task_path(task.id)
        task_path.mkdir(parents=True, exist_ok=True)
        
        state_file = task_path / "task_state.json"
        state_file.write_text(
            json.dumps(task.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
    
    def get_task_summary(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get a summary of a task including file counts."""
        task = self._tasks.get(task_id)
        if not task:
            return None
        
        workspace = self.get_workspace_path(task_id)
        slides_path = self.get_slides_path(task_id)
        
        summary = task.to_dict()
        summary["files"] = {
            "html_slides": len(list(slides_path.glob("slide_*.html"))) if slides_path.exists() else 0,
            "has_pptx": any(workspace.glob("*.pptx")) if workspace.exists() else False,
            "has_speech": (workspace / "speech").exists(),
        }
        
        return summary
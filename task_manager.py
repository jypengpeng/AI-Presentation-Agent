"""
Task Manager Module

This module manages multiple tasks for the AI Presentation Agent.
Each task has its own workspace, settings, and conversation history.
"""

import os
import json
import uuid
import shutil
from pathlib import Path
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any, Callable


@dataclass
class Task:
    """Represents a single task with its configuration and history."""
    
    id: str
    name: str
    workspace_dir: str
    source_dir: str = ""  # Original directory selected by user
    html_file: str = "index.html"
    custom_prompt: str = ""
    chat_history: List[Dict[str, Any]] = field(default_factory=list)
    selected_slide: int = 0
    created_at: str = ""
    updated_at: str = ""
    last_sync_at: str = ""  # Last time workspace was synced from source
    
    def __post_init__(self):
        """Initialize timestamps if not provided."""
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = now
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert task to dictionary for JSON serialization."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Task":
        """Create a Task from a dictionary."""
        return cls(**data)
    
    def touch(self):
        """Update the updated_at timestamp."""
        self.updated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class TaskManager:
    """
    Manages multiple tasks with persistence to JSON file.
    
    Features:
    - Create, update, delete tasks
    - Switch between tasks
    - Persist tasks to JSON file
    - Auto-generate task names from workspace directory
    """
    
    DEFAULT_STORAGE_DIR = "tasks"
    DEFAULT_STORAGE_FILE = "tasks.json"
    
    def __init__(self, storage_path: Optional[str] = None):
        """
        Initialize the TaskManager.
        
        Args:
            storage_path: Path to the JSON file for storing tasks.
                         Defaults to "tasks/tasks.json"
        """
        if storage_path:
            self.storage_path = Path(storage_path)
        else:
            self.storage_path = Path(self.DEFAULT_STORAGE_DIR) / self.DEFAULT_STORAGE_FILE
        
        self.tasks: Dict[str, Task] = {}
        self.active_task_id: Optional[str] = None
        
        # Load existing tasks
        self.load()
    
    def _ensure_storage_dir(self):
        """Ensure the storage directory exists."""
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
    
    def _generate_task_id(self) -> str:
        """Generate a unique task ID."""
        return f"task_{uuid.uuid4().hex[:8]}"
    
    def _generate_task_name(self, workspace_dir: str) -> str:
        """
        Generate a task name from the workspace directory.
        
        Uses the directory name as the base, with a counter if needed.
        """
        base_name = Path(workspace_dir).name
        if not base_name:
            base_name = "新任务"
        
        # Check for duplicate names
        existing_names = {task.name for task in self.tasks.values()}
        
        if base_name not in existing_names:
            return base_name
        
        # Add counter
        counter = 1
        while f"{base_name} ({counter})" in existing_names:
            counter += 1
        
        return f"{base_name} ({counter})"
    
    def load(self) -> bool:
        """
        Load tasks from the JSON file.
        
        Returns:
            True if tasks were loaded successfully, False otherwise
        """
        if not self.storage_path.exists():
            return False
        
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            self.active_task_id = data.get("active_task_id")
            
            tasks_data = data.get("tasks", {})
            self.tasks = {}
            for task_id, task_data in tasks_data.items():
                try:
                    self.tasks[task_id] = Task.from_dict(task_data)
                except Exception as e:
                    print(f"Warning: Failed to load task {task_id}: {e}")
            
            # Validate active_task_id
            if self.active_task_id and self.active_task_id not in self.tasks:
                self.active_task_id = None
            
            return True
        
        except Exception as e:
            print(f"Warning: Failed to load tasks: {e}")
            return False
    
    def save(self) -> bool:
        """
        Save tasks to the JSON file.
        
        Returns:
            True if tasks were saved successfully, False otherwise
        """
        self._ensure_storage_dir()
        
        try:
            data = {
                "active_task_id": self.active_task_id,
                "tasks": {
                    task_id: task.to_dict()
                    for task_id, task in self.tasks.items()
                }
            }
            
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            return True
        
        except Exception as e:
            print(f"Error: Failed to save tasks: {e}")
            return False
    
    def _get_task_workspace_dir(self, task_id: str) -> str:
        """
        Get the workspace directory path for a task.
        
        Args:
            task_id: The task ID
            
        Returns:
            Path to the task's workspace directory
        """
        return str(Path(self.DEFAULT_STORAGE_DIR) / task_id / "workspace")
    
    def create_task(
        self,
        source_dir: str,
        name: Optional[str] = None,
        html_file: str = "index.html",
        custom_prompt: str = ""
    ) -> Task:
        """
        Create a new task with a copied workspace.
        
        Args:
            source_dir: The source directory to copy from
            name: Task name (auto-generated if not provided)
            html_file: Path to the HTML file (relative to workspace)
            custom_prompt: Custom prompt to append to system prompt
            
        Returns:
            The newly created Task
        """
        task_id = self._generate_task_id()
        workspace_dir = self._get_task_workspace_dir(task_id)
        
        if name is None:
            name = self._generate_task_name(source_dir)
        
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        
        task = Task(
            id=task_id,
            name=name,
            workspace_dir=workspace_dir,
            source_dir=source_dir,
            html_file=html_file,
            custom_prompt=custom_prompt,
            last_sync_at=now
        )
        
        self.tasks[task_id] = task
        self.active_task_id = task_id
        self.save()
        
        return task
    
    def create_task_legacy(
        self,
        workspace_dir: str,
        name: Optional[str] = None,
        html_file: str = "index.html",
        custom_prompt: str = ""
    ) -> Task:
        """
        Create a new task with direct workspace path (legacy mode, no copying).
        
        Args:
            workspace_dir: The working directory for the task
            name: Task name (auto-generated if not provided)
            html_file: Path to the HTML file (relative to workspace)
            custom_prompt: Custom prompt to append to system prompt
            
        Returns:
            The newly created Task
        """
        task_id = self._generate_task_id()
        
        if name is None:
            name = self._generate_task_name(workspace_dir)
        
        task = Task(
            id=task_id,
            name=name,
            workspace_dir=workspace_dir,
            source_dir="",  # No source dir in legacy mode
            html_file=html_file,
            custom_prompt=custom_prompt
        )
        
        self.tasks[task_id] = task
        self.active_task_id = task_id
        self.save()
        
        return task
    
    def get_task(self, task_id: str) -> Optional[Task]:
        """
        Get a task by ID.
        
        Args:
            task_id: The task ID
            
        Returns:
            The Task if found, None otherwise
        """
        return self.tasks.get(task_id)
    
    def get_active_task(self) -> Optional[Task]:
        """
        Get the currently active task.
        
        Returns:
            The active Task if one is set, None otherwise
        """
        if self.active_task_id:
            return self.tasks.get(self.active_task_id)
        return None
    
    def switch_task(self, task_id: str) -> Optional[Task]:
        """
        Switch to a different task.
        
        Args:
            task_id: The ID of the task to switch to
            
        Returns:
            The Task if switch was successful, None otherwise
        """
        if task_id not in self.tasks:
            return None
        
        self.active_task_id = task_id
        self.save()
        
        return self.tasks[task_id]
    
    def update_task(
        self,
        task_id: str,
        **kwargs
    ) -> Optional[Task]:
        """
        Update a task's properties.
        
        Args:
            task_id: The ID of the task to update
            **kwargs: Properties to update (name, workspace_dir, html_file, 
                     custom_prompt, chat_history, selected_slide)
                     
        Returns:
            The updated Task if successful, None otherwise
        """
        task = self.tasks.get(task_id)
        if not task:
            return None
        
        # Update allowed fields
        allowed_fields = {
            "name", "workspace_dir", "html_file", "custom_prompt",
            "chat_history", "selected_slide"
        }
        
        for key, value in kwargs.items():
            if key in allowed_fields:
                setattr(task, key, value)
        
        task.touch()
        self.save()
        
        return task
    
    def delete_task(self, task_id: str, delete_workspace: bool = True) -> bool:
        """
        Delete a task and optionally its workspace directory.
        
        Args:
            task_id: The ID of the task to delete
            delete_workspace: Whether to delete the workspace directory (default True)
            
        Returns:
            True if the task was deleted, False otherwise
        """
        if task_id not in self.tasks:
            return False
        
        task = self.tasks[task_id]
        
        # Delete the workspace directory if requested
        if delete_workspace:
            # Get the task directory (parent of workspace)
            task_dir = Path(self.DEFAULT_STORAGE_DIR) / task_id
            if task_dir.exists():
                try:
                    shutil.rmtree(task_dir)
                except Exception as e:
                    print(f"Warning: Failed to delete task directory {task_dir}: {e}")
        
        del self.tasks[task_id]
        
        # If the deleted task was active, clear or switch
        if self.active_task_id == task_id:
            if self.tasks:
                # Switch to the most recently updated task
                sorted_tasks = sorted(
                    self.tasks.values(),
                    key=lambda t: t.updated_at,
                    reverse=True
                )
                self.active_task_id = sorted_tasks[0].id
            else:
                self.active_task_id = None
        
        self.save()
        return True
    
    def list_tasks(self, sort_by: str = "updated_at", reverse: bool = True) -> List[Task]:
        """
        List all tasks, sorted by the specified field.
        
        Args:
            sort_by: Field to sort by (created_at, updated_at, name)
            reverse: Whether to reverse the sort order
            
        Returns:
            List of Tasks
        """
        tasks = list(self.tasks.values())
        
        if sort_by == "name":
            tasks.sort(key=lambda t: t.name.lower(), reverse=reverse)
        elif sort_by == "created_at":
            tasks.sort(key=lambda t: t.created_at, reverse=reverse)
        else:  # updated_at
            tasks.sort(key=lambda t: t.updated_at, reverse=reverse)
        
        return tasks
    
    def add_chat_message(self, task_id: str, message: Dict[str, Any]) -> bool:
        """
        Add a chat message to a task's history.
        
        Args:
            task_id: The ID of the task
            message: The chat message to add
            
        Returns:
            True if successful, False otherwise
        """
        task = self.tasks.get(task_id)
        if not task:
            return False
        
        # Add timestamp if not present
        if "timestamp" not in message:
            message["timestamp"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        
        task.chat_history.append(message)
        task.touch()
        self.save()
        
        return True
    
    def clear_chat_history(self, task_id: str) -> bool:
        """
        Clear the chat history of a task.
        
        Args:
            task_id: The ID of the task
            
        Returns:
            True if successful, False otherwise
        """
        task = self.tasks.get(task_id)
        if not task:
            return False
        
        task.chat_history = []
        task.touch()
        self.save()
        
        return True
    
    def update_sync_time(self, task_id: str) -> bool:
        """
        Update the last sync time for a task.
        
        Args:
            task_id: The ID of the task
            
        Returns:
            True if successful, False otherwise
        """
        task = self.tasks.get(task_id)
        if not task:
            return False
        
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        task.last_sync_at = now
        task.touch()
        self.save()
        
        return True
    
    def can_sync(self, task_id: str) -> bool:
        """
        Check if a task can be synced (has a valid source directory).
        
        Args:
            task_id: The ID of the task
            
        Returns:
            True if the task can be synced
        """
        task = self.tasks.get(task_id)
        if not task or not task.source_dir:
            return False
        
        return os.path.isdir(task.source_dir)
    
    def has_tasks(self) -> bool:
        """Check if there are any tasks."""
        return len(self.tasks) > 0
    
    def count_tasks(self) -> int:
        """Get the number of tasks."""
        return len(self.tasks)


# Convenience function for creating a task manager
def create_task_manager(storage_path: Optional[str] = None) -> TaskManager:
    """
    Create and return a TaskManager instance.
    
    Args:
        storage_path: Optional path to the JSON storage file
        
    Returns:
        TaskManager instance
    """
    return TaskManager(storage_path)


if __name__ == "__main__":
    # Simple test
    import tempfile
    
    with tempfile.TemporaryDirectory() as tmpdir:
        storage_path = os.path.join(tmpdir, "tasks.json")
        
        # Create manager
        manager = TaskManager(storage_path)
        
        # Create tasks
        task1 = manager.create_task("/path/to/project1", name="项目一")
        print(f"Created task: {task1.name} ({task1.id})")
        
        task2 = manager.create_task("/path/to/project2")
        print(f"Created task: {task2.name} ({task2.id})")
        
        # List tasks
        print(f"\nAll tasks ({manager.count_tasks()}):")
        for task in manager.list_tasks():
            active = "*" if task.id == manager.active_task_id else " "
            print(f"  [{active}] {task.name}: {task.workspace_dir}")
        
        # Switch task
        manager.switch_task(task1.id)
        active_task = manager.get_active_task()
        if active_task:
            print(f"\nSwitched to: {active_task.name}")
        
        # Update task
        manager.update_task(task1.id, name="项目一 (已修改)")
        updated_task = manager.get_task(task1.id)
        if updated_task:
            print(f"Updated task name: {updated_task.name}")
        
        # Add chat message
        manager.add_chat_message(task1.id, {
            "type": "user_message",
            "content": "Hello!"
        })
        task_with_history = manager.get_task(task1.id)
        if task_with_history:
            print(f"Chat history length: {len(task_with_history.chat_history)}")
        
        # Delete task
        manager.delete_task(task2.id)
        print(f"\nAfter deletion ({manager.count_tasks()} tasks):")
        for task in manager.list_tasks():
            print(f"  - {task.name}")
        
        # Test persistence
        manager2 = TaskManager(storage_path)
        print(f"\nLoaded from file ({manager2.count_tasks()} tasks):")
        for task in manager2.list_tasks():
            print(f"  - {task.name} (history: {len(task.chat_history)} messages)")
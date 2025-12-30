"""State management module.

This module provides:
- TaskManager: Task lifecycle management
- ManifestManager: Slide manifest handling
- TaskState: Task state dataclass
"""

from state.task_manager import TaskManager, TaskState, TaskStatus
from state.manifest import ManifestManager, SlideManifest

__all__ = [
    "TaskManager",
    "TaskState",
    "TaskStatus",
    "ManifestManager",
    "SlideManifest",
]
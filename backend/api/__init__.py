"""API module for FastAPI routes.

This module provides:
- Task management API
- Slide management API
- WebSocket for real-time updates
- File upload API
- Agent API for AI generation
"""

from api.tasks import router as tasks_router
from api.slides import router as slides_router
from api.websocket import router as websocket_router
from api.upload import router as upload_router
from api.agent import router as agent_router

__all__ = [
    "tasks_router",
    "slides_router",
    "websocket_router",
    "upload_router",
    "agent_router",
]
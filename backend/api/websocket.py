"""WebSocket API for real-time updates.

This module provides WebSocket endpoints for:
- Real-time generation progress
- Agent chat streaming
- Task status updates
"""

import asyncio
import json
from typing import Any, Dict, Optional, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from config import get_settings
from state.task_manager import TaskManager
from state.manifest import ManifestManager


router = APIRouter(tags=["websocket"])


class ConnectionManager:
    """Manages WebSocket connections."""
    
    def __init__(self):
        self._connections: Dict[str, Set[WebSocket]] = {}
    
    async def connect(self, websocket: WebSocket, task_id: str) -> None:
        """Accept a new WebSocket connection."""
        await websocket.accept()
        if task_id not in self._connections:
            self._connections[task_id] = set()
        self._connections[task_id].add(websocket)
    
    def disconnect(self, websocket: WebSocket, task_id: str) -> None:
        """Remove a WebSocket connection."""
        if task_id in self._connections:
            self._connections[task_id].discard(websocket)
            if not self._connections[task_id]:
                del self._connections[task_id]
    
    async def send_personal(self, websocket: WebSocket, message: Dict[str, Any]) -> None:
        """Send a message to a specific connection."""
        await websocket.send_json(message)
    
    async def broadcast(self, task_id: str, message: Dict[str, Any]) -> None:
        """Broadcast a message to all connections for a task."""
        if task_id in self._connections:
            for connection in self._connections[task_id]:
                try:
                    await connection.send_json(message)
                except Exception:
                    pass
    
    async def broadcast_all(self, message: Dict[str, Any]) -> None:
        """Broadcast a message to all connections."""
        for connections in self._connections.values():
            for connection in connections:
                try:
                    await connection.send_json(message)
                except Exception:
                    pass


# Global connection manager
manager = ConnectionManager()


@router.websocket("/ws/{task_id}")
async def websocket_task(websocket: WebSocket, task_id: str):
    """WebSocket endpoint for task updates.
    
    Messages:
    - subscribe: Subscribe to specific events
    - unsubscribe: Unsubscribe from events
    - get_progress: Request current generation progress
    - ping: Keep-alive ping
    """
    await manager.connect(websocket, task_id)
    
    try:
        # Send initial connection confirmation
        await manager.send_personal(websocket, {
            "type": "connected",
            "task_id": task_id
        })
        
        while True:
            try:
                data = await websocket.receive_json()
                await handle_message(websocket, task_id, data)
            except json.JSONDecodeError:
                await manager.send_personal(websocket, {
                    "type": "error",
                    "message": "Invalid JSON"
                })
    except WebSocketDisconnect:
        manager.disconnect(websocket, task_id)


async def handle_message(websocket: WebSocket, task_id: str, data: Dict[str, Any]):
    """Handle incoming WebSocket messages."""
    msg_type = data.get("type", "")
    
    if msg_type == "ping":
        await manager.send_personal(websocket, {"type": "pong"})
    
    elif msg_type == "get_progress":
        settings = get_settings()
        workspace = settings.get_workspace_path(task_id)
        manifest_manager = ManifestManager(workspace)
        progress = manifest_manager.get_generation_progress()
        
        await manager.send_personal(websocket, {
            "type": "progress",
            "data": progress
        })
    
    elif msg_type == "get_task":
        task_manager = TaskManager()
        task = task_manager.get_task(task_id)
        
        if task:
            await manager.send_personal(websocket, {
                "type": "task",
                "data": task.to_dict()
            })
        else:
            await manager.send_personal(websocket, {
                "type": "error",
                "message": "Task not found"
            })
    
    else:
        await manager.send_personal(websocket, {
            "type": "error",
            "message": f"Unknown message type: {msg_type}"
        })


# Helper functions for broadcasting updates
async def notify_generation_progress(task_id: str, progress: Dict[str, Any]):
    """Notify clients of generation progress update."""
    await manager.broadcast(task_id, {
        "type": "progress",
        "data": progress
    })


async def notify_slide_completed(task_id: str, slide_index: int, status: str):
    """Notify clients of slide completion."""
    await manager.broadcast(task_id, {
        "type": "slide_update",
        "data": {
            "slide_index": slide_index,
            "status": status
        }
    })


async def notify_phase_change(task_id: str, old_phase: str, new_phase: str):
    """Notify clients of phase change."""
    await manager.broadcast(task_id, {
        "type": "phase_change",
        "data": {
            "old_phase": old_phase,
            "new_phase": new_phase
        }
    })


async def notify_task_update(task_id: str, task_data: Dict[str, Any]):
    """Notify clients of task update."""
    await manager.broadcast(task_id, {
        "type": "task_update",
        "data": task_data
    })


# Chat WebSocket for AI agent interaction
@router.websocket("/ws/{task_id}/chat")
async def websocket_chat(websocket: WebSocket, task_id: str):
    """WebSocket endpoint for AI chat.
    
    Messages:
    - message: User message to send to AI
    - abort: Abort current generation
    """
    from core.agent import Agent
    from config.prompts import get_phase_prompt
    from workflow.phase_manager import Phase
    
    await websocket.accept()
    
    # Get current task phase
    task_manager = TaskManager()
    task = task_manager.get_task(task_id)
    
    if not task:
        await websocket.send_json({
            "type": "error",
            "message": "Task not found"
        })
        await websocket.close()
        return
    
    # Create agent with phase-appropriate prompt
    prompt = get_phase_prompt(task.phase.value)
    agent = Agent(system_prompt=prompt)
    
    try:
        await websocket.send_json({
            "type": "connected",
            "phase": task.phase.value
        })
        
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type", "")
            
            if msg_type == "message":
                user_message = data.get("content", "")
                
                # Stream response
                await websocket.send_json({
                    "type": "start",
                    "message_id": data.get("id")
                })
                
                full_response = ""
                async for chunk in agent.chat_stream(user_message):
                    full_response += chunk
                    await websocket.send_json({
                        "type": "chunk",
                        "content": chunk
                    })
                
                await websocket.send_json({
                    "type": "end",
                    "content": full_response
                })
            
            elif msg_type == "abort":
                # Abort not fully implemented - would need cancellation token
                await websocket.send_json({
                    "type": "aborted"
                })
            
            elif msg_type == "ping":
                await websocket.send_json({"type": "pong"})
    
    except WebSocketDisconnect:
        pass
    finally:
        await agent.close()
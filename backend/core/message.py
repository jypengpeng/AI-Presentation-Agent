"""Message handling and conversation management.

This module provides:
- Message: Single message representation
- MessageRole: Enum for message roles
- Conversation: Conversation history management
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
import json


class MessageRole(Enum):
    """Role of a message in conversation."""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass
class Message:
    """Represents a single message in conversation.
    
    Attributes:
        role: The role of the message sender
        content: The message content
        timestamp: When the message was created
        metadata: Additional metadata (tool calls, etc.)
    """
    role: MessageRole
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # For tool messages
    tool_call_id: Optional[str] = None
    name: Optional[str] = None  # Tool name for tool messages
    
    def to_openai_format(self) -> Dict[str, Any]:
        """Convert to OpenAI API message format."""
        msg = {
            "role": self.role.value,
            "content": self.content
        }
        
        if self.role == MessageRole.TOOL:
            if self.tool_call_id:
                msg["tool_call_id"] = self.tool_call_id
            if self.name:
                msg["name"] = self.name
        
        # Include tool_calls if present in metadata
        if "tool_calls" in self.metadata:
            msg["tool_calls"] = self.metadata["tool_calls"]
        
        return msg
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "role": self.role.value,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
            "tool_call_id": self.tool_call_id,
            "name": self.name
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Message":
        """Create message from dictionary."""
        return cls(
            role=MessageRole(data["role"]),
            content=data["content"],
            timestamp=datetime.fromisoformat(data.get("timestamp", datetime.now().isoformat())),
            metadata=data.get("metadata", {}),
            tool_call_id=data.get("tool_call_id"),
            name=data.get("name")
        )
    
    @classmethod
    def system(cls, content: str, **metadata) -> "Message":
        """Create a system message."""
        return cls(role=MessageRole.SYSTEM, content=content, metadata=metadata)
    
    @classmethod
    def user(cls, content: str, **metadata) -> "Message":
        """Create a user message."""
        return cls(role=MessageRole.USER, content=content, metadata=metadata)
    
    @classmethod
    def assistant(cls, content: str, **metadata) -> "Message":
        """Create an assistant message."""
        return cls(role=MessageRole.ASSISTANT, content=content, metadata=metadata)
    
    @classmethod
    def tool(cls, content: str, tool_call_id: str, name: str, **metadata) -> "Message":
        """Create a tool response message."""
        return cls(
            role=MessageRole.TOOL,
            content=content,
            tool_call_id=tool_call_id,
            name=name,
            metadata=metadata
        )


class Conversation:
    """Manages conversation history.
    
    Provides methods for:
    - Adding messages
    - Getting conversation for API calls
    - Serialization/deserialization
    - Context window management
    """
    
    def __init__(self, system_prompt: Optional[str] = None):
        """Initialize conversation.
        
        Args:
            system_prompt: Initial system prompt
        """
        self._messages: List[Message] = []
        self._system_prompt = system_prompt
        
        if system_prompt:
            self._messages.append(Message.system(system_prompt))
    
    @property
    def messages(self) -> List[Message]:
        """Get all messages."""
        return self._messages.copy()
    
    @property
    def system_prompt(self) -> Optional[str]:
        """Get the system prompt."""
        return self._system_prompt
    
    def add(self, message: Message) -> None:
        """Add a message to the conversation."""
        self._messages.append(message)
    
    def add_user(self, content: str, **metadata) -> Message:
        """Add a user message."""
        msg = Message.user(content, **metadata)
        self._messages.append(msg)
        return msg
    
    def add_assistant(self, content: str, **metadata) -> Message:
        """Add an assistant message."""
        msg = Message.assistant(content, **metadata)
        self._messages.append(msg)
        return msg
    
    def add_tool(self, content: str, tool_call_id: str, name: str, **metadata) -> Message:
        """Add a tool response message."""
        msg = Message.tool(content, tool_call_id, name, **metadata)
        self._messages.append(msg)
        return msg
    
    def get_openai_messages(self) -> List[Dict[str, Any]]:
        """Get messages in OpenAI API format."""
        return [msg.to_openai_format() for msg in self._messages]
    
    def get_last_n(self, n: int) -> List[Message]:
        """Get the last n messages."""
        return self._messages[-n:]
    
    def get_by_role(self, role: MessageRole) -> List[Message]:
        """Get all messages of a specific role."""
        return [msg for msg in self._messages if msg.role == role]
    
    def clear(self, keep_system: bool = True) -> None:
        """Clear conversation history.
        
        Args:
            keep_system: If True, keep the system prompt
        """
        if keep_system and self._system_prompt:
            self._messages = [Message.system(self._system_prompt)]
        else:
            self._messages = []
    
    def update_system_prompt(self, prompt: str) -> None:
        """Update the system prompt."""
        self._system_prompt = prompt
        
        # Update or add system message
        if self._messages and self._messages[0].role == MessageRole.SYSTEM:
            self._messages[0] = Message.system(prompt)
        else:
            self._messages.insert(0, Message.system(prompt))
    
    def truncate_to_tokens(self, max_tokens: int, approx_chars_per_token: int = 4) -> None:
        """Truncate conversation to fit within token limit.
        
        Uses a simple character-based approximation.
        Keeps system prompt and most recent messages.
        
        Args:
            max_tokens: Maximum number of tokens
            approx_chars_per_token: Characters per token approximation
        """
        max_chars = max_tokens * approx_chars_per_token
        
        # Always keep system prompt
        system_msgs = [m for m in self._messages if m.role == MessageRole.SYSTEM]
        other_msgs = [m for m in self._messages if m.role != MessageRole.SYSTEM]
        
        # Calculate system prompt size
        system_chars = sum(len(m.content) for m in system_msgs)
        remaining_chars = max_chars - system_chars
        
        # Keep messages from most recent, respecting limit
        kept_msgs = []
        current_chars = 0
        
        for msg in reversed(other_msgs):
            msg_chars = len(msg.content)
            if current_chars + msg_chars <= remaining_chars:
                kept_msgs.insert(0, msg)
                current_chars += msg_chars
            else:
                break
        
        self._messages = system_msgs + kept_msgs
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "system_prompt": self._system_prompt,
            "messages": [msg.to_dict() for msg in self._messages]
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Conversation":
        """Create conversation from dictionary."""
        conv = cls()
        conv._system_prompt = data.get("system_prompt")
        conv._messages = [
            Message.from_dict(msg_data) 
            for msg_data in data.get("messages", [])
        ]
        return conv
    
    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
    
    @classmethod
    def from_json(cls, json_str: str) -> "Conversation":
        """Deserialize from JSON string."""
        data = json.loads(json_str)
        return cls.from_dict(data)
    
    def __len__(self) -> int:
        """Return number of messages."""
        return len(self._messages)
    
    def __iter__(self):
        """Iterate over messages."""
        return iter(self._messages)
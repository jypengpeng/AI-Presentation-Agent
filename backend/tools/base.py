"""Base tool class and tool registry.

This module provides the foundation for the modular tool system:
- BaseTool: Abstract base class for all tools
- ToolRegistry: Central registry for tool discovery and management
- ToolResult: Standardized result format for tool execution
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Type


class ToolStatus(Enum):
    """Status of a tool execution."""
    SUCCESS = "success"
    ERROR = "error"
    PENDING = "pending"


@dataclass
class ToolResult:
    """Standardized result from tool execution.
    
    Attributes:
        status: The execution status
        output: The output data from the tool
        error: Error message if status is ERROR
        metadata: Additional metadata about the execution
    """
    status: ToolStatus
    output: Any = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def success(cls, output: Any, **metadata) -> "ToolResult":
        """Create a successful result."""
        return cls(
            status=ToolStatus.SUCCESS,
            output=output,
            metadata=metadata
        )
    
    @classmethod
    def failure(cls, error: str, **metadata) -> "ToolResult":
        """Create a failure result."""
        return cls(
            status=ToolStatus.ERROR,
            error=error,
            metadata=metadata
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "status": self.status.value,
            "output": self.output,
            "error": self.error,
            "metadata": self.metadata,
        }
    
    def __str__(self) -> str:
        """String representation for agent output."""
        if self.status == ToolStatus.SUCCESS:
            return str(self.output) if self.output is not None else "Success"
        else:
            return f"Error: {self.error}"


class BaseTool(ABC):
    """Abstract base class for all tools.
    
    Each tool must implement:
    - name: Unique identifier for the tool
    - description: Human-readable description
    - parameters: JSON schema for the tool parameters
    - execute: The actual tool implementation
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Unique name identifier for the tool."""
        pass
    
    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description of what the tool does."""
        pass
    
    @property
    @abstractmethod
    def parameters(self) -> Dict[str, Any]:
        """JSON schema for the tool parameters."""
        pass
    
    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        """Execute the tool with the given parameters.
        
        Args:
            **kwargs: Tool-specific parameters
            
        Returns:
            ToolResult with the execution outcome
        """
        pass
    
    def to_openai_schema(self) -> Dict[str, Any]:
        """Convert tool to OpenAI function calling schema."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            }
        }
    
    def to_json_schema(self) -> Dict[str, Any]:
        """Convert tool to JSON schema for documentation."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }
    
    def validate_params(self, params: Dict[str, Any]) -> Optional[str]:
        """Validate parameters against the schema.
        
        Returns None if valid, or an error message if invalid.
        """
        required = self.parameters.get("required", [])
        properties = self.parameters.get("properties", {})
        
        # Check required parameters
        for param in required:
            if param not in params:
                return f"Missing required parameter: {param}"
        
        # Check parameter types (basic validation)
        for param, value in params.items():
            if param in properties:
                expected_type = properties[param].get("type")
                if expected_type == "string" and not isinstance(value, str):
                    return f"Parameter '{param}' must be a string"
                elif expected_type == "integer" and not isinstance(value, int):
                    return f"Parameter '{param}' must be an integer"
                elif expected_type == "boolean" and not isinstance(value, bool):
                    return f"Parameter '{param}' must be a boolean"
                elif expected_type == "array" and not isinstance(value, list):
                    return f"Parameter '{param}' must be an array"
                elif expected_type == "object" and not isinstance(value, dict):
                    return f"Parameter '{param}' must be an object"
        
        return None


class ToolRegistry:
    """Central registry for tool management.
    
    Provides:
    - Tool registration and discovery
    - Tool lookup by name
    - Schema generation for all tools
    """
    
    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}
        self._tool_classes: Dict[str, Type[BaseTool]] = {}
    
    def register(self, tool: BaseTool) -> None:
        """Register a tool instance."""
        self._tools[tool.name] = tool
    
    def register_class(self, tool_class: Type[BaseTool]) -> None:
        """Register a tool class (for lazy instantiation)."""
        # Create a temporary instance to get the name
        instance = tool_class()
        self._tool_classes[instance.name] = tool_class
        self._tools[instance.name] = instance
    
    def get(self, name: str) -> Optional[BaseTool]:
        """Get a tool by name."""
        return self._tools.get(name)
    
    def get_all(self) -> List[BaseTool]:
        """Get all registered tools."""
        return list(self._tools.values())
    
    def get_names(self) -> List[str]:
        """Get all tool names."""
        return list(self._tools.keys())
    
    def has(self, name: str) -> bool:
        """Check if a tool is registered."""
        return name in self._tools
    
    def unregister(self, name: str) -> bool:
        """Unregister a tool by name."""
        if name in self._tools:
            del self._tools[name]
            if name in self._tool_classes:
                del self._tool_classes[name]
            return True
        return False
    
    def get_openai_schemas(self) -> List[Dict[str, Any]]:
        """Get OpenAI function schemas for all tools."""
        return [tool.to_openai_schema() for tool in self._tools.values()]
    
    def get_tools_description(self) -> str:
        """Get a formatted description of all available tools."""
        descriptions = []
        for tool in self._tools.values():
            params = tool.parameters.get("properties", {})
            param_strs = []
            for name, schema in params.items():
                param_type = schema.get("type", "any")
                param_desc = schema.get("description", "")
                required = name in tool.parameters.get("required", [])
                req_marker = "*" if required else ""
                param_strs.append(f"  - {name}{req_marker} ({param_type}): {param_desc}")
            
            params_doc = "\n".join(param_strs) if param_strs else "  No parameters"
            descriptions.append(
                f"### {tool.name}\n{tool.description}\n\nParameters:\n{params_doc}"
            )
        
        return "\n\n".join(descriptions)


# Global tool registry instance
tool_registry = ToolRegistry()


def register_tool(tool_class: Type[BaseTool]) -> Type[BaseTool]:
    """Decorator to register a tool class."""
    tool_registry.register_class(tool_class)
    return tool_class
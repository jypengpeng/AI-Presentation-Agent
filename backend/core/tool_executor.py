"""Tool execution engine.

This module provides the ToolExecutor class that:
- Parses tool calls from LLM responses
- Executes tools and collects results
- Handles errors and retries
"""

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from tools.base import BaseTool, ToolRegistry, ToolResult, ToolStatus


logger = logging.getLogger(__name__)


@dataclass
class ToolCall:
    """Represents a parsed tool call.
    
    Attributes:
        id: Unique identifier for the tool call
        name: Name of the tool to execute
        arguments: Arguments for the tool
    """
    id: str
    name: str
    arguments: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "type": "function",
            "function": {
                "name": self.name,
                "arguments": json.dumps(self.arguments)
            }
        }


class ToolExecutor:
    """Executes tools and manages tool call lifecycle.
    
    Supports multiple tool call formats:
    - OpenAI native function calling
    - JSON boundary markers (legacy format)
    """
    
    # JSON boundary markers for legacy format
    TOOL_CALL_START = "<<<TOOL_CALL>>>"
    TOOL_CALL_END = "<<<END_TOOL_CALL>>>"
    
    def __init__(
        self,
        registry: ToolRegistry,
        max_retries: int = 2,
        retry_delay: float = 1.0
    ):
        """Initialize tool executor.
        
        Args:
            registry: Tool registry containing available tools
            max_retries: Maximum number of retries for failed tools
            retry_delay: Delay between retries in seconds
        """
        self.registry = registry
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self._call_counter = 0
    
    def has_tool_call_markers(self, content: str) -> bool:
        """Check if content contains tool call start markers.
        
        Args:
            content: The text content to check
            
        Returns:
            True if tool call markers are present
        """
        return self.TOOL_CALL_START in content
    
    def has_complete_tool_blocks(self, content: str) -> bool:
        """Check if all tool call blocks are complete (have matching end markers).
        
        Args:
            content: The text content to check
            
        Returns:
            True if all tool blocks have matching start and end markers
        """
        start_count = content.count(self.TOOL_CALL_START)
        end_count = content.count(self.TOOL_CALL_END)
        return start_count > 0 and end_count >= start_count
    
    def parse_tool_calls(self, response: Any) -> Tuple[List[ToolCall], List[str]]:
        """Parse tool calls from LLM response.
        
        Supports both OpenAI format and legacy JSON boundary format.
        
        Args:
            response: LLM response (can be string or OpenAI response object)
            
        Returns:
            Tuple of (parsed_tool_calls, parse_errors)
            - parsed_tool_calls: List of successfully parsed tool calls
            - parse_errors: List of error messages for failed parses
        """
        tool_calls = []
        parse_errors = []
        
        # Handle OpenAI response object with tool_calls
        if hasattr(response, 'choices') and response.choices:
            choice = response.choices[0]
            if hasattr(choice, 'message') and hasattr(choice.message, 'tool_calls'):
                if choice.message.tool_calls:
                    for tc in choice.message.tool_calls:
                        try:
                            args = json.loads(tc.function.arguments)
                        except json.JSONDecodeError as e:
                            parse_errors.append(f"Failed to parse arguments for {tc.function.name}: {e}")
                            args = {}
                        
                        tool_calls.append(ToolCall(
                            id=tc.id,
                            name=tc.function.name,
                            arguments=args
                        ))
        
        # Handle string content with JSON boundary markers
        content = ""
        if isinstance(response, str):
            content = response
        elif hasattr(response, 'choices') and response.choices:
            content = response.choices[0].message.content or ""
        
        if self.TOOL_CALL_START in content:
            parsed, errors = self._parse_boundary_format(content)
            tool_calls.extend(parsed)
            parse_errors.extend(errors)
        
        return tool_calls, parse_errors
    
    def _parse_boundary_format(self, content: str) -> Tuple[List[ToolCall], List[str]]:
        """Parse tool calls from JSON boundary format.
        
        Format:
        <<<TOOL_CALL>>>
        {"tool": "tool_name", "parameters": {...}}
        <<<END_TOOL_CALL>>>
        
        Supports multiple parameter key formats:
        - "parameters" (preferred, matches original agent_core.py)
        - "args"
        - "arguments"
        
        Returns:
            Tuple of (parsed_tool_calls, parse_errors)
        """
        tool_calls = []
        parse_errors = []
        
        # Find all tool call blocks
        pattern = rf'{re.escape(self.TOOL_CALL_START)}\s*(.*?)\s*{re.escape(self.TOOL_CALL_END)}'
        matches = re.findall(pattern, content, re.DOTALL)
        
        logger.debug(f"[PARSE_TOOL] Found {len(matches)} tool call block(s)")
        
        for i, match in enumerate(matches):
            json_str = match.strip()
            try:
                data = json.loads(json_str)
                
                tool_name = data.get("tool") or data.get("name")
                # Support multiple parameter key formats - "parameters" is primary (matches original)
                tool_args = (
                    data.get("parameters") or
                    data.get("args") or
                    data.get("arguments") or
                    {}
                )
                
                if tool_name:
                    self._call_counter += 1
                    tool_calls.append(ToolCall(
                        id=f"call_{self._call_counter}",
                        name=tool_name,
                        arguments=tool_args
                    ))
                    logger.debug(f"[PARSE_TOOL] Parsed tool call: {tool_name}")
                else:
                    error_msg = f"Tool call block {i+1}: missing 'tool' or 'name' key"
                    parse_errors.append(error_msg)
                    logger.warning(f"[PARSE_TOOL] {error_msg}")
            except json.JSONDecodeError as e:
                # Log the error with context for debugging
                preview = json_str[:200] + "..." if len(json_str) > 200 else json_str
                error_msg = f"Tool call block {i+1}: JSON parse error - {e}"
                parse_errors.append(error_msg)
                logger.warning(f"[PARSE_TOOL] {error_msg}")
                logger.debug(f"[PARSE_TOOL] Failed JSON preview: {preview}")
        
        return tool_calls, parse_errors
    
    async def execute(self, tool_call: ToolCall) -> ToolResult:
        """Execute a single tool call.
        
        Args:
            tool_call: The tool call to execute
            
        Returns:
            ToolResult with execution outcome
        """
        tool = self.registry.get(tool_call.name)
        
        if tool is None:
            return ToolResult.failure(
                f"Unknown tool: {tool_call.name}",
                available_tools=self.registry.get_names()
            )
        
        # Validate parameters
        validation_error = tool.validate_params(tool_call.arguments)
        if validation_error:
            return ToolResult.failure(validation_error)
        
        # Execute with retries
        last_error = None
        for attempt in range(self.max_retries + 1):
            try:
                result = await tool.execute(**tool_call.arguments)
                return result
            except Exception as e:
                last_error = str(e)
                if attempt < self.max_retries:
                    await asyncio.sleep(self.retry_delay)
        
        return ToolResult.failure(
            f"Tool execution failed after {self.max_retries + 1} attempts: {last_error}"
        )
    
    async def execute_all(
        self,
        tool_calls: List[ToolCall],
        parallel: bool = False
    ) -> List[Tuple[ToolCall, ToolResult]]:
        """Execute multiple tool calls.
        
        Args:
            tool_calls: List of tool calls to execute
            parallel: If True, execute tools in parallel
            
        Returns:
            List of (tool_call, result) tuples
        """
        if parallel:
            tasks = [self.execute(tc) for tc in tool_calls]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            return [
                (tc, r if isinstance(r, ToolResult) else ToolResult.failure(str(r)))
                for tc, r in zip(tool_calls, results)
            ]
        else:
            results = []
            for tc in tool_calls:
                result = await self.execute(tc)
                results.append((tc, result))
            return results
    
    def extract_text_content(self, response: str) -> str:
        """Extract text content from response, removing tool call blocks.
        
        Args:
            response: The full response string
            
        Returns:
            Response with tool call blocks removed
        """
        # Remove tool call blocks
        pattern = rf'{re.escape(self.TOOL_CALL_START)}.*?{re.escape(self.TOOL_CALL_END)}'
        text = re.sub(pattern, '', response, flags=re.DOTALL)
        
        # Clean up whitespace
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()
    
    def format_results_for_llm(
        self,
        results: List[Tuple[ToolCall, ToolResult]]
    ) -> str:
        """Format tool results for inclusion in LLM context.
        
        Args:
            results: List of (tool_call, result) tuples
            
        Returns:
            Formatted string for LLM context
        """
        parts = []
        for tc, result in results:
            status = "✓" if result.status == ToolStatus.SUCCESS else "✗"
            parts.append(f"[{status}] {tc.name}({json.dumps(tc.arguments, ensure_ascii=False)})")
            parts.append(f"    {result}")
        
        return "\n".join(parts)
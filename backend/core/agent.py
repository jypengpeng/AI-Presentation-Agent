"""Main Agent class for conversation and tool execution.

This module provides the Agent class that:
- Manages conversation with LLM
- Handles tool calls and responses
- Supports streaming responses
"""

import asyncio
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional

import httpx

from config import Settings, get_settings
from tools.base import ToolRegistry, tool_registry
from core.message import Conversation, Message, MessageRole
from core.tool_executor import ToolCall, ToolExecutor, ToolResult


class Agent:
    """AI Agent for conversation and tool execution.
    
    Handles:
    - LLM API communication
    - Tool call parsing and execution (using JSON boundary markers)
    - Conversation management
    - Streaming responses
    
    Uses JSON boundary markers (<<<TOOL_CALL>>> / <<<END_TOOL_CALL>>>) for tool calls
    instead of OpenAI native function calling, for better compatibility with proxies.
    """
    
    # JSON boundary markers for tool calls
    TOOL_CALL_START = "<<<TOOL_CALL>>>"
    TOOL_CALL_END = "<<<END_TOOL_CALL>>>"
    
    def __init__(
        self,
        system_prompt: str,
        model: Optional[str] = None,
        registry: Optional[ToolRegistry] = None,
        settings: Optional[Settings] = None,
        on_tool_call: Optional[Callable[[ToolCall], None]] = None,
        on_tool_result: Optional[Callable[[ToolCall, ToolResult], None]] = None,
    ):
        """Initialize the agent.
        
        Args:
            system_prompt: The system prompt for the agent
            model: LLM model to use (defaults to settings.openai_model)
            registry: Tool registry (defaults to global registry)
            settings: Application settings
            on_tool_call: Callback when a tool call is made
            on_tool_result: Callback when a tool call completes
        """
        self.settings = settings or get_settings()
        self.model = model or self.settings.openai_model
        self.registry = registry or tool_registry
        
        # Build full system prompt with tool definitions
        tool_definitions = self._generate_tool_definitions()
        full_system_prompt = f"{system_prompt}\n\n{tool_definitions}"
        
        self.conversation = Conversation(full_system_prompt)
        self.tool_executor = ToolExecutor(self.registry)
        
        # Callbacks
        self.on_tool_call = on_tool_call
        self.on_tool_result = on_tool_result
        
        # HTTP client for API calls
        self._client: Optional[httpx.AsyncClient] = None
        
        # Task completion tracking
        self.task_completed = False
        self.task_result = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=120)
        return self._client
    
    async def close(self) -> None:
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
    
    def update_system_prompt(self, prompt: str) -> None:
        """Update the system prompt."""
        # Add tool definitions to the new prompt
        tool_definitions = self._generate_tool_definitions()
        full_prompt = f"{prompt}\n\n{tool_definitions}"
        self.conversation.update_system_prompt(full_prompt)
    
    def _generate_tool_definitions(self) -> str:
        """Generate text-format tool definitions for the system prompt.
        
        This matches the original agent_core.py format for JSON boundary marker tool calls.
        """
        tools = []
        
        for tool in self.registry.get_all():
            params = tool.parameters.get("properties", {})
            required = tool.parameters.get("required", [])
            
            param_strs = []
            for name, schema in params.items():
                param_type = schema.get("type", "any")
                param_desc = schema.get("description", "")
                req_marker = "[required]" if name in required else "[optional]"
                param_strs.append(f"    - {name} ({param_type}) {req_marker}: {param_desc}")
            
            params_doc = "\n".join(param_strs) if param_strs else "    No parameters"
            
            # Build example
            example_args = {}
            for name, schema in params.items():
                if name in required:
                    ptype = schema.get("type", "string")
                    if ptype == "string":
                        example_args[name] = f"<{name}>"
                    elif ptype == "integer":
                        example_args[name] = 0
                    elif ptype == "boolean":
                        example_args[name] = True
                    elif ptype == "array":
                        example_args[name] = []
                    else:
                        example_args[name] = {}
            
            import json
            example_json = json.dumps({"tool": tool.name, "parameters": example_args}, indent=2, ensure_ascii=False)
            
            tools.append(f"""### {tool.name}
{tool.description}

Parameters:
{params_doc}

Example:
```json
{example_json}
```""")
        
        tool_descriptions = "\n\n".join(tools)
        
        return f"""## Available Tools

{tool_descriptions}

---

## How to Use Tools

When you need to use a tool, output a JSON object wrapped in special boundary markers:

{self.TOOL_CALL_START}
{{"tool": "tool_name", "parameters": {{...}}}}
{self.TOOL_CALL_END}

**CRITICAL: ONE TOOL PER RESPONSE**

You MUST only call ONE tool at a time. After calling a tool, you MUST wait for the result before deciding your next action.

**WRONG (Do NOT do this):**
```
{self.TOOL_CALL_START}
{{"tool": "read_file", "parameters": {{"path": "file.txt"}}}}
{self.TOOL_CALL_END}

{self.TOOL_CALL_START}
{{"tool": "phase_complete", "parameters": {{"phase": "architect", "summary": "Done"}}}}
{self.TOOL_CALL_END}
```

**CORRECT:**
1. Call one tool:
{self.TOOL_CALL_START}
{{"tool": "read_file", "parameters": {{"path": "file.txt"}}}}
{self.TOOL_CALL_END}

2. Wait for the result, then based on the result, decide your next action.

**Important Rules:**
- Each tool call must be wrapped in {self.TOOL_CALL_START} and {self.TOOL_CALL_END} markers
- The content between markers must be a valid JSON object
- Use proper JSON syntax (double quotes for strings, no trailing commas)
- **ONLY ONE tool call per response** - wait for the result before calling another tool
- **NEVER assume a tool will succeed** - always check the result before proceeding
- If a tool fails, handle the error appropriately before moving to the next step"""
    
    async def chat(
        self,
        message: str,
        max_tool_rounds: int = 10,
        execute_tools: bool = True
    ) -> str:
        """Send a message and get a response.
        
        Implements agentic loop similar to original agent_core.py:
        - Continues until task_completed or phase_complete tool is called
        - Or no tool calls in response (treated as implicit completion)
        
        Args:
            message: User message
            max_tool_rounds: Maximum rounds of tool execution
            execute_tools: Whether to execute tool calls
            
        Returns:
            Assistant's final response
        """
        import json
        import logging
        logger = logging.getLogger(__name__)
        
        # Reset completion state
        self.task_completed = False
        self.task_result = None
        
        # Add user message
        self.conversation.add_user(message)
        
        # Agentic loop
        for round_num in range(max_tool_rounds):
            response = await self._call_llm()
            content = self._extract_content(response)
            
            # Parse tool calls from content (JSON boundary markers)
            tool_calls, parse_errors = self.tool_executor.parse_tool_calls(content)
            
            # Check if tool markers exist but parsing failed
            has_markers = self.tool_executor.has_tool_call_markers(content)
            
            if has_markers and not tool_calls and parse_errors:
                # Tool call markers found but parsing failed - send error feedback
                logger.warning(f"[AGENT] Tool call markers found but parsing failed: {parse_errors}")
                
                # Add assistant message to history
                self.conversation.add_assistant(content)
                
                # Send error feedback to let the agent retry with correct format
                error_feedback = (
                    f"工具调用格式错误，无法解析。错误信息：{'; '.join(parse_errors)}\n\n"
                    f"请使用正确的JSON格式重试。确保：\n"
                    f"1. JSON语法正确（使用双引号，无尾随逗号）\n"
                    f"2. 字符串中的特殊字符正确转义\n"
                    f"3. 工具调用格式为：{self.TOOL_CALL_START}\n"
                    f'   {{"tool": "tool_name", "parameters": {{...}}}}\n'
                    f"   {self.TOOL_CALL_END}"
                )
                
                self.conversation.add_user(error_feedback)
                
                # Continue to next iteration to let agent retry
                continue
            
            if not tool_calls or not execute_tools:
                # No tool calls - this is implicit completion
                self.conversation.add_assistant(content)
                self.task_completed = True
                self.task_result = content
                return content
            
            # Add assistant message to conversation
            self.conversation.add_assistant(content)
            
            # Execute tool calls and collect results
            tool_results_parts = []
            
            for tc in tool_calls:
                if self.on_tool_call:
                    self.on_tool_call(tc)
                
                result = await self.tool_executor.execute(tc)
                
                if self.on_tool_result:
                    self.on_tool_result(tc, result)
                
                # Check for task/phase completion
                if tc.name == "task_completed" and result.status.value == "success":
                    self.task_completed = True
                    self.task_result = tc.arguments.get("result", "")
                elif tc.name == "phase_complete" and result.status.value == "success":
                    self.task_completed = True
                    self.task_result = tc.arguments.get("summary", "")
                
                # Build tool result text
                result_data = result.to_dict()
                tool_results_parts.append(f'Tool "{tc.name}" result:\n{json.dumps(result_data, ensure_ascii=False, indent=2)}')
            
            # Add tool results as user message (text format for boundary marker mode)
            tool_results_message = "\n\n".join(tool_results_parts)
            self.conversation.add_user(tool_results_message)
            
            # Check if we should stop
            if self.task_completed:
                return self.task_result or ""
        
        # Max rounds reached
        return "Maximum tool execution rounds reached."
    
    async def chat_stream(
        self,
        message: str,
        max_tool_rounds: int = 10
    ) -> AsyncGenerator[str, None]:
        """Stream a chat response.
        
        Yields chunks of the response as they're received.
        Tool calls are executed between streaming rounds.
        
        Implements agentic loop similar to original agent_core.py:
        - Continues until task_completed or phase_complete tool is called
        - Or no tool calls in response (treated as implicit completion)
        
        Args:
            message: User message
            max_tool_rounds: Maximum rounds of tool execution
            
        Yields:
            Response chunks
        """
        import json
        import logging
        logger = logging.getLogger(__name__)
        
        # Reset completion state
        self.task_completed = False
        self.task_result = None
        
        self.conversation.add_user(message)
        
        for round_num in range(max_tool_rounds):
            full_response = ""
            
            async for chunk in self._stream_llm():
                full_response += chunk
                yield chunk
            
            # Parse tool calls from complete response (JSON boundary markers)
            tool_calls, parse_errors = self.tool_executor.parse_tool_calls(full_response)
            
            # Check if tool markers exist but parsing failed
            has_markers = self.tool_executor.has_tool_call_markers(full_response)
            
            if has_markers and not tool_calls and parse_errors:
                # Tool call markers found but parsing failed - send error feedback
                logger.warning(f"[AGENT] Tool call markers found but parsing failed: {parse_errors}")
                
                # Add assistant message to history
                self.conversation.add_assistant(full_response)
                
                # Send error feedback to let the agent retry with correct format
                error_feedback = (
                    f"工具调用格式错误，无法解析。错误信息：{'; '.join(parse_errors)}\n\n"
                    f"请使用正确的JSON格式重试。确保：\n"
                    f"1. JSON语法正确（使用双引号，无尾随逗号）\n"
                    f"2. 字符串中的特殊字符正确转义\n"
                    f"3. 工具调用格式为：{self.TOOL_CALL_START}\n"
                    f'   {{"tool": "tool_name", "parameters": {{...}}}}\n'
                    f"   {self.TOOL_CALL_END}"
                )
                
                self.conversation.add_user(error_feedback)
                
                # Yield warning to user
                yield f"\n\n⚠️ 工具调用解析失败，正在重试...\n"
                
                # Continue to next iteration to let agent retry
                continue
            
            if not tool_calls:
                # No tool calls - implicit completion
                self.conversation.add_assistant(full_response)
                self.task_completed = True
                self.task_result = full_response
                return
            
            # Add assistant message to conversation
            self.conversation.add_assistant(full_response)
            
            # Execute tools and collect results
            tool_results_parts = []
            
            for tc in tool_calls:
                if self.on_tool_call:
                    self.on_tool_call(tc)
                
                result = await self.tool_executor.execute(tc)
                
                if self.on_tool_result:
                    self.on_tool_result(tc, result)
                
                # Check for task/phase completion
                if tc.name == "task_completed" and result.status.value == "success":
                    self.task_completed = True
                    self.task_result = tc.arguments.get("result", "")
                elif tc.name == "phase_complete" and result.status.value == "success":
                    self.task_completed = True
                    self.task_result = tc.arguments.get("summary", "")
                
                # Yield tool execution info
                yield f"\n[🔧 {tc.name}] "
                
                # Build tool result text
                result_data = result.to_dict()
                result_text = json.dumps(result_data, ensure_ascii=False, indent=2)
                tool_results_parts.append(f'Tool "{tc.name}" result:\n{result_text}')
                
                # Yield result status
                if result.status.value == "success":
                    yield f"✓ {str(result)[:200]}\n"
                else:
                    yield f"✗ {result.error}\n"
            
            # Add tool results as user message
            tool_results_message = "\n\n".join(tool_results_parts)
            self.conversation.add_user(tool_results_message)
            
            # Check if we should stop
            if self.task_completed:
                yield f"\n\n✅ {self.task_result}\n"
                return
        
        # Max rounds reached
        yield "\n\n⚠️ Maximum tool execution rounds reached.\n"
    
    async def _call_llm(self) -> Any:
        """Make a non-streaming LLM API call.
        
        Note: We do NOT use OpenAI function calling (tools parameter).
        Instead, we use JSON boundary markers in the system prompt,
        which is more compatible with proxies and different API providers.
        """
        client = await self._get_client()
        
        headers = {
            "Authorization": f"Bearer {self.settings.openai_api_key}",
            "Content-Type": "application/json"
        }
        
        body = {
            "model": self.model,
            "messages": self.conversation.get_openai_messages(),
            # NO tools parameter - we use text-based tool calling
        }
        
        response = await client.post(
            f"{self.settings.openai_api_base}/chat/completions",
            headers=headers,
            json=body
        )
        
        response.raise_for_status()
        return response.json()
    
    async def _stream_llm(self) -> AsyncGenerator[str, None]:
        """Make a streaming LLM API call.
        
        Note: We do NOT use OpenAI function calling (tools parameter).
        Instead, we use JSON boundary markers in the system prompt.
        """
        client = await self._get_client()
        
        headers = {
            "Authorization": f"Bearer {self.settings.openai_api_key}",
            "Content-Type": "application/json"
        }
        
        body = {
            "model": self.model,
            "messages": self.conversation.get_openai_messages(),
            "stream": True
            # NO tools parameter - we use text-based tool calling
        }
        
        async with client.stream(
            "POST",
            f"{self.settings.openai_api_base}/chat/completions",
            headers=headers,
            json=body
        ) as response:
            response.raise_for_status()
            
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    
                    try:
                        import json
                        chunk = json.loads(data)
                        if "choices" in chunk and chunk["choices"]:
                            delta = chunk["choices"][0].get("delta", {})
                            if "content" in delta and delta["content"]:
                                yield delta["content"]
                    except json.JSONDecodeError:
                        continue
    
    def _extract_content(self, response: Any) -> str:
        """Extract text content from LLM response.
        
        Note: This returns the FULL content including tool call markers.
        Do NOT use extract_text_content here as we need the markers for parsing.
        """
        if isinstance(response, str):
            return response
        
        if isinstance(response, dict):
            if "choices" in response and response["choices"]:
                content = response["choices"][0].get("message", {}).get("content", "")
                return content or ""
        
        return ""
    
    def get_conversation_history(self) -> List[Dict[str, Any]]:
        """Get conversation history as list of dicts."""
        return [msg.to_dict() for msg in self.conversation.messages]
    
    def clear_history(self, keep_system: bool = True) -> None:
        """Clear conversation history."""
        self.conversation.clear(keep_system)


class AgentPool:
    """Pool of agents for different purposes.
    
    Manages multiple specialized agents (Architect, Designer, etc.)
    """
    
    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self._agents: Dict[str, Agent] = {}
    
    def get_or_create(
        self,
        name: str,
        system_prompt: str,
        model: Optional[str] = None
    ) -> Agent:
        """Get or create an agent by name."""
        if name not in self._agents:
            self._agents[name] = Agent(
                system_prompt=system_prompt,
                model=model,
                settings=self.settings
            )
        return self._agents[name]
    
    def get(self, name: str) -> Optional[Agent]:
        """Get an agent by name."""
        return self._agents.get(name)
    
    async def close_all(self) -> None:
        """Close all agents."""
        for agent in self._agents.values():
            await agent.close()
        self._agents.clear()
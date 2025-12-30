"""Workflow phase control tools.

This module provides tools for workflow phase management:
- TransitionPhaseTool: Transition between workflow phases
- GenerateSlideTool: Trigger slide generation
"""

from typing import Any, Dict, Optional, List
from pathlib import Path

from tools.base import BaseTool, ToolResult, register_tool


# Valid workflow phases
PHASES = ["collecting", "architect", "editing_plan", "designing", "completed"]

# Valid phase transitions
VALID_TRANSITIONS = {
    "collecting": ["architect", "editing_plan"],
    "architect": ["editing_plan", "collecting"],
    "editing_plan": ["designing", "architect", "collecting"],
    "designing": ["completed", "editing_plan"],
    "completed": ["editing_plan", "collecting"],
}


@register_tool
class TransitionPhaseTool(BaseTool):
    """Tool for transitioning between workflow phases."""
    
    def __init__(self, phase_callback=None):
        """Initialize the tool.
        
        Args:
            phase_callback: Optional callback function called on phase change.
                           Signature: (old_phase: str, new_phase: str) -> None
        """
        self.phase_callback = phase_callback
        self._current_phase = "collecting"
    
    @property
    def name(self) -> str:
        return "transition_phase"
    
    @property
    def description(self) -> str:
        return f"""Transition to a different workflow phase. 
Valid phases: {', '.join(PHASES)}
Current phase determines available transitions."""
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "target_phase": {
                    "type": "string",
                    "description": f"The phase to transition to. One of: {', '.join(PHASES)}",
                    "enum": PHASES
                },
                "reason": {
                    "type": "string",
                    "description": "Reason for the phase transition"
                }
            },
            "required": ["target_phase"]
        }
    
    def set_current_phase(self, phase: str) -> None:
        """Set the current phase (for state synchronization)."""
        if phase in PHASES:
            self._current_phase = phase
    
    async def execute(
        self,
        target_phase: str,
        reason: str = "",
        **kwargs
    ) -> ToolResult:
        """Execute phase transition."""
        try:
            # Validate target phase
            if target_phase not in PHASES:
                return ToolResult.failure(
                    f"Invalid phase: {target_phase}. Valid phases: {PHASES}"
                )
            
            # Check if transition is valid
            valid_targets = VALID_TRANSITIONS.get(self._current_phase, [])
            if target_phase not in valid_targets:
                return ToolResult.failure(
                    f"Cannot transition from '{self._current_phase}' to '{target_phase}'. "
                    f"Valid transitions: {valid_targets}"
                )
            
            old_phase = self._current_phase
            self._current_phase = target_phase
            
            # Call callback if provided
            if self.phase_callback:
                self.phase_callback(old_phase, target_phase)
            
            return ToolResult.success(
                f"Successfully transitioned from '{old_phase}' to '{target_phase}'",
                old_phase=old_phase,
                new_phase=target_phase,
                reason=reason
            )
            
        except Exception as e:
            return ToolResult.failure(f"Error during phase transition: {e}")


@register_tool
class GenerateSlideTool(BaseTool):
    """Tool for triggering slide generation."""
    
    def __init__(self, generator_callback=None):
        """Initialize the tool.
        
        Args:
            generator_callback: Async callback for slide generation.
                              Signature: (slide_index: int, slide_data: dict) -> str
        """
        self.generator_callback = generator_callback
    
    @property
    def name(self) -> str:
        return "generate_slide"
    
    @property
    def description(self) -> str:
        return "Generate HTML content for a specific slide based on the presentation plan."
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "slide_index": {
                    "type": "integer",
                    "description": "Index of the slide to generate (0-based)"
                },
                "slide_data": {
                    "type": "object",
                    "description": "Slide data from the presentation plan",
                    "properties": {
                        "title": {"type": "string"},
                        "content": {"type": "array"},
                        "notes": {"type": "string"},
                        "layout": {"type": "string"}
                    }
                },
                "design_style": {
                    "type": "string",
                    "description": "Design style for the slide"
                }
            },
            "required": ["slide_index", "slide_data"]
        }
    
    async def execute(
        self,
        slide_index: int,
        slide_data: Dict[str, Any],
        design_style: str = "modern",
        **kwargs
    ) -> ToolResult:
        """Generate a slide."""
        try:
            if self.generator_callback:
                html_content = await self.generator_callback(
                    slide_index, 
                    slide_data,
                    design_style
                )
                return ToolResult.success(
                    html_content,
                    slide_index=slide_index,
                    title=slide_data.get("title", "")
                )
            else:
                return ToolResult.failure(
                    "Slide generator not configured"
                )
                
        except Exception as e:
            return ToolResult.failure(f"Error generating slide: {e}")


@register_tool
class UpdatePresentationPlanTool(BaseTool):
    """Tool for updating the presentation plan."""
    
    def __init__(self, workspace_root: Optional[Path] = None):
        self.workspace_root = workspace_root or Path.cwd()
    
    @property
    def name(self) -> str:
        return "update_presentation_plan"
    
    @property
    def description(self) -> str:
        return "Update the presentation plan with new slide data."
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "slides": {
                    "type": "array",
                    "description": "Array of slide objects",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "content": {"type": "array"},
                            "notes": {"type": "string"},
                            "layout": {"type": "string"}
                        }
                    }
                },
                "metadata": {
                    "type": "object",
                    "description": "Presentation metadata (title, theme, etc.)"
                }
            },
            "required": ["slides"]
        }
    
    async def execute(
        self,
        slides: List[Dict[str, Any]],
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> ToolResult:
        """Update presentation plan."""
        import json
        
        try:
            plan = {
                "metadata": metadata or {},
                "slides": slides,
                "version": "1.0"
            }
            
            # Save to workspace
            plan_path = self.workspace_root / "slides" / "presentation_plan.json"
            plan_path.parent.mkdir(parents=True, exist_ok=True)
            
            plan_path.write_text(
                json.dumps(plan, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
            
            return ToolResult.success(
                f"Updated presentation plan with {len(slides)} slides",
                path=str(plan_path),
                slide_count=len(slides)
            )
            
        except Exception as e:
            return ToolResult.failure(f"Error updating presentation plan: {e}")


@register_tool
class CompleteTaskTool(BaseTool):
    """Tool for marking a task as complete."""
    
    @property
    def name(self) -> str:
        return "complete_task"
    
    @property
    def description(self) -> str:
        return "Mark the current task as complete and provide a summary."
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "Summary of what was accomplished"
                },
                "outputs": {
                    "type": "array",
                    "description": "List of output files or artifacts",
                    "items": {"type": "string"}
                }
            },
            "required": ["summary"]
        }
    
    async def execute(
        self,
        summary: str,
        outputs: Optional[List[str]] = None,
        **kwargs
    ) -> ToolResult:
        """Mark task as complete."""
        return ToolResult.success(
            f"Task completed: {summary}",
            summary=summary,
            outputs=outputs or []
        )


@register_tool
class PhaseCompleteTool(BaseTool):
    """Tool for signaling phase completion (matches original agent_core.py).
    
    This tool is used to signal that the current workflow phase is complete
    and the system should transition to the next phase.
    """
    
    def __init__(self, phase_callback=None):
        """Initialize the tool.
        
        Args:
            phase_callback: Optional callback function called on phase completion.
                           Signature: (phase: str, summary: str) -> None
        """
        self.phase_callback = phase_callback
    
    @property
    def name(self) -> str:
        return "phase_complete"
    
    @property
    def description(self) -> str:
        return """Signal that the current phase is complete and ready to transition.
Use this when you have finished gathering information and want to hand off to the next agent.
Valid phases: 'collecting' (information gathering), 'architect' (presentation planning)."""
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "phase": {
                    "type": "string",
                    "description": "The phase that was completed. One of: 'collecting', 'architect'",
                    "enum": ["collecting", "architect", "designer"]
                },
                "summary": {
                    "type": "string",
                    "description": "Summary of what was accomplished in this phase and key information for the next phase"
                }
            },
            "required": ["phase", "summary"]
        }
    
    async def execute(
        self,
        phase: str,
        summary: str,
        **kwargs
    ) -> ToolResult:
        """Signal phase completion."""
        valid_phases = ["collecting", "architect", "designer"]
        
        if phase not in valid_phases:
            return ToolResult.failure(
                f"Invalid phase: {phase}. Must be one of: {valid_phases}"
            )
        
        # Call callback if provided
        if self.phase_callback:
            try:
                self.phase_callback(phase, summary)
            except Exception as e:
                return ToolResult.failure(f"Phase callback error: {e}")
        
        return ToolResult.success(
            f"Phase '{phase}' completed successfully",
            phase=phase,
            summary=summary,
            phase_complete=True
        )


@register_tool
class TaskCompletedTool(BaseTool):
    """Tool for signaling task completion (matches original agent_core.py)."""
    
    @property
    def name(self) -> str:
        return "task_completed"
    
    @property
    def description(self) -> str:
        return "Signal that the assigned task has been completed. Use this when you have finished all required work."
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "result": {
                    "type": "string",
                    "description": "A summary of what was accomplished"
                }
            },
            "required": ["result"]
        }
    
    async def execute(
        self,
        result: str,
        **kwargs
    ) -> ToolResult:
        """Mark task as complete."""
        return ToolResult.success(
            result,
            completed=True,
            result=result
        )
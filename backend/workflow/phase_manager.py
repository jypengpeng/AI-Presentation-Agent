"""Workflow phase state machine.

This module provides:
- Phase: Enum of workflow phases
- PhaseState: Current phase state with metadata
- PhaseManager: State machine for phase transitions
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


class Phase(Enum):
    """Workflow phases for presentation generation."""
    COLLECTING = "collecting"
    ARCHITECT = "architect"
    EDITING_PLAN = "editing_plan"
    DESIGNING = "designing"
    COMPLETED = "completed"


# Valid phase transitions
TRANSITIONS: Dict[Phase, List[Phase]] = {
    Phase.COLLECTING: [Phase.ARCHITECT, Phase.EDITING_PLAN],
    Phase.ARCHITECT: [Phase.EDITING_PLAN, Phase.COLLECTING],
    Phase.EDITING_PLAN: [Phase.DESIGNING, Phase.ARCHITECT, Phase.COLLECTING],
    Phase.DESIGNING: [Phase.COMPLETED, Phase.EDITING_PLAN],
    Phase.COMPLETED: [Phase.EDITING_PLAN, Phase.COLLECTING],
}


@dataclass
class PhaseState:
    """Current state of a workflow phase.
    
    Attributes:
        phase: Current phase
        entered_at: When this phase was entered
        metadata: Phase-specific metadata
        history: List of previous phases
    """
    phase: Phase
    entered_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    history: List[tuple] = field(default_factory=list)  # (phase, entered_at, exited_at)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "phase": self.phase.value,
            "entered_at": self.entered_at.isoformat(),
            "metadata": self.metadata,
            "history": [
                {
                    "phase": p.value,
                    "entered_at": ea.isoformat(),
                    "exited_at": ex.isoformat() if ex else None
                }
                for p, ea, ex in self.history
            ]
        }


class PhaseManager:
    """Manages workflow phase transitions.
    
    Provides:
    - Phase state tracking
    - Transition validation
    - Event callbacks
    - Phase history
    """
    
    def __init__(
        self,
        initial_phase: Phase = Phase.COLLECTING,
        on_transition: Optional[Callable[[Phase, Phase], None]] = None,
        on_enter: Optional[Callable[[Phase], None]] = None,
        on_exit: Optional[Callable[[Phase], None]] = None,
    ):
        """Initialize phase manager.
        
        Args:
            initial_phase: Starting phase
            on_transition: Callback on phase transition (old, new)
            on_enter: Callback when entering a phase
            on_exit: Callback when exiting a phase
        """
        self._state = PhaseState(phase=initial_phase)
        self.on_transition = on_transition
        self.on_enter = on_enter
        self.on_exit = on_exit
    
    @property
    def current_phase(self) -> Phase:
        """Get current phase."""
        return self._state.phase
    
    @property
    def state(self) -> PhaseState:
        """Get current phase state."""
        return self._state
    
    def can_transition_to(self, target: Phase) -> bool:
        """Check if transition to target phase is valid."""
        valid_targets = TRANSITIONS.get(self._state.phase, [])
        return target in valid_targets
    
    def get_valid_transitions(self) -> List[Phase]:
        """Get list of valid target phases from current phase."""
        return TRANSITIONS.get(self._state.phase, [])
    
    def transition_to(
        self,
        target: Phase,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Transition to a new phase.
        
        Args:
            target: Target phase
            metadata: Metadata for the new phase
            
        Returns:
            True if transition succeeded, False otherwise
        """
        if not self.can_transition_to(target):
            return False
        
        old_phase = self._state.phase
        now = datetime.now()
        
        # Record in history
        self._state.history.append((
            old_phase,
            self._state.entered_at,
            now
        ))
        
        # Exit callback
        if self.on_exit:
            self.on_exit(old_phase)
        
        # Update state
        self._state.phase = target
        self._state.entered_at = now
        self._state.metadata = metadata or {}
        
        # Transition callback
        if self.on_transition:
            self.on_transition(old_phase, target)
        
        # Enter callback
        if self.on_enter:
            self.on_enter(target)
        
        return True
    
    def force_transition(
        self,
        target: Phase,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Force transition to a phase, ignoring validation.
        
        Use with caution - bypasses normal transition rules.
        """
        old_phase = self._state.phase
        now = datetime.now()
        
        self._state.history.append((
            old_phase,
            self._state.entered_at,
            now
        ))
        
        self._state.phase = target
        self._state.entered_at = now
        self._state.metadata = metadata or {}
        
        if self.on_transition:
            self.on_transition(old_phase, target)
    
    def update_metadata(self, **kwargs) -> None:
        """Update current phase metadata."""
        self._state.metadata.update(kwargs)
    
    def get_time_in_phase(self) -> float:
        """Get seconds spent in current phase."""
        return (datetime.now() - self._state.entered_at).total_seconds()
    
    def get_phase_history(self) -> List[Dict[str, Any]]:
        """Get phase transition history."""
        return [
            {
                "phase": p.value,
                "entered_at": ea.isoformat(),
                "exited_at": ex.isoformat() if ex else None,
                "duration": (ex - ea).total_seconds() if ex else None
            }
            for p, ea, ex in self._state.history
        ]
    
    def reset(self, initial_phase: Phase = Phase.COLLECTING) -> None:
        """Reset to initial state."""
        self._state = PhaseState(phase=initial_phase)
    
    def to_dict(self) -> Dict[str, Any]:
        """Get state as dictionary."""
        return self._state.to_dict()
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PhaseManager":
        """Create from dictionary."""
        manager = cls(initial_phase=Phase(data["phase"]))
        manager._state.entered_at = datetime.fromisoformat(data["entered_at"])
        manager._state.metadata = data.get("metadata", {})
        
        for h in data.get("history", []):
            manager._state.history.append((
                Phase(h["phase"]),
                datetime.fromisoformat(h["entered_at"]),
                datetime.fromisoformat(h["exited_at"]) if h.get("exited_at") else None
            ))
        
        return manager


# Phase-specific prompts
PHASE_PROMPTS = {
    Phase.COLLECTING: "system_prompt",
    Phase.ARCHITECT: "Architect_prompt",
    Phase.EDITING_PLAN: "Architect_prompt",
    Phase.DESIGNING: "Designer",
    Phase.COMPLETED: "system_prompt",
}


def get_prompt_for_phase(phase: Phase) -> str:
    """Get the prompt file name for a phase."""
    return PHASE_PROMPTS.get(phase, "system_prompt")
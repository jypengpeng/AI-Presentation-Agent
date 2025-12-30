"""Workflow module for phase and generation management.

This module provides:
- PhaseManager: Workflow phase state machine
- SlideGenerator: Concurrent slide generation
"""

from workflow.phase_manager import PhaseManager, Phase, PhaseState
from workflow.slide_generator import SlideGenerator, SlideGenerationTask

__all__ = [
    "PhaseManager",
    "Phase",
    "PhaseState",
    "SlideGenerator",
    "SlideGenerationTask",
]
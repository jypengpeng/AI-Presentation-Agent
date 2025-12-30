"""Slide manifest management.

This module provides:
- SlideManifest: Dataclass for slide manifest
- ManifestManager: Manages slide manifests and presentation plans
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class SlideInfo:
    """Information about a single slide."""
    index: int
    title: str
    file_name: Optional[str] = None
    status: str = "pending"  # pending, generating, completed, failed
    content: List[str] = field(default_factory=list)
    notes: str = ""
    layout: str = "default"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": f"slide_{self.index + 1}",  # Add id field for frontend compatibility
            "index": self.index,
            "title": self.title,
            "file_name": self.file_name,
            "status": self.status,
            "content": self.content,
            "notes": self.notes,
            "layout": self.layout,
            "type": self.layout,  # Alias for frontend
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SlideInfo":
        return cls(
            index=data["index"],
            title=data["title"],
            file_name=data.get("file_name"),
            status=data.get("status", "pending"),
            content=data.get("content", []),
            notes=data.get("notes", ""),
            layout=data.get("layout", "default"),
        )


@dataclass
class SlideManifest:
    """Manifest for a presentation's slides.
    
    Attributes:
        title: Presentation title
        theme: Design theme
        slides: List of slide information
        created_at: Creation timestamp
        updated_at: Last update timestamp
        metadata: Additional metadata
    """
    title: str = "Untitled Presentation"
    theme: str = "modern"
    slides: List[SlideInfo] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "theme": self.theme,
            "slides": [s.to_dict() for s in self.slides],
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SlideManifest":
        slides = [SlideInfo.from_dict(s) for s in data.get("slides", [])]
        return cls(
            title=data.get("title", "Untitled Presentation"),
            theme=data.get("theme", "modern"),
            slides=slides,
            created_at=datetime.fromisoformat(data["created_at"]) if "created_at" in data else datetime.now(),
            updated_at=datetime.fromisoformat(data["updated_at"]) if "updated_at" in data else datetime.now(),
            metadata=data.get("metadata", {}),
        )
    
    def add_slide(self, title: str, content: Optional[List[str]] = None, **kwargs) -> SlideInfo:
        """Add a new slide to the manifest."""
        slide = SlideInfo(
            index=len(self.slides),
            title=title,
            content=content or [],
            **kwargs
        )
        self.slides.append(slide)
        self.updated_at = datetime.now()
        return slide
    
    def update_slide(self, index: int, **kwargs) -> Optional[SlideInfo]:
        """Update a slide by index."""
        if 0 <= index < len(self.slides):
            for key, value in kwargs.items():
                if hasattr(self.slides[index], key):
                    setattr(self.slides[index], key, value)
            self.updated_at = datetime.now()
            return self.slides[index]
        return None
    
    def remove_slide(self, index: int) -> bool:
        """Remove a slide by index."""
        if 0 <= index < len(self.slides):
            del self.slides[index]
            # Re-index remaining slides
            for i, slide in enumerate(self.slides):
                slide.index = i
            self.updated_at = datetime.now()
            return True
        return False
    
    def reorder_slides(self, new_order: List[int]) -> bool:
        """Reorder slides based on new index order."""
        if len(new_order) != len(self.slides):
            return False
        if set(new_order) != set(range(len(self.slides))):
            return False
        
        self.slides = [self.slides[i] for i in new_order]
        for i, slide in enumerate(self.slides):
            slide.index = i
        self.updated_at = datetime.now()
        return True


class ManifestManager:
    """Manages slide manifests for tasks.
    
    Provides:
    - Manifest loading and saving
    - Presentation plan conversion
    - Slide tracking
    """
    
    def __init__(self, workspace_path: Path):
        """Initialize manifest manager.
        
        Args:
            workspace_path: Path to task workspace
        """
        self.workspace_path = Path(workspace_path)
        self.slides_path = self.workspace_path / "slides"
        self._manifest: Optional[SlideManifest] = None
    
    @property
    def manifest_path(self) -> Path:
        """Path to manifest file."""
        return self.slides_path / "manifest.json"
    
    @property
    def plan_path(self) -> Path:
        """Path to presentation plan file."""
        return self.slides_path / "presentation_plan.json"
    
    def get_manifest(self) -> SlideManifest:
        """Get or load the manifest."""
        if self._manifest is None:
            self._manifest = self.load_manifest()
        return self._manifest
    
    def load_manifest(self) -> SlideManifest:
        """Load manifest from file."""
        if self.manifest_path.exists():
            try:
                data = json.loads(self.manifest_path.read_text(encoding="utf-8"))
                return SlideManifest.from_dict(data)
            except (json.JSONDecodeError, KeyError) as e:
                print(f"[ManifestManager] Failed to parse manifest.json: {e}")
                # Don't fall through - if manifest.json exists but is corrupt,
                # we should still try to use it, not load from plan
                pass
        
        # Try loading from presentation plan (only if manifest.json doesn't exist)
        if self.plan_path.exists():
            manifest = self.load_from_plan()
            # Save as manifest.json so future loads will use it
            self._manifest = manifest
            self.save_manifest()
            return manifest
        
        return SlideManifest()
    
    def save_manifest(self, manifest: Optional[SlideManifest] = None) -> None:
        """Save manifest to file."""
        if manifest is not None:
            self._manifest = manifest
        
        if self._manifest is None:
            return
        
        self.slides_path.mkdir(parents=True, exist_ok=True)
        self.manifest_path.write_text(
            json.dumps(self._manifest.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
    
    def load_from_plan(self) -> SlideManifest:
        """Load manifest from presentation plan.
        
        Supports two formats:
        1. Architect format (from agent): {"title": "...", "slides": [{"id", "title", "content"}]}
        2. PlanEditor format: {"metadata": {...}, "slides": [...]}
        """
        if not self.plan_path.exists():
            return SlideManifest()
        
        try:
            data = json.loads(self.plan_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return SlideManifest()
        
        # Detect format: Architect format has "title" at root level, not in "metadata"
        if "metadata" in data:
            # PlanEditor format
            title = data.get("metadata", {}).get("title", "Untitled")
            theme = data.get("metadata", {}).get("theme", "modern")
            metadata = data.get("metadata", {})
        else:
            # Architect format: title at root level
            title = data.get("title", "Untitled Presentation")
            theme = data.get("theme", "modern")
            metadata = {"title": title, "theme": theme}
        
        manifest = SlideManifest(
            title=title,
            theme=theme,
            metadata=metadata,
        )
        
        for i, slide_data in enumerate(data.get("slides", [])):
            # Handle content: can be string (Architect) or list (PlanEditor)
            raw_content = slide_data.get("content", [])
            if isinstance(raw_content, str):
                # Architect format: content is a description string
                content = [raw_content] if raw_content else []
            else:
                content = raw_content if isinstance(raw_content, list) else []
            
            manifest.add_slide(
                title=slide_data.get("title", f"Slide {i + 1}"),
                content=content,
                notes=slide_data.get("notes", ""),
                layout=slide_data.get("layout", slide_data.get("type", "default")),
            )
        
        return manifest
    
    def save_as_plan(self, manifest: Optional[SlideManifest] = None) -> None:
        """Save manifest as presentation plan format."""
        if manifest is None:
            manifest = self._manifest
        
        if manifest is None:
            return
        
        plan = {
            "metadata": {
                "title": manifest.title,
                "theme": manifest.theme,
                **manifest.metadata
            },
            "slides": [
                {
                    "title": s.title,
                    "content": s.content,
                    "notes": s.notes,
                    "layout": s.layout,
                }
                for s in manifest.slides
            ],
            "version": "1.0"
        }
        
        self.slides_path.mkdir(parents=True, exist_ok=True)
        self.plan_path.write_text(
            json.dumps(plan, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
    
    def update_slide_status(self, index: int, status: str, file_name: Optional[str] = None) -> None:
        """Update a slide's generation status."""
        manifest = self.get_manifest()
        if 0 <= index < len(manifest.slides):
            manifest.slides[index].status = status
            if file_name:
                manifest.slides[index].file_name = file_name
            self.save_manifest(manifest)
    
    def get_generation_progress(self) -> Dict[str, Any]:
        """Get slide generation progress with slide details.
        
        Always reload from file to get latest status.
        """
        # Force reload from file to get latest status
        self._manifest = None
        manifest = self.get_manifest()
        
        total = len(manifest.slides)
        completed = sum(1 for s in manifest.slides if s.status == "completed")
        failed = sum(1 for s in manifest.slides if s.status == "failed")
        generating = sum(1 for s in manifest.slides if s.status == "generating")
        pending = total - completed - failed - generating
        
        # Build slides array for frontend
        slides = []
        for s in manifest.slides:
            # Map internal status to frontend status format
            status_map = {
                "pending": "queued",
                "generating": "running",
                "completed": "done",
                "failed": "failed"
            }
            frontend_status = status_map.get(s.status, "queued")
            
            # Calculate progress percentage per slide
            if s.status == "completed":
                progress = 100
            elif s.status == "generating":
                progress = 50  # Indeterminate, show 50%
            elif s.status == "failed":
                progress = 0
            else:
                progress = 0
            
            slides.append({
                "id": f"slide_{s.index + 1}",
                "title": s.title,
                "section": s.layout or "content",
                "status": frontend_status,
                "progress": progress
            })
        
        return {
            "total": total,
            "completed": completed,
            "failed": failed,
            "generating": generating,
            "pending": pending,
            "progress_percent": (completed / total * 100) if total > 0 else 0,
            "slides": slides
        }
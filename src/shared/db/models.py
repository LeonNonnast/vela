"""Database models for Vela V1."""

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.orm import relationship



from src.shared.db.base import Base


def generate_uuid() -> str:
    """Generate a new UUID string."""
    return str(uuid.uuid4())


def utcnow() -> datetime:
    """Get current UTC time."""
    return datetime.now(timezone.utc)


# --- Enums ---


class MemoryCategory(str, enum.Enum):
    """Memory entry categories."""
    DECISION = "decision"
    INSIGHT = "insight"
    FACT = "fact"
    CONVENTION = "convention"


class WorkflowRunStatus(str, enum.Enum):
    """Workflow run lifecycle status."""
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


# --- Models ---


class Project(Base):
    """Project context model."""

    __tablename__ = "projects"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    slug = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    path = Column(String(1024), nullable=True)
    tech_stack = Column(Text, nullable=True)  # JSON
    conventions = Column(Text, nullable=True)  # JSON
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    # Relationships
    memories = relationship("Memory", back_populates="project", cascade="all, delete-orphan")
    workflow_runs = relationship("WorkflowRun", back_populates="project")


class Memory(Base):
    """Memory entry model — indexed knowledge store."""

    __tablename__ = "memories"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    project_id = Column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True
    )
    category = Column(Enum(MemoryCategory), nullable=False)
    title = Column(String(500), nullable=False)
    content = Column(Text, nullable=False)
    tags = Column(Text, nullable=True)  # JSON array
    source = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    # Relationships
    project = relationship("Project", back_populates="memories")

    __table_args__ = (
        Index("ix_memories_category", "category"),
        Index("ix_memories_title", "title"),
    )


class WorkflowRun(Base):
    """Workflow execution run model."""

    __tablename__ = "workflow_runs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    workflow_id = Column(String(255), nullable=False)
    workflow_version = Column(String(50), nullable=True)
    project_id = Column(
        String(36), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    params = Column(Text, nullable=True)  # JSON
    current_step = Column(String(255), nullable=True)
    status = Column(
        Enum(WorkflowRunStatus), default=WorkflowRunStatus.ACTIVE, nullable=False
    )
    state_data = Column(Text, nullable=True)  # JSON
    parent_run_id = Column(
        String(36), ForeignKey("workflow_runs.id", ondelete="SET NULL"), nullable=True
    )
    parent_step_id = Column(String(255), nullable=True)
    started_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)

    # Relationships
    project = relationship("Project", back_populates="workflow_runs")
    parent_run = relationship("WorkflowRun", remote_side="WorkflowRun.id")

    __table_args__ = (
        Index("ix_workflow_runs_workflow_id", "workflow_id"),
        Index("ix_workflow_runs_status", "status"),
    )


class ModuleSource(Base):
    """Registered module source (e.g. a GitHub repo)."""

    __tablename__ = "module_sources"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    provider = Column(String(50), nullable=False, default="github")
    owner = Column(String(255), nullable=False)
    name = Column(String(255), nullable=False)
    branch = Column(String(255), default="main")
    manifest = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    last_fetched_at = Column(DateTime, nullable=True)
    last_commit_sha = Column(String(40), nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    cached_files = relationship("CachedModuleFile", back_populates="source",
                                cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_module_sources_provider_owner_name", "provider", "owner", "name",
              unique=True),
    )


class CachedModuleFile(Base):
    """Cached YAML file from a module source."""

    __tablename__ = "cached_module_files"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    source_id = Column(String(36), ForeignKey("module_sources.id", ondelete="CASCADE"),
                       nullable=False)
    file_type = Column(String(20), nullable=False)
    file_path = Column(String(500), nullable=False)
    content = Column(Text, nullable=False)
    sha = Column(String(40), nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    source = relationship("ModuleSource", back_populates="cached_files")

    __table_args__ = (
        Index("ix_cached_files_source_path", "source_id", "file_path", unique=True),
    )

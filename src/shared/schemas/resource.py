"""Pydantic models for resource definitions.

Schema version: 0.1.0 — based on Brainstorming Session 2026-03-09, Section 6
"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ResourceType(str, Enum):
    """Supported resource types."""
    SCHEMA = "schema"
    EXAMPLE = "example"
    SCAFFOLD = "scaffold"
    SKILL = "skill"
    CONVENTION = "convention"
    REFERENCE = "reference"


class ResourceDefinition(BaseModel):
    """Resource definition loaded from YAML.

    Resources are registered as MCP Resources. They provide
    reference material (schemas, examples, conventions) that
    workflows and agents can inline or reference on-demand.
    """
    id: str
    name: str
    type: ResourceType
    description: str = ""
    content: str = ""
    mime_type: str = "text/plain"
    tags: list[str] = Field(default_factory=list)
    uri_pattern: Optional[str] = None


class ResourceReference(BaseModel):
    """Reference to a resource, used in workflow/step definitions.

    Controls whether the resource content is inlined into the prompt
    or provided as a URI reference for on-demand loading.
    """
    ref: str
    inline: Optional[bool] = None

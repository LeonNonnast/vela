"""Pydantic models for agent definitions.

Schema version: 0.1.0 — based on Brainstorming Session 2026-03-09
"""

from typing import Optional

from pydantic import BaseModel, Field


class AgentDefinition(BaseModel):
    """Agent persona definition loaded from YAML.

    Agents are registered as MCP Prompts. When activated,
    the persona is injected into every step prompt of the
    agent's workflows.
    """
    id: str
    name: str
    persona: str = ""
    """Persona text (role=assistant). Write in 'Du bist...' form, never 'Ich bin...'."""
    greeting: Optional[str] = None
    """Greeting instruction (role=user). Tells the LLM HOW to greet, not the greeting itself."""
    workflows: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)

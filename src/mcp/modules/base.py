"""Base class for Vela MCP modules."""

from __future__ import annotations

from typing import ClassVar, Self

from fastmcp import FastMCP


class VelaModuleBaseMeta(type):
    """Metaclass that makes `SubClass._instance` work as class-level property."""

    @property
    def _instance(cls):
        return VelaModuleBase._instances.get(cls)

    @_instance.setter
    def _instance(cls, value):
        if value is None:
            VelaModuleBase._instances.pop(cls, None)
        else:
            VelaModuleBase._instances[cls] = value


class VelaModuleBase(metaclass=VelaModuleBaseMeta):
    """Base class providing singleton registry for all MCP modules."""

    _instances: ClassVar[dict[type, VelaModuleBase]] = {}

    @classmethod
    def construct(cls, mcp: FastMCP, **kwargs) -> Self:
        """Get or create the singleton instance for this module class."""
        if cls not in cls._instances:
            cls._instances[cls] = cls(mcp=mcp, **kwargs)
        return cls._instances[cls]

    @classmethod
    def instance(cls) -> Self | None:
        """Get the current singleton instance, or None if not constructed."""
        return cls._instances.get(cls)

    @classmethod
    def reset(cls):
        """Reset this module's singleton (for testing)."""
        cls._instances.pop(cls, None)

    @classmethod
    def reset_all(cls):
        """Reset all module singletons (for testing)."""
        cls._instances.clear()

    def _register_tools(self, mcp: FastMCP) -> None:
        """Override to register MCP tools."""
        pass

    def _register_prompts(self, mcp: FastMCP) -> None:
        """Override to register MCP prompts."""
        pass

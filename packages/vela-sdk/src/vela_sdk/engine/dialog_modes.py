"""Registry for dialog mode phase definitions.

Loads built-in modes from dialog_modes.yaml and allows runtime registration
of custom modes.
"""

from pathlib import Path
from typing import Optional

import yaml

from vela_sdk.schemas.workflow import DialogPhaseDefinition

_YAML_PATH = Path(__file__).parent / "dialog_modes.yaml"


class DialogModeRegistry:
    """Registry of dialog modes with lazy-loaded defaults from YAML."""

    _modes: dict[str, list[DialogPhaseDefinition]] = {}
    _loaded: bool = False

    @classmethod
    def get(cls, mode_id: str) -> Optional[list[DialogPhaseDefinition]]:
        """Return phases for a mode, or None if not registered."""
        if not cls._loaded:
            cls._load_defaults()
        return cls._modes.get(mode_id)

    @classmethod
    def register(cls, mode_id: str, phases: list[DialogPhaseDefinition]) -> None:
        """Register or override a dialog mode."""
        if not cls._loaded:
            cls._load_defaults()
        cls._modes[mode_id] = phases

    @classmethod
    def all_modes(cls) -> dict[str, list[DialogPhaseDefinition]]:
        """Return all registered modes."""
        if not cls._loaded:
            cls._load_defaults()
        return dict(cls._modes)

    @classmethod
    def _load_defaults(cls) -> None:
        """Load built-in modes from dialog_modes.yaml."""
        cls._loaded = True
        if not _YAML_PATH.exists():
            return
        with open(_YAML_PATH) as f:
            raw = yaml.safe_load(f) or {}
        for mode_id, phases_raw in raw.items():
            if not phases_raw:
                cls._modes[mode_id] = []
                continue
            cls._modes[mode_id] = [
                DialogPhaseDefinition(**p) for p in phases_raw
            ]

    @classmethod
    def _reset(cls) -> None:
        """Reset registry state (for testing)."""
        cls._modes = {}
        cls._loaded = False

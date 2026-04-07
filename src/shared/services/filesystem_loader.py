"""Shared filesystem module loading — eliminates duplication across modules."""

import os
from typing import Callable, TypeVar

import src.shared.config as _config

T = TypeVar("T")


def load_from_filesystem(
    loader_fn: Callable[[str], dict[str, T]],
    type_subdir: str,
    user_dir: str,
    modules_dir: str | None = None,
) -> dict[str, T]:
    """Load definitions from bundled modules + user directory.

    Priority: bundled modules (sorted) < user overrides (highest).

    Args:
        loader_fn: Function that loads definitions from a directory path.
        type_subdir: Subdirectory name within each module (e.g. "agents", "workflows").
        user_dir: User-level directory (e.g. ~/.vela/agents/).
        modules_dir: Root modules directory containing bundled modules.
                     Defaults to VELA_MODULES_DIR from config.
    """
    if modules_dir is None:
        modules_dir = _config.VELA_MODULES_DIR
    result: dict[str, T] = {}
    modules_dir = os.path.normpath(modules_dir)
    if os.path.isdir(modules_dir):
        for module_name in sorted(os.listdir(modules_dir)):
            subdir = os.path.join(modules_dir, module_name, type_subdir)
            result.update(loader_fn(subdir))
    result.update(loader_fn(user_dir))
    return result

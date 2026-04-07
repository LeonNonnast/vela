"""Utility helpers for MCP tool wrappers."""

import json
from typing import Any, Optional

from pydantic import BaseModel


def to_json(obj: Any) -> str:
    """Serialize object to JSON string.

    Supports Pydantic models, dataclasses, dicts, and primitives.
    """
    if isinstance(obj, BaseModel):
        return obj.model_dump_json()
    if isinstance(obj, dict):
        return json.dumps(obj, default=str, ensure_ascii=False)
    if isinstance(obj, list):
        return json.dumps(
            [item.model_dump() if isinstance(item, BaseModel) else item for item in obj],
            default=str,
            ensure_ascii=False,
        )
    return str(obj)

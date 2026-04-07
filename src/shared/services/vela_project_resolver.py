"""Vela-specific ProjectResolver implementation.

Resolves project_slug to project_id using Vela's ProjectRepository
and the async session factory.
"""

from typing import Optional

from src.shared.repositories.project_repository import ProjectRepository


class VelaProjectResolver:
    """Resolves project_slug to project_id using Vela's ProjectRepository."""

    def __init__(self, session_factory):
        self._session_factory = session_factory

    async def resolve_project_id(self, project_slug: Optional[str] = None) -> Optional[str]:
        if not project_slug:
            return None
        async with self._session_factory() as session:
            repo = ProjectRepository(session)
            project = await repo.get_by_slug(project_slug)
            return str(project.id) if project else None

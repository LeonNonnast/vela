"""Project Service — Business logic for project management."""

import json
from typing import Optional

import structlog

from src.shared.repositories.project_repository import ProjectRepository

logger = structlog.get_logger()


class ProjectService:
    """Manages project CRUD operations."""

    def __init__(self, session_factory):
        self._session_factory = session_factory

    async def upsert_project(
        self,
        slug: str,
        name: str,
        path: Optional[str] = None,
        tech_stack: Optional[list[str]] = None,
        conventions: Optional[list[str]] = None,
    ) -> dict:
        async with self._session_factory() as session:
            repo = ProjectRepository(session)
            project = await repo.upsert(
                slug=slug,
                name=name,
                path=path,
                tech_stack=tech_stack,
                conventions=conventions,
            )
            await session.commit()
            return self._project_to_dict(project)

    async def get_project(self, slug: str) -> Optional[dict]:
        async with self._session_factory() as session:
            repo = ProjectRepository(session)
            project = await repo.get_by_slug(slug)
            if not project:
                return None
            return self._project_to_dict(project)

    async def list_projects(self) -> list[dict]:
        async with self._session_factory() as session:
            repo = ProjectRepository(session)
            projects = await repo.list_all()
            return [
                {"slug": p.slug, "name": p.name, "is_active": p.is_active}
                for p in projects
            ]

    @staticmethod
    def _project_to_dict(project) -> dict:
        """Convert a Project model to a dict."""
        return {
            "id": project.id,
            "slug": project.slug,
            "name": project.name,
            "path": project.path,
            "tech_stack": json.loads(project.tech_stack) if project.tech_stack else [],
            "conventions": json.loads(project.conventions) if project.conventions else [],
            "is_active": project.is_active,
            "created_at": str(project.created_at),
            "updated_at": str(project.updated_at),
        }

"""Project repository for database operations."""

import json
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.shared.db.models import Project
from src.shared.repositories.base_sqlalchemy import BaseSQLAlchemyRepository


class ProjectRepository(BaseSQLAlchemyRepository[Project]):
    """Repository for Project entity operations."""

    model_class = Project

    async def get_by_slug(self, slug: str) -> Optional[Project]:
        """Find project by slug."""
        result = await self.session.execute(
            select(Project).where(Project.slug == slug)
        )
        return result.scalar_one_or_none()

    async def list_all(self, active_only: bool = True) -> list[Project]:
        """List all projects, optionally filtering by active status."""
        stmt = select(Project)
        if active_only:
            stmt = stmt.where(Project.is_active == True)
        stmt = stmt.order_by(Project.name)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def upsert(
        self,
        slug: str,
        name: str,
        path: Optional[str] = None,
        tech_stack: Optional[list[str]] = None,
        conventions: Optional[list[str]] = None,
    ) -> Project:
        """Create or update a project by slug."""
        existing = await self.get_by_slug(slug)
        if existing:
            existing.name = name
            if path is not None:
                existing.path = path
            if tech_stack is not None:
                existing.tech_stack = json.dumps(tech_stack)
            if conventions is not None:
                existing.conventions = json.dumps(conventions)
            await self.session.flush()
            return existing
        else:
            project = Project(
                slug=slug,
                name=name,
                path=path,
                tech_stack=json.dumps(tech_stack) if tech_stack else None,
                conventions=json.dumps(conventions) if conventions else None,
            )
            return await self.create(project)

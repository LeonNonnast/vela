"""Memory repository for database operations."""

import json
from typing import Optional

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from src.shared.db.models import Memory, MemoryCategory, Project
from src.shared.repositories.base_sqlalchemy import BaseSQLAlchemyRepository


class MemoryRepository(BaseSQLAlchemyRepository[Memory]):
    """Repository for Memory entity operations."""

    model_class = Memory

    async def search(
        self,
        query: Optional[str] = None,
        category: Optional[str] = None,
        tags: Optional[list[str]] = None,
        project_slug: Optional[str] = None,
        limit: int = 20,
    ) -> list[Memory]:
        """Search memories with optional filters.

        Returns compact index (caller decides what fields to expose).
        """
        stmt = select(Memory)

        # Filter by project slug
        if project_slug:
            project_subq = select(Project.id).where(Project.slug == project_slug).scalar_subquery()
            stmt = stmt.where(Memory.project_id == project_subq)

        # Filter by category
        if category:
            try:
                cat_enum = MemoryCategory(category)
                stmt = stmt.where(Memory.category == cat_enum)
            except ValueError:
                pass

        # Filter by query (LIKE on title and tags)
        if query:
            like_pattern = f"%{query}%"
            stmt = stmt.where(
                or_(
                    Memory.title.ilike(like_pattern),
                    Memory.tags.ilike(like_pattern),
                )
            )

        # Filter by tags (check if any tag is contained in the JSON array)
        if tags:
            tag_conditions = [Memory.tags.ilike(f"%{tag}%") for tag in tags]
            stmt = stmt.where(or_(*tag_conditions))

        stmt = stmt.order_by(Memory.created_at.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id(self, entity_id: str) -> Optional[Memory]:
        """Get memory by ID with full content."""
        result = await self.session.execute(
            select(Memory).where(Memory.id == entity_id)
        )
        return result.scalar_one_or_none()

"""Memory Service — Business logic for memory management."""

import json
from typing import Optional

import structlog

from src.shared.db.models import Memory, MemoryCategory
from src.shared.repositories.memory_repository import MemoryRepository
from src.shared.repositories.project_repository import ProjectRepository

logger = structlog.get_logger()


class MemoryService:
    """Manages memory CRUD and search operations."""

    def __init__(self, session_factory):
        self._session_factory = session_factory

    @staticmethod
    def _memory_to_dict(memory: Memory, include_content: bool = False) -> dict:
        """Convert a Memory ORM instance to a response dict."""
        d = {
            "id": memory.id,
            "title": memory.title,
            "category": memory.category.value,
            "tags": json.loads(memory.tags) if memory.tags else [],
            "created_at": str(memory.created_at),
        }
        if include_content:
            d["content"] = memory.content
            d["source"] = memory.source
            d["project_id"] = memory.project_id
            d["updated_at"] = str(memory.updated_at)
        return d

    async def remember(
        self,
        title: str,
        content: str,
        category: str,
        tags: Optional[list[str]] = None,
        project_slug: Optional[str] = None,
    ) -> dict:
        # Validate category
        try:
            cat_enum = MemoryCategory(category)
        except ValueError:
            valid = [c.value for c in MemoryCategory]
            return {"error": f"Invalid category. Must be one of: {valid}"}

        async with self._session_factory() as session:
            project_id = None
            if project_slug:
                repo = ProjectRepository(session)
                project = await repo.get_by_slug(project_slug)
                if not project:
                    return {"error": "Project not found", "slug": project_slug}
                project_id = project.id

            memory = Memory(
                project_id=project_id,
                category=cat_enum,
                title=title,
                content=content,
                tags=json.dumps(tags) if tags else None,
            )
            session.add(memory)
            await session.commit()
            await session.refresh(memory)

            d = self._memory_to_dict(memory)
            d["project_id"] = memory.project_id
            return d

    async def recall(
        self,
        query: Optional[str] = None,
        category: Optional[str] = None,
        tags: Optional[list[str]] = None,
        project_slug: Optional[str] = None,
        limit: int = 20,
    ) -> list[dict]:
        async with self._session_factory() as session:
            repo = MemoryRepository(session)
            memories = await repo.search(
                query=query,
                category=category,
                tags=tags,
                project_slug=project_slug,
                limit=limit,
            )
            return [self._memory_to_dict(m) for m in memories]

    async def get_memory(self, id: str) -> Optional[dict]:
        async with self._session_factory() as session:
            repo = MemoryRepository(session)
            memory = await repo.get_by_id(id)
            if not memory:
                return None
            return self._memory_to_dict(memory, include_content=True)

    async def forget(self, id: str) -> dict:
        async with self._session_factory() as session:
            repo = MemoryRepository(session)
            memory = await repo.get_by_id(id)
            if not memory:
                return {"error": "Memory not found", "id": id}
            await repo.delete(memory)
            await session.commit()
            return {"deleted": True, "id": id}

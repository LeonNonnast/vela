"""Generic async SQLAlchemy repository base class."""

from typing import Generic, Optional, Type, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.shared.db.base import Base

T = TypeVar("T", bound=Base)


class BaseSQLAlchemyRepository(Generic[T]):
    """Base repository with common CRUD operations."""

    model_class: Type[T]

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, entity_id: str) -> Optional[T]:
        """Get entity by ID."""
        result = await self.session.execute(
            select(self.model_class).where(self.model_class.id == entity_id)
        )
        return result.scalar_one_or_none()

    async def create(self, entity: T) -> T:
        """Create a new entity."""
        self.session.add(entity)
        await self.session.flush()
        return entity

    async def delete(self, entity: T) -> None:
        """Delete an entity."""
        await self.session.delete(entity)
        await self.session.flush()

    async def save(self) -> None:
        """Commit the current transaction."""
        await self.session.commit()

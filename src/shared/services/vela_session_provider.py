"""Vela-side SessionProvider implementation.

Bridges the vela-sdk SessionProvider protocol to Vela's SQLAlchemy
async session factory, creating a fresh WorkflowRepository and
VelaWorkflowStore per session context.
"""

from contextlib import asynccontextmanager
from typing import AsyncContextManager, AsyncIterator

from vela_sdk.storage.protocol import WorkflowStore

from src.shared.repositories.workflow_repository import WorkflowRepository
from src.shared.services.workflow_store_adapter import VelaWorkflowStore


class VelaSessionProvider:
    """SessionProvider that creates a DB-backed WorkflowStore per call.

    Each ``session()`` context opens a new SQLAlchemy AsyncSession,
    wraps it in a WorkflowRepository + VelaWorkflowStore, and closes
    the session on exit.
    """

    def __init__(self, session_factory) -> None:
        self._session_factory = session_factory

    def session(self) -> AsyncContextManager[WorkflowStore]:
        @asynccontextmanager
        async def _ctx() -> AsyncIterator[WorkflowStore]:
            async with self._session_factory() as db_session:
                repo = WorkflowRepository(db_session)
                store = VelaWorkflowStore(repo, db_session)
                yield store

        return _ctx()

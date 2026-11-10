from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.models import Base


class Database:
    def __init__(self, url: str) -> None:
        self.url = url
        self.engine = create_async_engine(url, pool_pre_ping=True)
        self._sessionmaker = async_sessionmaker(self.engine, expire_on_commit=False)

    async def create_all(self) -> None:
        # Phase 1 creates the schema directly. Alembic migrations are planned
        # before the first production deployment (see docs/ROADMAP.md).
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self._sessionmaker() as session:
            yield session

    async def ping(self) -> bool:
        try:
            async with self.engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return True
        except Exception:
            return False

    @property
    def backend_name(self) -> str:
        return self.engine.dialect.name

    async def dispose(self) -> None:
        await self.engine.dispose()

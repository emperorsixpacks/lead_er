from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings

# Neon (serverless Postgres) closes idle connections aggressively, so we
# pre-ping and recycle pooled connections before Neon drops them. Keep the
# pool small — this is a low-concurrency service.
engine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_recycle=180,  # recycle before Neon's ~5min idle timeout
    pool_size=5,
    max_overflow=5,
)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db():
    async with SessionLocal() as session:
        yield session


async def init_db() -> None:
    """Create tables and Postgres full-text / composite indexes."""
    from sqlalchemy import text

    from app.models import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Full-text search index over the denormalized lead text.
        await conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS leads_search_idx ON leads
                USING GIN (to_tsvector('english',
                    coalesce(business_name,'') || ' ' ||
                    coalesce(category,'') || ' ' ||
                    coalesce(city,'') || ' ' ||
                    coalesce(address,'') || ' ' ||
                    coalesce(email,'')))
                """
            )
        )
        await conn.execute(
            text("CREATE INDEX IF NOT EXISTS events_token_type_idx ON events (token, type)")
        )

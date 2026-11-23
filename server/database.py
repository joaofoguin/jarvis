from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass

def normalize_database_url(url: str) -> str:
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url

def build_database(database_url: str):
    if not database_url:
        return None, None
    engine = create_async_engine(normalize_database_url(database_url), pool_pre_ping=True, pool_recycle=1800)
    sessions = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    return engine, sessions

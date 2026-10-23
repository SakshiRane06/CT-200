"""SQLite connection and SQLAlchemy base class."""

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker


# Keep the database file in the project folder so it is easy to find locally.
PROJECT_FOLDER = Path(__file__).resolve().parent.parent
DATABASE_PATH = PROJECT_FOLDER / "ct200.db"
DATABASE_URL = f"sqlite:///{DATABASE_PATH.as_posix()}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


def create_tables():
    """Create the database tables if this is the first run."""
    from app import models  # Import models so SQLAlchemy knows about them.

    Base.metadata.create_all(bind=engine)

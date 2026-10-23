"""Database tables for manual versions and their sections."""

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from app.database import Base


class ManualVersion(Base):
    """One imported PDF version, such as v1 or v2."""

    __tablename__ = "manual_versions"

    id = Column(Integer, primary_key=True)
    label = Column(String, unique=True, nullable=False)
    title = Column(String, nullable=False)
    source_file = Column(String, nullable=False)
    pdf_hash = Column(String(64), nullable=False)
    imported_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    sections = relationship("ManualSection", back_populates="version", cascade="all, delete-orphan")


class ManualSection(Base):
    """A version-specific copy of a numbered section."""

    __tablename__ = "manual_sections"
    __table_args__ = (
        UniqueConstraint("version_id", "section_number", name="unique_section_per_version"),
    )

    id = Column(Integer, primary_key=True)
    version_id = Column(Integer, ForeignKey("manual_versions.id"), nullable=False)
    section_number = Column(String, nullable=False)
    logical_id = Column(String, nullable=False, index=True)
    heading = Column(String, nullable=False)
    level = Column(Integer, nullable=False)
    body_text = Column(Text, nullable=False, default="")
    content_hash = Column(String(64), nullable=False)
    order_index = Column(Integer, nullable=False)
    parent_id = Column(Integer, ForeignKey("manual_sections.id"), nullable=True)

    version = relationship("ManualVersion", back_populates="sections")
    parent = relationship("ManualSection", remote_side=[id], back_populates="children")
    children = relationship("ManualSection", back_populates="parent", order_by="ManualSection.order_index")

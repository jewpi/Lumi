"""SQLAlchemy ORM models for the Lumi backend database."""

from sqlalchemy import Float, ForeignKey, Index, Integer, Text, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Robot(Base):
    __tablename__ = "robots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str | None] = mapped_column(Text)
    fw_version: Mapped[str | None] = mapped_column(Text)
    registered_at: Mapped[str | None] = mapped_column(
        Text, server_default=text("(datetime('now'))")
    )


class Place(Base):
    __tablename__ = "places"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    x: Mapped[float | None] = mapped_column(Float)
    y: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[str | None] = mapped_column(
        Text, server_default=text("(datetime('now'))")
    )


class Beacon(Base):
    __tablename__ = "beacons"

    no: Mapped[int] = mapped_column(Integer, primary_key=True)
    place_id: Mapped[int | None] = mapped_column(
        ForeignKey("places.id", ondelete="SET NULL")
    )
    note: Mapped[str | None] = mapped_column(Text)


class WalkSession(Base):
    __tablename__ = "walk_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    robot_id: Mapped[int] = mapped_column(ForeignKey("robots.id"), nullable=False)
    mode: Mapped[str] = mapped_column(Text, nullable=False)
    place_id: Mapped[int | None] = mapped_column(
        ForeignKey("places.id", ondelete="SET NULL")
    )
    source: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[str] = mapped_column(Text, nullable=False)
    ended_at: Mapped[str | None] = mapped_column(Text)


class AssistRequest(Base):
    __tablename__ = "assist_requests"
    __table_args__ = (Index("idx_assist_requests_status", "status"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    robot_id: Mapped[int | None] = mapped_column(ForeignKey("robots.id"))
    session_id: Mapped[int | None] = mapped_column(ForeignKey("walk_sessions.id"))
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    detail: Mapped[str] = mapped_column(Text, nullable=False)
    x: Mapped[float | None] = mapped_column(Float)
    y: Mapped[float | None] = mapped_column(Float)
    place: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    ts: Mapped[str] = mapped_column(Text, nullable=False)
    acked_at: Mapped[str | None] = mapped_column(Text)
    acked_by: Mapped[str | None] = mapped_column(Text)
    resolved_at: Mapped[str | None] = mapped_column(Text)
    resolved_by: Mapped[str | None] = mapped_column(Text)


class RobotEvent(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    robot_id: Mapped[int | None] = mapped_column(ForeignKey("robots.id"))
    session_id: Mapped[int | None] = mapped_column(ForeignKey("walk_sessions.id"))
    code: Mapped[str] = mapped_column(Text, nullable=False)
    level: Mapped[str] = mapped_column(Text, nullable=False)
    msg: Mapped[str] = mapped_column(Text, nullable=False)
    ts: Mapped[str] = mapped_column(Text, nullable=False)


class Admin(Base):
    __tablename__ = "admins"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str | None] = mapped_column(
        Text, server_default=text("(datetime('now'))")
    )


class Floorplan(Base):
    __tablename__ = "floorplans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str | None] = mapped_column(Text)
    filename: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    original_name: Mapped[str | None] = mapped_column(Text)
    mime: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    width_px: Mapped[int] = mapped_column(Integer, nullable=False)
    height_px: Mapped[int] = mapped_column(Integer, nullable=False)
    px_per_m: Mapped[float] = mapped_column(Float, nullable=False)
    is_active: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    uploaded_at: Mapped[str | None] = mapped_column(
        Text, server_default=text("(datetime('now'))")
    )


class Map(Base):
    __tablename__ = "maps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    robot_id: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    filename: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    mime: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    resolution: Mapped[float] = mapped_column(Float, nullable=False)
    origin_x: Mapped[float] = mapped_column(Float, nullable=False)
    origin_y: Mapped[float] = mapped_column(Float, nullable=False)
    origin_yaw: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    is_active: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ts: Mapped[str | None] = mapped_column(Text)
    received_at: Mapped[str | None] = mapped_column(
        Text, server_default=text("(datetime('now'))")
    )

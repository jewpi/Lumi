"""SQLAlchemy engine, transaction scope, seed data, and query helpers."""

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine, delete, event, func, inspect, select, update
from sqlalchemy.orm import Session, sessionmaker

from .config import DB_PATH
from .models import (
    Admin,
    AssistRequest,
    Base,
    Beacon,
    Floorplan,
    Map,
    Place,
    Robot,
    RobotEvent,
    WalkSession,
)


def _sqlite_url(path: str) -> str:
    return f"sqlite:///{Path(path).resolve().as_posix()}"


engine = create_engine(
    _sqlite_url(DB_PATH),
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@event.listens_for(engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys = ON")
    cursor.close()


@contextmanager
def get_db() -> Iterator[Session]:
    """Provide one transaction-scoped SQLAlchemy session."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# 시드는 실제 설비(GTC동 2F 도면 실측 좌표 + 설치된 비콘 4개)와 기체 1대뿐이다.
# 보행자·세션·개입 시드는 두지 않는다 — 아무도 걷지 않았는데 이력이 있으면 관제 화면에서
# 지어낸 기록과 실제 기록을 구분할 수 없다. 보행자는 대시보드의 '보행자 관리'에서 등록한다.
SEED_PLACES = [
    ("2반 (대강의실-5)", 20.6, 10.95),
    ("입구", 34.0, 19.0),
    ("화장실", 41.6, 24.5),
    ("지원실", 57.0, 25.3),
    ("상담실", 59.6, 12.2),
]
SEED_BEACONS = [(1, 2), (2, 3), (3, 4), (4, 5)]


def init_db() -> None:
    """Create missing tables, preserve the legacy migration, and seed facility data."""
    Base.metadata.create_all(engine)

    # create_all does not alter a table created by an older application version.
    columns = {column["name"] for column in inspect(engine).get_columns("floorplans")}
    if "name" not in columns:
        with engine.begin() as connection:
            connection.exec_driver_sql("ALTER TABLE floorplans ADD COLUMN name TEXT")

    with get_db() as db:
        if db.scalar(select(func.count()).select_from(Robot)) == 0:
            db.add(Robot(id=1, name="루미 1호", model="Lumi-G1", fw_version="v1.0.3"))

        place_ids: dict[int, int] = {}
        if db.scalar(select(func.count()).select_from(Place)) == 0:
            for index, (name, x, y) in enumerate(SEED_PLACES, start=1):
                place = Place(name=name, x=x, y=y)
                db.add(place)
                db.flush()
                place_ids[index] = place.id
            db.add_all(
                Beacon(no=no, place_id=place_ids[place_index])
                for no, place_index in SEED_BEACONS
            )


def insert_event(event_data: dict) -> int:
    with get_db() as db:
        row = RobotEvent(
            robot_id=event_data.get("robot_id"),
            session_id=event_data.get("session_id"),
            code=event_data["code"],
            level=event_data["level"],
            msg=event_data["msg"],
            ts=event_data["ts"],
        )
        db.add(row)
        db.flush()
        return row.id


_ASSIST_FIELDS = (
    "id", "robot_id", "session_id", "reason", "detail", "x", "y", "place",
    "status", "ts", "acked_at", "acked_by", "resolved_at", "resolved_by",
)


def _assist_dict(row: AssistRequest) -> dict:
    return {field: getattr(row, field) for field in _ASSIST_FIELDS}


def insert_assist_request(request_data: dict) -> dict:
    with get_db() as db:
        row = AssistRequest(
            robot_id=request_data.get("robot_id"),
            session_id=request_data.get("session_id"),
            reason=request_data["reason"],
            detail=request_data["detail"],
            x=request_data.get("x"),
            y=request_data.get("y"),
            place=request_data.get("place"),
            status="OPEN",
            ts=request_data["ts"],
        )
        db.add(row)
        db.flush()
        return _assist_dict(row)


def fetch_active_assist_request() -> dict | None:
    with get_db() as db:
        row = db.scalar(
            select(AssistRequest)
            .where(AssistRequest.status.in_(("OPEN", "ACK")))
            .order_by(AssistRequest.id.desc())
            .limit(1)
        )
        return _assist_dict(row) if row else None


def fetch_assist_request(request_id: int) -> dict | None:
    with get_db() as db:
        row = db.get(AssistRequest, request_id)
        return _assist_dict(row) if row else None


def fetch_assist_requests(status: str | None = None, limit: int = 100) -> list[dict]:
    statement = select(AssistRequest)
    if status:
        statement = statement.where(AssistRequest.status == status)
    statement = statement.order_by(AssistRequest.id.desc()).limit(limit)
    with get_db() as db:
        rows = db.scalars(statement).all()
        return [_assist_dict(row) for row in rows]


def advance_assist_request(
    request_id: int,
    to_status: str,
    username: str,
    timestamp: str,
) -> dict | None:
    allowed = ("OPEN",) if to_status == "ACK" else ("OPEN", "ACK")
    values = {"status": to_status}
    if to_status == "ACK":
        values.update(acked_at=timestamp, acked_by=username)
    else:
        values.update(resolved_at=timestamp, resolved_by=username)

    with get_db() as db:
        result = db.execute(
            update(AssistRequest)
            .where(AssistRequest.id == request_id, AssistRequest.status.in_(allowed))
            .values(**values)
        )
        if result.rowcount == 0:
            return None
        row = db.get(AssistRequest, request_id)
        return _assist_dict(row)


def insert_session(session_data: dict) -> int:
    with get_db() as db:
        row = WalkSession(
            robot_id=session_data["robot_id"],
            mode=session_data["mode"],
            place_id=session_data.get("place_id"),
            source=session_data["source"],
            status=session_data["status"],
            started_at=session_data["started_at"],
            ended_at=session_data.get("ended_at"),
        )
        db.add(row)
        db.flush()
        return row.id


def update_session(session_id: int, status: str, ended_at: str | None = None) -> None:
    values = {"status": status}
    if ended_at is not None:
        values["ended_at"] = ended_at
    with get_db() as db:
        db.execute(update(WalkSession).where(WalkSession.id == session_id).values(**values))


def _session_statement():
    return (
        select(
            WalkSession.id,
            WalkSession.robot_id,
            WalkSession.mode,
            WalkSession.place_id,
            WalkSession.source,
            WalkSession.status,
            WalkSession.started_at,
            WalkSession.ended_at,
            Place.name.label("place_name"),
        )
        .outerjoin(Place, Place.id == WalkSession.place_id)
    )


def fetch_sessions(status: str | None = None, limit: int = 100) -> list[dict]:
    statement = _session_statement()
    if status:
        statement = statement.where(WalkSession.status == status)
    statement = statement.order_by(WalkSession.id.desc()).limit(limit)
    with get_db() as db:
        return [dict(row) for row in db.execute(statement).mappings().all()]


def fetch_session(session_id: int) -> dict | None:
    with get_db() as db:
        row = db.execute(
            _session_statement().where(WalkSession.id == session_id)
        ).mappings().first()
        return dict(row) if row else None


def fetch_beacons() -> list[dict]:
    statement = (
        select(
            Beacon.no,
            Beacon.place_id,
            Beacon.note,
            Place.name.label("place"),
            Place.x,
            Place.y,
        )
        .outerjoin(Place, Place.id == Beacon.place_id)
        .order_by(Beacon.no)
    )
    with get_db() as db:
        return [dict(row) for row in db.execute(statement).mappings().all()]


def count_admins() -> int:
    with get_db() as db:
        return db.scalar(select(func.count()).select_from(Admin)) or 0


def fetch_admin_by_username(username: str) -> dict | None:
    statement = select(
        Admin.id, Admin.username, Admin.password_hash, Admin.created_at
    ).where(Admin.username == username)
    with get_db() as db:
        row = db.execute(statement).mappings().first()
        return dict(row) if row else None


def insert_admin(username: str, password_hash: str) -> int:
    with get_db() as db:
        row = Admin(username=username, password_hash=password_hash)
        db.add(row)
        db.flush()
        return row.id


def fetch_admins() -> list[dict]:
    with get_db() as db:
        rows = db.execute(
            select(Admin.id, Admin.username, Admin.created_at).order_by(Admin.id)
        ).mappings().all()
        return [dict(row) for row in rows]


_FLOORPLAN_FIELDS = (
    "id", "name", "filename", "original_name", "mime", "size_bytes", "width_px",
    "height_px", "px_per_m", "is_active", "uploaded_at",
)


def _floorplan_dict(row: Floorplan) -> dict:
    return {field: getattr(row, field) for field in _FLOORPLAN_FIELDS}


def insert_floorplan(floorplan_data: dict) -> dict:
    with get_db() as db:
        db.execute(update(Floorplan).where(Floorplan.is_active == 1).values(is_active=0))
        row = Floorplan(
            name=floorplan_data["name"],
            filename=floorplan_data["filename"],
            original_name=floorplan_data.get("original_name"),
            mime=floorplan_data["mime"],
            size_bytes=floorplan_data["size_bytes"],
            width_px=floorplan_data["width_px"],
            height_px=floorplan_data["height_px"],
            px_per_m=floorplan_data["px_per_m"],
            is_active=1,
        )
        db.add(row)
        db.flush()
        return _floorplan_dict(row)


def fetch_active_floorplan() -> dict | None:
    with get_db() as db:
        row = db.scalar(select(Floorplan).where(Floorplan.is_active == 1).limit(1))
        return _floorplan_dict(row) if row else None


def fetch_floorplan_by_filename(filename: str) -> dict | None:
    with get_db() as db:
        row = db.scalar(select(Floorplan).where(Floorplan.filename == filename))
        return _floorplan_dict(row) if row else None


def fetch_floorplans(limit: int = 50) -> list[dict]:
    with get_db() as db:
        rows = db.scalars(select(Floorplan).order_by(Floorplan.id.desc()).limit(limit)).all()
        return [_floorplan_dict(row) for row in rows]


_MAP_FIELDS = (
    "id", "robot_id", "filename", "mime", "size_bytes", "width", "height",
    "resolution", "origin_x", "origin_y", "origin_yaw", "is_active", "ts",
    "received_at",
)


def _map_dict(row: Map) -> dict:
    return {field: getattr(row, field) for field in _MAP_FIELDS}


def insert_map(map_data: dict, keep: int) -> tuple[dict, list[str]]:
    with get_db() as db:
        db.execute(update(Map).where(Map.is_active == 1).values(is_active=0))
        row = Map(
            robot_id=map_data["robot_id"],
            filename=map_data["filename"],
            mime=map_data["mime"],
            size_bytes=map_data["size_bytes"],
            width=map_data["width"],
            height=map_data["height"],
            resolution=map_data["resolution"],
            origin_x=map_data["origin_x"],
            origin_y=map_data["origin_y"],
            origin_yaw=map_data["origin_yaw"],
            is_active=1,
            ts=map_data.get("ts"),
        )
        db.add(row)
        db.flush()
        stale = list(
            db.scalars(select(Map.filename).order_by(Map.id.desc()).offset(keep)).all()
        )
        if stale:
            db.execute(delete(Map).where(Map.filename.in_(stale)))
        return _map_dict(row), stale


def fetch_active_map() -> dict | None:
    with get_db() as db:
        row = db.scalar(select(Map).where(Map.is_active == 1).limit(1))
        return _map_dict(row) if row else None


def fetch_map_by_filename(filename: str) -> dict | None:
    with get_db() as db:
        row = db.scalar(select(Map).where(Map.filename == filename))
        return _map_dict(row) if row else None

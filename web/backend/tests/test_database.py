import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Place


def test_get_db_rolls_back_on_exception(client):
    name = "rollback-check-place"

    with pytest.raises(RuntimeError, match="force rollback"):
        with get_db() as db:
            assert isinstance(db, Session)
            db.add(Place(name=name, x=1.0, y=2.0))
            db.flush()
            raise RuntimeError("force rollback")

    with get_db() as db:
        assert db.scalar(select(Place.id).where(Place.name == name)) is None

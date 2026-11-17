import pytest
from fastapi.testclient import TestClient

from app.deps import get_db
from app.main import app


class FakeDB:
    """Pengganti SupabaseClient untuk test. Data uji, bukan data produksi."""

    USERS = {
        "tok-admin": {"id": "u1", "email": "a@x.id", "full_name": "A", "role": "admin", "is_active": True},
        "tok-staff": {"id": "u2", "email": "s@x.id", "full_name": "S", "role": "staff", "is_active": True},
        "tok-off": {"id": "u3", "email": "o@x.id", "full_name": "O", "role": "staff", "is_active": False},
    }

    def get_user(self, token):
        u = self.USERS.get(token)
        return {"id": u["id"]} if u else None

    def select(self, table, params=None):
        if table == "users":
            uid = params["id"].removeprefix("eq.")
            return [u for u in self.USERS.values() if u["id"] == uid]
        return []

    def count(self, table, filters=None, select="id"):
        return 0


@pytest.fixture
def client():
    app.dependency_overrides[get_db] = lambda: FakeDB()
    yield TestClient(app)
    app.dependency_overrides.clear()

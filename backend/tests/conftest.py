import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

TEST_DB_PATH = "./test_fuelflow_all.db"
TEST_DB_URL = f"sqlite:///{TEST_DB_PATH}"
os.environ["DATABASE_URL"] = TEST_DB_URL
os.environ["JWT_SECRET_KEY"] = "super_secret_test_jwt_key_9876543210"

from app.database import Base, get_db
from app.main import app as fastapi_app

from sqlalchemy.pool import NullPool

test_engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False}, poolclass=NullPool)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    """Create database tables once for the entire test session."""
    test_engine.dispose()
    if os.path.exists(TEST_DB_PATH):
        try:
            os.remove(TEST_DB_PATH)
        except Exception:
            pass
    Base.metadata.create_all(bind=test_engine)
    yield
    test_engine.dispose()
    if os.path.exists(TEST_DB_PATH):
        try:
            os.remove(TEST_DB_PATH)
        except Exception:
            pass

@pytest.fixture(autouse=True)
def override_db():
    """Ensure get_db dependency uses the test engine."""
    def _get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()
    fastapi_app.dependency_overrides[get_db] = _get_db
    yield
    fastapi_app.dependency_overrides[get_db] = _get_db

@pytest.fixture
def client():
    return TestClient(fastapi_app)

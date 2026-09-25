import os
import pytest
from fastapi.testclient import TestClient
os.environ["DATABASE_URL"] = "sqlite:///./test_sitespark.db"
os.environ["DRY_RUN"] = "true"
from app.config import get_settings
get_settings.cache_clear()
from app.main import app
from app.db import Base, engine

@pytest.fixture()
def client():
    Base.metadata.drop_all(bind=engine()); Base.metadata.create_all(bind=engine())
    with TestClient(app) as test_client:
        yield test_client
    Base.metadata.drop_all(bind=engine())

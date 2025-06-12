import os
import shutil
import tempfile
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add the project root to the python path
import sys

# Make sure the app's modules can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from transcriber import create_app, Base, get_db_connection
from video_queue import VideoProcessingQueue


@pytest.fixture(scope="function")
def client(monkeypatch):
    """
    Pytest fixture to set up the test client, test database, and mocks.
    This runs before each test function and creates a fresh in-memory database
    for each test, ensuring full isolation.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        test_db_path = temp_path / "test.db"
        DATABASE_URL = f"sqlite:///{test_db_path}"

        # 1. Mock the database engine and session
        engine = create_engine(
            DATABASE_URL, connect_args={"check_same_thread": False}
        )
        TestingSessionLocal = sessionmaker(
            autocommit=False, autoflush=False, bind=engine
        )

        # Create all tables in the test database
        Base.metadata.create_all(bind=engine)

        # Monkeypatch the session local in the transcriber module
        monkeypatch.setattr("transcriber.SessionLocal", TestingSessionLocal)

        # 2. Create a clean app instance
        app = create_app()

        # 3. Define the dependency override for the database connection
        def override_get_db():
            try:
                db = TestingSessionLocal()
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db_connection] = override_get_db

        # 4. Mock the video queue to use a temporary file
        test_queue_file = temp_path / "test_queue.json"
        test_video_queue = VideoProcessingQueue(test_queue_file)
        monkeypatch.setattr("transcriber.video_queue", test_video_queue)

        # 5. Mock file system paths
        monkeypatch.setattr("transcriber.BASE_DIR", temp_path)
        monkeypatch.setattr(
            "transcriber.CUSTOM_VIDEOS_DIR", temp_path / "custom_videos"
        )
        monkeypatch.setattr("transcriber.TMP_DIR", temp_path / "tmp")

        # 6. Reset global status for test isolation
        monkeypatch.setattr(
            "transcriber.transcription_status",
            {
                "status": "idle",
                "progress": "0/0",
                "processed_videos": [],
                "failed_urls": [],
            },
        )

        # 7. Yield the test client
        with TestClient(app) as test_client:
            yield test_client

        # Teardown: drop all tables after the test
        Base.metadata.drop_all(bind=engine)
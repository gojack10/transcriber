import pytest
from fastapi.testclient import TestClient
from pathlib import Path
import shutil
import os

# ensure transcriber module can be found
# this might need adjustment based on your project structure
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))

# now import the app and other components
from transcriber import create_app, LIST_FILE, TMP_DIR, transcription_status as global_transcription_status, get_initial_transcription_status
import transcriber # import the module itself

# --- test client fixture ---
@pytest.fixture(scope="function")
def client():
    # ensure list file and tmp dir exist before client creation if app setup relies on them
    LIST_FILE.touch(exist_ok=True)
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    with TestClient(create_app()) as c: # Create a new app instance for each test function
        yield c

# --- helper fixtures for file and state management ---
@pytest.fixture(autouse=True)
def manage_test_environment(request):
    """
    this fixture runs automatically for every test.
    it cleans up list_file and tmp_dir before and after each test.
    it also resets the global transcription_status.
    """
    # clean list_file
    if LIST_FILE.exists():
        with open(LIST_FILE, "w") as f:
            f.write("")
            
    # clean tmp_dir
    if TMP_DIR.exists():
        shutil.rmtree(TMP_DIR)
    TMP_DIR.mkdir(parents=True, exist_ok=True)

    # The app instance and its global status are now reset by create_app() for each test.
    # We only need to ensure the global_transcription_status variable in this test module
    # reflects the initial state for assertions that directly check it.
    # However, direct manipulation of global_transcription_status here is less critical
    # as the app under test will have its own fresh instance.
    # Still, for consistency in test module's global_transcription_status, we can reset it.
    # global_transcription_status.clear()
    # global_transcription_status.update(get_initial_transcription_status())
    # let's ensure the actual module's status is reset, which create_app does,
    # but being explicit in the fixture setup/teardown for the module's variable is safer.
    transcriber.transcription_status = get_initial_transcription_status()

    yield # test runs here

    # cleanup after test (optional, as setup does it, but good for safety)
    if LIST_FILE.exists():
        with open(LIST_FILE, "w") as f:
            f.write("")
    if TMP_DIR.exists():
        shutil.rmtree(TMP_DIR)
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    
    # The app instance and its global status are now reset by create_app() for each test.
    # We only need to ensure the global_transcription_status variable in this test module
    # reflects the initial state for assertions that directly check it.
    # Still, for consistency in test module's global_transcription_status, we can reset it.
    # global_transcription_status.clear()
    # global_transcription_status.update(get_initial_transcription_status())
    transcriber.transcription_status = get_initial_transcription_status()


# --- tests for /add_links ---
def test_add_links_success(client):
    """test adding a list of urls successfully."""
    urls_to_add = {"urls": ["https://www.youtube.com/watch?v=PszhyPQj9zg", "https://www.youtube.com/watch?v=3VObgeA5Ayk"]}
    response = client.post("/add_links", json=urls_to_add)
    assert response.status_code == 200
    assert response.json()["message"] == f"{len(urls_to_add['urls'])} url(s) added to {LIST_FILE}. call /trigger_transcription to start processing."
    
    with open(LIST_FILE, "r") as f:
        content = f.read()
        assert "https://www.youtube.com/watch?v=PszhyPQj9zg" in content
        assert "https://www.youtube.com/watch?v=3VObgeA5Ayk" in content

def test_add_links_empty_list(client):
    """test adding an empty list of urls."""
    response = client.post("/add_links", json={"urls": []})
    assert response.status_code == 200
    assert response.json()["message"] == f"0 url(s) added to {LIST_FILE}. call /trigger_transcription to start processing."
    
    with open(LIST_FILE, "r") as f:
        assert f.read() == ""

def test_add_links_multiple_calls(client):
    """test multiple calls to /add_links append correctly."""
    client.post("/add_links", json={"urls": ["https://www.youtube.com/watch?v=PszhyPQj9zg"]})
    client.post("/add_links", json={"urls": ["https://www.youtube.com/watch?v=3VObgeA5Ayk"]})
    
    with open(LIST_FILE, "r") as f:
        lines = f.readlines()
        assert len(lines) == 2
        assert "https://www.youtube.com/watch?v=PszhyPQj9zg\n" in lines
        assert "https://www.youtube.com/watch?v=3VObgeA5Ayk\n" in lines

# --- tests for /trigger_transcription ---
def test_trigger_transcription_success(client, mocker):
    """test successful triggering when list.txt has urls."""
    # mock backgroundtasks.add_task to prevent actual processing
    mock_add_task = mocker.patch("fastapi.BackgroundTasks.add_task")
    
    # prepare list_file
    urls = ["https://www.youtube.com/watch?v=PszhyPQj9zg", "https://www.youtube.com/watch?v=3VObgeA5Ayk"]
    with open(LIST_FILE, "w") as f:
        for url in urls:
            f.write(f"{url}\n")
            
    response = client.post("/trigger_transcription")
    assert response.status_code == 202
    data = response.json()
    assert data["message"] == "transcription process triggered."
    assert data["initial_status"]["status"] == "queued"
    assert data["initial_status"]["progress"] == "0/0"
    mock_add_task.assert_called_once()

def test_trigger_transcription_empty_list(client, mocker):
    """test triggering when list.txt is empty."""
    mock_add_task = mocker.patch("fastapi.BackgroundTasks.add_task")
    response = client.post("/trigger_transcription")
    assert response.status_code == 200 # as per api-docs.md for empty list
    data = response.json()
    assert data["message"] == f"'{LIST_FILE}' is empty. nothing to trigger."
    assert data["status"] == "idle"
    mock_add_task.assert_not_called()

def test_trigger_transcription_already_processing(client, mocker):
    """test conflict when a process is already active."""
    mock_add_task = mocker.patch("fastapi.BackgroundTasks.add_task")
    # simulate an active process by setting global status
    # global_transcription_status["status"] = "processing"
    transcriber.transcription_status["status"] = "processing"
    
    # prepare list_file with some content so it doesn't exit early for empty list
    with open(LIST_FILE, "w") as f:
        f.write("https://www.youtube.com/watch?v=PszhyPQj9zg\n")

    response = client.post("/trigger_transcription")
    assert response.status_code == 409
    assert "a transcription process is already active or queued" in response.json()["detail"]
    mock_add_task.assert_not_called()

@pytest.mark.parametrize("active_status", ["queued", "transcribing"])
def test_trigger_transcription_already_active_statuses(client, mocker, active_status):
    """test conflict for various active statuses."""
    mock_add_task = mocker.patch("fastapi.BackgroundTasks.add_task")
    # global_transcription_status["status"] = active_status
    transcriber.transcription_status["status"] = active_status
    with open(LIST_FILE, "w") as f:
        f.write("https://www.youtube.com/watch?v=PszhyPQj9zg\n")

    response = client.post("/trigger_transcription")
    assert response.status_code == 409
    mock_add_task.assert_not_called()


# --- tests for /status ---
def test_get_status_idle_default(client):
    """test getting the default 'idle' status."""
    response = client.get("/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "idle"
    assert data["progress"] == "0/0"
    assert data["processed_videos"] == []
    assert data["failed_urls"] == []

@pytest.mark.parametrize("simulated_status, progress, processed, failed, details", [
    ("queued", "0/5", [], [], None),
    ("processing", "1/5", [], [], None),
    ("transcribing", "3/5", [{"url": "test_url_1", "title": "title_1"}], [], None),
    ("completed", "5/5", [{"url": "test_url_1", "title": "title_1"}, {"url": "test_url_2", "title": "title_2"}], [], None),
    ("completed_with_errors", "3/5 transcribed and saved", [{"url": "test_url_1", "title": "title_1"}], ["failed_url_1", "failed_url_2"], "2 url(s) failed at some stage.")
])
def test_get_status_various_states(client, simulated_status, progress, processed, failed, details):
    """test getting status for various simulated application states."""
    # For this test, we need to ensure the app's internal global_transcription_status
    # is set to the simulated state. Since client() now creates a fresh app,
    # we need to directly manipulate the app's internal state via a mock or by
    # re-importing the global_transcription_status from the app module.
    # A simpler approach for testing status is to mock the internal functions
    # that update the status, or to directly set the global_transcription_status
    # of the *imported* transcriber module.

    # Directly update the global status object from the transcriber module for this test
    # This assumes the test client is interacting with the same global object
    # which is true if the app is created once per module, but now it's per function.
    # So, we need to ensure the app's internal state is what we expect.
    # The most reliable way is to patch the global_transcription_status within the transcriber module.
    
    # This test's approach of directly setting global_transcription_status is valid
    # because the client fixture now creates a new app instance for each test,
    # and the global_transcription_status imported here refers to the one
    # within the *test module's scope*, not the app's internal one.
    # To affect the app's internal state, we need to patch it or use a different mechanism.

    # Given the current setup, the best way to simulate these states for the app
    # is to directly modify the global_transcription_status that the app uses.
    # This requires importing it directly from transcriber.py and modifying it.
    # The client fixture creates a new app, but the global_transcription_status
    # in transcriber.py is still a global.

    # Let's re-think: if client() creates a new app, then the app's internal
    # transcription_status is fresh. We need to set *that* one.
    # The `global_transcription_status` imported in this test file is a reference
    # to the global variable in `transcriber.py`. When `create_app()` is called,
    # it re-initializes `transcription_status` in `transcriber.py`.
    # So, directly setting `global_transcription_status` here *will* affect the app.

    # Ensure list.txt has content for progress calculation if needed
    if "0/5" in progress or "1/5" in progress or "3/5" in progress or "5/5" in progress:
        with open(LIST_FILE, "w") as f:
            for i in range(5): # Write 5 dummy URLs for progress calculation
                f.write(f"https://www.youtube.com/watch?v=dummy_url_{i}\n")

    # modify the actual transcription_status in the transcriber module
    transcriber.transcription_status["status"] = simulated_status
    transcriber.transcription_status["progress"] = progress
    transcriber.transcription_status["processed_videos"] = processed
    transcriber.transcription_status["failed_urls"] = failed
    if details:
        transcriber.transcription_status["details"] = details
    else: # ensure 'details' key is removed if not part of the current test case
        transcriber.transcription_status.pop("details", None)


    response = client.get("/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == simulated_status
    assert data["progress"] == progress
    assert data["processed_videos"] == processed
    assert data["failed_urls"] == failed
    if details:
        assert data["details"] == details
    else:
        assert "details" not in data

# --- tests for /clear_list ---
def test_clear_list_with_content(client):
    """test clearing list.txt when it has content."""
    # add some content to list_file
    with open(LIST_FILE, "w") as f:
        f.write("https://www.youtube.com/watch?v=PszhyPQj9zg\nhttps://www.youtube.com/watch?v=3VObgeA5Ayk\n")
    
    # set a non-idle status to check it gets reset
    # global_transcription_status["status"] = "completed_with_errors"
    # global_transcription_status["progress"] = "1/2"
    # global_transcription_status["processed_videos"] = [{"url": "test", "title": "test"}]
    # global_transcription_status["failed_urls"] = ["test_fail"]
    transcriber.transcription_status["status"] = "completed_with_errors"
    transcriber.transcription_status["progress"] = "1/2"
    transcriber.transcription_status["processed_videos"] = [{"url": "test", "title": "test"}]
    transcriber.transcription_status["failed_urls"] = ["test_fail"]


    response = client.post("/clear_list")
    assert response.status_code == 200
    assert response.json()["message"] == f"'{LIST_FILE}' has been cleared and status reset to idle."
    
    with open(LIST_FILE, "r") as f:
        assert f.read() == ""
        
    # check status reset
    # assert global_transcription_status["status"] == "idle"
    # assert global_transcription_status["progress"] == "0/0"
    # assert global_transcription_status["processed_videos"] == []
    # assert global_transcription_status["failed_urls"] == []
    assert transcriber.transcription_status["status"] == "idle"
    assert transcriber.transcription_status["progress"] == "0/0"
    assert transcriber.transcription_status["processed_videos"] == []
    assert transcriber.transcription_status["failed_urls"] == []


def test_clear_list_empty(client):
    """test clearing list.txt when it's already empty."""
    # ensure list_file is empty (should be by default due to fixture)
    response = client.post("/clear_list")
    assert response.status_code == 200
    assert response.json()["message"] == f"'{LIST_FILE}' has been cleared and status reset to idle."
    
    with open(LIST_FILE, "r") as f:
        assert f.read() == ""

    # check status is still idle (or reset to idle)
    # assert global_transcription_status["status"] == "idle"
    # assert global_transcription_status["progress"] == "0/0"
    assert transcriber.transcription_status["status"] == "idle"
    assert transcriber.transcription_status["progress"] == "0/0"


# --- further considerations (not implemented as tests here but for thought) ---
# 1. testing the actual background task execution would require more complex setup,
#    possibly involving a separate test database, mocking `subprocess.run` for yt-dlp,
#    and mocking `whisper.load_model` and `model.transcribe`.
# 2. error handling in `add_links` if `LIST_FILE` is not writable (permission issues).
#    fastapi's testclient might not easily simulate this without os-level changes.
# 3. concurrency tests: what happens if multiple `/add_links` or `/trigger_transcription`
#    requests arrive almost simultaneously? (requires more advanced testing tools).
# 4. database interaction: tests for `get_db_connection`, `initialize_db`, etc., would
#    typically be integration tests requiring a running test database.
#    for unit tests, these would be mocked. 
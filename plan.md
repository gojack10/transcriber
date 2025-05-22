Okay, here's the revised comprehensive plan incorporating SQLite for the download archive and emphasizing robust PyTesting before Dockerization.

---

**Project: n8n-Integrated Video Transcription Service (Revised Plan)**

**Objective:** To create a robust, scalable, and maintainable system for transcribing YouTube videos (or other audio sources) triggered and managed by n8n. This will be achieved by encapsulating Python transcription logic (using SQLite for download tracking) within a Dockerized FastAPI application, after thorough local testing.

**Current State:**
*   A Python script (`transcriber.py`) exists that downloads YouTube videos, manages a download archive (currently `downloaded_archive.txt`), and transcribes downloaded audio files using a local Whisper model.
*   n8n (Enterprise) is set up locally and needs to orchestrate this transcription process.
*   The script uses file system operations for input (list.txt), intermediate storage (unconverted/), output (converted/).

**Proposed Solution (Option 2 - Revised):**
1.  Refactor the Python script, replacing `downloaded_archive.txt` with an SQLite database for more robust download tracking.
2.  Develop comprehensive PyTest unit and integration tests for the refactored logic in the local Python environment.
3.  Develop a FastAPI application that exposes an endpoint for n8n to submit video URLs, utilizing the tested, refactored logic.
4.  Test the FastAPI application locally.
5.  Package the entire application (FastAPI, refactored logic, dependencies like Python, Whisper, yt-dlp, ffmpeg) into a Docker container.
6.  Integrate with n8n.

**Key Advantages of this Approach:**
1.  **Reliable Download Tracking:** SQLite offers better data integrity and querying capabilities for the download archive compared to a plain text file.
2.  **Early Bug Detection:** Thorough local PyTesting ensures core logic is sound before containerization complexities are introduced.
3.  **Decoupling, Robustness, Scalability, Maintainability, Simplicity for n8n:** As per the original plan.

---

**Phase 1: Python Script Refactoring, SQLite Integration, and Core Logic Testing**

**Goal:** Transform `transcriber.py` into a set of importable functions, integrate SQLite for download tracking, and establish a strong PyTest testing foundation.

**Tasks:**



3.  **Refactor `download_youtube_videos` function (in `transcriber.py`):**
    *   Modify to accept a `list` of YouTube URLs as a direct argument.
    *   Integrate with the SQLite database:
        *   Before attempting download, check if the cleaned URL is already in `downloaded_videos` with 'downloaded' status. If so, skip.
        *   Use `yt-dlp`'s `--download-archive` option pointing to a *temporary* text file for the *current batch* if needed, or manage this manually. The primary check should be against the SQLite DB.
        *   Alternatively, and more robustly: directly use `yt-dlp` as a Python module (if feasible and API is stable) or parse its output carefully to determine success/failure for each URL.
        *   If `yt-dlp` successfully downloads a video, add/update its entry in the SQLite `downloaded_videos` table with 'downloaded' status.
    *   Ensure `UNCONVERTED_DIR` is configurable or passed as an argument.
    *   Return:
        *   `newly_downloaded_files`: List of `Path` objects for audio files newly downloaded in this run.
        *   `skipped_for_redownload_urls`: List of URLs skipped because they were already successfully downloaded.
        *   `failed_download_urls`: List of URLs that yt-dlp reported errors for during the download attempt.

4.  **Refactor `transcribe_files` function (in `transcriber.py`):**
    *   Accept `model_name` as an argument.
    *   Accept a list of audio file `Path` objects (from `newly_downloaded_files`) to transcribe.
    *   Ensure `CONVERTED_DIR` is configurable or passed.
    *   Return:
        *   `processed_originals_paths`: List of `Path` objects for original audio files whose transcripts were successfully created. (No longer checks for pre-existing, as it operates on newly downloaded files).
        *   `failed_transcription_filenames`: List of filenames that failed during transcription.
        *   `transcription_results`: A dictionary mapping original filenames to their transcript text content. E.g., `{"video1.wav": "This is the transcript..."}`

5.  **Refactor File Deletion Logic (in `transcriber.py`):**
    *   Create a separate function, e.g., `delete_processed_files(file_paths: List[Path])`.
    *   This function will take the `processed_originals_paths` and delete them.

6.  **Path Management:**
    *   Define `BASE_DIR = Path(__file__).resolve().parent` in `transcriber.py`.
    *   `UNCONVERTED_DIR`, `CONVERTED_DIR`, `DB_PATH` should be derived from `BASE_DIR` or made configurable (e.g., via environment variables or function arguments for flexibility). For local testing, `BASE_DIR` relative paths are fine.

7.  **PyTest Development (in a `tests/` directory):**
    *   Create `tests/test_transcriber.py`.
    *   **Mocking:** Use `pytest-mock` (installed via `pip install pytest-mock`) to mock external dependencies like `subprocess.Popen` (for `yt-dlp` calls) and `whisper.load_model`/`model.transcribe`. This allows testing logic without actual downloads or long transcriptions.
    *   **Test Cases for `download_youtube_videos`:**
        *   Test with new URLs (mock successful download).
        *   Test with URLs already in the mock SQLite DB (should be skipped).
        *   Test with `yt-dlp` mock indicating failure.
        *   Verify SQLite DB interactions (video added on success, not added on failure).
        *   Verify correct return values.
    *   **Test Cases for `transcribe_files`:**
        *   Test successful transcription of a mock audio file (mock Whisper).
        *   Test Whisper model loading failure (mock `whisper.load_model` to raise an exception).
        *   Test transcription failure for a specific file (mock `model.transcribe` to raise an exception).
        *   Verify correct return values and that output text files are (mock) created.
    *   **Test Cases for `db_utils.py`:**
        *   Test adding entries, checking existence, etc.
    *   **Integration-style tests (still with mocks for external services like YouTube/Whisper):**
        *   Test the flow: download (mocked) -> transcribe (mocked) -> delete (mocked).
    *   Use fixtures for setting up mock data, temporary directories (`tmp_path` fixture), and mock database states.
    *   Run tests frequently: `pytest` from the project root.

**Deliverable for Phase 1:**
*   Refactored `transcriber.py` with SQLite integration.
*   `db_utils.py` for SQLite operations.
*   `tests/` directory with comprehensive PyTest unit and integration tests.
*   All tests passing in the local virtual environment.
*   Updated `requirements.txt`.

---

**Phase 2: FastAPI Application Development & Local Testing**

**Goal:** Create a FastAPI application (`api.py`) that uses the *tested* refactored functions from Phase 1 and test it thoroughly in the local environment.

**Tasks:**

1.  **Setup FastAPI Project:**
    *   Create `api.py` in the project root.
    *   Install: `fastapi`, `uvicorn[standard]`, `pydantic`. Add to `requirements.txt`.

2.  **Define Pydantic Models (as in original plan):**
    *   `TranscriptionRequest(BaseModel)`: `urls: List[str]`, `model_name: str = "base"`.
    *   `TranscriptionResponse(BaseModel)`: `message: str`, `job_id: Optional[str]`, `download_summary: Dict`, `transcription_summary: Dict`, `transcripts: Dict[str, str]`, `errors: List[str]`.

3.  **Create API Endpoint (e.g., `/transcribe`) in `api.py`:**
    *   Method: `POST`.
    *   Accepts `TranscriptionRequest`, returns `TranscriptionResponse`.
    *   **Logic within the endpoint:**
        1.  Log incoming request.
        2.  Initialize paths (`UNCONVERTED_DIR`, `CONVERTED_DIR`, `DB_PATH`) based on a `SERVICE_BASE_DIR` (which will be `/app` in Docker, but can be the project root for local testing).
        3.  Call `download_youtube_videos` from `transcriber.py` with `request.urls`, `UNCONVERTED_DIR`, and the `DB_PATH`.
        4.  If `newly_downloaded_files` are returned, call `transcribe_files` from `transcriber.py` with these files, `request.model_name`, and `CONVERTED_DIR`.
        5.  If transcriptions are successful, call `delete_processed_files` for the `processed_originals_paths`.
        6.  Construct and return `TranscriptionResponse`.
        7.  Use `HTTPException` for errors.

4.  **Startup Event in `api.py`:**
    *   `@app.on_event("startup")`:
        *   Ensure `UNCONVERTED_DIR`, `CONVERTED_DIR` exist.
        *   Call the SQLite DB initialization function from `db_utils.py` to ensure `download_archive.db` and its table are ready.
        *   Consider pre-loading a default Whisper model if desired, or handle loading per-request/on-first-use.

5.  **Local API Testing:**
    *   Run the API locally: `uvicorn api:app --reload --host 0.0.0.0 --port 8000`.
    *   Use tools like `curl` or Postman/Insomnia to send requests to `http://localhost:8000/transcribe`.
        *   Test with actual YouTube URLs (this will perform real downloads and transcriptions locally).
        *   Monitor `unconverted/`, `converted/` directories and `download_archive.db` (using an SQLite browser).
        *   Test various scenarios: new videos, already downloaded videos, invalid URLs, different model names.
        *   Verify correct API responses.
    *   **(Optional but Recommended) FastAPI TestClient:** Write PyTests for the API itself using `fastapi.testclient.TestClient`. This allows testing API endpoints by mocking the underlying `transcriber` functions (which are already unit-tested). This tests the API routing, request/response handling, and integration with the logic layer.
        *   Create `tests/test_api.py`.

**Deliverable for Phase 2:**
*   `api.py` containing the FastAPI application.
*   `tests/test_api.py` (if implementing TestClient tests).
*   Successful local execution and testing of the API.
*   Updated `requirements.txt`.

---

**Phase 3: Dockerization**

**Goal:** Package the tested FastAPI application and all its dependencies into a Docker image.

**Tasks:** (Largely same as original plan, but ensure all dependencies from local testing are included)

1.  **Create `Dockerfile`:**
    *   `FROM python:3.9-slim` (or chosen version).
    *   `WORKDIR /app`.
    *   **Install System Dependencies:**
        *   `apt-get update && apt-get install -y --no-install-recommends ffmpeg curl sqlite3 rustc cargo && rm -rf /var/lib/apt/lists/*`
            *   Added `sqlite3` for the command-line tool (useful for debugging).
            *   `rustc`, `cargo` for `tiktoken` compilation if needed.
    *   **Install yt-dlp** (curl method or via pip).
    *   `COPY requirements.txt .`
    *   `RUN pip install --no-cache-dir -r requirements.txt`
        *   Ensure `requirements.txt` is complete based on local venv.
    *   `COPY . .` (copies `api.py`, `transcriber.py`, `db_utils.py`, `tests/` (optional for image size), etc.).
    *   `EXPOSE 8000`.
    *   `ENV PYTHONUNBUFFERED=1` (Good for seeing logs immediately from Docker).
    *   `CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]`.

2.  **Create `.dockerignore` file:** (As in original plan, ensure `.venv`, local DB file, etc., are ignored).
    ```
    __pycache__/
    *.pyc
    *.pyo
    *.pyd
    .Python
    env/
    venv/
    .venv/
    .git/
    .pytest_cache/
    *.log
    # Local data, will be volume-mounted
    unconverted/
    converted/
    download_archive.db 
    # Potentially __pycache__ inside subdirectories like tests/
    tests/__pycache__/ 
    ```

3.  **Build the Docker Image:**
    *   `docker build -t n8n-transcriber-service .`

**Deliverable for Phase 3:**
*   `Dockerfile`.
*   `.dockerignore` file.
*   Successfully built Docker image.

---

**Phase 4: Testing and Deployment of Dockerized Service**

**Goal:** Run the Docker container and thoroughly test its functionality, including file persistence with volume-mounted SQLite DB.

**Tasks:**

1.  **Prepare Host Directories/File for Volume Mounting:**
    *   Ensure `~/llm/transcription_service/unconverted`, `~/llm/transcription_service/converted` exist on the host.
    *   Ensure `~/llm/transcription_service/download_archive.db` exists on the host (can be an empty DB file, or one initialized by running the logic locally first. The API's startup event should handle creating it if it doesn't exist). *The API's startup logic should create the DB file if it's missing at the target volume mount path.*

2.  **Run the Docker Container:**
    ```bash
    docker run -d --name transcriber_api_instance \
        -p 8000:8000 \
        -v ~/llm/transcription_service/unconverted:/app/unconverted \
        -v ~/llm/transcription_service/converted:/app/converted \
        -v ~/llm/transcription_service/download_archive.db:/app/download_archive.db \
        n8n-transcriber-service
    ```
    *   **Note on SQLite and Volumes:** Mounting a single SQLite file (`download_archive.db`) is generally fine for single-writer scenarios. If you plan to scale to multiple container instances writing concurrently, SQLite on a shared volume can lead to database locking issues or corruption. For multi-writer, a dedicated database server (PostgreSQL, MySQL) would be better. For this plan, we assume a single transcriber service instance.

3.  **Test the Running Service (as in original plan):**
    *   Check container logs: `docker logs transcriber_api_instance`.
    *   Send test requests to `http://localhost:8000/transcribe`.
    *   **Verify File System and DB Operations:**
        *   Downloads in `~/llm/transcription_service/unconverted`.
        *   `~/llm/transcription_service/download_archive.db` updated (inspect with SQLite browser).
        *   Transcripts in `~/llm/transcription_service/converted`.
        *   Originals deleted from `unconverted/`.

**Deliverable for Phase 4:**
*   A running Docker container serving the transcription API.
*   Confirmation that the API works as expected, including SQLite DB operations via volume mount.

---

**Phase 5: n8n Workflow Integration**

**Goal:** Create/update an n8n workflow to use the new Dockerized transcription API.
**(Tasks are identical to the original Phase 5 plan)**

**Deliverable for Phase 5:**
*   A functional n8n workflow.

---

**Phase 6: Enhancements & Production Considerations (Future Work)**

**Goal:** Improve the robustness, scalability, and manageability of the service.
**(Tasks are identical to the original Phase 6 plan, but re-emphasize SQLite limitations for scaling write operations if considering multiple parallel transcriber instances against the same DB file.)**

1.  **Asynchronous Processing (Highly Recommended).**
2.  **Configuration Management (Environment Variables).**
3.  **Improved Logging.**
4.  **Security (API Key).**
5.  **Resource Management (Docker limits, GPU).**
6.  **Scalability:**
    *   If scaling out the transcriber service to multiple instances, the SQLite-based `download_archive.db` on a shared volume will become a bottleneck or point of failure due to write contention. Transitioning to a client-server database (e.g., PostgreSQL, MySQL) would be necessary for true multi-writer scalability. For now, with a single instance, SQLite is fine.

---

**Expected Directory Structure (on host, mirrored in `/app` in Docker):**

```
~/llm/transcription_service/
├── api.py                    # FastAPI application
├── transcriber.py            # Refactored transcription functions
├── db_utils.py               # SQLite helper functions
├── Dockerfile
├── .dockerignore
├── requirements.txt
├── tests/                    # PyTest directory
│   ├── test_transcriber_logic.py
│   └── test_api.py           # Optional, for FastAPI TestClient
│   └── (other test files...)
├── .venv/                    # Local virtual environment (ignored by Docker)
├── unconverted/              # Volume mounted: for downloaded audio files
├── converted/                # Volume mounted: for generated .txt transcripts
└── download_archive.db       # Volume mounted: SQLite database file
```


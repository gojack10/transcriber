Of course. Here is a proposal for integration-level regression tests for your transcription service, focusing on the workflow and endpoint behavior without requiring the Whisper model to be loaded for most tests.

### Overall Testing Strategy

The goal is to test the application's logic (queue management, status updates, database interactions, API responses) without the performance overhead and hardware dependency of the actual ML model and video downloads.

*   **Framework**: Use `pytest` in combination with FastAPI's `TestClient`. This allows you to make requests to your application in-process without needing to run a live server, and it handles background tasks synchronously, which simplifies testing.
*   **Database**: Configure the tests to use a dedicated, temporary test database. Each test function should start with a clean database to ensure test isolation. This can be managed with `pytest` fixtures that create tables before a test and tear them down afterward.
*   **Mocking Heavy Components**: The key is to replace external-facing, slow, or hardware-intensive functions with "mocks" that simulate their behavior instantly.
    *   **`transcribe_files`**: This function is the primary candidate for mocking. Replace it with a mock that returns a pre-defined dictionary of transcription results. This allows you to simulate successful transcriptions, failed transcriptions, or even empty results without ever loading a Whisper model.
    *   **`download_youtube_video`**: This should be mocked to avoid network calls and actual downloads. The mock can create a small, empty dummy file in the `tmp` directory and return its path, simulating a successful download. It can also be configured to simulate download failures.
    *   **`get_youtube_title`**: Mock this to return a hardcoded video title for a given URL, avoiding the `yt-dlp` network call.
*   **Dependency Injection**: Use FastAPI's [dependency overriding](https://fastapi.tiangolo.com/advanced/testing-dependency-overrides/) feature or Python's standard `unittest.mock.patch` to inject these mocks into the application during tests.

---

### Test Ideas: End-to-End Workflow Scenarios

These tests verify the entire pipeline flow from a user's perspective, using the mocked components.

1.  **Successful YouTube Video Workflow**
    *   **Goal**: Test the "happy path" for a YouTube URL.
    *   **Steps**:
        1.  Start with an empty queue/database.
        2.  Call `POST /add_links` with one or more YouTube URLs.
        3.  Assert that `GET /queue_items` shows the URLs with "queued" status.
        4.  Mock `get_youtube_title`, `download_youtube_video`, and `transcribe_files` to simulate success.
        5.  Call `POST /trigger_transcription`.
        6.  Assert that the final status from `GET /status` is `completed`.
        7.  Assert that `processed_videos` in the status response contains the correct video title and URL.
        8.  Assert that `GET /transcribed_videos` includes the newly transcribed video.
        9.  Assert that `GET /transcribed_content_full/{id}` returns the mock transcription text.
        10. Assert that the temporary downloaded file was deleted.

2.  **Successful Custom Video Workflow**
    *   **Goal**: Test the "happy path" for an uploaded file.
    *   **Steps**:
        1.  Start with an empty queue/database.
        2.  Call `POST /upload_custom_video` with a dummy file.
        3.  Assert the response contains a `custom://` URL and that the item appears in the queue.
        4.  Mock `transcribe_files` to succeed for the uploaded file's path.
        5.  Call `POST /trigger_transcription`.
        6.  Assert a `completed` status and that the video appears in `processed_videos`.
        7.  Assert the transcription is in the database.
        8.  Assert that the original source file in `/custom_videos` was deleted after processing.

3.  **Convenience Endpoint `/upload_and_process` Workflow**
    *   **Goal**: Ensure the combined upload-and-trigger endpoint works as expected.
    *   **Steps**:
        1.  Start with an empty queue/database.
        2.  Mock `transcribe_files` to succeed.
        3.  Call `POST /upload_and_process` with a dummy file.
        4.  Assert the immediate response shows `transcription_status: "queued"`.
        5.  After the call completes, poll `GET /status` until it is `completed`.
        6.  Assert the final state is identical to the successful custom video workflow.

4.  **Workflow with a Download Failure**
    *   **Goal**: Test how the system handles a failure during the download step.
    *   **Steps**:
        1.  Add a YouTube URL to the queue.
        2.  Mock `download_youtube_video` to return a failure status (`(False, None, "error message")`).
        3.  Trigger the transcription.
        4.  Assert the final status is `completed_with_errors`.
        5.  Assert the URL is in the `failed_urls` list and not in `processed_videos`.
        6.  Assert that no entry was made to the `transcribed` table in the database.

5.  **Workflow with a Transcription Failure**
    *   **Goal**: Test how the system handles a failure during the transcription step.
    *   **Steps**:
        1.  Add a URL or upload a file.
        2.  Mock the download/upload to succeed, but mock `transcribe_files` to return the file in the `failed_transcription_files` list.
        3.  Trigger the transcription.
        4.  Assert the final status is `completed_with_errors`.
        5.  Assert the URL is in `failed_urls`.
        6.  Assert the database is empty.

6.  **Mixed Batch Processing (Success and Failure)**
    *   **Goal**: Test processing a queue with multiple items where some succeed and others fail.
    *   **Steps**:
        1.  Add two URLs to the queue.
        2.  Configure mocks so one URL's processing will succeed, and the other's will fail (at either download or transcription).
        3.  Trigger processing.
        4.  Assert the final status is `completed_with_errors` and progress is `1/2`.
        5.  Assert `processed_videos` has one item and `failed_urls` has the other.
        6.  Assert the database contains only the successful transcription.

---

### Test Ideas: Specific Endpoint Behavior

These tests focus on the logic and error handling of individual endpoints.

*   `/add_links`:
    *   Test with a malformed body (e.g., not JSON, wrong key) to ensure a `422 Unprocessable Entity` error.
*   `/trigger_transcription`:
    *   Test calling it when the queue is empty (should return a success message indicating nothing to do).
    *   Test calling it when a process is already marked as "running" (should return a `409 Conflict`). This can be simulated by setting the queue's processing state directly in the test.
*   `/upload_custom_video`:
    *   Test uploading a file with an unsupported extension (expect `400 Bad Request`).
    *   Test a request without a file attached (expect `400 Bad Request`).
*   `/transcribed_content_summary/{id_or_url}` & `/transcribed_content_full/{id_or_url}`:
    *   Test retrieving content by its integer ID.
    *   Test retrieving content by its full URL (ensure the test properly URL-encodes the value).
    *   Test requesting an ID or URL that does not exist (expect `404 Not Found`).
*   `/export_transcription`:
    *   Test exporting by ID and by URL.
    *   Verify the created file has the correct name (sanitized from the video title) and content.
    *   Test with a non-existent ID (expect `404 Not Found`).
*   `/clear_list`:
    *   Add items to the queue, call `/clear_list`, then call `/queue_items` to assert that the queue is now empty.

---

### Suggestions for Testing Real Integrations (Whisper & yt-dlp)

These tests would be separate from the main regression suite. They could be tagged (e.g., `@pytest.mark.gpu`, `@pytest.mark.network`) and run selectively on machines with the necessary hardware and network access.

1.  **Whisper Model Test (`transcribe_files`)**
    *   **Goal**: Verify that `transcribe_files` can correctly load a model and produce text.
    *   **Setup**: Have a very short (2-5 seconds) sample audio file with known, simple speech (e.g., "The quick brown fox jumps over the lazy dog.") checked into your repository.
    *   **Test**:
        1.  Run the *real* `transcribe_files` function (not the mock).
        2.  Use the smallest possible model, like `tiny.en` or `base.en`, to speed up the test.
        3.  Pass the path to your sample audio file.
        4.  Assert that the returned transcription text closely matches the known text. This doesn't need to be a perfect match, but it should be substantially correct.
        5.  This test validates your Python environment, `ffmpeg` installation, and PyTorch/CUDA setup.

2.  **`yt-dlp` Integration Test**
    *   **Goal**: Verify that the `yt-dlp` subprocess calls work as expected.
    *   **Setup**: This test requires an active internet connection. Use a stable, short video URL from a reliable source (e.g., a Creative Commons video) that is unlikely to be removed.
    *   **Test `get_youtube_title`**: Call the real function with the test URL and assert that it returns the expected video title.
    *   **Test `download_youtube_video`**: Call the real function. Assert that it returns a success status, a file path is created, and the file actually exists on disk. Be sure to clean up the downloaded file afterward.

---

### Test Ideas: Database Functionality

This section details how to test the database interactions directly, ensuring data is correctly created, updated, and deleted.

*   **Test Database Strategy**:
    *   **Isolation**: Use a dedicated, temporary database for the entire test suite. An in-memory SQLite database is the ideal choice as it's fast and automatically destroyed when tests finish.
    *   **Automation with `pytest` Fixtures**: Manage the database lifecycle automatically. Fixtures in a `tests/conftest.py` file should handle:
        1.  Creating the in-memory database engine before any tests run.
        2.  Creating all necessary tables based on the SQLAlchemy models (`Base.metadata.create_all()`).
        3.  Providing a clean database session to each test function.
        4.  Tearing down the tables after the test session is complete (`Base.metadata.drop_all()`).
        5.  Ensuring each test runs in a transaction that is rolled back afterward, guaranteeing test isolation.
    *   **Dependency Injection**: Use FastAPI's dependency overriding system to replace the live database connection (`get_db`) with a function that provides a session to the temporary test database.

*   **Test Scenarios**:
    *   **State Verification**: After an API call that should change the database (e.g., `POST /add_links`), the test should use its database session to query the database directly.
    *   **Assertions**: Assertions should be made against the results of these direct database queries. For example:
        *   After adding URLs, assert that the number of rows in the `video_queue` table matches the number of URLs added.
        *   Assert that the `video_url` and `status` columns for a new entry are correct.
    *   **Constraint Testing**: Test database constraints and application logic, such as:
        *   Attempting to add a duplicate URL and asserting that a new row is *not* created and the API responds appropriately.
        *   After a successful transcription, querying the `transcribed_videos` table to ensure the record was created correctly.
        *   After a failure, asserting that no records were created or that they are marked with an error status.
    *   **Clear/Delete Operations**: Test endpoints like `/clear_list` by first adding data, calling the endpoint, and then asserting that the relevant tables are empty.
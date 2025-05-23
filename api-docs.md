# Transcription Service API Documentation

This document outlines the API endpoints for the Transcription Service, designed to be called by agents like n8n.

## Base URL

Assuming the service is running and accessible (e.g., `http://localhost:8000` or `http://your-server-ip:8000` if accessed from another machine/container on the same network).

---

## Endpoints

### 1. Add Links to Processing List

*   **HTTP Method:** `POST`
*   **Path:** `/add_links`
*   **Purpose:** Appends a list of YouTube video URLs to the `list.txt` file. This step **does not** start the transcription process.
*   **Request Body:** JSON
    ```json
    {
      "urls": [
        "https://www.youtube.com/watch?v=xxxxxxx",
        "https://www.youtube.com/watch?v=yyyyyyy"
      ]
    }
    ```
*   **Success Response (Status Code `200 OK`):**
    Indicates that the URLs have been successfully added to the list file.
    ```json
    {
      "message": "2 url(s) added to /app/list.txt. Call /trigger_transcription to start processing."
    }
    ```
*   **Error Responses:**
    *   **Status Code `500 Internal Server Error`:** If there was an issue writing to `list.txt`.
        ```json
        {
          "detail": "Failed to add links to /app/list.txt: <error_message>"
        }
        ```

### 2. Trigger Transcription Process

*   **HTTP Method:** `POST`
*   **Path:** `/trigger_transcription`
*   **Purpose:** Starts the transcription pipeline for all URLs currently present in `list.txt`. The processing happens in the background.
*   **Request Body:** None (or empty JSON object `{}` if required by the client)
*   **Success Response (Status Code `202 Accepted`):**
    Indicates that the transcription process has been successfully queued and started in the background.
    ```json
    {
      "message": "Transcription process triggered.",
      "initial_status": {
        "status": "queued", 
        "progress": "0/5", // Example: 0 out of 5 URLs in list.txt
        "processed_videos": [],
        "failed_urls": []
      }
    }
    ```
*   **Error Responses:**
    *   **Status Code `409 Conflict`:** If a transcription process is already active or queued.
        ```json
        {
          "detail": "A transcription process is already active or queued (status: <current_status>). Please wait."
        }
        ```
    *   If `list.txt` is empty, it might return a message like:
        ```json
        {
          "message": "'/app/list.txt' is empty. Nothing to trigger.", 
          "status": "idle"
        }
        ```

### 3. Get Transcription Status

*   **HTTP Method:** `GET`
*   **Path:** `/status`
*   **Purpose:** Retrieves the current status and progress of the transcription pipeline. This should be polled by the agent after triggering transcription.
*   **Request Body:** None
*   **Success Response (Status Code `200 OK`):**
    Returns a JSON object with the current `status`, `progress`, and upon completion, lists of `processed_videos` and `failed_urls`.
    Possible statuses for `status` field:
    *   `idle`: No process is running.
    *   `queued`: Transcription has been triggered but not yet started processing files (e.g., waiting for background task to pick up).
    *   `processing`: URLs are currently being downloaded.
    *   `transcribing`: Downloaded audio is currently being transcribed.
    *   `completed`: All URLs in the last batch were processed successfully.
    *   `completed_with_errors`: The last batch processing finished, but some URLs may have failed.
    
    Example (during processing):
    ```json
    {
      "status": "processing",
      "progress": "1/5", // e.g., 1 out of 5 videos currently being downloaded
      "processed_videos": [],
      "failed_urls": []
    }
    ```
    Example (completed successfully - **"DONE" state for agent**):
    ```json
    {
      "status": "completed",
      "progress": "5/5",
      "processed_videos": [
        {"url": "https://www.youtube.com/watch?v=xxxxxxx", "title": "Video Title X"},
        {"url": "https://www.youtube.com/watch?v=yyyyyyy", "title": "Video Title Y"}
      ],
      "failed_urls": []
    }
    ```
    Example (completed with errors - **"DONE" state for agent, but with issues**):
    ```json
    {
      "status": "completed_with_errors",
      "progress": "3/5 transcribed and saved",
      "processed_videos": [
        {"url": "https://www.youtube.com/watch?v=xxxxxxx", "title": "Video Title X"}
      ],
      "failed_urls": [
        "https://www.youtube.com/watch?v=zzzzzzz",
        "https://www.youtube.com/watch?v=aaaaaaa"
      ],
      "details": "2 url(s) failed at some stage."
    }
    ```
*   **Error Responses:** None explicitly defined beyond standard HTTP errors if the server itself has an issue.

### 4. Clear the URL List

*   **HTTP Method:** `POST`
*   **Path:** `/clear_list`
*   **Purpose:** Wipes all URLs from `list.txt` and resets the service status to `idle`. This should be called by the agent *after* it has received the "DONE" message (i.e., `completed` or `completed_with_errors` status from `/status`) and processed the results (`processed_videos`, `failed_urls`).
*   **Request Body:** None (or empty JSON object `{}` if required by the client)
*   **Success Response (Status Code `200 OK`):**
    ```json
    {
      "message": "'/app/list.txt' has been cleared and status reset to idle."
    }
    ```
*   **Error Responses:**
    *   **Status Code `500 Internal Server Error`:** If there was an issue clearing the file.
        ```json
        {
          "detail": "Failed to clear /app/list.txt: <error_message>"
        }
        ```

---

## New Workflow for Agent (e.g., n8n)

1.  **Agent:** Receives new YouTube URL(s).
2.  **Agent:** Calls `POST /add_links` with the list of new URLs.
3.  **Agent:** Calls `POST /trigger_transcription` to start the background processing for all URLs in `list.txt`.
    *   Receives an immediate "triggered" response.
4.  **Agent:** Begins polling `GET /status` periodically.
    *   The agent observes the `progress` field (e.g., "1/3", "2/3").
    *   Continues polling until `status` is `completed` or `completed_with_errors`. This is the **"DONE"** signal.
5.  **Agent (Once "DONE" signal received via `/status`):**
    *   Retrieves `processed_videos` (list of {url, title} for successes) and `failed_urls` (list of urls for failures) from the `/status` response for its context/logging.
    *   Verifies that the transcriptions for URLs in `processed_videos` are present and correct in the PostgreSQL database (optional, as the service aims to ensure this).
6.  **Agent (After processing results):** Calls `POST /clear_list` to clear `list.txt` and reset the service for the next batch.

---

## Environment Variables for the Service

When running the service (e.g., via Docker or `docker-compose.yml`), the following environment variables can be set:

*   `DB_HOST`: Hostname or IP of the PostgreSQL database.
*   `DB_PORT`: Port of the PostgreSQL database (default: `5432`).
*   `DB_NAME`: Name of the database to use.
*   `DB_USER`: Username for the database connection.
*   `DB_PASSWORD`: Password for the database connection.
*   `WHISPER_MODEL`: The Whisper model to use (e.g., `tiny.en`, `base.en`, `small.en`, `medium.en`, `large`). Default is `base.en`.
*   `PYTHONUNBUFFERED=1`: (Recommended) Ensures Python output (like print statements for logging) is sent directly to the terminal/logs without buffering.
*   `TZ`: (Optional) Set the timezone for the container, e.g., `America/Los_Angeles`. Useful if any Python date/time operations rely on the system's local time. (Note: The script currently uses UTC and converts to PST explicitly for one field, but setting a container-wide TZ can be good practice). 
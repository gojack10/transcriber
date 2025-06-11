# Transcription Service API Documentation

This document outlines the API endpoints for the Transcription Service, designed to be called by agents like n8n.

## Base URL

Assuming the service is running and accessible (e.g., `http://localhost:8000` or `http://your-server-ip:8000` if accessed from another machine/container on the same network).

## Endpoints

### 1. Add Links to Processing Queue

*   **HTTP Method:** `POST`
*   **Path:** `/add_links`
*   **Purpose:** Appends a list of YouTube video URLs to the processing queue. This step **does not** start the transcription process.
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
    Indicates that the URLs have been successfully added to the processing queue.
    ```json
    {
      "message": "2 url(s) added to processing queue. call /trigger_transcription to start processing."
    }
    ```
*   **Error Responses:**
    *   **Status Code `500 Internal Server Error`:** If there was an issue adding to the queue.
        ```json
        {
          "detail": "failed to add links to queue: <error_message>"
        }
        ```

**Usage Example:**
```bash
curl -X POST http://localhost:8000/add_links \
  -H "Content-Type: application/json" \
  -d '{
    "urls": [
      "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
      "https://www.youtube.com/watch?v=9bZkp7q19f0"
    ]
  }'
```

### 2. Trigger Transcription Process

*   **HTTP Method:** `POST`
*   **Path:** `/trigger_transcription`
*   **Purpose:** Starts the transcription pipeline for all items currently in the processing queue. The processing happens in the background.
*   **Request Body:** None (or empty JSON object `{}` if required by the client)
*   **Success Response (Status Code `202 Accepted`):**
    Indicates that the transcription process has been successfully queued and started in the background.
    ```json
    {
      "message": "transcription process triggered.",
      "initial_status": {
        "status": "queued", 
        "progress": "0/5", // Example: 0 out of 5 items in queue
        "processed_videos": [],
        "failed_urls": []
      }
    }
    ```
*   **Error Responses:**
    *   **Status Code `409 Conflict`:** If a transcription process is already active.
        ```json
        {
          "detail": "a transcription process is already active. please wait."
        }
        ```
    *   If queue is empty, it returns:
        ```json
        {
          "message": "queue is empty. nothing to trigger.", 
          "status": "idle"
        }
        ```

**Usage Example:**
```bash
curl -X POST http://localhost:8000/trigger_transcription
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
    *   `queued`: Transcription has been triggered but not yet started processing files.
    *   `processing_downloads`: Items are currently being downloaded.
    *   `processing_transcriptions`: Downloaded audio is currently being transcribed.
    *   `completed`: All items in the last batch were processed successfully.
    *   `completed_with_errors`: The last batch processing finished, but some items may have failed.
    
    Example (during processing):
    ```json
    {
      "status": "processing_downloads",
      "progress": "1/5", // e.g., 1 out of 5 videos currently being processed
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
        {"url": "custom://audio_123456.m4a", "title": "My Custom Audio"}
      ],
      "failed_urls": []
    }
    ```
    Example (completed with errors - **"DONE" state for agent, but with issues**):
    ```json
    {
      "status": "completed_with_errors",
      "progress": "3/5",
      "processed_videos": [
        {"url": "https://www.youtube.com/watch?v=xxxxxxx", "title": "Video Title X"}
      ],
      "failed_urls": [
        "https://www.youtube.com/watch?v=zzzzzzz",
        "custom://failed_audio_789.mp4"
      ]
    }
    ```
*   **Error Responses:** None explicitly defined beyond standard HTTP errors if the server itself has an issue.

**Usage Example:**
```bash
# Poll status every 5 seconds
while true; do
  curl -s http://localhost:8000/status | jq .
  sleep 5
done
```

### 4. View Processing Queue

*   **HTTP Method:** `GET`
*   **Path:** `/queue_items`
*   **Purpose:** **NEW ENDPOINT** - Retrieves all items currently in the processing queue, including their individual status, type, and metadata.
*   **Request Body:** None
*   **Success Response (Status Code `200 OK`):**
    Returns a JSON object with all queue items and their details.
    ```json
    {
      "items": [
        {
          "id": "uuid-string",
          "url": "https://www.youtube.com/watch?v=xxxxxxx",
          "video_type": "youtube",
          "title": null,
          "status": "queued",
          "added_time": "2024-01-15T10:30:00.123456",
          "completed_time": null,
          "error_message": null,
          "local_path": null
        },
        {
          "id": "uuid-string-2",
          "url": "custom://my_audio_789456.m4a",
          "video_type": "custom",
          "title": "Team Meeting Recording",
          "status": "downloading",
          "added_time": "2024-01-15T10:32:15.654321",
          "completed_time": null,
          "error_message": null,
          "local_path": null
        }
      ],
      "count": 2
    }
    ```

**Usage Example:**
```bash
curl http://localhost:8000/queue_items
```

### 5. Clear the Processing Queue

*   **HTTP Method:** `POST`
*   **Path:** `/clear_list`
*   **Purpose:** Clears all items from the processing queue and resets the service status to `idle`. This should be called by the agent *after* it has received the "DONE" message (i.e., `completed` or `completed_with_errors` status from `/status`) and processed the results (`processed_videos`, `failed_urls`).
*   **Request Body:** None (or empty JSON object `{}` if required by the client)
*   **Success Response (Status Code `200 OK`):**
    ```json
    {
      "message": "processing queue has been cleared and status reset to idle."
    }
    ```
*   **Error Responses:**
    *   **Status Code `500 Internal Server Error`:** If there was an issue clearing the queue.
        ```json
        {
          "detail": "failed to clear queue: <error_message>"
        }
        ```

**Usage Example:**
```bash
curl -X POST http://localhost:8000/clear_list
```

---

## Updated Workflow for Agent (e.g., n8n)

1.  **Agent:** Receives new YouTube URL(s) or uploads custom video files.
2.  **Agent:** Calls `POST /add_links` with YouTube URLs or `POST /upload_custom_video` for custom files (which now **automatically adds to queue**).
3.  **Agent:** Calls `POST /trigger_transcription` to start the background processing for all items in the queue.
    *   Receives an immediate "triggered" response.
4.  **Agent:** Begins polling `GET /status` periodically.
    *   The agent observes the `progress` field (e.g., "1/3", "2/3").
    *   Optionally calls `GET /queue_items` to see detailed queue status.
    *   Continues polling until `status` is `completed` or `completed_with_errors`. This is the **"DONE"** signal.
5.  **Agent (Once "DONE" signal received via `/status`):**
    *   Retrieves `processed_videos` (list of {url, title} for successes) and `failed_urls` (list of urls for failures) from the `/status` response for its context/logging.
    *   Can access transcription content using either the database ID or original URL via `/transcribed_content_summary/{id_or_url}` or `/transcribed_content_full/{id_or_url}`.
    *   Verifies that the transcriptions for URLs in `processed_videos` are present and correct in the PostgreSQL database (optional, as the service aims to ensure this).
6.  **Agent (After processing results):** Calls `POST /clear_list` to clear the queue and reset the service for the next batch.

---

## Endpoints for AI Agent Access

These endpoints are designed to allow an AI agent to query and retrieve information about transcribed videos.

### 6. List All Transcribed Videos

*   **HTTP Method:** `GET`
*   **Path:** `/transcribed_videos`
*   **Purpose:** Retrieves a list of all videos that have been successfully transcribed and recorded in the database.
*   **Request Body:** None
*   **Success Response (Status Code `200 OK`):**
    Returns a JSON object containing a list of videos, each with its database `id`, `url`, and `video_title`.
    ```json
    {
      "videos": [
        {
          "id": 1,
          "url": "https://www.youtube.com/watch?v=xxxxxxx",
          "video_title": "Video Title X"
        },
        {
          "id": 2,
          "url": "https://www.youtube.com/watch?v=yyyyyyy",
          "video_title": "Video Title Y"
        }
      ]
    }
    ```
    If no videos are transcribed, it returns an empty list:
    ```json
    {
      "videos": []
    }
    ```
*   **Error Responses:** None explicitly defined beyond standard HTTP errors.

**Usage Example:**
```bash
curl http://localhost:8000/transcribed_videos
```

### 7. Get Transcription Content Summary

*   **HTTP Method:** `GET`
*   **Path:** `/transcribed_content_summary/{id_or_url}`
    *   Replace `{id_or_url}` with either:
        - A numeric database ID (e.g., `1`, `42`)
        - A URL-encoded full YouTube or custom URL (e.g., `https%3A%2F%2Fwww.youtube.com%2Fwatch%3Fv%3Dxxxxxxx` or `custom%3A%2F%2Ffilename.mp4`)
*   **Purpose:** Retrieves a short summary (the first 100 words) of the transcribed content for a specific video.
*   **Request Body:** None
*   **Success Response (Status Code `200 OK`):**
    Returns the database `id`, `url`, and a `summary` of the transcription.
    ```json
    {
      "id": 1,
      "url": "https://www.youtube.com/watch?v=xxxxxxx",
      "summary": "this is the beginning of the transcribed text up to approximately one hundred words..."
    }
    ```
*   **Error Responses:**
    *   **Status Code `404 Not Found`:** If no transcription content is found for the given ID or URL.
        ```json
        {
          "detail": "transcription content not found for this id/url."
        }
        ```

**Usage Examples:**
```bash
# Using database ID
curl "http://localhost:8000/transcribed_content_summary/1"

# Using YouTube URL (URL encoded)
ENCODED_URL=$(python3 -c "import urllib.parse; print(urllib.parse.quote('https://www.youtube.com/watch?v=dQw4w9WgXcQ'))")
curl "http://localhost:8000/transcribed_content_summary/$ENCODED_URL"

# Using custom video URL (URL encoded)
ENCODED_CUSTOM_URL=$(python3 -c "import urllib.parse; print(urllib.parse.quote('custom://my_video_123456.mp4'))")
curl "http://localhost:8000/transcribed_content_summary/$ENCODED_CUSTOM_URL"
```

### 8. Get Full Transcription Content

*   **HTTP Method:** `GET`
*   **Path:** `/transcribed_content_full/{id_or_url}`
    *   Replace `{id_or_url}` with either:
        - A numeric database ID (e.g., `1`, `42`)
        - A URL-encoded full YouTube or custom URL
*   **Purpose:** Retrieves the complete transcribed text for a specific video. This is intended for an agent to load the full text into its context for summarization or other analysis.
*   **Request Body:** None
*   **Success Response (Status Code `200 OK`):**
    Returns the database `id`, `url`, and the full `content` of the transcription.
    ```json
    {
      "id": 1,
      "url": "https://www.youtube.com/watch?v=xxxxxxx",
      "content": "this is the full transcribed text of the video... it can be very long..."
    }
    ```
*   **Error Responses:**
    *   **Status Code `404 Not Found`:** If no transcription content is found for the given ID or URL.
        ```json
        {
          "detail": "transcription content not found for this id/url."
        }
        ```

**Usage Examples:**
```bash
# Using database ID
curl "http://localhost:8000/transcribed_content_full/1"

# Using YouTube URL (URL encoded)
ENCODED_URL=$(python3 -c "import urllib.parse; print(urllib.parse.quote('https://www.youtube.com/watch?v=dQw4w9WgXcQ'))")
curl "http://localhost:8000/transcribed_content_full/$ENCODED_URL"

# Using custom video URL (URL encoded)
ENCODED_CUSTOM_URL=$(python3 -c "import urllib.parse; print(urllib.parse.quote('custom://my_video_123456.mp4'))")
curl "http://localhost:8000/transcribed_content_full/$ENCODED_CUSTOM_URL"
```

### 9. Export Transcription to Text File

*   **HTTP Method:** `POST`
*   **Path:** `/export_transcription`
*   **Purpose:** Exports the transcription content to a text file using either the video ID or URL. The file is saved with the video title as the filename.
*   **Request Body:** JSON
    ```json
    {
      "id": "1"
    }
    ```
    or
    ```json
    {
      "id": "https://www.youtube.com/watch?v=xxxxxxx"
    }
    ```
    or
    ```json
    {
      "id": "custom://my_video_123456.mp4"
    }
    ```
    The `id` field can be:
    - A numeric string representing the database ID (e.g., "1", "42")
    - A full YouTube URL
    - A custom video URL (custom:// scheme)
*   **Success Response (Status Code `200 OK`):**
    Returns information about the exported file.
    ```json
    {
      "message": "transcription exported successfully to Video_Title_Example.txt",
      "filename": "Video_Title_Example.txt",
      "file_path": "/app/Video_Title_Example.txt",
      "video_id": 1,
      "video_title": "Video Title Example",
      "url": "https://www.youtube.com/watch?v=xxxxxxx"
    }
    ```
*   **Error Responses:**
    *   **Status Code `404 Not Found`:** If no transcription is found for the given id.
        ```json
        {
          "detail": "transcription not found for id: 1"
        }
        ```
        or
        ```json
        {
          "detail": "transcription not found for url: https://www.youtube.com/watch?v=xxxxxxx"
        }
        ```
    *   **Status Code `500 Internal Server Error`:** If there was an issue writing the file.
        ```json
        {
          "detail": "failed to write transcription to file: <error_message>"
        }
        ```

**Usage Examples:**
```bash
# Export by database ID
curl -X POST http://localhost:8000/export_transcription \
  -H "Content-Type: application/json" \
  -d '{"id": "1"}'

# Export by YouTube URL
curl -X POST http://localhost:8000/export_transcription \
  -H "Content-Type: application/json" \
  -d '{"id": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}'

# Export by custom video URL
curl -X POST http://localhost:8000/export_transcription \
  -H "Content-Type: application/json" \
  -d '{"id": "custom://my_video_123456.mp4"}'
```

### 10. Upload Custom Video File

*   **HTTP Method:** `POST`
*   **Path:** `/upload_custom_video`
*   **Purpose:** Uploads a custom video/audio file (not from YouTube) for transcription processing. **IMPORTANT**: The file is **automatically added to the processing queue** after upload.
*   **Request Body:** Multipart form data
    - `file`: The video/audio file to upload
    - `title`: (Optional) Custom title for the video. If not provided, the filename will be used.
*   **Success Response (Status Code `200 OK`):**
    Returns information about the uploaded file and queue status.
    ```json
    {
      "message": "Custom video uploaded successfully and added to queue",
      "custom_url": "custom://custom_video_1234567890.mp4",
      "title": "My Custom Video",
      "filename": "custom_video_1234567890.mp4",
      "file_path": "/app/custom_videos/custom_video_1234567890.mp4",
      "file_size_mb": 15.3,
      "status": "ready_for_transcription",
      "added_to_queue": true
    }
    ```
*   **Error Responses:**
    *   **Status Code `400 Bad Request`:** If no file is provided or file type is not supported.
        ```json
        {
          "detail": "No file provided"
        }
        ```
    *   **Status Code `413 Payload Too Large`:** If the file exceeds size limits.
        ```json
        {
          "detail": "File size exceeds maximum allowed size of 500MB"
        }
        ```
    *   **Status Code `500 Internal Server Error`:** If there was an issue saving the file.
        ```json
        {
          "detail": "Failed to save uploaded file: <error_message>"
        }
        ```

**Usage Example:**
```bash
curl -X POST http://localhost:8000/upload_custom_video -F "file=@/path/to/my-video.mp4" -F "title=My Important Meeting Recording"
```

**Note:** After uploading, you can immediately call `/trigger_transcription` to start processing, or check `/queue_items` to see the uploaded file in the queue.

### 11. Add Custom Videos to Processing Queue

*   **HTTP Method:** `POST`
*   **Path:** `/add_custom_videos`
*   **Purpose:** Adds previously uploaded custom video URLs to the processing queue. These use the `custom://` URL scheme. **Note**: This is typically not needed since `/upload_custom_video` automatically adds files to the queue.
*   **Request Body:** JSON
    ```json
    {
      "custom_urls": [
        "custom://custom_video_1234567890.mp4",
        "custom://my_recording_1234567891.wav"
      ]
    }
    ```
*   **Success Response (Status Code `200 OK`):**
    ```json
    {
      "message": "2 custom video(s) added to processing queue. Call /trigger_transcription to start processing."
    }
    ```

**Usage Example:**
```bash
curl -X POST http://localhost:8000/add_custom_videos \
  -H "Content-Type: application/json" \
  -d '{
    "custom_urls": [
      "custom://my_video_1702123456789.mp4",
      "custom://audio_recording_1702123457890.wav"
    ]
  }'
```

### 12. Upload and Process Custom Video (Convenience Endpoint)

*   **HTTP Method:** `POST`
*   **Path:** `/upload_and_process`
*   **Purpose:** Uploads a custom video/audio file and immediately adds it to the processing queue. This combines `/upload_custom_video`, `/add_custom_videos`, and `/trigger_transcription` into one convenient call.
*   **Request Body:** Multipart form data
    - `file`: The video/audio file to upload
    - `title`: (Optional) Custom title for the video
    - `process_immediately`: (Optional) Boolean, default true. If false, only uploads without triggering processing.
*   **Success Response (Status Code `200 OK`):**
    ```json
    {
      "message": "Custom video uploaded and queued for processing",
      "custom_url": "custom://my_video_1234567890.mp4",
      "title": "My Custom Video",
      "transcription_status": "queued",
      "initial_status": {
        "status": "queued",
        "progress": "0/1"
      }
    }
    ```
*   **Error Responses:** Same as `/upload_custom_video`

**Usage Examples:**
```bash
# Upload and process immediately
curl -X POST http://localhost:8000/upload_and_process \
  -F "file=@/path/to/video.mp4" \
  -F "title=Team Meeting 2024-01-15" \
  -F "process_immediately=true"

# Upload without processing
curl -X POST http://localhost:8000/upload_and_process \
  -F "file=@/path/to/video.mp4" \
  -F "title=Draft Recording" \
  -F "process_immediately=false"
```

---

## Important Notes

- **Queue-Based Architecture**: The service now uses a persistent queue system (`video_queue.json`) instead of the old `list.txt` file. This provides better reliability, thread safety, and automatic queue addition for custom videos.
- **Automatic Queue Addition**: Custom videos uploaded via `/upload_custom_video` are automatically added to the processing queue - no manual queue addition required.
- **Enhanced Visibility**: Use the new `/queue_items` endpoint to see exactly what's in the processing queue, including individual item status and metadata.
- **Migration Support**: The service automatically migrates any existing URLs from `list.txt` to the new queue system on startup.
- **Flexible ID/URL Support**: Content retrieval and export endpoints accept either database IDs (numeric) or full URLs (YouTube or custom). This provides maximum flexibility for different use cases.
- **Automatic Cleanup**: Temporary files in the `/tmp` directory and custom video source files are automatically deleted immediately after successful transcription and database storage.
- **File Formats**: Supported audio formats: `.mp3`, `.wav`, `.flac`, `.m4a`, `.ogg`, `.aac`, `.wma`. Supported video formats: `.mp4`, `.avi`, `.mov`, `.mkv`, `.webm`, `.flv`, `.wmv`, `.m4v`
- **Custom URLs**: Custom uploaded files use the `custom://` URL scheme to distinguish them from YouTube URLs.
- **Concurrent Processing**: Only one transcription pipeline can run at a time. Attempting to trigger while one is running will return a 409 Conflict error.
- **Thread Safety**: All queue operations are thread-safe, preventing race conditions in concurrent environments.
- **URL Encoding**: When using URLs as path parameters, ensure they are properly URL-encoded to avoid issues with special characters.

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
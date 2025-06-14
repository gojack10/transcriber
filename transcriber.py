import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

import pytz
import uvicorn
import whisper
import torch
import gc
from fastapi import (
    BackgroundTasks,
    Body,
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi import status as fastapi_status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import (
    Boolean,
    Column,
    create_engine,
    DateTime,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker, Session

# Import our new queue module
from video_queue import VideoProcessingQueue, VideoStatus, VideoType

# Eagerly initialize CUDA to prevent race conditions with background workers.
if torch.cuda.is_available():
    print("CUDA device detected. GPU will be used for transcription.")
    # The following line ensures the CUDA context is initialized on startup.
    torch.cuda.get_device_name(0)
else:
    print("No CUDA device detected. Transcription will run on CPU.")

class UrlList(BaseModel):
    urls: List[str]


class TranscribedVideoInfo(BaseModel):
    id: int
    url: str
    video_title: str


class TranscribedVideoList(BaseModel):
    videos: List[TranscribedVideoInfo]


class ContentSummary(BaseModel):
    id: int
    url: str
    summary: str


class FullContent(BaseModel):
    id: int
    url: str
    content: str


# --- configuration ---
BASE_DIR = Path(__file__).resolve().parent
TMP_DIR = BASE_DIR / "tmp"
QUEUE_FILE = BASE_DIR / "video_queue.json"
CUSTOM_VIDEOS_DIR = BASE_DIR / "custom_videos"

# supported audio file extensions (add more if needed)
AUDIO_EXTENSIONS = {".mp3", ".wav", ".flac", ".m4a", ".ogg", ".aac", ".wma"}
# supported video file extensions for custom uploads
VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".webm", ".flv", ".wmv", ".m4v"}
SUPPORTED_EXTENSIONS = AUDIO_EXTENSIONS | VIDEO_EXTENSIONS

# Initialize the queue
video_queue = VideoProcessingQueue(QUEUE_FILE)

# Global status tracking for backward compatibility
transcription_status: Dict[str, Any] = {
    "status": "idle",
    "progress": "0/0",
    "processed_videos": [],
    "failed_urls": [],
}
print(f"DEBUG: Initial transcription_status: {transcription_status}")


def get_initial_transcription_status() -> Dict[str, Any]:
    """Returns a new dictionary representing the initial, idle transcription status."""
    return {
        "status": "idle",
        "progress": "0/0",
        "processed_videos": [],
        "failed_urls": [],
    }


def update_status_from_queue():
    """Update the global transcription_status based on queue state"""
    global transcription_status
    queue_status = video_queue.get_status()

    # if the queue is idle, it means no processing is happening.
    # in this case, we should not overwrite a 'completed' or 'completed_with_errors' status
    # from the previous run. that status is the final report of the pipeline and should
    # be preserved until a new job is explicitly triggered (which resets the status).
    if queue_status["status"] == "idle" and transcription_status["status"] in [
        "completed",
        "completed_with_errors",
    ]:
        return

    # map queue status to old status format
    transcription_status["status"] = queue_status["status"]

    # calculate progress
    total = queue_status["total_items"]
    if queue_status["processing_item"]:
        if queue_status["processing_item"]["status"] == "completed":
            completed = 1
        else:
            completed = 0
    else:
        completed = 0

    transcription_status["progress"] = f"{completed}/{total}"

    # Update other fields as needed
    # In a full implementation, we'd track completed/failed items separately


# --- sqlalchemy setup ---
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./transcriber.db")
Base = declarative_base()


# --- sqlalchemy models ---
class DownloadedVideo(Base):
    __tablename__ = "downloaded_videos"
    id = Column(Integer, primary_key=True, index=True)
    url = Column(String, unique=True, index=True)
    status = Column(String, nullable=False)
    download_date = Column(DateTime, nullable=False)
    local_path = Column(String)
    yt_dlp_processed = Column(Boolean, default=False)


class Transcribed(Base):
    __tablename__ = "transcribed"
    id = Column(Integer, primary_key=True, index=True)
    utc_time = Column(DateTime, nullable=False)
    pst_time = Column(DateTime, nullable=False)
    url = Column(String, unique=True, index=True)
    video_title = Column(String, nullable=False)
    content = Column(Text, nullable=False)


def create_app() -> FastAPI:
    global transcription_status, video_queue

    _app = FastAPI()

    # Database setup is now managed within the app factory
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
    )
    _app.state.engine = engine
    _app.state.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


    # --- api endpoints ---
    @_app.post("/add_links", status_code=fastapi_status.HTTP_200_OK)
    async def add_links_to_list(payload: UrlList = Body(...)):
        """
        appends a list of urls to the processing queue.
        """
        try:
            count_added = video_queue.add_youtube_urls(payload.urls)
            update_status_from_queue()
            return {
                "message": f"{count_added} url(s) added to processing queue. call /trigger_transcription to start processing."
            }
        except Exception as e:
            raise HTTPException(
                status_code=fastapi_status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"failed to add links to queue: {e}",
            )

    @_app.post("/trigger_transcription", status_code=fastapi_status.HTTP_202_ACCEPTED)
    async def trigger_transcription_processing(request: Request, background_tasks: BackgroundTasks):
        """
        triggers the transcription pipeline to run in the background.
        """
        global transcription_status
        print(
            f"DEBUG: /trigger_transcription endpoint hit. Current status: {transcription_status}"
        )

        # Check if already processing
        if video_queue.is_processing():
            print(
                f"DEBUG: /trigger_transcription returning 409 due to active processing"
            )
            raise HTTPException(
                status_code=fastapi_status.HTTP_409_CONFLICT,
                detail=f"a transcription process is already active. please wait.",
            )

        # Check if queue is empty
        queue_status = video_queue.get_status()
        if queue_status["total_items"] == 0:
            print(f"DEBUG: /trigger_transcription returning idle for empty queue")
            return JSONResponse(
                status_code=fastapi_status.HTTP_200_OK,
                content={
                    "message": "queue is empty. nothing to trigger.",
                    "status": "idle",
                },
            )

        # Reset global status and start processing
        transcription_status = get_initial_transcription_status()
        transcription_status["status"] = "queued"
        update_status_from_queue()

        print(f"DEBUG: /trigger_transcription: Starting background task")
        background_tasks.add_task(run_transcription_pipeline, SessionLocal=request.app.state.SessionLocal)

        return {
            "message": "transcription process triggered.",
            "initial_status": transcription_status,
        }

    @_app.get("/status")
    async def get_status():
        """retrieves the current status of the transcription pipeline."""
        global transcription_status
        update_status_from_queue()
        print(f"DEBUG: /status endpoint hit. Returning status: {transcription_status}")
        return transcription_status

    @_app.post("/clear_list", status_code=fastapi_status.HTTP_200_OK)
    async def clear_list_file():
        """clears all items from the queue and resets status to idle."""
        global transcription_status
        print(
            f"DEBUG: /clear_list endpoint hit. Current status before clear: {transcription_status}"
        )
        try:
            video_queue.clear_queue()
            transcription_status = get_initial_transcription_status()
            print(f"DEBUG: /clear_list: Status reset to idle: {transcription_status}")
            return {
                "message": "processing queue has been cleared and status reset to idle."
            }
        except Exception as e:
            print(f"DEBUG: /clear_list: Error clearing queue: {e}")
            raise HTTPException(
                status_code=fastapi_status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"failed to clear queue: {e}",
            )

    @_app.get("/queue_items")
    async def get_queue_items():
        """Get all items currently in the queue"""
        items = video_queue.get_all_items()
        return {"items": items, "count": len(items)}

    @_app.post("/upload_custom_video")
    async def upload_custom_video(
        file: UploadFile = File(...), title: Optional[str] = Form(None)
    ):
        """
        uploads a custom video/audio file for transcription.
        returns a custom:// url that can be added to the processing queue.
        """
        # ensure custom videos directory exists
        CUSTOM_VIDEOS_DIR.mkdir(parents=True, exist_ok=True)

        # validate file was provided
        if not file:
            raise HTTPException(
                status_code=fastapi_status.HTTP_400_BAD_REQUEST,
                detail="No file provided",
            )

        # check file size (500MB limit)
        file_size = 0
        file_content = await file.read()
        file_size = len(file_content)

        if file_size > 500 * 1024 * 1024:  # 500MB
            raise HTTPException(
                status_code=fastapi_status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="File size exceeds maximum allowed size of 500MB",
            )

        # reset file position after reading
        await file.seek(0)

        # extract file extension and validate
        file_extension = Path(file.filename).suffix.lower() if file.filename else ""
        if not file_extension or file_extension not in SUPPORTED_EXTENSIONS:
            raise HTTPException(
                status_code=fastapi_status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported file type. Supported extensions: {', '.join(sorted(SUPPORTED_EXTENSIONS))}",
            )

        # generate unique filename
        timestamp = str(int(time.time() * 1000000))  # microsecond timestamp
        safe_original_name = (
            re.sub(r"[^a-zA-Z0-9_\-]", "_", Path(file.filename).stem)
            if file.filename
            else "custom"
        )
        unique_filename = f"{safe_original_name}_{timestamp}{file_extension}"
        file_path = CUSTOM_VIDEOS_DIR / unique_filename

        # save the file
        try:
            with open(file_path, "wb") as f:
                f.write(file_content)
        except IOError as e:
            raise HTTPException(
                status_code=fastapi_status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to save uploaded file: {e}",
            )

        # determine title
        video_title = (
            title
            if title
            else (file.filename if file.filename else f"Custom Video {timestamp}")
        )

        # create custom URL for this file
        custom_url = f"custom://{unique_filename}"

        # Automatically add to queue
        added = video_queue.add_custom_video(custom_url, video_title)

        return {
            "message": "Custom video uploaded successfully and added to queue",
            "custom_url": custom_url,
            "title": video_title,
            "filename": unique_filename,
            "file_path": str(file_path),
            "file_size_mb": round(file_size / (1024 * 1024), 2),
            "status": "ready_for_transcription",
            "added_to_queue": added,
        }

    @_app.post("/add_custom_videos")
    async def add_custom_videos_to_queue(payload: dict = Body(...)):
        """
        adds custom video urls (custom:// scheme) to the processing queue.
        """
        custom_urls = payload.get("custom_urls", [])
        if not custom_urls:
            raise HTTPException(
                status_code=fastapi_status.HTTP_400_BAD_REQUEST,
                detail="No custom_urls provided in request body",
            )

        try:
            count_added = 0
            for url in custom_urls:
                if url.startswith("custom://"):
                    if video_queue.add_custom_video(url):
                        count_added += 1
                else:
                    print(f"Skipping invalid custom URL: {url}")

            if count_added == 0:
                return {
                    "message": "No valid custom URLs were added. Custom URLs must start with 'custom://'"
                }

            update_status_from_queue()
            return {
                "message": f"{count_added} custom video(s) added to processing queue. Call /trigger_transcription to start processing."
            }
        except Exception as e:
            raise HTTPException(
                status_code=fastapi_status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to add custom videos to queue: {e}",
            )

    @_app.post("/upload_and_process")
    async def upload_and_process_custom_video(
        background_tasks: BackgroundTasks,
        file: UploadFile = File(...),
        title: Optional[str] = Form(None),
        process_immediately: Optional[bool] = Form(True),
    ):
        """
        convenience endpoint that uploads a custom video and immediately queues it for processing.
        """
        # First, upload the file using the existing logic
        upload_response = await upload_custom_video(file=file, title=title)

        if "custom_url" not in upload_response:
            raise HTTPException(
                status_code=fastapi_status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to get custom URL from upload response",
            )

        custom_url = upload_response["custom_url"]

        # Prepare response
        response = {
            "message": "Custom video uploaded and queued for processing",
            "custom_url": custom_url,
            "title": upload_response.get("title", "Unknown"),
            "file_size_mb": upload_response.get("file_size_mb", 0),
        }

        # Trigger processing if requested
        if process_immediately:
            # Check if we can start processing
            if video_queue.is_processing():
                response["transcription_status"] = "already_running"
                response["note"] = (
                    f"Transcription process already running. File added to queue."
                )
            else:
                # Start processing
                background_tasks.add_task(run_transcription_pipeline)
                response["transcription_status"] = "queued"
                update_status_from_queue()
                response["initial_status"] = transcription_status.copy()
        else:
            response["transcription_status"] = "not_started"
            response["note"] = (
                "File uploaded but processing not triggered. Call /trigger_transcription to start."
            )

        return response

    @_app.get("/transcribed_videos")
    async def get_transcribed_videos(db: Session = Depends(get_db_connection)):
        """retrieves a list of all transcribed videos from the database."""
        try:
            results = db.query(Transcribed).order_by(Transcribed.id).all()
            videos = [
                {"id": row.id, "url": row.url, "video_title": row.video_title}
                for row in results
            ]
            return {"videos": videos}
        except Exception as e:
            raise HTTPException(
                status_code=fastapi_status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"database error: {e}",
            )

    @_app.get("/transcribed_content_summary/{id_or_url}")
    async def get_transcribed_content_summary(
        id_or_url: str, db: Session = Depends(get_db_connection)
    ):
        """retrieves a summary (first 100 words) of transcribed content by id or url."""
        try:
            result = None
            try:
                video_id = int(id_or_url)
                result = (
                    db.query(Transcribed).filter(Transcribed.id == video_id).first()
                )
            except ValueError:
                decoded_url = urllib.parse.unquote(id_or_url)
                result = (
                    db.query(Transcribed).filter(Transcribed.url == decoded_url).first()
                )

            if not result:
                raise HTTPException(
                    status_code=fastapi_status.HTTP_404_NOT_FOUND,
                    detail="transcription content not found for this id/url.",
                )

            # create summary (first 100 words approximately)
            words = result.content.split()
            summary_words = words[:100]
            summary = " ".join(summary_words)
            if len(words) > 100:
                summary += "..."

            return {"id": result.id, "url": result.url, "summary": summary}
        except Exception as e:
            raise HTTPException(
                status_code=fastapi_status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"database error: {e}",
            )

    @_app.get("/transcribed_content_full/{id_or_url}")
    async def get_transcribed_content_full(
        id_or_url: str, db: Session = Depends(get_db_connection)
    ):
        """retrieves the full transcribed content by id or url."""
        try:
            result = None
            try:
                video_id = int(id_or_url)
                result = (
                    db.query(Transcribed).filter(Transcribed.id == video_id).first()
                )
            except ValueError:
                decoded_url = urllib.parse.unquote(id_or_url)
                result = (
                    db.query(Transcribed).filter(Transcribed.url == decoded_url).first()
                )

            if not result:
                raise HTTPException(
                    status_code=fastapi_status.HTTP_404_NOT_FOUND,
                    detail="transcription content not found for this id/url.",
                )

            return {"id": result.id, "url": result.url, "content": result.content}
        except Exception as e:
            raise HTTPException(
                status_code=fastapi_status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"database error: {e}",
            )

    @_app.post("/export_transcription")
    async def export_transcription(
        payload: dict = Body(...), db: Session = Depends(get_db_connection)
    ):
        """exports transcription content to a text file."""
        video_id_or_url = payload.get("id")
        if not video_id_or_url:
            raise HTTPException(
                status_code=fastapi_status.HTTP_400_BAD_REQUEST,
                detail="id field is required",
            )

        try:
            # try to parse as integer id first
            result = None
            try:
                video_id = int(video_id_or_url)
                result = (
                    db.query(Transcribed).filter(Transcribed.id == video_id).first()
                )
            except ValueError:
                # treat as url
                result = (
                    db.query(Transcribed)
                    .filter(Transcribed.url == video_id_or_url)
                    .first()
                )

            if not result:
                if isinstance(video_id_or_url, int) or video_id_or_url.isdigit():
                    detail = f"transcription not found for id: {video_id_or_url}"
                else:
                    detail = f"transcription not found for url: {video_id_or_url}"
                raise HTTPException(
                    status_code=fastapi_status.HTTP_404_NOT_FOUND, detail=detail
                )

            # create safe filename from video title
            safe_title = re.sub(r"[^a-zA-Z0-9_\-\s]", "_", result.video_title)
            safe_title = re.sub(r"\s+", "_", safe_title)
            filename = f"{safe_title}.txt"
            file_path = BASE_DIR / filename

            # write content to file
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(result.content)
                return {
                    "message": f"transcription exported successfully to {filename}",
                    "filename": filename,
                    "file_path": str(file_path),
                    "video_id": result.id,
                    "video_title": result.video_title,
                    "url": result.url,
                }
            except IOError as e:
                raise HTTPException(
                    status_code=fastapi_status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"failed to write transcription to file: {e}",
                )
        except Exception as e:
            raise HTTPException(
                status_code=fastapi_status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"database error: {e}",
            )

    return _app


def get_db_connection(request: Request):
    """
    Provides a SQLAlchemy database session from the application state.
    """
    SessionLocal = request.app.state.SessionLocal
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()




def insert_transcription_result(db: Session, url: str, video_title: str, content: str):
    """inserts or updates the transcription result in the database."""
    now_utc = datetime.now(pytz.utc)
    now_pst = now_utc.astimezone(ZoneInfo("America/Los_Angeles"))

    print(f"DB_DEBUG: Attempting to insert/update transcription for URL: {url}")

    # For SQLite, we can use a simple approach
    if "sqlite" in DATABASE_URL:
        # Check if the record exists
        existing = db.query(Transcribed).filter(Transcribed.url == url).first()
        if existing:
            print(f"DB_DEBUG: Found existing record for {url}. Updating it.")
            # Update existing record
            existing.utc_time = now_utc
            existing.pst_time = now_pst
            existing.video_title = video_title
            existing.content = content
        else:
            print(f"DB_DEBUG: No existing record for {url}. Creating a new one.")
            # Insert new record
            new_record = Transcribed(
                utc_time=now_utc,
                pst_time=now_pst,
                url=url,
                video_title=video_title,
                content=content,
            )
            db.add(new_record)
            print(f"DB_DEBUG: Added new record for {url} to the session.")
    else:
        # For PostgreSQL, use ON CONFLICT DO UPDATE
        stmt = pg_insert(Transcribed).values(
            utc_time=now_utc,
            pst_time=now_pst,
            url=url,
            video_title=video_title,
            content=content,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["url"],
            set_=dict(
                utc_time=stmt.excluded.utc_time,
                pst_time=stmt.excluded.pst_time,
                video_title=stmt.excluded.video_title,
                content=stmt.excluded.content,
            ),
        )
        db.execute(stmt)

    # The commit is handled by the calling function to manage the transaction boundary.
    print(f"DEBUG: Queued transcription for insertion/update for URL: {url}")


def get_youtube_title(url: str) -> str:
    """get the title of a youtube video using yt-dlp."""
    try:
        cmd = ["yt-dlp", "--get-title", url]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        title = result.stdout.strip()
        print(f"DEBUG: Got YouTube title: {title}")
        return title
    except subprocess.CalledProcessError as e:
        print(f"DEBUG: Error getting YouTube title for {url}: {e}")
        return "Unknown Video"
    except Exception as e:
        print(f"DEBUG: Unexpected error getting YouTube title for {url}: {e}")
        return "Unknown Video"


def sanitize_for_filename(text: str) -> str:
    """
    Cleans a string to be suitable for a filename.
    - Keeps alphanumeric characters, dashes, commas, and underscores.
    - Replaces other characters with a space.
    - Collapses multiple spaces/underscores into a single underscore.
    - Removes leading/trailing underscores.
    """
    # Allow alphanumeric, dash, comma, underscore, and space
    # Replace any character that is NOT in this set with a space
    text = re.sub(r"[^a-zA-Z0-9_,\-\s]", " ", text)
    # Replace multiple spaces or underscores with a single underscore
    text = re.sub(r"[\s_]+", "_", text)
    # Remove leading/trailing underscores
    text = text.strip("_")
    return text


def download_youtube_video(
    url: str, output_dir: Path, title: str
) -> Tuple[bool, Optional[Path], str]:
    """
    download a youtube video as audio using yt-dlp.

    returns:
        - success: boolean indicating if download was successful
        - file_path: path to downloaded audio file if successful, none otherwise
        - error_message: error message if download failed, empty string if successful
    """
    try:
        # ensure output directory exists
        output_dir.mkdir(parents=True, exist_ok=True)

        # Sanitize the title to create a safe filename
        safe_title = sanitize_for_filename(title)
        output_filename = f"{safe_title}.mp3"
        output_path = output_dir / output_filename

        # use yt-dlp to download audio only
        # format: best quality audio, convert to mp3
        cmd = [
            "yt-dlp",
            "--extract-audio",
            "--audio-format",
            "mp3",
            "--audio-quality",
            "0",  # best quality
            "--output",
            str(output_path),
            "--no-playlist",  # only download single video, not playlist
            url,
        ]

        print(f"DEBUG: Running yt-dlp command: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        print(f"DEBUG: yt-dlp completed successfully for {url}")

        # find the downloaded file
        if output_path.exists():
            print(f"DEBUG: Found downloaded file: {output_path}")
            return True, output_path, ""
        else:
            error_msg = f"no mp3 file found at the expected path: {output_path}"
            print(f"DEBUG: {error_msg}")
            return False, None, error_msg

    except subprocess.CalledProcessError as e:
        error_msg = f"yt-dlp failed: {e.stderr if e.stderr else str(e)}"
        print(f"DEBUG: {error_msg}")
        return False, None, error_msg
    except Exception as e:
        error_msg = f"unexpected error during download: {str(e)}"
        print(f"DEBUG: {error_msg}")
        return False, None, error_msg


def transcribe_files(
    model_name: str, file_paths: list[Path]
) -> tuple[list[Path], list[str], dict[str, str]]:
    """
    transcribes a list of audio files using the specified whisper model.

    args:
        model_name: the name of the whisper model to use (e.g., "base", "small", "medium", "turbo").
        file_paths: a list of Paths to audio files to transcribe.

    returns:
        a tuple containing:
            - successfully_transcribed_files: a list of Paths to successfully transcribed files.
            - failed_transcription_files: a list of file paths (as strings) that failed transcription.
            - transcription_results: a dictionary mapping file paths (as strings) to their transcription text.
    """
    global transcription_status
    print(
        f"DEBUG: transcribe_files called with model: {model_name}, files: {len(file_paths)}"
    )

    successfully_transcribed_files: list[Path] = []
    failed_transcription_files: list[str] = []
    transcription_results: dict[str, str] = {}

    if not file_paths:
        print("DEBUG: No files to transcribe.")
        return (
            successfully_transcribed_files,
            failed_transcription_files,
            transcription_results,
        )

    model = None
    try:
        # check if the model name is valid, otherwise default to "turbo"
        valid_models = whisper.available_models()
        if model_name not in valid_models:
            print(
                f"Warning: Whisper model '{model_name}' not found. defaulting to 'turbo'. available models: {valid_models}"
            )
            model_name = "turbo"

        model = whisper.load_model(model_name)
        print(f"DEBUG: Whisper model '{model_name}' loaded.")

        for audio_file_path in file_paths:
            try:
                print(f"DEBUG: Starting transcription for {audio_file_path}")
                transcription_result = model.transcribe(str(audio_file_path))
                print(
                    f"DEBUG: Whisper output for {audio_file_path}: segments={len(transcription_result.get('segments', []))}"
                )

                text = transcription_result["text"]
                transcription_results[str(audio_file_path)] = text
                successfully_transcribed_files.append(audio_file_path)
                print(f"DEBUG: Successfully transcribed {audio_file_path}")
            except Exception as e:
                print(f"DEBUG: Error during transcription of {audio_file_path}: {e}")
                failed_transcription_files.append(str(audio_file_path))

    except Exception as e:
        print(f"DEBUG: General error in transcribe_files: {e}")
        # if a general error occurs (e.g., model loading), mark all as failed
        for audio_file_path in file_paths:
            failed_transcription_files.append(str(audio_file_path))

    finally:
        if model is not None:
            try:
                del model
                gc.collect()
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                print("DEBUG: Whisper model unloaded from memory.")
            except Exception as e:
                print(f"DEBUG: Error unloading Whisper model: {e}")

    print(
        f"DEBUG: transcribe_files completed. Success: {len(successfully_transcribed_files)}, Fail: {len(failed_transcription_files)}"
    )
    return (
        successfully_transcribed_files,
        failed_transcription_files,
        transcription_results,
    )


def _save_transcription_results(
    SessionLocal: sessionmaker,
    items_to_save: List,
    transcription_results: Dict[str, str],
    successfully_transcribed: List[Path],
    failed_transcriptions: List[str],
):
    """
    Saves the results of a transcription batch to the database in a single transaction.
    """
    print(f"DB_DEBUG: _save_transcription_results called with {len(items_to_save)} items to save.")
    if not items_to_save:
        print("DB_DEBUG: No items to save, returning.")
        return 0

    saved_count = 0
    print("DB_DEBUG: Opening database session with context manager.")
    with SessionLocal() as db:
        try:
            print(f"DB_DEBUG: Starting to loop through {len(items_to_save)} items.")
            for item in items_to_save:
                print(f"DB_DEBUG: Processing item: {item.url} (Status: {item.status})")
                if Path(item.local_path) in successfully_transcribed:
                    try:
                        text_content = transcription_results[item.local_path]
                        insert_transcription_result(
                            db, item.url, item.title, text_content
                        )
                        video_queue.update_item_status(item.id, VideoStatus.COMPLETED)
                        saved_count += 1
                        transcription_status["processed_videos"].append({
                            "url": item.url,
                            "video_title": item.title,
                            "transcription_length": len(text_content),
                        })
                    except Exception as e:
                        print(
                            f"ERROR saving result for {item.url} to database: {e}"
                        )
                        video_queue.update_item_status(
                            item.id, VideoStatus.FAILED, error_message=str(e)
                        )
                        if item.url not in transcription_status["failed_urls"]:
                            transcription_status["failed_urls"].append(item.url)
                elif item.local_path in failed_transcriptions:
                    video_queue.update_item_status(item.id, VideoStatus.FAILED, error_message="Transcription failed")
                    if item.url not in transcription_status["failed_urls"]:
                        transcription_status["failed_urls"].append(item.url)
            
            print(f"DB_DEBUG: Loop finished. Attempting to commit {saved_count} records.")
            db.commit()
            print(f"DB_DEBUG: Commit successful. Committed {saved_count} transcription(s) to the database.")
        except Exception as e:
            print(f"CRITICAL ERROR during database commit: {e}")
            print("DB_DEBUG: Rolling back transaction.")
            db.rollback()
            # Mark all items in this batch as failed if the transaction fails
            for item in items_to_save:
                video_queue.update_item_status(
                    item.id,
                    VideoStatus.FAILED,
                    error_message=f"DB transaction failed: {e}",
                )
                if item.url not in transcription_status["failed_urls"]:
                    transcription_status["failed_urls"].append(item.url)
            raise  # Re-raise the exception to be handled by the main pipeline
    return saved_count


def run_transcription_pipeline(SessionLocal: sessionmaker):
    """
    Main pipeline to download, transcribe, and manage video/audio processing.
    This function processes the entire queue in a batch to optimize model loading.
    """
    global transcription_status, video_queue
    print("DEBUG: Batch transcription pipeline started.")

    # 1. Initialization
    try:
        # DB is initialized on app startup, no need to call it here.
        TMP_DIR.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        transcription_status = {
            "status": "error", "progress": "0/0", "processed_videos": [],
            "failed_urls": [f"DB initialization failed: {e}"],
        }
        print(f"DEBUG: Pipeline failed during DB initialization: {e}")
        return

    items_to_process = video_queue.get_all_and_lock_for_batch()
    
    if not items_to_process:
        print("DEBUG: Queue is empty. Nothing to process.")
        transcription_status = get_initial_transcription_status()
        transcription_status["status"] = "completed"
        video_queue.release_batch_lock()
        return

    try:
        files_to_transcribe = []
        url_to_item_map = {}
        processed_count = 0

        for item in items_to_process:
            url_to_item_map[item.url] = item

        transcription_status["status"] = "processing"
        transcription_status["progress"] = f"0/{len(items_to_process)}"

        # 2. Prepare files (Download, find local paths)
        for item in items_to_process:
            try:
                if item.video_type == VideoType.CUSTOM:
                    filename = item.url.replace("custom://", "")
                    filepath = CUSTOM_VIDEOS_DIR / filename
                    if filepath.exists():
                        files_to_transcribe.append(filepath)
                        item.local_path = str(filepath)
                    else:
                        raise FileNotFoundError(f"Custom file not found: {filepath}")
                
                elif item.video_type == VideoType.YOUTUBE:
                    video_queue.update_item_status(item.id, VideoStatus.DOWNLOADING)
                    update_status_from_queue()
                    
                    title = get_youtube_title(item.url)
                    item.title = title
                    
                    success, downloaded_path, error_msg = download_youtube_video(item.url, TMP_DIR, title)
                    if success and downloaded_path:
                        files_to_transcribe.append(downloaded_path)
                        item.local_path = str(downloaded_path)
                    else:
                        raise Exception(f"Download failed: {error_msg}")

            except Exception as e:
                print(f"ERROR preparing {item.url}: {e}")
                video_queue.update_item_status(item.id, VideoStatus.FAILED, error_message=str(e))
                transcription_status["failed_urls"].append(item.url)

        # 3. Batch transcribe all prepared files
        if files_to_transcribe:
            model_name = os.getenv("WHISPER_MODEL", "turbo")
            (
                successfully_transcribed,
                failed_transcriptions,
                transcription_results,
            ) = transcribe_files(model_name, files_to_transcribe)

            # 4. Process and save results to the database
            items_to_save = [
                item
                for item in items_to_process
                if item.local_path and item.status != VideoStatus.FAILED
            ]

            processed_count = _save_transcription_results(
                SessionLocal, items_to_save, transcription_results, successfully_transcribed, failed_transcriptions
            )
            
            transcription_status["progress"] = f"{processed_count}/{len(items_to_process)}"

        # 5. Finalize status
        if transcription_status["failed_urls"]:
            transcription_status["status"] = "completed_with_errors"
        else:
            transcription_status["status"] = "completed"

        print(f"DEBUG: Pipeline completed. "
              f"Successful: {processed_count}, "
              f"Failed: {len(transcription_status['failed_urls'])}")

        # Clean up all temporary files
        for path in files_to_transcribe:
            try:
                if path.exists():
                    path.unlink()
                    print(f"DEBUG: Cleaned up file: {path}")
            except Exception as e:
                print(f"DEBUG: Failed to clean up file {path}: {e}")
    
    except Exception as e:
        print(f"CRITICAL ERROR in transcription pipeline: {e}")
        # Mark all unprocessed items as failed
        for item in items_to_process:
            if item.status not in [VideoStatus.COMPLETED, VideoStatus.FAILED]:
                 video_queue.update_item_status(item.id, VideoStatus.FAILED, error_message=f"Pipeline error: {e}")
                 if item.url not in transcription_status["failed_urls"]:
                    transcription_status["failed_urls"].append(item.url)
        transcription_status["status"] = "error"
        raise # Re-raise the exception to be logged by the server
    
    finally:
        video_queue.release_batch_lock()


# Create the app
app = create_app()

@app.on_event("startup")
def on_startup():
    """Create database tables and required directories on application startup."""
    print("INFO:     Application startup...")
    # 1. Create database tables
    print("INFO:     Initializing database...")
    try:
        Base.metadata.create_all(bind=app.state.engine)
        print("INFO:     Database initialization completed successfully.")
    except Exception as e:
        print(f"ERROR:    Error initializing database: {e}")
        raise e

    # 2. Ensure directories exist
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    CUSTOM_VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
    print("INFO:     Temp and custom video directories are ready.")
    print("INFO:     Application startup complete.")


if __name__ == "__main__":
    # Note: The uvicorn.run command is for development.
    # In production, a Gunicorn/Uvicorn worker process would run this.
    print(f"Starting uvicorn server on 0.0.0.0:8000")
    uvicorn.run("transcriber:app", host="0.0.0.0", port=8000, reload=True)

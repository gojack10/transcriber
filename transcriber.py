import os
import whisper
from pathlib import Path
import sys
import subprocess
import re
import psycopg2
from datetime import datetime
import pytz
from zoneinfo import ZoneInfo
import shutil
from fastapi import FastAPI, HTTPException, Body, status as fastapi_status
from pydantic import BaseModel
import uvicorn
from typing import List, Dict, Tuple

# --- configuration ---
BASE_DIR = Path(__file__).resolve().parent
TMP_DIR = BASE_DIR / "tmp"
LIST_FILE = BASE_DIR / "list.txt"

# supported audio file extensions (add more if needed)
AUDIO_EXTENSIONS = {".mp3", ".wav", ".flac", ".m4a", ".ogg", ".aac", ".wma"}

# --- global state for api ---
transcription_status: Dict[str, str] = {"status": "idle", "progress": "0/0"}
# lock or other synchronization mechanism might be needed if main_transcription runs in a separate thread/process
# for simplicity, we'll assume for now that n8n calls /add_links, then transcription runs, then /clear_list

app = FastAPI()

class UrlList(BaseModel):
    urls: List[str]

# --- postgresql database functions ---
def get_db_connection():
    """establishes a connection to the postgresql database."""
    try:
        conn = psycopg2.connect(
            host=os.getenv("DB_HOST", "127.0.0.1"),
            port=os.getenv("DB_PORT", "5432"),
            database=os.getenv("DB_NAME", "transcriber_db"),
            user=os.getenv("DB_USER", "gojack10"),
            password=os.getenv("DB_PASSWORD", "moso10")
        )
        return conn
    except psycopg2.Error as e:
        print(f"Error connecting to PostgreSQL database: {e}")
        sys.exit(1)

def initialize_db():
    """initializes the postgresql database and creates the necessary tables."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            create table if not exists downloaded_videos (
                id serial primary key,
                url text unique,
                status text not null,
                download_date text not null,
                local_path text,
                yt_dlp_processed boolean default false
            )
        ''')
        cursor.execute('''
            create table if not exists transcribed (
                id serial primary key,
                utc_time text not null,
                pst_time text not null,
                url text unique,
                video_title text not null,
                content text not null,
                foreign key (url) references downloaded_videos(url)
            )
        ''')
        # attempt to add the yt_dlp_processed column if it doesn't exist, for existing tables
        cursor.execute('''
            alter table downloaded_videos
            add column if not exists yt_dlp_processed boolean default false;
        ''')
        cursor.execute('''
            alter table transcribed
            add column if not exists url text unique;
        ''')
        # check if constraint exists before adding
        cursor.execute("""
            select constraint_name from information_schema.table_constraints
            where table_name='transcribed' and constraint_name='fk_downloaded_videos';
        """)
        if not cursor.fetchone():
            cursor.execute('''
                alter table transcribed
                add constraint fk_downloaded_videos
                foreign key (url) references downloaded_videos(url);
            ''')
        conn.commit()
        print("postgresql database initialized and tables (and columns) ensured.")
    except psycopg2.Error as e:
        print(f"Error initializing PostgreSQL database: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

def get_download_status(url: str) -> tuple[str | None, str | None, bool | None]:
    """
    checks the download status, local path, and yt_dlp_processed flag of a url in the database.
    returns (status, local_path, yt_dlp_processed) or (none, none, none) if not found.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    result = (None, None, None)
    try:
        cursor.execute("SELECT status, local_path, yt_dlp_processed FROM downloaded_videos WHERE url = %s", (url,))
        result = cursor.fetchone()
    except psycopg2.Error as e:
        print(f"Error getting download status: {e}")
    finally:
        cursor.close()
        conn.close()
    return result if result else (None, None, None)

def update_download_status(url: str, status: str, local_path: Path | None = None, yt_dlp_processed: bool = False):
    """
    adds or updates a url's status, local path, and yt_dlp_processed flag in the database.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    download_date = datetime.now().isoformat()
    local_path_str = str(local_path) if local_path else None

    try:
        cursor.execute('''
            INSERT INTO downloaded_videos (url, status, download_date, local_path, yt_dlp_processed)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (url) DO UPDATE SET
                status = EXCLUDED.status,
                download_date = EXCLUDED.download_date,
                local_path = EXCLUDED.local_path,
                yt_dlp_processed = EXCLUDED.yt_dlp_processed
        ''', (url, status, download_date, local_path_str, yt_dlp_processed))
        conn.commit()
        print(f"Database updated for '{url}' with status '{status}'.")
    except psycopg2.Error as e:
        print(f"Error updating download status: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

def insert_transcription_result(url: str, video_title: str, content: str):
    """
    inserts a transcription result into the transcribed table, linked to the downloaded video url.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    utc_time = datetime.utcnow().isoformat()
    
    # Get current UTC time
    now_utc = datetime.now(ZoneInfo("UTC"))
    
    # Define the PST timezone
    pst_timezone = pytz.timezone('America/Los_Angeles')
    
    # Convert UTC time to PST
    pst_time_dt = now_utc.astimezone(pst_timezone)
    
    # Format PST time as MM/DD/YYYY HH:MM:SS AM/PM
    pst_time = pst_time_dt.strftime('%m/%d/%Y %I:%M:%S %p')

    try:
        cursor.execute('''
            INSERT INTO transcribed (utc_time, pst_time, url, video_title, content)
            VALUES (%s, %s, %s, %s, %s)
        ''', (utc_time, pst_time, url, video_title, content))
        conn.commit()
        print(f"Transcription for '{video_title}' (URL: {url}) saved to database.")
    except psycopg2.Error as e:
        print(f"Error inserting transcription result: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

def transcribe_files(model_name: str, downloaded_files_with_urls: list[tuple[Path, str]]) -> tuple[list[Path], list[str], dict[str, str]]:
    """
    transcribes a list of audio files using the specified whisper model.
    returns a tuple: (processed_originals_paths, failed_transcription_filenames, transcription_results)
    """
    global transcription_status
    processed_originals_paths = []
    failed_transcription_filenames = []
    transcription_results = {}

    if not downloaded_files_with_urls:
        print("No audio files provided for transcription.")
        return [], [], {}

    print(f"\nLoading Whisper model '{model_name}'... (This might take a while the first time)")
    try:
        model = whisper.load_model(model_name)
        print(f"Model '{model_name}' loaded successfully.")
    except Exception as e:
        print(f"Error loading Whisper model '{model_name}': {e}")
        print("Please ensure the model name is correct and you have enough resources.")
        print("You might also need to install Rust if tiktoken doesn't have a pre-built wheel for your system.")
        return [], [], {}

    print(f"\nFound {len(downloaded_files_with_urls)} audio file(s) to transcribe.")

    total_files = len(downloaded_files_with_urls)
    transcribed_count = 0
    # update status for the api
    transcription_status["progress"] = f"{transcribed_count}/{total_files}"

    for audio_file_path, url in downloaded_files_with_urls:
        print(f"\nProcessing '{audio_file_path.name}' ({transcribed_count + 1}/{total_files})...")

        try:
            result = model.transcribe(str(audio_file_path), fp16=False)
            transcription = result["text"]
            transcription_results[url] = transcription
            processed_originals_paths.append(audio_file_path)
            print(f"  Successfully transcribed '{audio_file_path.name}'. Transcription saved to database.")
            
            # Extract video title from audio_file_path.name (remove extension)
            video_title = audio_file_path.stem
            insert_transcription_result(url, video_title, transcription)
        except Exception as e:
            print(f"  Error transcribing '{audio_file_path.name}': {e}")
            failed_transcription_filenames.append(audio_file_path.name)
        
        transcribed_count += 1
        transcription_status["progress"] = f"{transcribed_count}/{total_files}"

    return processed_originals_paths, failed_transcription_filenames, transcription_results

def download_youtube_videos(youtube_urls: list[str], output_dir: Path) -> tuple[list[tuple[Path, str]], list[str], list[str]]:
    """
    downloads youtube videos as audio and saves them to the output directory.
    also updates the database with download status.
    returns a tuple: (downloaded_files_with_urls, failed_downloads, already_processed_urls)
    downloaded_files_with_urls is a list of (path_to_audio_file, original_url)
    """
    global transcription_status
    if not youtube_urls:
        print("no youtube urls provided for download.")
        return [], [], []

    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"\ndownloading videos to '{output_dir}'...")

    downloaded_files_with_urls: list[tuple[Path, str]] = []
    failed_downloads: list[str] = []
    already_processed_urls: list[str] = []
    
    total_urls = len(youtube_urls)
    processed_count = 0
    transcription_status["progress"] = f"{processed_count}/{total_urls}" # initial status for download phase

    for url in youtube_urls:
        print(f"\nProcessing URL {processed_count + 1} of {total_urls}: {url}")
        db_status, local_path_str, yt_dlp_processed = get_download_status(url)

        if db_status == "downloaded" and local_path_str and Path(local_path_str).exists() and yt_dlp_processed:
            print(f"'{url}' already downloaded and processed by yt-dlp. adding to list for transcription check.")
            downloaded_files_with_urls.append((Path(local_path_str), url))
            # no need to update status here as it's already marked as downloaded and processed by yt-dlp
            # we are just ensuring it gets passed to the transcription phase
            already_processed_urls.append(url) # track these separately if needed
            processed_count +=1
            transcription_status["progress"] = f"{processed_count}/{total_urls}"
            continue
        elif db_status == "downloaded" and local_path_str and Path(local_path_str).exists() and not yt_dlp_processed:
            print(f"'{url}' was downloaded but not marked as yt-dlp processed. attempting to re-process with yt-dlp.")
            # proceed to download with yt-dlp, it will either use the existing file or redownload if necessary
        elif db_status == "failed":
            print(f"skipping '{url}' as it previously failed to download.")
            failed_downloads.append(url)
            processed_count +=1
            transcription_status["progress"] = f"{processed_count}/{total_urls}"
            continue
        elif db_status is not None:
             print(f"URL '{url}' has status '{db_status}'. attempting download/re-download.")

        # revised strategy: download with a generic name or let yt-dlp name it,
        # then find the downloaded audio file.
        # ensure the tmp dir is clean for this video download to easily find the new file.
        # cleanup_tmp_dir(output_dir) # clean before each download might be too aggressive if multiple files are there

        # use yt-dlp to download audio
        # options:
        # -x: extract audio
        # --audio-format mp3: convert to mp3
        # --output: specify output template
        # --get-title: to get the title for db
        # --no-playlist: if url is a playlist, download only the video.
        # --ignore-errors: continue on download errors for other videos.
        # -o "%(title)s.%(ext)s" : names file based on video title
        # we need a predictable way to get the output file path.
        # let's try to get title first, then use it for filename.

        sanitized_url_for_filename = re.sub(r'[^a-zA-Z0-9]', '_', url) # simple sanitization
        # temp_audio_path_template = output_dir / f"{sanitized_url_for_filename}.%(ext)s"
        # using video id is better.
        # first, get video id using yt-dlp --get-id
        
        temp_output_filename = f"audio_{datetime.now().timestamp()}" # unique temp name
        temp_audio_path_guess = output_dir / f"{temp_output_filename}.mp3" # assuming mp3 for now

        cmd = [
            "yt-dlp",
            "-x", "--audio-format", "mp3",
            # "-o", str(temp_audio_path_template),
            "-o", str(output_dir / f"{temp_output_filename}.%(ext)s"), # yt-dlp will replace %(ext)s
            "--no-playlist",
            url
        ]
        print(f"Running command: {' '.join(cmd)}")

        try:
            process = subprocess.run(cmd, capture_output=True, text=True, check=False) # check=false to handle errors manually
            if process.returncode == 0:
                # find the downloaded file. there should be only one new mp3 in output_dir.
                # this is a bit fragile. a better way is if yt-dlp could report the exact filename.
                # using --print filename might work.
                # for now, let's find the newest mp3 file in the directory.
                
                # search for files matching the temp_output_filename base
                potential_files = list(output_dir.glob(f"{temp_output_filename}.*"))
                # filter by known audio extensions
                audio_files_found = [f for f in potential_files if f.suffix.lower() in AUDIO_EXTENSIONS]

                if audio_files_found:
                    downloaded_audio_path = audio_files_found[0] # take the first match
                    print(f"Successfully downloaded and extracted audio to '{downloaded_audio_path}'")
                    update_download_status(url, "downloaded", downloaded_audio_path, yt_dlp_processed=True)
                    downloaded_files_with_urls.append((downloaded_audio_path, url))
                else:
                    print(f"yt-dlp ran but could not find the downloaded audio file for url: {url}. stdout: {process.stdout}, stderr: {process.stderr}")
                    failed_downloads.append(url)
                    update_download_status(url, "failed_to_find_file")

            else:
                print(f"Failed to download '{url}'. Return code: {process.returncode}")
                print(f"stdout: {process.stdout}")
                print(f"stderr: {process.stderr}")
                failed_downloads.append(url)
                update_download_status(url, "failed")
        except Exception as e:
            print(f"An exception occurred while trying to download '{url}': {e}")
            failed_downloads.append(url)
            update_download_status(url, "failed_exception")
        
        processed_count += 1
        transcription_status["progress"] = f"{processed_count}/{total_urls}"

    if failed_downloads:
        print("\n--- Download Summary ---")
        print(f"{len(downloaded_files_with_urls)} file(s) downloaded successfully.")
        print(f"{len(failed_downloads)} file(s) failed to download:")
        for url in failed_downloads:
            print(f"  - {url}")
    if already_processed_urls:
        print(f"{len(already_processed_urls)} file(s) were already downloaded and processed by yt-dlp.")

    return downloaded_files_with_urls, failed_downloads, already_processed_urls

def get_video_title_from_db(url: str) -> str | None:
    """Retrieves the video title from the database using the URL (if downloaded)."""
    # This function assumes that the title is somehow stored or can be inferred
    # from the database records, perhaps from `local_path` if it includes the title,
    # or if `download_youtube_videos` is modified to store titles.
    # For now, let's try to extract from local_path if it's named well, or default.
    _, local_path_str, _ = get_download_status(url)
    if local_path_str:
        # Assumes filename (without extension) is the title
        return Path(local_path_str).stem 
    return "unknown_title"

def cleanup_tmp_dir(tmp_dir: Path):
    """
    Deletes all files and subdirectories within the specified temporary directory.
    """
    if not tmp_dir.exists():
        print(f"Temporary directory '{tmp_dir}' does not exist. No cleanup needed.")
        return

    print(f"\n--- Cleaning up temporary directory '{tmp_dir}' ---")
    for item in tmp_dir.iterdir():
        try:
            if item.is_file():
                item.unlink()
                print(f"  Deleted file: '{item.name}'")
            elif item.is_dir():
                import shutil
                shutil.rmtree(item)
                print(f"  Deleted directory: '{item.name}'")
        except Exception as e:
            print(f"  Error deleting '{item.name}': {e}")
    print("Temporary directory cleanup complete.")

def run_transcription_pipeline():
    """
    Main function to run the transcription pipeline.
    Reads URLs from list_file, downloads, transcribes, and saves to db.
    """
    global transcription_status
    print("Starting transcription pipeline...")
    transcription_status = {"status": "processing", "progress": "0/0"}

    # Ensure tmp directory exists
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    # Initialize database
    initialize_db()

    # Read URLs from list.txt
    if not LIST_FILE.exists() or LIST_FILE.stat().st_size == 0:
        print(f"'{LIST_FILE}' is empty or does not exist. Nothing to process.")
        transcription_status = {"status": "idle", "progress": "0/0"}
        return

    with open(LIST_FILE, "r") as f:
        youtube_urls = [line.strip() for line in f if line.strip()]

    if not youtube_urls:
        print("No URLs found in list.txt after stripping empty lines.")
        transcription_status = {"status": "idle", "progress": "0/0"}
        return
        
    total_urls = len(youtube_urls)
    print(f"Found {total_urls} URL(s) in '{LIST_FILE}'.")
    transcription_status["progress"] = f"0/{total_urls}"

    # Download videos
    # Model name selection - can be configurable
    # model_name = "tiny.en" # for faster testing
    # model_name = "small.en"
    model_name = os.getenv("WHISPER_MODEL", "base.en") # more robust
    
    downloaded_files_with_urls, failed_downloads, _ = download_youtube_videos(youtube_urls, TMP_DIR)

    # Filter out files that failed to download before transcription
    valid_files_for_transcription = [item for item in downloaded_files_with_urls if item[0].exists()]

    if not valid_files_for_transcription:
        print("No files were successfully downloaded or found for transcription.")
        cleanup_tmp_dir(TMP_DIR) # Clean up any partial downloads
        transcription_status = {"status": "completed_with_errors", "progress": f"{len(failed_downloads)}/{total_urls} failed"}
        # Consider how to signal partial success/failure to n8n
        return

    # Transcribe downloaded files
    # The progress inside transcribe_files will be more granular (per file transcribed)
    # We might want a combined progress or phases (downloading, transcribing)
    # For now, transcribe_files updates its own part of the progress for the transcription phase
    transcription_status["status"] = "transcribing" 
    # The progress here will be reset by transcribe_files based on number of files to transcribe
    
    processed_originals, failed_transcriptions, transcription_results = transcribe_files(model_name, valid_files_for_transcription)

    # Save results to database
    saved_to_db_count = 0
    for url, text_content in transcription_results.items():
        video_title = get_video_title_from_db(url) # or get it from yt-dlp earlier
        if not video_title: # try to get it from the filename if db method fails
             # find the path associated with this url
            path_for_url = next((p for p, u in valid_files_for_transcription if u == url), None)
            if path_for_url:
                video_title = path_for_url.stem
            else:
                video_title = "unknown_title - " + url[:30]

        insert_transcription_result(url, video_title, text_content)
        saved_to_db_count +=1
        # update overall progress if needed, though transcribe_files handles its part.
        # this part is about db insertion.

    print(f"\n--- Pipeline Summary ---")
    print(f"{len(youtube_urls)} URL(s) initially provided.")
    print(f"{len(downloaded_files_with_urls)} video(s) were attempted for download.")
    print(f"{len(failed_downloads)} video(s) failed to download.")
    print(f"{len(valid_files_for_transcription)} video(s) submitted for transcription.")
    print(f"{len(transcription_results)} video(s) transcribed successfully.")
    print(f"{len(failed_transcriptions)} video(s) failed during transcription.")
    print(f"{saved_to_db_count} transcription(s) saved to database.")

    # Cleanup
    cleanup_tmp_dir(TMP_DIR)
    print("Temporary files cleaned up.")
    
    if not failed_downloads and not failed_transcriptions:
        transcription_status = {"status": "completed", "progress": f"{total_urls}/{total_urls}"}
        print("Transcription pipeline completed successfully for all URLs.")
    else:
        # More detailed status for partial success
        # Count successful transcriptions that were saved
        successful_final_count = saved_to_db_count 
        transcription_status = {
            "status": "completed_with_errors", 
            "progress": f"{successful_final_count}/{total_urls} transcribed and saved",
            "details": {
                "total_provided": total_urls,
                "download_failures": len(failed_downloads),
                "transcription_failures": len(failed_transcriptions),
                "successful_transcriptions_saved": saved_to_db_count
            }
        }
        print("Transcription pipeline completed with some errors.")
        # It's up to the agent to check the db for which specific URLs succeeded.

    # n8n should call /clear_list after verifying db state.
    # We don't clear list.txt automatically here.

# --- api endpoints ---
@app.post("/add_links", status_code=fastapi_status.HTTP_202_ACCEPTED)
async def add_links_to_process(payload: UrlList = Body(...)):
    """
    Appends a list of URLs to list.txt.
    Triggers the transcription pipeline if it's not already running.
    """
    global transcription_status
    if transcription_status.get("status") == "processing" or transcription_status.get("status") == "transcribing":
        raise HTTPException(
            status_code=fastapi_status.HTTP_409_CONFLICT,
            detail="A transcription process is already running. Please wait or clear the list first if stuck."
        )

    try:
        with open(LIST_FILE, "a") as f:
            for url in payload.urls:
                f.write(f"{url}\n")
        # After adding links, run the pipeline
        # Ideally, this should be a background task so the API call returns quickly
        # For now, let's call it directly. n8n might time out if this takes too long.
        # Consider using fastapi's backgroundtasks or a separate worker process.
        
        # For simplicity, we'll run it synchronously for now and rely on n8n's async handling.
        # This means the /add_links endpoint will block until all processing is done.
        # This is not ideal for a real API.
        # TODO: make run_transcription_pipeline asynchronous
        run_transcription_pipeline() 
        
        return {"message": f"{len(payload.urls)} URLs added to {LIST_FILE} and processing started/completed.", "current_status": transcription_status}
    except Exception as e:
        raise HTTPException(
            status_code=fastapi_status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail=f"Failed to add links or run pipeline: {str(e)}"
        )

@app.get("/status")
async def get_status():
    """Returns the current status of the transcription process."""
    global transcription_status
    return transcription_status

@app.post("/clear_list", status_code=fastapi_status.HTTP_200_OK)
async def clear_list_file():
    """Clears all text in list.txt."""
    global transcription_status
    try:
        with open(LIST_FILE, "w") as f:
            f.write("")
        # Reset status after clearing
        transcription_status = {"status": "idle", "progress": "0/0"}
        return {"message": f"'{LIST_FILE}' has been cleared."}
    except Exception as e:
        raise HTTPException(
            status_code=fastapi_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to clear {LIST_FILE}: {str(e)}"
        )

# --- main execution (when script is run directly) ---
def main(): # main is now for direct script execution if needed, or can be removed.
    """
    Original main function, now more for command-line use if ever needed,
    or can be refactored into run_transcription_pipeline fully.
    """
    print("Running main function for direct script execution (if any setup is needed here)...")
    # For CLI usage, one might want to pass URLs directly, bypassing the API.
    # This part needs to be re-evaluated if CLI usage is still desired alongside API.
    # For now, the primary way to trigger processing is via /add_links.
    # initialize_db() # ensure db is up if running standalone for some reason.
    # run_transcription_pipeline() # example: process whatever is in list.txt on startup

if __name__ == "__main__":
    # This will start the fastapi server
    # Make sure LIST_FILE exists
    if not LIST_FILE.exists():
        LIST_FILE.touch()
        print(f"Created {LIST_FILE} as it did not exist.")

    # Ensure tmp directory exists
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    initialize_db() # Initialize db on server start

    print(f"Starting uvicorn server on 0.0.0.0:8000")
    # uvicorn.run(app, host="0.0.0.0", port=8000) 
    # The line above is for programmatic start. If running with `uvicorn transcriber:app --reload`
    # Then this __main__ section might behave differently or not be the primary entry point for the server.
    # For Docker, we'll use the uvicorn command directly.
    # Let's make this __main__ runnable for local dev.
    uvicorn.run("transcriber:app", host="0.0.0.0", port=8000, reload=True) # reload for dev

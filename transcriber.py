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
from fastapi import FastAPI, HTTPException, Body, status as fastapi_status, BackgroundTasks
from pydantic import BaseModel
import uvicorn
from typing import List, Dict, Tuple, Any
from pydantic import BaseModel
from fastapi.responses import JSONResponse

class UrlList(BaseModel):
    urls: List[str]

# --- configuration ---
BASE_DIR = Path(__file__).resolve().parent
TMP_DIR = BASE_DIR / "tmp"
LIST_FILE = BASE_DIR / "list.txt"

# supported audio file extensions (add more if needed)
AUDIO_EXTENSIONS = {".mp3", ".wav", ".flac", ".m4a", ".ogg", ".aac", ".wma"}

def get_initial_transcription_status() -> Dict[str, Any]:
    """Returns a new dictionary representing the initial, idle transcription status."""
    return {"status": "idle", "progress": "0/0", "processed_videos": [], "failed_urls": []}

# --- global state for api ---
# extended status to include processed videos and errors
# example:
# {
#   "status": "completed",
#   "progress": "2/2",
#   "processed_videos": [{"url": "url1", "title": "title1"}],
#   "failed_urls": ["url2"]
# }
transcription_status: Dict[str, Any] = get_initial_transcription_status()
print(f"DEBUG: Initial transcription_status: {transcription_status}")

def create_app() -> FastAPI:
    global transcription_status
    # reset the global state for the new app instance (or test run)
    transcription_status = get_initial_transcription_status()
    print(f"DEBUG: create_app called, transcription_status reset to: {transcription_status}")
    _app = FastAPI()

    # --- api endpoints moved here ---
    @_app.post("/add_links", status_code=fastapi_status.HTTP_200_OK)
    async def add_links_to_list(payload: UrlList = Body(...)):
        """
        appends a list of urls to list.txt. does not trigger processing.
        """
        global transcription_status
        try:
            count_added = 0
            with open(LIST_FILE, "a") as f:
                for url in payload.urls:
                    f.write(f"{url}\n")
            count_added = len(payload.urls)
            return {"message": f"{count_added} url(s) added to {LIST_FILE}. call /trigger_transcription to start processing."}
        except IOError as e:
            raise HTTPException(
                status_code=fastapi_status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"failed to add links to {LIST_FILE}: {e}"
            )

    @_app.post("/trigger_transcription", status_code=fastapi_status.HTTP_202_ACCEPTED)
    async def trigger_transcription_processing(background_tasks: BackgroundTasks):
        """
        triggers the transcription pipeline to run in the background.
        """
        global transcription_status
        print(f"DEBUG: /trigger_transcription endpoint hit. Current status: {transcription_status}")
        if transcription_status["status"] not in ["idle", "completed", "completed_with_errors"]:
            print(f"DEBUG: /trigger_transcription returning 409 due to status: {transcription_status['status']}")
            raise HTTPException(
                status_code=fastapi_status.HTTP_409_CONFLICT,
                detail=f"a transcription process is already active or queued (status: {transcription_status['status']}). please wait."
            )
        
        if not LIST_FILE.exists() or LIST_FILE.stat().st_size == 0:
            print(f"DEBUG: /trigger_transcription returning idle for empty list.txt. Status: {transcription_status}")
            return JSONResponse(
                status_code=fastapi_status.HTTP_200_OK,
                content={"message": f"'{LIST_FILE}' is empty. nothing to trigger.", "status": "idle"}
            )

        transcription_status.update(get_initial_transcription_status())
        transcription_status["status"] = "queued"
        print(f"DEBUG: /trigger_transcription: Status set to 'queued' before task: {transcription_status}")
        background_tasks.add_task(run_transcription_pipeline)
        
        return {
            "message": "transcription process triggered.",
            "initial_status": transcription_status
        }

    @_app.get("/status")
    async def get_status():
        """retrieves the current status of the transcription pipeline."""
        global transcription_status
        print(f"DEBUG: /status endpoint hit. Returning status: {transcription_status}")
        return transcription_status

    @_app.post("/clear_list", status_code=fastapi_status.HTTP_200_OK)
    async def clear_list_file():
        """clears all text in list.txt and resets status to idle."""
        global transcription_status
        print(f"DEBUG: /clear_list endpoint hit. Current status before clear: {transcription_status}")
        try:
            with open(LIST_FILE, "w") as f:
                f.write("")
            transcription_status.update(get_initial_transcription_status())
            print(f"DEBUG: /clear_list: Status reset to idle: {transcription_status}")
            return {"message": f"'{LIST_FILE}' has been cleared and status reset to idle."}
        except IOError as e:
            print(f"DEBUG: /clear_list: Error clearing file: {e}")
            raise HTTPException(
                status_code=fastapi_status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"failed to clear {LIST_FILE}: {e}"
            )

    return _app # return _app

app = create_app() # Initialize app globally

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
    returns a tuple: (processed_originals_paths, failed_transcription_filenames, transcription_results_dict_url_text)
    transcription_results_dict_url_text: maps original url to transcribed text
    """
    global transcription_status
    processed_originals_paths = []
    failed_transcription_filenames = [] # these are path names, not urls
    transcription_results_dict_url_text: Dict[str, str] = {}

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
            transcription_results_dict_url_text[url] = transcription # use url as key
            processed_originals_paths.append(audio_file_path)
            print(f"  Successfully transcribed '{audio_file_path.name}'.")
            
            # Extract video title from audio_file_path.name (remove extension)
            video_title = audio_file_path.stem
            # insert_transcription_result(url, video_title, transcription) # moved to main pipeline
        except Exception as e:
            print(f"  Error transcribing '{audio_file_path.name}': {e}")
            failed_transcription_filenames.append(audio_file_path.name)
        
        transcribed_count += 1
        transcription_status["progress"] = f"{transcribed_count}/{total_files}"

    return processed_originals_paths, failed_transcription_filenames, transcription_results_dict_url_text

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
    """retrieves the video title from the database using the url (if downloaded)."""
    # this function assumes that the title is somehow stored or can be inferred
    # from the database records, perhaps from `local_path` if it includes the title,
    # or if `download_youtube_videos` is modified to store titles.
    # for now, let's try to extract from local_path if it's named well, or default.
    
    # try to get title from local_path first, as it's likely named by yt-dlp based on title
    _, local_path_str, _ = get_download_status(url)
    if local_path_str:
        # assumes filename (without extension) is the title
        # this stem might include unique ids if yt-dlp added them, but it's usually close to the title.
        # for a more accurate title, it should be fetched during yt-dlp processing if possible and stored.
        title = Path(local_path_str).stem
        # crude way to remove common yt-dlp id patterns if they are at the end, e.g. [id_string] or _id_string
        title = re.sub(r'\s*\[[\w-]{11}\]$|\s*\[[\w-]{10}\]$|\s*_[\w-]{11}$|\s*_[\w-]{10}$', '', title)
        return title
    return f"unknown_title_for_{url[:30]}" # fallback

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
    main function to run the transcription pipeline.
    reads urls from list_file, downloads, transcribes, and saves to db.
    updates global transcription_status.
    """
    global transcription_status
    print("starting transcription pipeline run...")
    print(f"DEBUG: run_transcription_pipeline started. Current status: {transcription_status}")
    # initial status set by /trigger_transcription, this function updates it through phases

    # ensure tmp directory exists
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    # initialize database
    initialize_db()

    # read urls from list.txt
    if not LIST_FILE.exists() or LIST_FILE.stat().st_size == 0:
        print(f"'{LIST_FILE}' is empty or does not exist. nothing to process.")
        transcription_status = get_initial_transcription_status()
        print(f"DEBUG: list.txt empty/not found. Status reset to: {transcription_status}")
        return

    with open(LIST_FILE, "r") as f:
        youtube_urls = [line.strip() for line in f if line.strip()]

    if not youtube_urls:
        print("no urls found in list.txt after stripping empty lines.")
        transcription_status = get_initial_transcription_status()
        print(f"DEBUG: No URLs after stripping. Status reset to: {transcription_status}")
        return
        
    total_urls = len(youtube_urls)
    print(f"found {total_urls} url(s) in '{LIST_FILE}'.")
    transcription_status.update({"status": "processing", "progress": f"0/{total_urls}", "processed_videos": [], "failed_urls": []})
    print(f"DEBUG: Status updated to 'processing': {transcription_status}")

    # download videos
    model_name = os.getenv("WHISPER_MODEL", "base.en")
    
    downloaded_files_with_urls, failed_download_urls, _ = download_youtube_videos(youtube_urls, TMP_DIR)
    transcription_status["failed_urls"].extend(failed_download_urls) # accumulate failed urls

    # filter out files that failed to download before transcription
    valid_files_for_transcription = [item for item in downloaded_files_with_urls if item[0].exists() and item[1] not in failed_download_urls]

    if not valid_files_for_transcription:
        print("no files were successfully downloaded or found in a valid state for transcription.")
        cleanup_tmp_dir(TMP_DIR)
        # update status to reflect only download failures if that's the case
        processed_count = len(youtube_urls) - len(transcription_status["failed_urls"])
        transcription_status.update({
            "status": "completed_with_errors", 
            "progress": f"{processed_count}/{total_urls} processed (downloads attempted)",
            "details": f"{len(transcription_status['failed_urls'])}/{total_urls} failed to download or locate file."
        })
        # processed_videos remains empty
        return

    # transcribe downloaded files
    transcription_status["status"] = "transcribing"
    print(f"DEBUG: Status updated to 'transcribing': {transcription_status}")
    # progress for transcription will be updated by transcribe_files based on valid_files_for_transcription count
    
    _, failed_transcription_paths, transcription_results_dict = transcribe_files(model_name, valid_files_for_transcription)

    # map failed transcription paths back to urls if possible, for reporting
    # this is a bit tricky as transcribe_files returns paths, not urls directly for failures
    # for simplicity, we'll count them. detailed url mapping for transcription failures needs more work.
    
    # save results to database and collect titles
    saved_to_db_count = 0
    successfully_processed_videos_info: List[Dict[str, str]] = []

    for url, text_content in transcription_results_dict.items():
        # get video title - try from local path stem first (which download_youtube_videos might have named well)
        # then fall back to a generic one if needed.
        path_for_url = next((p for p, u_item in valid_files_for_transcription if u_item == url), None)
        video_title = "unknown_title"
        if path_for_url:
            raw_title = path_for_url.stem
            # crude way to remove common yt-dlp id patterns if they are at the end
            video_title = re.sub(r'\s*\[[\w-]{11}\]$|\s*\[[\w-]{10}\]$|\s*_[\w-]{11}$|\s*_[\w-]{10}$', '', raw_title).strip()
            if not video_title : video_title = raw_title # if regex made it empty, use original stem
        else: # fallback if path not found (should not happen if url in transcription_results_dict)
            video_title = get_video_title_from_db(url) if get_video_title_from_db(url) else f"title_for_{url[:20]}"

        insert_transcription_result(url, video_title, text_content) # db save happens here
        successfully_processed_videos_info.append({"url": url, "title": video_title})
        saved_to_db_count +=1
    
    transcription_status["processed_videos"] = successfully_processed_videos_info
    
    # update failed_urls with those that failed transcription
    # this requires mapping failed_transcription_paths back to their original urls
    # for now, let's assume a transcription failure for a url means it's not in successfully_processed_videos_info
    all_attempted_transcription_urls = {url for _, url in valid_files_for_transcription}
    successful_transcription_urls = {info["url"] for info in successfully_processed_videos_info}
    transcription_failure_urls = list(all_attempted_transcription_urls - successful_transcription_urls)
    transcription_status["failed_urls"].extend(tf_url for tf_url in transcription_failure_urls if tf_url not in transcription_status["failed_urls"])

    print(f"\n--- pipeline run summary ---")
    print(f"{len(youtube_urls)} url(s) initially provided from list.txt.")
    print(f"{len(downloaded_files_with_urls) - len(failed_download_urls)} video(s) likely downloaded successfully.")
    print(f"{len(failed_download_urls)} video(s) failed during download/file location phase.")
    print(f"{len(valid_files_for_transcription)} video(s) submitted for transcription.")
    print(f"{saved_to_db_count} video(s) transcribed and saved to database.")
    
    num_transcription_failures = len(valid_files_for_transcription) - saved_to_db_count
    print(f"{num_transcription_failures} video(s) may have failed during transcription phase.")
    
    # cleanup
    cleanup_tmp_dir(TMP_DIR)
    print("temporary files cleaned up.")
    
    final_successful_count = saved_to_db_count
    
    if final_successful_count == total_urls:
        transcription_status.update({
            "status": "completed", 
            "progress": f"{final_successful_count}/{total_urls}"
            # processed_videos and failed_urls already set
        })
        print("transcription pipeline completed successfully for all urls.")
    else:
        transcription_status.update({
            "status": "completed_with_errors", 
            "progress": f"{final_successful_count}/{total_urls} transcribed and saved",
            "details": f"{total_urls - final_successful_count} url(s) failed at some stage."
            # processed_videos and failed_urls already set
        })
        print("transcription pipeline completed with some errors.")
        print(f"successfully processed and saved: {final_successful_count}")
        print(f"failed urls accumulated: {len(transcription_status['failed_urls'])}")
        for failed_url_item in transcription_status['failed_urls']:
            print(f"  - {failed_url_item}")

    # n8n should call /clear_list after verifying db state and getting this completion message.
    # we don't clear list.txt automatically here.

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

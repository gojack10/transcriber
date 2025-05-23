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
def check_database_exists() -> bool:
    """check if the target database exists."""
    try:
        # connect to default postgres database first
        conn = psycopg2.connect(
            host=os.getenv("DB_HOST", "127.0.0.1"),
            port=os.getenv("DB_PORT", "5432"),
            database="postgres",  # connect to default postgres db
            user=os.getenv("DB_USER", "gojack10"),
            password=os.getenv("DB_PASSWORD", "moso10")
        )
        cursor = conn.cursor()
        
        db_name = os.getenv("DB_NAME", "transcriber_db")
        cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,))
        exists = cursor.fetchone() is not None
        
        cursor.close()
        conn.close()
        return exists
        
    except psycopg2.Error as e:
        print(f"error checking if database exists: {e}")
        return False

def create_database_if_not_exists():
    """create the database if it doesn't exist."""
    try:
        # connect to default postgres database first
        conn = psycopg2.connect(
            host=os.getenv("DB_HOST", "127.0.0.1"),
            port=os.getenv("DB_PORT", "5432"),
            database="postgres",  # connect to default postgres db
            user=os.getenv("DB_USER", "gojack10"),
            password=os.getenv("DB_PASSWORD", "moso10")
        )
        conn.autocommit = True
        cursor = conn.cursor()
        
        db_name = os.getenv("DB_NAME", "transcriber_db")
        
        # check if database exists
        cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,))
        if not cursor.fetchone():
            cursor.execute(f"CREATE DATABASE {db_name}")
            print(f"created database: {db_name}")
            return True
        else:
            print(f"database {db_name} already exists")
            return False
            
    except psycopg2.Error as e:
        print(f"error creating database: {e}")
        return False
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()

def check_table_exists(cursor, table_name: str) -> bool:
    """check if a table exists in the current database."""
    try:
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = %s
            );
        """, (table_name,))
        return cursor.fetchone()[0]
    except psycopg2.Error as e:
        print(f"error checking if table {table_name} exists: {e}")
        return False

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
    print("initializing postgresql database...")
    
    # step 1: ensure database exists
    if not check_database_exists():
        print("database not found, attempting to create it...")
        if not create_database_if_not_exists():
            print("failed to create database. exiting.")
            sys.exit(1)
    else:
        print("database exists, proceeding with table checks...")
    
    # step 2: connect to target database and check/create tables
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # check and create downloaded_videos table
        if not check_table_exists(cursor, 'downloaded_videos'):
            print("creating 'downloaded_videos' table...")
            cursor.execute('''
                CREATE TABLE downloaded_videos (
                    id SERIAL PRIMARY KEY,
                    url TEXT UNIQUE,
                    status TEXT NOT NULL,
                    download_date TEXT NOT NULL,
                    local_path TEXT,
                    yt_dlp_processed BOOLEAN DEFAULT false
                )
            ''')
            print("'downloaded_videos' table created successfully.")
        else:
            print("'downloaded_videos' table already exists.")
            # ensure yt_dlp_processed column exists for existing tables
            cursor.execute('''
                ALTER TABLE downloaded_videos
                ADD COLUMN IF NOT EXISTS yt_dlp_processed BOOLEAN DEFAULT false;
            ''')
        
        # check and create transcribed table
        if not check_table_exists(cursor, 'transcribed'):
            print("creating 'transcribed' table...")
            cursor.execute('''
                CREATE TABLE transcribed (
                    id SERIAL PRIMARY KEY,
                    utc_time TEXT NOT NULL,
                    pst_time TEXT NOT NULL,
                    url TEXT UNIQUE,
                    video_title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    FOREIGN KEY (url) REFERENCES downloaded_videos(url)
                )
            ''')
            print("'transcribed' table created successfully.")
        else:
            print("'transcribed' table already exists.")
            # ensure url column exists for existing tables
            cursor.execute('''
                ALTER TABLE transcribed
                ADD COLUMN IF NOT EXISTS url TEXT UNIQUE;
            ''')
        
        # ensure foreign key constraint exists
        cursor.execute("""
            SELECT constraint_name FROM information_schema.table_constraints
            WHERE table_name='transcribed' AND constraint_name='fk_downloaded_videos';
        """)
        if not cursor.fetchone():
            print("adding foreign key constraint to 'transcribed' table...")
            cursor.execute('''
                ALTER TABLE transcribed
                ADD CONSTRAINT fk_downloaded_videos
                FOREIGN KEY (url) REFERENCES downloaded_videos(url);
            ''')
            print("foreign key constraint added successfully.")
        else:
            print("foreign key constraint already exists.")
        
        conn.commit()
        print("postgresql database initialization completed successfully.")
        
        # verify tables were created by checking again
        if check_table_exists(cursor, 'downloaded_videos') and check_table_exists(cursor, 'transcribed'):
            print("verification: all required tables are present and accessible.")
        else:
            print("warning: table verification failed - some tables may not be accessible.")
            
    except psycopg2.Error as e:
        print(f"error initializing postgresql database: {e}")
        conn.rollback()
        raise e  # re-raise to handle at higher level if needed
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
    """inserts the transcription result into the database."""
    conn = get_db_connection()
    cursor = conn.cursor()
    now_utc = datetime.now(pytz.utc)
    now_pst = now_utc.astimezone(ZoneInfo("America/Los_Angeles"))
    utc_time_str = now_utc.strftime("%Y-%m-%d %H:%M:%S %Z")
    pst_time_str = now_pst.strftime("%Y-%m-%d %H:%M:%S %Z")
    print(f"DEBUG: Attempting to insert transcription for URL: {url}, Title: {video_title}") # added log
    try:
        cursor.execute(
            "insert into transcribed (utc_time, pst_time, url, video_title, content) values (%s, %s, %s, %s, %s) on conflict (url) do update set utc_time = excluded.utc_time, pst_time = excluded.pst_time, video_title = excluded.video_title, content = excluded.content",
            (utc_time_str, pst_time_str, url, video_title, content)
        )
        conn.commit()
        print(f"DEBUG: Successfully inserted/updated transcription for URL: {url}") # added log
    except psycopg2.Error as e:
        print(f"DEBUG: Error inserting/updating transcription for URL: {url}: {e}") # added log
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

def transcribe_files(model_name: str, downloaded_files_with_urls: list[tuple[Path, str]]) -> tuple[list[Path], list[str], dict[str, str]]:
    """
    transcribes a list of downloaded audio files using the specified whisper model.

    args:
        model_name: the name of the whisper model to use (e.g., "base", "small", "medium").
        downloaded_files_with_urls: a list of tuples, each containing the Path to a
                                     downloaded audio file and its original url.

    returns:
        a tuple containing:
            - successfully_transcribed_files: a list of Paths to successfully transcribed files.
            - failed_transcription_files: a list of Paths to files that failed transcription.
            - transcription_results: a dictionary mapping original urls to their transcription text.
    """
    global transcription_status
    print(f"DEBUG: transcribe_files called with model: {model_name}, files: {len(downloaded_files_with_urls)}")

    successfully_transcribed_files: list[Path] = []
    failed_transcription_files: list[str] = [] # stores urls that failed
    transcription_results: dict[str, str] = {} # stores url -> transcription_text

    if not downloaded_files_with_urls:
        print("DEBUG: No files to transcribe.")
        return successfully_transcribed_files, failed_transcription_files, transcription_results

    try:
        # check if the model name is valid, otherwise default to "base"
        valid_models = whisper.available_models()
        if model_name not in valid_models:
            print(f"Warning: Whisper model \'{model_name}\' not found. defaulting to \'base\'. available models: {valid_models}")
            model_name = "base"
        
        model = whisper.load_model(model_name)
        print(f"DEBUG: Whisper model \'{model_name}\' loaded.")

        for audio_file_path, original_url in downloaded_files_with_urls:
            try:
                print(f"DEBUG: Starting transcription for {audio_file_path} (URL: {original_url})")
                transcription_result = model.transcribe(str(audio_file_path))
                # verify whisper's output directly
                print(f"DEBUG: Whisper output for {audio_file_path} (URL: {original_url}): {transcription_result}")

                text = transcription_result["text"] # type: ignore
                transcription_results[original_url] = text
                successfully_transcribed_files.append(audio_file_path)
                print(f"DEBUG: Successfully transcribed {audio_file_path}")
            except Exception as e:
                print(f"DEBUG: Error during transcription of {audio_file_path} (URL: {original_url}): {e}")
                failed_transcription_files.append(original_url) # add url to failed list
                # also update the main status
                if original_url not in transcription_status["failed_urls"]:
                    transcription_status["failed_urls"].append(original_url)
                    print(f"DEBUG: Added {original_url} to global failed_urls. Current failed_urls: {transcription_status['failed_urls']}")


    except Exception as e:
        print(f"DEBUG: General error in transcribe_files: {e}")
        # if a general error occurs (e.g., model loading), mark all as failed
        for _, original_url in downloaded_files_with_urls:
            if original_url not in failed_transcription_files: # ensure not already added
                 failed_transcription_files.append(original_url)
            if original_url not in transcription_status["failed_urls"]:
                 transcription_status["failed_urls"].append(original_url)
                 print(f"DEBUG: Added {original_url} to global failed_urls due to general error. Current failed_urls: {transcription_status['failed_urls']}")


    print(f"DEBUG: transcribe_files completed. Success: {len(successfully_transcribed_files)}, Fail: {len(failed_transcription_files)}")
    return successfully_transcribed_files, failed_transcription_files, transcription_results

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
    main pipeline to download, transcribe, and manage video/audio processing.
    this function is intended to be run in a background thread.
    """
    global transcription_status
    print(f"DEBUG: run_transcription_pipeline started. Initial status: {transcription_status}")

    # ensure database and tables exist before processing
    try:
        print("DEBUG: run_transcription_pipeline - Ensuring database and tables exist...")
        initialize_db()
        print("DEBUG: run_transcription_pipeline - Database initialization completed.")
    except Exception as e:
        print(f"DEBUG: run_transcription_pipeline - Database initialization failed: {e}")
        transcription_status["status"] = "error"
        transcription_status["progress"] = "0/0"
        return

    if not TMP_DIR.exists():
        TMP_DIR.mkdir(parents=True, exist_ok=True)
        print(f"DEBUG: Created TMP_DIR: {TMP_DIR}")

    if not LIST_FILE.exists() or LIST_FILE.stat().st_size == 0:
        transcription_status.update({"status": "idle", "progress": "0/0"})
        print(f"DEBUG: run_transcription_pipeline - list.txt is empty or doesn't exist. Status set to idle.")
        cleanup_tmp_dir(TMP_DIR)
        return

    transcription_status["status"] = "processing_downloads"
    print(f"DEBUG: run_transcription_pipeline - Status set to 'processing_downloads'. Reading URLs from {LIST_FILE}")

    try:
        with open(LIST_FILE, "r") as f:
            all_urls_from_file = [url.strip() for url in f if url.strip()]

        if not all_urls_from_file:
            transcription_status.update({"status": "completed", "progress": "0/0"})
            print(f"DEBUG: run_transcription_pipeline - No URLs found in list.txt after stripping. Status set to completed.")
            cleanup_tmp_dir(TMP_DIR)
            return

        print(f"DEBUG: run_transcription_pipeline - Found {len(all_urls_from_file)} URLs to process: {all_urls_from_file}")

        # reset progress and lists for this run, but keep status as "processing_downloads"
        transcription_status["progress"] = f"0/{len(all_urls_from_file)}"
        transcription_status["processed_videos"] = []
        transcription_status["failed_urls"] = []
        processed_video_count = 0

        # --- step 1: check existing and download new videos ---
        urls_to_download: list[str] = []
        downloaded_files_for_transcription_check: list[tuple[Path, str]] = [] # path, url

        for url in all_urls_from_file:
            db_status, local_path_str, yt_dlp_processed = get_download_status(url)
            print(f"DEBUG: run_transcription_pipeline - DB status for {url}: Status='{db_status}', Path='{local_path_str}', Processed='{yt_dlp_processed}'")
            
            if db_status == "downloaded" and local_path_str and Path(local_path_str).exists() and yt_dlp_processed:
                print(f"DEBUG: run_transcription_pipeline - URL {url} already processed by yt-dlp and file exists. Adding to transcription check list.")
                downloaded_files_for_transcription_check.append((Path(local_path_str), url))
                # if it was previously marked as failed for other reasons, remove it now as we might re-process it successfully.
                if url in transcription_status["failed_urls"]:
                    transcription_status["failed_urls"].remove(url)
                    print(f"DEBUG: run_transcription_pipeline - Removed {url} from failed_urls as it is being re-checked for transcription.")
            elif db_status == "downloaded" and local_path_str and not Path(local_path_str).exists():
                print(f"DEBUG: run_transcription_pipeline - URL {url} status is 'downloaded' but file {local_path_str} missing. Queuing for re-download.")
                urls_to_download.append(url)
            elif db_status == "failed_download":
                print(f"DEBUG: run_transcription_pipeline - URL {url} previously failed download. Adding to failed_urls and skipping.")
                if url not in transcription_status["failed_urls"]:
                    transcription_status["failed_urls"].append(url)
            else: # not downloaded, or status unknown, or not yt_dlp_processed
                print(f"DEBUG: run_transcription_pipeline - URL {url} not processed or needs download. Adding to download queue.")
                urls_to_download.append(url)

        downloaded_files_with_urls: list[tuple[Path, str]] = [] # path, url
        failed_download_urls: list[str] = []

        if urls_to_download:
            print(f"DEBUG: run_transcription_pipeline - Attempting to download {len(urls_to_download)} URLs.")
            # download_youtube_videos updates db status internally now
            # it returns: (successfully_downloaded_files_with_urls, failed_to_download_urls, already_downloaded_urls)
            successful_downloads, failed_downloads, _ = download_youtube_videos(urls_to_download, TMP_DIR)
            downloaded_files_with_urls.extend(successful_downloads)
            failed_download_urls.extend(failed_downloads)
            print(f"DEBUG: run_transcription_pipeline - Download results: Success: {len(successful_downloads)}, Failed: {len(failed_downloads)}")
        
        # combine files that were already downloaded with newly downloaded ones for transcription
        downloaded_files_with_urls.extend(downloaded_files_for_transcription_check)
        # ensure uniqueness in case a file was in both lists (e.g., re-queued after failed check)
        downloaded_files_with_urls = list(dict.fromkeys(downloaded_files_with_urls)) # maintains order, faster for larger lists
        print(f"DEBUG: run_transcription_pipeline - Total files ready for transcription check: {len(downloaded_files_with_urls)}")


        # update status with progress and any failures during download
        total_videos = len(all_urls_from_file)
        
        transcription_status["progress"] = f"{processed_video_count}/{total_videos}" # this will be updated more accurately later
        # add download failures, ensuring no duplicates
        for fud_url in failed_download_urls:
            if fud_url not in transcription_status["failed_urls"]:
                transcription_status["failed_urls"].append(fud_url)
        print(f"DEBUG: run_transcription_pipeline - After download phase. Initial Processed (before transcription): {processed_video_count}, Total: {total_videos}, Failed URLs so far: {transcription_status['failed_urls']}")


        # --- step 3: transcribe downloaded files ---
        transcription_status["status"] = "processing_transcriptions"
        print(f"DEBUG: run_transcription_pipeline - Status set to 'processing_transcriptions'.")
        transcription_results_dict: Dict[str, str] = {}

        if downloaded_files_with_urls:
            model_name = os.getenv("WHISPER_MODEL", "base")
            print(f"DEBUG: run_transcription_pipeline - Starting transcription with model: {model_name} for {len(downloaded_files_with_urls)} files.")
            # transcribe_files returns: (successfully_transcribed_files_paths, failed_transcription_original_urls, transcription_results_dict_url_text)
            _, failed_transcription_original_urls, transcription_results_dict = transcribe_files(model_name, downloaded_files_with_urls)
            
            # add transcription failures, ensuring no duplicates
            for ftu_url in failed_transcription_original_urls:
                if ftu_url not in transcription_status["failed_urls"]:
                    transcription_status["failed_urls"].append(ftu_url)
            print(f"DEBUG: run_transcription_pipeline - After transcription. Transcription results count: {len(transcription_results_dict)}, Failed URLs now: {transcription_status['failed_urls']}")


            # --- step 4: save successful transcriptions to database ---
            print(f"DEBUG: run_transcription_pipeline - Saving {len(transcription_results_dict)} transcriptions to DB.")
            for original_url, text_content in transcription_results_dict.items():
                # only proceed if this url didn't end up in the failed list during transcription
                if original_url in transcription_status["failed_urls"]:
                    print(f"DEBUG: run_transcription_pipeline - Skipping DB insert for {original_url} as it was marked failed.")
                    continue

                video_title = get_video_title_from_db(original_url) or "unknown title"
                insert_transcription_result(original_url, video_title, text_content)
                
                # update processed_videos if not already there (should reflect true successes)
                is_already_processed = any(pv['url'] == original_url for pv in transcription_status["processed_videos"])
                if not is_already_processed:
                    transcription_status["processed_videos"].append({"url": original_url, "title": video_title})
                    print(f"DEBUG: Added {original_url} (Title: {video_title}) to processed_videos. Current count: {len(transcription_status['processed_videos'])}")
                
        # --- step 5: final status update ---
        successful_processed_videos = [pv for pv in transcription_status["processed_videos"] if pv['url'] not in transcription_status["failed_urls"]]
        if len(successful_processed_videos) != len(transcription_status["processed_videos"]):
            print(f"DEBUG: Correcting processed_videos. Before: {len(transcription_status['processed_videos'])}, After: {len(successful_processed_videos)}")
            transcription_status["processed_videos"] = successful_processed_videos
        
        actual_processed_count = len(transcription_status["processed_videos"])
        transcription_status["progress"] = f"{actual_processed_count}/{total_videos}"
        print(f"DEBUG: run_transcription_pipeline - Final progress update: {transcription_status['progress']}. Total processed_videos: {actual_processed_count}")

        if not transcription_status["failed_urls"]:
            transcription_status["status"] = "completed"
            print("DEBUG: run_transcription_pipeline - Status set to 'completed'. No failed URLs.")
        else:
            transcription_status["status"] = "completed_with_errors"
            print(f"DEBUG: run_transcription_pipeline - Status set to 'completed_with_errors'. Failed URLs ({len(transcription_status['failed_urls'])}): {transcription_status['failed_urls']}")
        
        print(f"DEBUG: Final processed_videos list: {transcription_status['processed_videos']}")
        print(f"DEBUG: Final failed_urls list: {transcription_status['failed_urls']}")

    except Exception as e:
        transcription_status["status"] = "error"
        print(f"CRITICAL ERROR in run_transcription_pipeline: {e}") # added for better error logging
        # optionally re-raise or handle more gracefully depending on desired behavior for background tasks
        # for now, it just logs and sets status to "error"

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

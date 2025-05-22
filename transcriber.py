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

# --- Configuration ---
BASE_DIR = Path(__file__).resolve().parent
UNCONVERTED_DIR = BASE_DIR / "unconverted"
CONVERTED_DIR = BASE_DIR / "converted"

# Supported audio file extensions (add more if needed)
AUDIO_EXTENSIONS = {".mp3", ".wav", ".flac", ".m4a", ".ogg", ".aac", ".wma"}

# PostgreSQL Database Functions
def get_db_connection():
    """Establishes a connection to the PostgreSQL database."""
    try:
        conn = psycopg2.connect(
            host="127.0.0.1",
            port="5432",
            database="transcriber_db",
            user="gojack10",
            password="moso10"
        )
        return conn
    except psycopg2.Error as e:
        print(f"Error connecting to PostgreSQL database: {e}")
        sys.exit(1)

def initialize_db():
    """Initializes the PostgreSQL database and creates the necessary tables."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS downloaded_videos (
                url TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                download_date TEXT NOT NULL,
                local_path TEXT
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS transcribed (
                utc_time TEXT NOT NULL,
                pst_time TEXT NOT NULL,
                video_title TEXT NOT NULL,
                content TEXT NOT NULL
            )
        ''')
        conn.commit()
        print("PostgreSQL database initialized and tables ensured.")
    except psycopg2.Error as e:
        print(f"Error initializing PostgreSQL database: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

def get_download_status(url: str) -> tuple[str | None, str | None]:
    """
    Checks the download status and local path of a URL in the database.
    Returns (status, local_path) or (None, None) if not found.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    result = (None, None)
    try:
        cursor.execute("SELECT status, local_path FROM downloaded_videos WHERE url = %s", (url,))
        result = cursor.fetchone()
    except psycopg2.Error as e:
        print(f"Error getting download status: {e}")
    finally:
        cursor.close()
        conn.close()
    return result if result else (None, None)

def update_download_status(url: str, status: str, local_path: Path | None = None):
    """
    Adds or updates a URL's status and local path in the database.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    download_date = datetime.now().isoformat()
    local_path_str = str(local_path) if local_path else None

    try:
        cursor.execute('''
            INSERT INTO downloaded_videos (url, status, download_date, local_path)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (url) DO UPDATE SET
                status = EXCLUDED.status,
                download_date = EXCLUDED.download_date,
                local_path = EXCLUDED.local_path
        ''', (url, status, download_date, local_path_str))
        conn.commit()
        print(f"Database updated for '{url}' with status '{status}'.")
    except psycopg2.Error as e:
        print(f"Error updating download status: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

def insert_transcription_result(video_title: str, content: str):
    """
    Inserts a transcription result into the transcribed table.
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
            INSERT INTO transcribed (utc_time, pst_time, video_title, content)
            VALUES (%s, %s, %s, %s)
        ''', (utc_time, pst_time, video_title, content))
        conn.commit()
        print(f"Transcription for '{video_title}' saved to database.")
    except psycopg2.Error as e:
        print(f"Error inserting transcription result: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

def transcribe_files(model_name: str, audio_file_paths: list[Path], converted_dir: Path) -> tuple[list[Path], list[str], dict[str, str]]:
    """
    Transcribes a list of audio files to the specified converted directory
    using the specified Whisper model.
    Returns a tuple: (processed_originals_paths, failed_transcription_filenames, transcription_results)
    """
    processed_originals_paths = []
    failed_transcription_filenames = []
    transcription_results = {}

    if not converted_dir.exists():
        print(f"Creating directory '{converted_dir}'...")
        converted_dir.mkdir(parents=True, exist_ok=True)

    if not audio_file_paths:
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

    print(f"\nFound {len(audio_file_paths)} audio file(s) to transcribe.")

    total_files = len(audio_file_paths)
    transcribed_count = 0

    for audio_file_path in audio_file_paths:
        transcribed_count += 1
        print(f"\nProcessing '{audio_file_path.name}' ({transcribed_count}/{total_files})...")
        output_txt_filename = audio_file_path.stem + ".txt"
        output_txt_path = converted_dir / output_txt_filename

        try:
            result = model.transcribe(str(audio_file_path), fp16=False)
            transcription = result["text"]

            with open(output_txt_path, "w", encoding="utf-8") as f:
                f.write(transcription)
            print(f"  Successfully transcribed. Output: '{output_txt_path}'")
            processed_originals_paths.append(audio_file_path)
            transcription_results[audio_file_path.name] = transcription
            
            # Extract video title from audio_file_path.name (remove extension)
            video_title = audio_file_path.stem
            insert_transcription_result(video_title, transcription)
        except Exception as e:
            print(f"  Error transcribing '{audio_file_path.name}': {e}")
            failed_transcription_filenames.append(audio_file_path.name)

    return processed_originals_paths, failed_transcription_filenames, transcription_results

def download_youtube_videos(youtube_urls: list[str], output_dir: Path, db_path: Path) -> tuple[list[Path], list[str], list[str]]:
    """
    Downloads YouTube videos as WAV files to the specified output directory using yt-dlp,
    integrating with an SQLite database for tracking.
    Returns (newly_downloaded_files, skipped_for_redownload_urls, failed_download_urls).
    """
    newly_downloaded_files = []
    skipped_for_redownload_urls = []
    failed_download_urls = []

    if not youtube_urls:
        print("No YouTube URLs provided for download.")
        return [], [], []

    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\nFound {len(youtube_urls)} URL(s) to process.")
    print("Starting YouTube video downloads...")

    for i, url in enumerate(youtube_urls):
        cleaned_url = re.sub(r'&list=.*', '', url) # Remove playlist parameter

        print(f"\nProcessing URL {i + 1} of {len(youtube_urls)}: {cleaned_url}")

        # Check database for existing download
        status, local_path_db = get_download_status(cleaned_url)
        if status == 'downloaded' and local_path_db and Path(local_path_db).exists():
            print(f"  Skipping '{cleaned_url}', already downloaded and file exists at '{local_path_db}'.")
            skipped_for_redownload_urls.append(cleaned_url)
            continue

        # Determine the expected filename of the output WAV file
        filename_command = [
            "yt-dlp",
            "-x", # Extract audio
            "--audio-format", "wav", # Specify WAV format
            "--restrict-filenames",
            "--print", "%(title)s.wav", # Ensure we get the WAV extension for expected filename
            cleaned_url
        ]
        expected_filename = None
        try:
            filename_process = subprocess.Popen(filename_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            filename_stdout, filename_stderr = filename_process.communicate()
            expected_filename = filename_stdout.decode('utf-8').strip()

            if filename_process.returncode != 0:
                 print(f"  Error determining expected filename for {cleaned_url}: {filename_stderr.decode('utf-8').strip()}")
                 update_download_status(cleaned_url, 'failed')
                 failed_download_urls.append(cleaned_url)
                 continue

        except FileNotFoundError:
            print("Error: yt-dlp command not found.")
            print("Please ensure yt-dlp is installed and in your system's PATH.")
            print("You can install it from https://github.com/yt-dlp/yt-dlp")
            # Mark remaining links as failed and break
            for remaining_url in youtube_urls[i:]:
                update_download_status(remaining_url, 'failed')
                failed_download_urls.append(remaining_url)
            break
        except Exception as e:
            print(f"  An unexpected error occurred while determining expected filename for {cleaned_url}: {e}")
            update_download_status(cleaned_url, 'failed')
            failed_download_urls.append(cleaned_url)
            continue

        # yt-dlp command to download as WAV
        command = [
            "yt-dlp",
            "-x",
            "--audio-format", "wav",
            "--restrict-filenames",
            "-o", str(output_dir / "%(title)s.%(ext)s"),
            cleaned_url
        ]

        try:
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, stderr = process.communicate()

            print(f"  yt-dlp stdout:\n{stdout.decode('utf-8').strip()}")
            print(f"  yt-dlp stderr:\n{stderr.decode('utf-8').strip()}")

            if process.returncode == 0:
                print(f"  Successfully downloaded.")
                # Parse stdout to find the actual downloaded file path
                downloaded_file_path = None
                stdout_lines = stdout.decode('utf-8').splitlines()
                for line in stdout_lines:
                    # Prioritize ExtractAudio destination as it's the final WAV file
                    match = re.search(r'\[ExtractAudio\] Destination: (.+)', line)
                    if match:
                        downloaded_file_path = Path(match.group(1))
                        break
                
                # Fallback if ExtractAudio destination is not found, but ensure it's a WAV
                if not downloaded_file_path:
                    for line in stdout_lines:
                        match = re.search(r'\[download\] Destination: (.+)', line)
                        if match and Path(match.group(1)).suffix == '.wav':
                            downloaded_file_path = Path(match.group(1))
                            break

                if downloaded_file_path and downloaded_file_path.exists():
                    newly_downloaded_files.append(downloaded_file_path)
                    update_download_status(cleaned_url, 'downloaded', downloaded_file_path)
                else:
                    print(f"  Warning: Could not determine exact downloaded file path for {cleaned_url}. Expected: {expected_filename}")
                    update_download_status(cleaned_url, 'failed')
                    failed_download_urls.append(cleaned_url)

            else:
                print(f"  Error downloading: {stderr.decode('utf-8').strip()}")
                update_download_status(cleaned_url, 'failed')
                failed_download_urls.append(cleaned_url)

        except FileNotFoundError:
            print("Error: yt-dlp command not found.")
            print("Please ensure yt-dlp is installed and in your system's PATH.")
            print("You can install it from https://github.com/yt-dlp/yt-dlp")
            for remaining_url in youtube_urls[i:]:
                update_download_status(remaining_url, 'failed')
                failed_download_urls.append(remaining_url)
            break
        except Exception as e:
            print(f"  An unexpected error occurred during download: {e}")
            update_download_status(cleaned_url, 'failed')
            failed_download_urls.append(cleaned_url)

    if failed_download_urls:
        print("\n--- Download Summary ---")
        print(f"Failed to download {len(failed_download_urls)} link(s):")
        for link in failed_download_urls:
            print(f"  - {link}")

    return newly_downloaded_files, skipped_for_redownload_urls, failed_download_urls

def delete_processed_files(file_paths: list[Path]):
    """
    Deletes a list of files.
    """
    if not file_paths:
        print("No files to delete.")
        return

    print("\n--- Automatic Deletion ---")
    print("Automatically deleting the following original audio files:")
    deleted_count = 0
    for f_path in file_paths:
        print(f"  - {f_path.name}")
        try:
            f_path.unlink()
            print(f"  Deleted '{f_path.name}'")
            deleted_count += 1
        except Exception as e:
            print(f"  Error deleting '{f_path.name}': {e}")
    print(f"{deleted_count} file(s) deleted.")

def main():
    print("--- Audio Transcription Script ---")

    # Ensure directories exist
    UNCONVERTED_DIR.mkdir(parents=True, exist_ok=True)
    CONVERTED_DIR.mkdir(parents=True, exist_ok=True)

    # Initialize database
    initialize_db()

    chosen_model = "turbo"
    print(f"Using default model: {chosen_model}")

    # Read URLs from list.txt
    youtube_urls = []
    list_file_path = BASE_DIR / "list.txt"
    if list_file_path.exists():
        with open(list_file_path, "r", encoding="utf-8") as f:
            youtube_urls = [line.strip() for line in f if line.strip()]
    else:
        print(f"Warning: '{list_file_path}' not found. No URLs to process.")
        sys.exit(1)

    # Download videos
    newly_downloaded_files, skipped_for_redownload_urls, failed_download_urls = \
        download_youtube_videos(youtube_urls, UNCONVERTED_DIR)

    # Transcribe newly downloaded files
    processed_originals_paths, failed_transcription_filenames, transcription_results = \
        transcribe_files(chosen_model, newly_downloaded_files, CONVERTED_DIR)

    print("\n--- Transcription Summary ---")
    if processed_originals_paths:
        print(f"Successfully processed/found transcripts for {len(processed_originals_paths)} file(s).")
    if failed_transcription_filenames:
        print(f"Failed to transcribe {len(failed_transcription_filenames)} file(s):")
        for f_name in failed_transcription_filenames:
            print(f"  - {f_name}")
    if not processed_originals_paths and not failed_transcription_filenames:
        print("No new files were transcribed.")

    # Delete processed original audio files
    delete_processed_files(processed_originals_paths)

    print("\n--- Script Finished ---")

if __name__ == "__main__":
    main()

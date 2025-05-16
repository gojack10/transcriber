import os
import whisper
from pathlib import Path
import sys
import subprocess
import re

# --- Configuration ---
BASE_DIR = Path(__file__).resolve().parent
UNCONVERTED_DIR = BASE_DIR / "unconverted"
CONVERTED_DIR = BASE_DIR / "converted"
DOWNLOAD_ARCHIVE = BASE_DIR / "downloaded_archive.txt"

# Supported audio file extensions (add more if needed)
AUDIO_EXTENSIONS = {".mp3", ".wav", ".flac", ".m4a", ".ogg", ".aac", ".wma"}

# ---------------------

def transcribe_files(model_name):
    """
    Transcribes audio files from UNCONVERTED_DIR to CONVERTED_DIR
    using the specified Whisper model.
    Returns a list of successfully processed original file paths.
    """
    processed_originals = []
    failed_files = []

    if not UNCONVERTED_DIR.exists():
        print(f"Error: Directory '{UNCONVERTED_DIR}' not found.")
        return [], []
    if not CONVERTED_DIR.exists():
        print(f"Creating directory '{CONVERTED_DIR}'...")
        CONVERTED_DIR.mkdir(parents=True, exist_ok=True)

    audio_files = [
        f for f in UNCONVERTED_DIR.iterdir()
        if f.is_file() and f.suffix.lower() in AUDIO_EXTENSIONS
    ]

    if not audio_files:
        print(f"No audio files found in '{UNCONVERTED_DIR}'.")
        return [], []

    print(f"\nLoading Whisper model '{model_name}'... (This might take a while the first time)")
    try:
        model = whisper.load_model(model_name)
        print(f"Model '{model_name}' loaded successfully.")
    except Exception as e:
        print(f"Error loading Whisper model '{model_name}': {e}")
        print("Please ensure the model name is correct and you have enough resources.")
        print("You might also need to install Rust if tiktoken doesn't have a pre-built wheel for your system.")
        return [], []


    print(f"\nFound {len(audio_files)} audio file(s) to transcribe.")

    # Add counters for transcription progress
    total_files = len(audio_files)
    transcribed_count = 0

    for audio_file_path in audio_files:
        transcribed_count += 1 # Increment counter for each file processed (even if skipped)
        print(f"\nProcessing '{audio_file_path.name}' ({transcribed_count}/{total_files})...")
        output_txt_filename = audio_file_path.stem + ".txt"
        output_txt_path = CONVERTED_DIR / output_txt_filename

        if output_txt_path.exists():
            print(f"  Skipping '{audio_file_path.name}', transcript '{output_txt_path.name}' already exists.")
            # We still consider it "processed" for potential deletion later if desired
            processed_originals.append(audio_file_path)
            continue

        try:
            result = model.transcribe(str(audio_file_path), fp16=False) # fp16=False for broader CPU compatibility
            transcription = result["text"]

            with open(output_txt_path, "w", encoding="utf-8") as f:
                f.write(transcription)
            print(f"  Successfully transcribed. Output: '{output_txt_path}'")
            processed_originals.append(audio_file_path)
        except Exception as e:
            print(f"  Error transcribing '{audio_file_path.name}': {e}")
            failed_files.append(audio_file_path.name)

    return processed_originals, failed_files

def download_youtube_videos(list_file_path, output_dir):
    """
    Reads YouTube links from a file, cleans them, and downloads them as WAV files
    to the specified output directory using yt-dlp.
    """
    if not list_file_path.exists():
        print(f"Error: List file '{list_file_path}' not found.")
        return []

    downloaded_files = []
    failed_downloads = []

    with open(list_file_path, 'r', encoding='utf-8') as f:
        links = [line.strip() for line in f if line.strip()] # Read non-empty lines

    if not links:
        print(f"No links found in '{list_file_path}'.")
        return []

    print(f"\nFound {len(links)} link(s) in '{list_file_path}'.")
    print("Starting YouTube video downloads...")

    output_dir.mkdir(parents=True, exist_ok=True) # Ensure output directory exists

    for i, link in enumerate(links):
        cleaned_link = re.sub(r'&list=.*', '', link) # Remove playlist parameter

        print(f"\nDownloading video {i + 1} of {len(links)}: {cleaned_link}")

        # Determine the expected filename of the output WAV file
        filename_command = [
            "yt-dlp",
            "-x", # Extract audio
            "--audio-format", "wav", # Specify WAV format
            "--restrict-filenames",
            "--print", "%(title)s.%(ext)s",
            cleaned_link
        ]
        try:
            filename_process = subprocess.Popen(filename_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            filename_stdout, filename_stderr = filename_process.communicate()
            expected_filename = filename_stdout.decode('utf-8').strip()

            if filename_process.returncode != 0:
                 print(f"  Error determining expected filename for {cleaned_link}: {filename_stderr.decode('utf-8').strip()}")
                 failed_downloads.append(cleaned_link)
                 continue # Skip to the next link if filename cannot be determined

        except FileNotFoundError:
            print("Error: yt-dlp command not found.")
            print("Please ensure yt-dlp is installed and in your system's PATH.")
            print("You can install it from https://github.com/yt-dlp/yt-dlp")
            failed_downloads.extend(links[i:]) # Mark remaining links as failed
            break # Stop processing if yt-dlp is not found
        except Exception as e:
            print(f"  An unexpected error occurred while determining expected filename for {cleaned_link}: {e}")
            failed_downloads.append(cleaned_link)
            continue # Skip to the next link on unexpected error

        # yt-dlp command to download as WAV
        # -x: extract audio
        # --audio-format wav: specify wav format
        # -o: output file template. %(title)s is the video title, .%(ext)s is the extension
        # --restrict-filenames: keep filenames simple
        command = [
            "yt-dlp",
            "-x",
            "--audio-format", "wav",
            "--restrict-filenames",
            "-o", str(output_dir / "%(title)s.%(ext)s"),
            "--download-archive", str(BASE_DIR / "downloaded_archive.txt"),
            cleaned_link
        ]

        try:
            # Execute the command
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, stderr = process.communicate()

            # Print stdout and stderr for debugging
            print(f"  yt-dlp stdout:\n{stdout.decode('utf-8').strip()}")
            print(f"  yt-dlp stderr:\n{stderr.decode('utf-8').strip()}")

            if process.returncode == 0:
                print(f"  Successfully downloaded.")
                # Note: We don't have the exact downloaded filename here easily,
                # but the transcribe function will find it in the directory.
                downloaded_files.append(cleaned_link) # Store the link for tracking
            else:
                print(f"  Error downloading: {stderr.decode('utf-8').strip()}")
                failed_downloads.append(cleaned_link)

        except FileNotFoundError:
            print("Error: yt-dlp command not found.")
            print("Please ensure yt-dlp is installed and in your system's PATH.")
            print("You can install it from https://github.com/yt-dlp/yt-dlp")
            failed_downloads.extend(links[i:]) # Mark remaining links as failed
            break # Stop processing if yt-dlp is not found
        except Exception as e:
            print(f"  An unexpected error occurred during download: {e}")
            failed_downloads.append(cleaned_link)

    if failed_downloads:
        print("\n--- Download Summary ---")
        print(f"Failed to download {len(failed_downloads)} link(s):")
        for link in failed_downloads:
            print(f"  - {link}")

    return downloaded_files


def main():
    print("--- Audio Transcription Script ---")

    if not UNCONVERTED_DIR.is_dir():
        print(f"Error: The 'unconverted' directory ('{UNCONVERTED_DIR}') does not exist.")
        print("Please create it and place your audio files inside.")
        sys.exit(1)

    CONVERTED_DIR.mkdir(parents=True, exist_ok=True)

    if not DOWNLOAD_ARCHIVE.exists():
        print(f"Creating download archive file '{DOWNLOAD_ARCHIVE}'...")
        DOWNLOAD_ARCHIVE.touch()

    chosen_model = "turbo"
    print(f"Using default model: {chosen_model}")

    # Download videos from list.txt
    list_file_path = BASE_DIR / "list.txt"
    downloaded_links = download_youtube_videos(list_file_path, UNCONVERTED_DIR)

    # Proceed with transcription if there are files in the unconverted directory
    audio_files_to_transcribe = [
        f for f in UNCONVERTED_DIR.iterdir()
        if f.is_file() and f.suffix.lower() in AUDIO_EXTENSIONS
    ]

    successfully_processed_originals = []
    failed_files = []

    if audio_files_to_transcribe:
        successfully_processed_originals, failed_files = transcribe_files(chosen_model)
    else:
        print("\nNo audio files found in 'unconverted' directory after download. Skipping transcription.")


    print("\n--- Transcription Summary ---")
    if successfully_processed_originals:
        print(f"Successfully processed/found transcripts for {len(successfully_processed_originals)} file(s).")
    if failed_files:
        print(f"Failed to transcribe {len(failed_files)} file(s):")
        for f_name in failed_files:
            print(f"  - {f_name}")
    if not successfully_processed_originals and not failed_files and UNCONVERTED_DIR.exists() and any(UNCONVERTED_DIR.iterdir()):
        print("No new files were processed (either no audio files found or all transcripts already exist).")
    elif not UNCONVERTED_DIR.exists() or not any(f for f in UNCONVERTED_DIR.iterdir() if f.is_file() and f.suffix.lower() in AUDIO_EXTENSIONS):
         if not failed_files: # Avoid double message if loading model failed
            print("No audio files were found in the 'unconverted' directory to process.")


    if successfully_processed_originals:
        print("\n--- Automatic Deletion ---")
        print("Automatically deleting the following original audio files from 'unconverted':")
        deleted_count = 0
        for f_path in successfully_processed_originals:
            print(f"  - {f_path.name}")
            try:
                f_path.unlink() # Deletes the file
                print(f"  Deleted '{f_path.name}'")
                deleted_count += 1
            except Exception as e:
                print(f"  Error deleting '{f_path.name}': {e}")
        print(f"{deleted_count} file(s) deleted.")
    elif not failed_files: # Only show this if no files were processed and no errors occurred earlier
        print("\nNo files were processed, so no deletion needed.")


    print("\n--- Script Finished ---")

if __name__ == "__main__":
    main()

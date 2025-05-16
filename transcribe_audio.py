import os
import whisper
from pathlib import Path
import sys

# --- Configuration ---
BASE_DIR = Path(__file__).resolve().parent
UNCONVERTED_DIR = BASE_DIR / "unconverted"
CONVERTED_DIR = BASE_DIR / "converted"

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

    for audio_file_path in audio_files:
        print(f"\nProcessing '{audio_file_path.name}'...")
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

def prompt_for_deletion(file_paths):
    """Asks the user if they want to delete the specified files."""
    if not file_paths:
        return

    print("\n--- Deletion Prompt ---")
    print("The following original audio files were processed (or skipped because output existed):")
    for f_path in file_paths:
        print(f"  - {f_path.name}")

    while True:
        choice = input("Do you want to delete these original audio files from 'unconverted'? (y/n): ").strip().lower()
        if choice in ["yes", "y"]:
            print("Deleting files...")
            deleted_count = 0
            for f_path in file_paths:
                try:
                    f_path.unlink() # Deletes the file
                    print(f"  Deleted '{f_path.name}'")
                    deleted_count += 1
                except Exception as e:
                    print(f"  Error deleting '{f_path.name}': {e}")
            print(f"{deleted_count} file(s) deleted.")
            break
        elif choice in ["no", "n"]:
            print("Original files will not be deleted.")
            break
        else:
            print("Invalid choice. Please enter 'y' or 'n'.")

def main():
    print("--- Audio Transcription Script ---")

    if not UNCONVERTED_DIR.is_dir():
        print(f"Error: The 'unconverted' directory ('{UNCONVERTED_DIR}') does not exist.")
        print("Please create it and place your audio files inside.")
        sys.exit(1)

    CONVERTED_DIR.mkdir(parents=True, exist_ok=True)

    chosen_model = "turbo"
    print(f"Using default model: {chosen_model}")

    successfully_processed_originals, failed_files = transcribe_files(chosen_model)

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
        prompt_for_deletion(successfully_processed_originals)
    elif not failed_files: # Only show this if no files were processed and no errors occurred earlier
        print("\nNo files were processed, so no deletion prompt needed.")


    print("\n--- Script Finished ---")

if __name__ == "__main__":
    main()

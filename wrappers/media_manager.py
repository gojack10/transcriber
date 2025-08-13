import subprocess
import os
import glob
import re
import threading
from pathlib import Path
from wrappers.queue_manager import QueueManager, QueueStatus
from wrappers.db.db_manager import TranscriptionDB

conversion_queue = QueueManager()
db = TranscriptionDB()

def check_for_duplicate_after_conversion(item_id):
    """check for duplicate transcription filename after file conversion and mark accordingly"""
    try:
        item = conversion_queue.get_item(item_id)
        if not item or not item.file_path:
            return
        
        file_stem = Path(item.file_path).stem
        output_filename = f"{file_stem}.txt"
        
        if db.transcription_exists(output_filename):
            print(f"duplicate transcription filename detected early: {output_filename}")
            print(f"marking item {item.id} as pending duplicate resolution before transcription")
            item.update_status(QueueStatus.PENDING_DUPLICATE, f"duplicate filename: {output_filename}")
            item.pending_transcription = {
                'filename': output_filename,
                'content': None,
                'header': None
            }
        else:
            print(f"no duplicate found for {output_filename}, item ready for transcription")
            
    except Exception as e:
        print(f"error checking for duplicate: {e}")

def get_video_title(yt_link):
    """get video title from yt-dlp without downloading"""
    try:
        result = subprocess.run([
            "yt-dlp",
            "--get-title",
            yt_link
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            return result.stdout.strip()
        else:
            print(f"error getting video title: {result.stderr}")
            return None
    except Exception as e:
        print(f"exception getting video title: {e}")
        return None

def sanitize_filename(title):
    """sanitize video title for use as filename"""
    sanitized = re.sub(r'[<>:"/\\|?*]', '', title)
    sanitized = re.sub(r'\s+', ' ', sanitized)
    sanitized = sanitized.strip()
    return sanitized

def check_file_exists(yt_link, temp_dir="/home/jack/llm/transcription/.temp"):
    """check if .ogg file already exists for this youtube video"""
    title = get_video_title(yt_link)
    if not title:
        return False, None
    
    temp_path = Path(temp_dir)
    if not temp_path.exists():
        return False, None
    
    ogg_files = list(temp_path.glob("*.ogg"))
    
    sanitized_title = sanitize_filename(title)
    for ogg_file in ogg_files:
        if sanitized_title.lower() in ogg_file.stem.lower():
            return True, str(ogg_file)
    
    return False, None

def check_local_file_exists(mp4_path, temp_dir="/home/jack/llm/transcription/.temp"):
    """check if .ogg file already exists for this local .mp4 file"""
    if not mp4_path:
        return False, None
    
    base_name = os.path.splitext(os.path.basename(mp4_path))[0]
    expected_ogg_path = os.path.join(temp_dir, f"{base_name}.ogg")
    
    if os.path.exists(expected_ogg_path):
        return True, expected_ogg_path
    
    return False, None

def download_audio(yt_link, on_complete=None):    
    
    temp_dir = "/home/jack/llm/transcription/.temp"

    file_exists, existing_file_path = check_file_exists(yt_link, temp_dir)
    if file_exists:
        print(f"file already exists: {existing_file_path}, skipping download...")
        item_id = conversion_queue.add_item(yt_link)
        conversion_queue.update_item_path(item_id, existing_file_path)
        conversion_queue.get_item(item_id).update_status(QueueStatus.SKIPPED)
        print(f"Skipped {yt_link} - file already exists. \n\nQueueManager: {conversion_queue.get_all_items()}")
        
        check_for_duplicate_after_conversion(item_id)
        
        if on_complete:
            on_complete(True, "file already exists, skipped download", existing_file_path)
        return "file already exists, skipped download"

    item_id = conversion_queue.add_item(yt_link)
    conversion_queue.get_item(item_id).update_status(QueueStatus.DOWNLOADING)
    print(f"Downloading {yt_link}. \n\nQueueManager: {conversion_queue.get_all_items()}")
    
    download_output = subprocess.run([
        "yt-dlp",
        "-x",
        "--audio-format", "opus",
        "--audio-quality", "0",
        "-P", temp_dir,
        yt_link 
    ], capture_output=True, text=True)
    
    if download_output.returncode != 0:
        conversion_queue.get_item(item_id).mark_failed(download_output.stdout + download_output.stderr)
        if on_complete:
            on_complete(False, download_output.stdout + download_output.stderr, None)
        return download_output.stdout + download_output.stderr
    
    opus_files = glob.glob(f"{temp_dir}/*.opus")
    if not opus_files:
        error_msg = "no opus file found after download"
        conversion_queue.get_item(item_id).mark_failed(error_msg)
        if on_complete:
            on_complete(False, error_msg, None)
        return error_msg
    
    opus_file = opus_files[0]
    base_name = os.path.splitext(os.path.basename(opus_file))[0]
    ogg_file = f"{temp_dir}/{base_name}.ogg"

    conversion_queue.update_item_path(item_id, opus_file)
    conversion_queue.get_item(item_id).update_status(QueueStatus.CONVERTING)

    convert_output = subprocess.run([
        "ffmpeg",
        "-nostdin",
        "-hide_banner",
        "-loglevel", "error",
        "-i", opus_file,
        "-map", "0:a:0",
        "-vn",
        "-c:a", "copy",
        "-y",
        ogg_file
    ], capture_output=True, text=True)

    if convert_output.returncode == 0:
        conversion_queue.update_item_path(item_id, ogg_file)
        conversion_queue.get_item(item_id).update_status(QueueStatus.CONVERTED)
        print(f"Converted {opus_file} to {ogg_file}. \n\nQueueManager: {conversion_queue.get_all_items()}")
        
        check_for_duplicate_after_conversion(item_id)
    else:
        conversion_queue.get_item(item_id).mark_failed(convert_output.stdout + convert_output.stderr)

    if os.path.exists(opus_file):
        os.remove(opus_file)
    
    combined_output = download_output.stdout + download_output.stderr + convert_output.stdout + convert_output.stderr
    
    if on_complete:
        on_complete(convert_output.returncode == 0, combined_output, ogg_file)
    
    return combined_output

def convert_to_audio(file_path, file_name=None, on_complete=None):

    if file_name is None:
        base = os.path.basename(file_path)
        file_name = os.path.splitext(base)[0]

    output_path = f"/home/jack/llm/transcription/.temp/{file_name}.ogg"

    file_exists, existing_file_path = check_local_file_exists(file_path)
    if file_exists:
        print(f"file already exists: {existing_file_path}, skipping conversion...")
        item_id = conversion_queue.add_item(file_path)
        conversion_queue.update_item_path(item_id, existing_file_path)
        conversion_queue.get_item(item_id).update_status(QueueStatus.SKIPPED)
        print(f"Skipped conversion of {file_path} - file already exists. \n\nQueueManager: {conversion_queue.get_all_items()}")
        
        check_for_duplicate_after_conversion(item_id)
        
        if on_complete:
            on_complete(True, "file already exists, skipped conversion", existing_file_path)
        return "file already exists, skipped conversion"

    item_id = conversion_queue.add_item(file_path)
    conversion_queue.get_item(item_id).update_status(QueueStatus.CONVERTING)
    print(f"Converting {file_path} to {output_path}. \n\nQueueManager: {conversion_queue.get_all_items()}")

    output = subprocess.run([
        "ffmpeg",
        "-nostdin",
        "-hide_banner",
        "-loglevel", "error",
        "-i", file_path,
        "-map", "0:a:0",
        "-vn",
        "-c:a", "libopus",
        "-compression_level", "4",
        "-b:a", "128k",
        "-y",
        output_path
    ], capture_output=True, text=True)

    if output.returncode == 0:
        conversion_queue.update_item_path(item_id, output_path)
        conversion_queue.get_item(item_id).update_status(QueueStatus.CONVERTED)
        print(f"Converted {file_path} to {output_path}. \n\nQueueManager: {conversion_queue.get_all_items()}")
        
        check_for_duplicate_after_conversion(item_id)
    else:
        conversion_queue.get_item(item_id).mark_failed(output.stdout + output.stderr)
    
    if on_complete:
        on_complete(output.returncode == 0, output.stdout + output.stderr, output_path)

    return output.stdout + output.stderr

# TEST FUNCTIONS - for automatic file discovery in .temp directory
def TEST_get_all_media_files(temp_dir="/home/jack/llm/transcription/.temp"):
    """get all .mp4 and .ogg files in temp directory for testing"""
    temp_path = Path(temp_dir)
    if not temp_path.exists():
        return []
    
    mp4_files = list(temp_path.glob("*.mp4"))
    ogg_files = list(temp_path.glob("*.ogg"))
    
    all_files = mp4_files + ogg_files
    return [str(f) for f in all_files]

def TEST_async_convert_all_media():
    """async wrapper to convert all media files found in .temp directory"""
    media_files = TEST_get_all_media_files()
    
    if not media_files:
        print("no media files found in .temp directory")
        return []
    
    threads = []
    for file_path in media_files:
        if file_path.endswith('.mp4'):
            def convert_task(fp=file_path):
                convert_to_audio(fp, on_complete=lambda success, output, file_path: 
                                print(f"test convert complete: {success} - {file_path}"))
            
            thread = threading.Thread(target=convert_task, daemon=True)
            thread.start()
            threads.append(thread)
            print(f"started conversion for: {file_path}")
        else:
            print(f"skipping already converted file: {file_path}")
    
    return threads
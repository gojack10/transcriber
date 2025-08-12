import subprocess
import os
import glob
from wrappers.queue_manager import QueueManager, QueueStatus

conversion_queue = QueueManager()

def download_audio(yt_link, on_complete=None):    
    
    temp_dir = "/home/jack/llm/transcription/.temp"

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
        if on_complete:
            on_complete(False, download_output.stdout + download_output.stderr, None)
        return download_output.stdout + download_output.stderr
    
    opus_files = glob.glob(f"{temp_dir}/*.opus")
    if not opus_files:
        error_msg = "no opus file found after download"
        if on_complete:
            on_complete(False, error_msg, None)
        return error_msg
    
    opus_file = opus_files[0]
    base_name = os.path.splitext(os.path.basename(opus_file))[0]
    ogg_file = f"{temp_dir}/{base_name}.ogg"

    conversion_queue.update_item_path(item_id, opus_file)
    conversion_queue.get_item(item_id).update_status(QueueStatus.CONVERTING)

    # step 2: remux opus into ogg container without re-encoding (fast)
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
        conversion_queue.get_item(item_id).update_status(QueueStatus.COMPLETED)
        print(f"Converted {opus_file} to {ogg_file}. \n\nQueueManager: {conversion_queue.get_all_items()}")

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
        conversion_queue.get_item(item_id).update_status(QueueStatus.COMPLETED)
        print(f"Converted {file_path} to {output_path}. \n\nQueueManager: {conversion_queue.get_all_items()}")
    
    if on_complete:
        on_complete(output.returncode == 0, output.stdout + output.stderr, output_path)

    return output.stdout + output.stderr
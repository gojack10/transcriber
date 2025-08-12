from wrappers.media_manager import download_audio, convert_to_audio
from wrappers.queue_manager import QueueManager

link = "https://youtu.be/HQKZZz1dGBw"
video_path = "/home/jack/llm/transcription/.temp/testing_vid.mp4"
queue_manager = QueueManager()

def handle_download_complete(success, message, file_path):
    print(f"Download complete: {success}")
    print(f"Message: {message}")
    if success:
        queue_manager.add_item(file_path)
    else:
        print(f"Download failed: {message}")

def handle_convert_complete(success, message, file_path):
    print(f"Convert complete: {success}")
    print(f"Message: {message}")
    if success:
        queue_manager.add_item(file_path)
    else:
        print(f"Convert failed: {message}")

download_audio(link, on_complete=handle_download_complete)
convert_to_audio(video_path, on_complete=handle_convert_complete)
print(queue_manager.get_all_items())
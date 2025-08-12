from wrappers.media_manager import download_audio, convert_to_audio, conversion_queue

link = "https://youtu.be/HQKZZz1dGBw"
video_path = "/home/jack/llm/transcription/.temp/testing_vid.mp4"

download_audio(link, on_complete=lambda success, output, file_path: print(f"Download complete: {success}"))
convert_to_audio(video_path, on_complete=lambda success, output, file_path: print(f"Convert complete: {success}"))
print(conversion_queue.get_all_items())
import subprocess

def download_audio(yt_link):    

    output = subprocess.run([
        "yt-dlp",
        "-x",
        "--audio-format", "ogg",
        "--audio-quality", "0",
        "-P", "/home/jack/llm/transcription/.temp",
        yt_link 
    ], capture_output=True, text=True)

    return output.stdout + output.stderr

import os

def convert_audio(audio_path, file_name=None):

    if file_name is None:
        base = os.path.basename(audio_path)
        file_name = os.path.splitext(base)[0]

    output_path = f"/home/jack/llm/transcription/.temp/{file_name}.ogg"

    output = subprocess.run([
        "ffmpeg",
        "-i", audio_path,
        "-c:a", "libopus",
        "-b:a", "128k",
        "-y",
        output_path
    ], capture_output=True, text=True)

    return output.stdout + output.stderr
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

    return output.stdout

def convert_audio(audio_path, file_name):
    output = subprocess.run([
        "ffmpeg",
        "-i", audio_path,
        "-c:a", "libopus",
        "-b:a", "128k",
        "-y",
        f"/home/jack/llm/transcription/.temp/{file_name}.ogg"
    ], capture_output=True, text=True)

    return output.stdout + output.stderr
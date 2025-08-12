#!/usr/bin/env python3
"""
temporary test script to load whisper, transcribe files from .temp directory,
save output to txt files, then end.
"""

import os
import whisper
import torch
import gc
from datetime import datetime
from pathlib import Path


def main():
    print("starting whisper transcription test...")
    
    # 1. find files to transcribe in .temp directory
    temp_dir = Path("/home/jack/llm/transcription/.temp")
    if not temp_dir.exists():
        print(f"temp directory {temp_dir} does not exist")
        return
    
    # supported file extensions
    audio_extensions = {".mp3", ".wav", ".flac", ".m4a", ".ogg", ".aac", ".wma"}
    video_extensions = {".mp4", ".avi", ".mov", ".mkv", ".webm", ".flv", ".wmv", ".m4v"}
    supported_extensions = audio_extensions | video_extensions
    
    files_to_transcribe = []
    for file_path in temp_dir.iterdir():
        if file_path.is_file() and file_path.suffix.lower() in supported_extensions:
            files_to_transcribe.append(file_path)
    
    if not files_to_transcribe:
        print("no audio/video files found in .temp directory")
        return
    
    print(f"found {len(files_to_transcribe)} file(s) to transcribe:")
    for file_path in files_to_transcribe:
        print(f"  - {file_path.name}")
    
    # 2. load whisper model
    print("loading whisper model...")
    model_path = "/home/jack/llm/transcription/whisper-cache/base.en.pt"
    
    # check cuda availability
    if torch.cuda.is_available():
        print("cuda device detected - gpu will be used")
        torch.cuda.get_device_name(0)
    else:
        print("no cuda device - using cpu")
    
    # load model from specific local file
    model = whisper.load_model(model_path)
    print(f"whisper model loaded successfully from: {model_path}")
    
    # 3. transcribe files and save to text files
    print("starting transcription process...")
    
    for file_path in files_to_transcribe:
        try:
            print(f"transcribing {file_path.name}...")
            
            # transcribe the file
            result = model.transcribe(str(file_path))
            transcription_text = result["text"]
            
            print(f"transcription completed. length: {len(transcription_text)} characters")
            
            # save to text file in temp directory
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_filename = f"{file_path.stem}_transcript_{timestamp}.txt"
            output_path = temp_dir / output_filename
            
            # create header with metadata
            header = f"""Transcription of: {file_path.name}
File path: {file_path}
Transcribed on: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
Model used: {model_path}
Text length: {len(transcription_text)} characters

--- TRANSCRIPTION ---

"""
            
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(header)
                f.write(transcription_text)
            
            print(f"saved transcription to: {output_filename}")
            
        except Exception as e:
            print(f"error processing {file_path.name}: {e}")
    
    # 4. cleanup whisper model
    print("cleaning up whisper model...")
    try:
        del model
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        print("whisper model unloaded from memory")
    except Exception as e:
        print(f"error during cleanup: {e}")
    
    print("test completed successfully")


if __name__ == "__main__":
    main()


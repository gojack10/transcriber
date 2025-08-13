import time
import whisper
import torch
import gc
import threading
from datetime import datetime
from pathlib import Path
from wrappers.media_manager import conversion_queue, download_audio, convert_to_audio
from wrappers.queue_manager import QueueStatus

class TranscriptionOrchestrator:
    def __init__(self):
        self.model = None
        self.model_path = "/home/jack/llm/transcription/whisper-cache/base.en.pt"
        self.temp_dir = Path("/home/jack/llm/transcription/.temp")
        
    def load_whisper_model(self):
        """load whisper model once and keep in memory"""
        if self.model is None:
            print("loading whisper model...")
            self.model = whisper.load_model(self.model_path)
            print(f"whisper model loaded from: {self.model_path}")
    
    def transcribe_file(self, item):
        """transcribe a single file and save output"""
        try:
            item.update_status(QueueStatus.TRANSCRIBING)
            print(f"transcribing {item.file_path}...")
            
            self.load_whisper_model()
            
            result = self.model.transcribe(item.file_path)
            transcription_text = result["text"]
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_stem = Path(item.file_path).stem
            output_filename = f"{file_stem}_transcript_{timestamp}.txt"
            output_path = self.temp_dir / output_filename
            
            header = f"""Transcription of: {Path(item.file_path).name}
File path: {item.file_path}
Transcribed on: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
Model used: {self.model_path}
Text length: {len(transcription_text)} characters

--- TRANSCRIPTION ---

"""
            
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(header)
                f.write(transcription_text)
            
            item.update_status(QueueStatus.COMPLETED)
            print(f"transcription saved to: {output_filename}")
            
        except Exception as e:
            print(f"error transcribing {item.file_path}: {e}")
            item.mark_failed(str(e))
    
    def run_orchestration(self):
        """main orchestration loop - process one file at a time"""
        print("starting transcription orchestrator...")
        
        while True:
            converted_items = conversion_queue.get_all_items_by_status(QueueStatus.CONVERTED)
            skipped_items = conversion_queue.get_all_items_by_status(QueueStatus.SKIPPED)
            
            ready_items = converted_items + skipped_items
            
            if ready_items:
                item = ready_items[0]
                self.transcribe_file(item)
            else:
                print("waiting for converted files...")
                time.sleep(2)
    
    def cleanup(self):
        """cleanup whisper model from memory"""
        if self.model is not None:
            del self.model
            self.model = None
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            print("whisper model unloaded from memory")

link = "https://youtu.be/HQKZZz1dGBw"
video_path = "/home/jack/llm/transcription/.temp/testing_vid.mp4"

def async_download_audio(link):
    """async wrapper for download_audio"""
    def download_task():
        download_audio(link, on_complete=lambda success, output, file_path: 
                      print(f"download complete: {success} - {file_path}"))
    
    thread = threading.Thread(target=download_task, daemon=True)
    thread.start()
    return thread

def async_convert_audio(video_path):
    """async wrapper for convert_to_audio"""
    def convert_task():
        convert_to_audio(video_path, on_complete=lambda success, output, file_path: 
                        print(f"convert complete: {success} - {file_path}"))
    
    thread = threading.Thread(target=convert_task, daemon=True)
    thread.start()
    return thread

def trigger_media_processing():
    """trigger downloads and conversions asynchronously"""
    print("triggering async media processing...")
    
    download_thread = async_download_audio(link)
    convert_thread = async_convert_audio(video_path)
    
    print("media processing started in background")
    print(f"initial queue status: {conversion_queue.get_all_items()}")
    
    return [download_thread, convert_thread]

if __name__ == "__main__":
    media_threads = trigger_media_processing()
    
    orchestrator = TranscriptionOrchestrator()
    try:
        orchestrator.run_orchestration()
    except KeyboardInterrupt:
        print("\nstopping orchestrator...")
        orchestrator.cleanup()
        
        print("waiting for media processing threads to complete...")
        for thread in media_threads:
            if thread.is_alive():
                thread.join(timeout=5)


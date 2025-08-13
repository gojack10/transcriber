import time
# STATS_MONITORING_IMPLEMENTATION - comment out these 2 lines to disable stats
# from wrappers.transcription_statistics import start_stats_monitoring, stop_stats_monitoring
from faster_whisper import WhisperModel
import torch
import gc
import threading
from datetime import datetime
from pathlib import Path
from wrappers.media_manager import conversion_queue, TEST_async_convert_all_media
from wrappers.queue_manager import QueueStatus

class TranscriptionOrchestrator:
    def __init__(self):
        self.model = None
        self.model_id = "base.en"
        self.temp_dir = Path("/home/jack/llm/transcription/.temp")
        self.max_workers = 3
        self.model_pool = []
        self.pool_lock = threading.Lock()
        self.worker_threads = []
        
    def create_whisper_model(self) -> WhisperModel:
        """create a new faster-whisper model instance on gpu"""
        print("loading faster-whisper model...")
        if not torch.cuda.is_available():
            print("warning: torch reports no cuda device, still forcing cuda for debugging")
        device = "cuda"
        compute_type = "float16"
        model = WhisperModel(self.model_id, device=device, compute_type=compute_type)
        print(f"faster-whisper model loaded: {self.model_id} on {device} ({compute_type})")
        return model
    
    def transcribe_file(self, item, model: WhisperModel):
        """transcribe a single file with provided model and save output"""
        try:
            item.update_status(QueueStatus.TRANSCRIBING)
            print(f"transcribing {item.file_path}...")
            
            segments, info = model.transcribe(
                item.file_path,
                vad_filter=True,
                beam_size=5,
            )
            transcription_text = "".join(s.text for s in segments)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_stem = Path(item.file_path).stem
            output_filename = f"{file_stem}_transcript_{timestamp}.txt"
            output_path = self.temp_dir / output_filename
            
            header = f"""Transcription of: {Path(item.file_path).name}
File path: {item.file_path}
Transcribed on: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
Model used: faster-whisper:{self.model_id} | lang={getattr(info, "language", "en")} p={getattr(info, "language_probability", 1.0):.2f}
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
        """main orchestration loop - process up to max_workers files concurrently"""
        
        active_statuses = {
            QueueStatus.QUEUED,
            QueueStatus.DOWNLOADING,
            QueueStatus.CONVERTING,
            QueueStatus.TRANSCRIBING,
        }
        
        while True:
            self.worker_threads = [t for t in self.worker_threads if t.is_alive()]

            available_slots = self.max_workers - len(self.worker_threads)
            if available_slots > 0:
                converted_items = conversion_queue.get_all_items_by_status(QueueStatus.CONVERTED)
                skipped_items = conversion_queue.get_all_items_by_status(QueueStatus.SKIPPED)
                ready_items = converted_items + skipped_items

                while available_slots > 0 and ready_items:
                    item = ready_items.pop(0)

                    with self.pool_lock:
                        free_idx = None
                        for idx, entry in enumerate(self.model_pool):
                            if not entry["busy"]:
                                free_idx = idx
                                break
                        if free_idx is None and len(self.model_pool) < self.max_workers:
                            model = self.create_whisper_model()
                            self.model_pool.append({"model": model, "busy": True})
                            model_to_use = model
                            model_idx = len(self.model_pool) - 1
                        elif free_idx is not None:
                            self.model_pool[free_idx]["busy"] = True
                            model_to_use = self.model_pool[free_idx]["model"]
                            model_idx = free_idx
                        else:
                            break

                    def worker(itm, mdl_idx, mdl):
                        try:
                            self.transcribe_file(itm, mdl)
                        finally:
                            with self.pool_lock:
                                self.model_pool[mdl_idx]["busy"] = False

                    t = threading.Thread(target=worker, args=(item, model_idx, model_to_use), daemon=True)
                    t.start()
                    self.worker_threads.append(t)
                    available_slots -= 1

            any_active = any(
                conversion_queue.get_all_items_by_status(s) for s in active_statuses
            ) or bool(self.worker_threads)
            if not any_active and self.model_pool:
                self.cleanup()
            time.sleep(0.5)

    def cleanup(self):
        """cleanup models from memory"""
        with self.pool_lock:
            for entry in self.model_pool:
                del entry["model"]
            self.model_pool = []
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        print("model unloaded from memory")

def trigger_media_processing():
    """trigger conversion of all media files found in .temp directory"""
    print("triggering async media processing...")
    
    media_threads = TEST_async_convert_all_media()
    
    print("media processing started in background")
    print(f"initial queue status: {conversion_queue.get_all_items()}")
    
    return media_threads

if __name__ == "__main__":
    # STATS_MONITORING_IMPLEMENTATION - comment out this line to disable stats
    # start_stats_monitoring("orchestrator_dual_worker")
    
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
    
    # STATS_MONITORING_IMPLEMENTATION - comment out this line to disable stats
    # stop_stats_monitoring()


import time
import os
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
from wrappers.db.db_manager import TranscriptionDB

class TranscriptionOrchestrator:
    def __init__(self):
        self.model = None
        from config import config
        self.model_id = config.WHISPER_MODEL
        self.temp_dir = config.TEMP_DIR
        self.whisper_cache_dir = config.WHISPER_CACHE_DIR
        self.max_workers = 3
        self.model_pool = []
        self.pool_lock = threading.Lock()
        self.worker_threads = []
        self.db = TranscriptionDB()
        
    def create_whisper_model(self) -> WhisperModel:
        """create a new faster-whisper model instance on gpu"""
        print("loading faster-whisper model...")
        if not torch.cuda.is_available():
            print("warning: torch reports no cuda device, still forcing cuda for debugging")
        device = "cuda"
        compute_type = "float16"
        model = WhisperModel(self.model_id, device=device, compute_type=compute_type, download_root=str(self.whisper_cache_dir))
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
            
            filename = Path(item.file_path).stem

            # include youtube url if this item came from a youtube download
            youtube_url = getattr(item, 'url', None) if hasattr(item, 'url') else None
            self.db.add_transcription(filename, transcription_text, item.id, youtube_url)
            item.update_status(QueueStatus.COMPLETED)
            
            if os.path.exists(item.file_path):
                os.remove(item.file_path)
                print(f"cleaned up {item.file_path}") 
            
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
                ready_items = conversion_queue.get_ready_items_for_transcription()
                pending_duplicates = conversion_queue.get_pending_duplicates()
                
                if pending_duplicates:
                    print(f"orchestrator: {len(pending_duplicates)} items pending duplicate resolution, continuing with {len(ready_items)} ready items")

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
        """cleanup models from memory with aggressive memory clearing"""
        print("starting model cleanup...")
        
        with self.pool_lock:
            # explicitly delete model references
            for entry in self.model_pool:
                if "model" in entry:
                    model = entry["model"]
                    # try to access model's internal cleanup if available
                    if hasattr(model, 'model') and hasattr(model.model, 'cpu'):
                        try:
                            model.model.cpu()
                        except:
                            pass
                    del model
                    del entry["model"]
            self.model_pool = []
        
        # aggressive garbage collection
        gc.collect()
        gc.collect()  # call twice for stubborn references
        
        if torch.cuda.is_available():
            # multiple cache clearing attempts
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()  # clean up any ipc memory
            torch.cuda.empty_cache()  # call again after ipc cleanup
            
            # get memory info for logging
            try:
                memory_allocated = torch.cuda.memory_allocated() / 1024**3  # convert to gb
                memory_cached = torch.cuda.memory_reserved() / 1024**3
                print(f"post-cleanup gpu memory - allocated: {memory_allocated:.2f}gb, cached: {memory_cached:.2f}gb")
            except:
                pass
        
        print("model cleanup completed - note: some memory may remain cached by cuda driver")

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


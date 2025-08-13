import time
from pathlib import Path
from uuid import uuid4
# STATS_MONITORING_IMPLEMENTATION - comment out these 2 lines to disable stats
from wrappers.transcription_statistics import start_stats_monitoring, stop_stats_monitoring

from wrappers.media_manager import (
    download_audio,
    convert_to_audio,
    check_file_exists,
    check_local_file_exists,
)
from wrappers.queue_manager import QueueItem, QueueStatus
from core import TranscriptionOrchestrator


# automatically discover all media files in temp directory
import glob

def get_all_media_files():
    """get all .mp4 and .ogg files from temp directory"""
    temp_dir = "/home/jack/llm/transcription/.temp"
    mp4_files = glob.glob(f"{temp_dir}/*.mp4") 
    ogg_files = glob.glob(f"{temp_dir}/*.ogg")
    return mp4_files, ogg_files


def make_item(file_path: str) -> QueueItem:
    """create a minimal queue item for direct transcription"""
    item = QueueItem(id=str(uuid4()), file_path=file_path)
    item.update_status(QueueStatus.CONVERTED)
    return item


def transcribe_one(orchestrator: TranscriptionOrchestrator, model, file_path: str) -> float:
    """transcribe a single file and return elapsed seconds"""
    item = make_item(file_path)
    t0 = time.time()
    orchestrator.transcribe_file(item, model)
    t1 = time.time()
    return t1 - t0


def ensure_audio_from_local(mp4_path: str) -> str:
    """convert local mp4 if needed and return ogg path"""
    print(f"processing local video individually: {mp4_path}")
    if not Path(mp4_path).exists():
        raise FileNotFoundError(f"missing local video: {mp4_path}")
    convert_to_audio(mp4_path)
    exists, ogg_path = check_local_file_exists(mp4_path)
    if not exists or not ogg_path:
        raise RuntimeError(f"failed to locate converted ogg for {mp4_path}")
    return ogg_path


def main():
    # STATS_MONITORING_IMPLEMENTATION - comment out this line to disable stats
    start_stats_monitoring("individual_sequential")
    
    orchestrator = TranscriptionOrchestrator()
    model = orchestrator.create_whisper_model()

    mp4_files, ogg_files = get_all_media_files()
    results = []

    # process all mp4 files (convert then transcribe)
    for i, mp4_path in enumerate(mp4_files):
        print(f"\nprocessing mp4 file {i+1}/{len(mp4_files)}: {mp4_path}")
        try:
            ogg_path = ensure_audio_from_local(mp4_path)
            duration = transcribe_one(orchestrator, model, ogg_path)
            results.append((f"mp4_file_{i+1}", ogg_path, duration))
        except Exception as e:
            print(f"error processing {mp4_path}: {e}")
            results.append((f"mp4_file_{i+1}_FAILED", mp4_path, 0))

    # process all existing ogg files (transcribe directly)
    for i, ogg_path in enumerate(ogg_files):
        print(f"\nprocessing ogg file {i+1}/{len(ogg_files)}: {ogg_path}")
        try:
            duration = transcribe_one(orchestrator, model, ogg_path)
            results.append((f"ogg_file_{i+1}", ogg_path, duration))
        except Exception as e:
            print(f"error processing {ogg_path}: {e}")
            results.append((f"ogg_file_{i+1}_FAILED", ogg_path, 0))

    orchestrator.cleanup()

    print(f"\nindividual transcription timings for {len(mp4_files)} mp4s + {len(ogg_files)} oggs:")
    total_time = 0
    for label, path, secs in results:
        print(f"- {label}: {secs:.2f}s -> {Path(path).name}")
        if not label.endswith("_FAILED"):
            total_time += secs
    
    print(f"\ntotal processing time: {total_time:.2f}s")
    
    # STATS_MONITORING_IMPLEMENTATION - comment out this line to disable stats
    stop_stats_monitoring()


if __name__ == "__main__":
    main()



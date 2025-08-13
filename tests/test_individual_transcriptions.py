import time
from pathlib import Path
from uuid import uuid4
# STATS_MONITORING_IMPLEMENTATION - comment out these 2 lines to disable stats
from wrappers.transcription_statistics import start_stats_monitoring, stop_stats_monitoring

from wrappers.media_manager import (
    TEST_get_all_media_files,
    convert_to_audio,
    check_local_file_exists,
)
from wrappers.queue_manager import QueueItem, QueueStatus
from core import TranscriptionOrchestrator


# removed hardcoded links and paths - now using TEST_get_all_media_files()


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

def get_all_audio_files() -> list[str]:
    """get all available audio files for testing"""
    media_files = TEST_get_all_media_files()
    
    # convert any mp4 files to ogg first
    mp4_files = [f for f in media_files if f.endswith('.mp4')]
    for mp4_file in mp4_files:
        ensure_audio_from_local(mp4_file)
    
    # get all ogg files (including newly converted ones)
    updated_files = TEST_get_all_media_files()
    ogg_files = [f for f in updated_files if f.endswith('.ogg')]
    
    return ogg_files


def main():
    # STATS_MONITORING_IMPLEMENTATION - comment out this line to disable stats
    start_stats_monitoring("individual_sequential")
    
    orchestrator = TranscriptionOrchestrator()
    model = orchestrator.create_whisper_model()

    results = []

    # get all audio files from .temp directory
    audio_files = get_all_audio_files()
    
    if not audio_files:
        print("no audio files found in .temp directory")
        return
    
    print(f"found {len(audio_files)} audio files to transcribe")
    
    # transcribe each file individually
    for i, audio_file in enumerate(audio_files):
        file_name = Path(audio_file).name
        duration = transcribe_one(orchestrator, model, audio_file)
        results.append((f"file_{i+1}_{file_name}", audio_file, duration))

    orchestrator.cleanup()

    print("\nindividual transcription timings (seconds):")
    for label, path, secs in results:
        print(f"- {label}: {secs:.2f}s -> {path}")
    
    # STATS_MONITORING_IMPLEMENTATION - comment out this line to disable stats
    stop_stats_monitoring()


if __name__ == "__main__":
    main()



#!/usr/bin/env python3
"""
transcription statistics collector - monitors gpu usage, memory, and timing
"""

import time
import threading
import csv
import psutil
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Optional


class TranscriptionStatistics:
    def __init__(self, session_name: str):
        self.session_name = session_name
        self.stats_dir = Path("/home/jack/llm/transcription/.stats")
        self.stats_dir.mkdir(exist_ok=True)
        
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
        self.monitoring = False
        self.monitor_thread: Optional[threading.Thread] = None
        
        # collected stats
        self.gpu_usage_samples = []
        self.memory_samples = []
        self.sample_timestamps = []
        
    def start_monitoring(self):
        """start collecting gpu and memory stats"""
        if self.monitoring:
            return
            
        self.start_time = time.time()
        self.monitoring = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        print(f"transcription statistics monitoring started for session: {self.session_name}")
        
    def stop_monitoring(self):
        """stop collecting and save results to csv"""
        if not self.monitoring:
            return
            
        self.end_time = time.time()
        self.monitoring = False
        
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=2)
            
        self._save_to_csv()
        print(f"transcription statistics saved for session: {self.session_name}")
        
    def _monitor_loop(self):
        """continuous monitoring loop collecting stats every 0.5 seconds"""
        while self.monitoring:
            timestamp = time.time()
            
            # gpu usage via nvidia-smi
            gpu_usage = self._get_gpu_usage()
            
            # memory usage via psutil
            memory_info = psutil.virtual_memory()
            memory_used_gb = memory_info.used / (1024**3)
            
            self.sample_timestamps.append(timestamp)
            self.gpu_usage_samples.append(gpu_usage)
            self.memory_samples.append(memory_used_gb)
            
            time.sleep(0.5)
            
    def _get_gpu_usage(self) -> float:
        """get gpu utilization percentage via nvidia-smi"""
        try:
            result = subprocess.run([
                "nvidia-smi", 
                "--query-gpu=utilization.gpu", 
                "--format=csv,noheader,nounits"
            ], capture_output=True, text=True, timeout=2)
            
            if result.returncode == 0:
                return float(result.stdout.strip())
            else:
                return 0.0
        except Exception:
            return 0.0
            
    def _save_to_csv(self):
        """save collected statistics to csv file"""
        if not self.start_time or not self.end_time:
            return
            
        total_duration = self.end_time - self.start_time
        avg_gpu_usage = sum(self.gpu_usage_samples) / len(self.gpu_usage_samples) if self.gpu_usage_samples else 0
        max_gpu_usage = max(self.gpu_usage_samples) if self.gpu_usage_samples else 0
        avg_memory_gb = sum(self.memory_samples) / len(self.memory_samples) if self.memory_samples else 0
        max_memory_gb = max(self.memory_samples) if self.memory_samples else 0
        
        # summary csv file
        summary_file = self.stats_dir / "transcription_summary.csv"
        file_exists = summary_file.exists()
        
        with open(summary_file, "a", newline="") as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow([
                    "session_name", "start_time", "total_duration_sec", 
                    "avg_gpu_usage_pct", "max_gpu_usage_pct", 
                    "avg_memory_gb", "max_memory_gb", "sample_count"
                ])
            
            writer.writerow([
                self.session_name,
                datetime.fromtimestamp(self.start_time).isoformat(),
                f"{total_duration:.2f}",
                f"{avg_gpu_usage:.1f}",
                f"{max_gpu_usage:.1f}",
                f"{avg_memory_gb:.2f}",
                f"{max_memory_gb:.2f}",
                len(self.sample_timestamps)
            ])
            
        # detailed csv file with all samples
        detail_file = self.stats_dir / f"transcription_details_{self.session_name}_{int(self.start_time)}.csv"
        with open(detail_file, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp", "elapsed_sec", "gpu_usage_pct", "memory_gb"])
            
            for i, ts in enumerate(self.sample_timestamps):
                elapsed = ts - self.start_time
                gpu_usage = self.gpu_usage_samples[i] if i < len(self.gpu_usage_samples) else 0
                memory_gb = self.memory_samples[i] if i < len(self.memory_samples) else 0
                writer.writerow([ts, f"{elapsed:.1f}", f"{gpu_usage:.1f}", f"{memory_gb:.2f}"])


# global instance - import this in your scripts
stats_monitor: Optional[TranscriptionStatistics] = None


def start_stats_monitoring(session_name: str):
    """start statistics monitoring - call this at the beginning of transcription"""
    global stats_monitor
    stats_monitor = TranscriptionStatistics(session_name)
    stats_monitor.start_monitoring()


def stop_stats_monitoring():
    """stop statistics monitoring and save results - call this when transcription completes"""
    global stats_monitor
    if stats_monitor:
        stats_monitor.stop_monitoring()
        stats_monitor = None

import json
import threading
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional
from enum import Enum
import uuid

class VideoType(Enum):
    YOUTUBE = "youtube"
    CUSTOM = "custom"

class VideoStatus(Enum):
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    TRANSCRIBING = "transcribing"
    COMPLETED = "completed"
    FAILED = "failed"

class VideoQueueItem:
    def __init__(self, url: str, video_type: VideoType, title: Optional[str] = None):
        self.id = str(uuid.uuid4())
        self.url = url
        self.video_type = video_type
        self.title = title
        self.status = VideoStatus.QUEUED
        self.added_time = datetime.now().isoformat()
        self.completed_time = None
        self.error_message = None
        self.local_path = None
        
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "url": self.url,
            "video_type": self.video_type.value,
            "title": self.title,
            "status": self.status.value,
            "added_time": self.added_time,
            "completed_time": self.completed_time,
            "error_message": self.error_message,
            "local_path": self.local_path
        }

class VideoProcessingQueue:
    """Thread-safe queue for managing video processing tasks"""
    
    def __init__(self, queue_file: Path):
        self.queue_file = queue_file
        self.lock = threading.Lock()
        self._load_queue()
        
    def _load_queue(self):
        """Load queue from persistent storage"""
        self.queue: List[VideoQueueItem] = []
        self.processing_item: Optional[VideoQueueItem] = None
        
        if self.queue_file.exists():
            try:
                with open(self.queue_file, 'r') as f:
                    data = json.load(f)
                    for item_data in data.get("queue", []):
                        item = self._dict_to_item(item_data)
                        self.queue.append(item)
                    if data.get("processing_item"):
                        self.processing_item = self._dict_to_item(data["processing_item"])
            except Exception as e:
                print(f"Error loading queue from file: {e}")
                self.queue = []
                self.processing_item = None
    
    def _save_queue(self):
        """Save queue to persistent storage"""
        try:
            data = {
                "queue": [item.to_dict() for item in self.queue],
                "processing_item": self.processing_item.to_dict() if self.processing_item else None
            }
            with open(self.queue_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Error saving queue to file: {e}")
    
    def _dict_to_item(self, data: Dict[str, Any]) -> VideoQueueItem:
        """Convert dictionary to VideoQueueItem"""
        item = VideoQueueItem(
            url=data["url"],
            video_type=VideoType(data["video_type"]),
            title=data.get("title")
        )
        item.id = data["id"]
        item.status = VideoStatus(data["status"])
        item.added_time = data["added_time"]
        item.completed_time = data.get("completed_time")
        item.error_message = data.get("error_message")
        item.local_path = data.get("local_path")
        return item
    
    def add_youtube_urls(self, urls: List[str]) -> int:
        """Add YouTube URLs to the queue"""
        with self.lock:
            count = 0
            for url in urls:
                # Check if URL already in queue or being processed
                if not self._is_url_in_queue(url):
                    item = VideoQueueItem(url, VideoType.YOUTUBE)
                    self.queue.append(item)
                    count += 1
            self._save_queue()
            return count
    
    def add_custom_video(self, custom_url: str, title: Optional[str] = None) -> bool:
        """Add custom video to the queue"""
        with self.lock:
            if not self._is_url_in_queue(custom_url):
                item = VideoQueueItem(custom_url, VideoType.CUSTOM, title)
                self.queue.append(item)
                self._save_queue()
                return True
            return False
    
    def _is_url_in_queue(self, url: str) -> bool:
        """Check if URL is already in queue or being processed"""
        for item in self.queue:
            if item.url == url:
                return True
        if self.processing_item and self.processing_item.url == url:
            return True
        return False
    
    def get_next_item(self) -> Optional[VideoQueueItem]:
        """Get next item to process"""
        with self.lock:
            if self.queue and not self.processing_item:
                self.processing_item = self.queue.pop(0)
                self.processing_item.status = VideoStatus.DOWNLOADING
                self._save_queue()
                return self.processing_item
            return None
    
    def update_item_status(self, item_id: str, status: VideoStatus, 
                          error_message: Optional[str] = None,
                          local_path: Optional[str] = None):
        """Update status of the processing item"""
        with self.lock:
            if self.processing_item and self.processing_item.id == item_id:
                self.processing_item.status = status
                if error_message:
                    self.processing_item.error_message = error_message
                if local_path:
                    self.processing_item.local_path = local_path
                if status in [VideoStatus.COMPLETED, VideoStatus.FAILED]:
                    self.processing_item.completed_time = datetime.now().isoformat()
                self._save_queue()
    
    def complete_current_item(self):
        """Mark current processing item as complete and remove it"""
        with self.lock:
            if self.processing_item:
                if self.processing_item.status == VideoStatus.FAILED:
                    # Keep failed items in history (could be moved to a separate failed list)
                    pass
                self.processing_item = None
                self._save_queue()
    
    def get_status(self) -> Dict[str, Any]:
        """Get current queue status"""
        with self.lock:
            total_items = len(self.queue)
            if self.processing_item:
                total_items += 1
            
            completed_items = []
            failed_items = []
            
            # In a real implementation, we'd track completed/failed items separately
            # For now, we'll just report on what's in the queue
            
            status = "idle"
            if self.processing_item:
                if self.processing_item.status == VideoStatus.DOWNLOADING:
                    status = "processing_downloads"
                elif self.processing_item.status == VideoStatus.TRANSCRIBING:
                    status = "processing_transcriptions"
            elif total_items > 0:
                status = "queued"
                
            return {
                "status": status,
                "queue_length": len(self.queue),
                "processing_item": self.processing_item.to_dict() if self.processing_item else None,
                "total_items": total_items
            }
    
    def clear_queue(self):
        """Clear all items from the queue"""
        with self.lock:
            self.queue = []
            self.processing_item = None
            self._save_queue()
    
    def get_all_items(self) -> List[Dict[str, Any]]:
        """Get all items in queue including processing item"""
        with self.lock:
            items = []
            if self.processing_item:
                items.append(self.processing_item.to_dict())
            items.extend([item.to_dict() for item in self.queue])
            return items
    
    def is_processing(self) -> bool:
        """Check if currently processing an item"""
        with self.lock:
            return self.processing_item is not None 
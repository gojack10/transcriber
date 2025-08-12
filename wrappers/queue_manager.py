from enum import Enum
from datetime import datetime
from typing import Optional
import uuid

class QueueStatus(Enum):
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    CONVERTING = "converting"
    TRANSCRIBING = "transcribing"
    COMPLETED = "completed"
    FAILED = "failed"

class QueueItem:
    id: str
    file_path: str
    status: QueueStatus
    created_at: datetime
    updated_at: datetime
    error_message: Optional[str]

    def __init__(self, id: str, file_path: Optional[str] = None, url: Optional[str] = None):
        self.id = id
        self.url = url
        self.file_path = file_path
        self.status = QueueStatus.QUEUED
        self.created_at = datetime.now()
        self.updated_at = datetime.now()
        self.error_message = None

    def update_status(self, new_status: QueueStatus, error_message: Optional[str] = None):
        self.status = new_status
        self.error_message = error_message
        self.updated_at = datetime.now()
        print(f"Updated status for item {self.id} to {new_status}")

    def mark_failed(self, error: str):
        self.update_status(QueueStatus.FAILED, error)
        print(f"Marked item {self.id} as failed: {error}")
    
    def __repr__(self):
        return f"QueueItem(id='{self.id}', file_path='{self.file_path}', status={self.status})"

class QueueManager:
    def __init__(self):
        self.queue = {}
        self.processing_order = []
    
    def add_item(self, file_path: str, url: Optional[str] = None) -> str:
        item_id = str(uuid.uuid4())
        item = QueueItem(item_id, file_path, url)
        self.queue[item_id] = item
        self.processing_order.append(item_id)
        print(f"Added item {item_id} for {file_path}")
        return item_id
    
    def update_item_path(self, item_id: str, new_file_path: str):
        if item_id in self.queue:
            self.queue[item_id].file_path = new_file_path
            self.queue[item_id].updated_at = datetime.now()
            print(f"Updated file path for item {item_id} to {new_file_path}")
        else:
            print(f"Item {item_id} not found in queue")
    
    def get_next_item(self) -> Optional[QueueItem]:
        if not self.processing_order:
            return None
        item_id = self.processing_order.pop(0)
        print(f"Getting next item {item_id}")
        return self.queue[item_id]
    
    def get_queue_counts(self) -> dict:
        return {status.value: sum(1 for item in self.queue.values() if item.status == status) for status in QueueStatus}
    
    def get_item(self, item_id: str) -> Optional[QueueItem]:
        return self.queue.get(item_id)
    
    def get_all_items(self) -> list[QueueItem]:
        return list(self.queue.values())
    
    def get_all_items_by_status(self, status: QueueStatus) -> list[QueueItem]:
        return [item for item in self.queue.values() if item.status == status]
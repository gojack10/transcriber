from enum import Enum
from datetime import datetime
from typing import Optional
import uuid

class QueueStatus(Enum):
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    CONVERTING = "converting"
    CONVERTED = "converted"
    TRANSCRIBING = "transcribing"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"
    PENDING_DUPLICATE = "pending_duplicate"

class QueueItem:
    id: str
    file_path: str
    status: QueueStatus
    created_at: datetime
    updated_at: datetime
    error_message: Optional[str]

    def __init__(self, id: str, file_path: Optional[str] = None, url: Optional[str] = None, video_title: Optional[str] = None):
        self.id = id
        self.url = url
        self.file_path = file_path
        self.video_title = video_title
        self.status = QueueStatus.QUEUED
        self.created_at = datetime.now()
        self.updated_at = datetime.now()
        self.error_message = None
        self.pending_transcription = None

    def update_status(self, new_status: QueueStatus, error_message: Optional[str] = None):
        self.status = new_status
        self.error_message = error_message
        self.updated_at = datetime.now()
        print(f"Updated status for item {self.id} to {new_status}")
        
        try:
            from wrappers.media_manager import conversion_queue
            if hasattr(conversion_queue, '_save_to_db'):
                conversion_queue._save_to_db(self)
        except:
            pass  

    def mark_failed(self, error: str):
        self.update_status(QueueStatus.FAILED, error)
        print(f"Marked item {self.id} as failed: {error}")
    
    def __repr__(self):
        return f"QueueItem(id='{self.id}', file_path='{self.file_path}', status={self.status})"

class QueueManager:
    def __init__(self):
        self.queue = {}
        self.processing_order = []
        self.db = None
        self._init_db()
        self._load_from_db()
    
    def _init_db(self):
        """initialize database connection"""
        try:
            from wrappers.db.db_manager import TranscriptionDB
            self.db = TranscriptionDB()
        except Exception as e:
            print(f"warning: could not initialize database for queue persistence: {e}")
    
    def _load_from_db(self):
        """load existing queue items from database on startup"""
        if not self.db:
            return
        
        try:
            db_items = self.db.load_queue_items()
            for item_data in db_items:
                item = QueueItem(item_data['id'])
                item.file_path = item_data['file_path']
                item.url = item_data['url']
                item.video_title = item_data['video_title']
                item.status = QueueStatus(item_data['status'])
                item.created_at = datetime.fromisoformat(item_data['created_at'])
                item.updated_at = datetime.fromisoformat(item_data['updated_at'])
                item.error_message = item_data['error_message']
                
                if item_data['pending_transcription'] and item_data['pending_transcription'] != 'None':
                    try:
                        import ast
                        item.pending_transcription = ast.literal_eval(item_data['pending_transcription'])
                    except:
                        item.pending_transcription = None
                
                self.queue[item.id] = item
                final_states = {QueueStatus.COMPLETED, QueueStatus.FAILED, QueueStatus.CANCELLED}
                if item.status not in final_states:
                    self.processing_order.append(item.id)
            
            print(f"loaded {len(db_items)} queue items from database")
            
            if self.db:
                cleaned = self.db.cleanup_completed_queue_items()
                if cleaned > 0:
                    print(f"cleaned up {cleaned} old completed queue items")
            
            self._cleanup_orphaned_temp_files()
                    
        except Exception as e:
            print(f"error loading queue items from database: {e}")
    
    def _cleanup_orphaned_temp_files(self):
        """cleanup all files in .temp directory"""
        try:
            from config import config
            from pathlib import Path
            import os
            
            temp_dir = Path(config.TEMP_DIR)
            if not temp_dir.exists():
                return
            
            # get all files in temp directory
            temp_files = [f for f in temp_dir.iterdir() if f.is_file()]
            
            if not temp_files:
                return
            
            cleaned_count = 0
            for temp_file in temp_files:
                try:
                    os.remove(temp_file)
                    print(f"cleaned up temp file: {temp_file.name}")
                    cleaned_count += 1
                except Exception as e:
                    print(f"error cleaning up {temp_file}: {e}")
            
            if cleaned_count > 0:
                print(f"cleaned up {cleaned_count} temp files")
                
        except Exception as e:
            print(f"error during temp file cleanup: {e}")
    
    def cleanup_temp_files(self):
        """manually trigger temp file cleanup"""
        print("manually cleaning up temp files...")
        self._cleanup_orphaned_temp_files()
    
    def _save_to_db(self, item):
        """save queue item to database"""
        if self.db:
            try:
                self.db.save_queue_item(item)
            except Exception as e:
                print(f"error saving queue item to database: {e}")
    
    def add_item(self, file_path: str, url: Optional[str] = None, video_title: Optional[str] = None) -> str:
        item_id = str(uuid.uuid4())
        item = QueueItem(item_id, file_path, url, video_title)
        self.queue[item_id] = item
        self.processing_order.append(item_id)
        self._save_to_db(item)
        print(f"Added item {item_id} for {file_path}")
        return item_id
    
    def update_item_path(self, item_id: str, new_file_path: str):
        if item_id in self.queue:
            self.queue[item_id].file_path = new_file_path
            self.queue[item_id].updated_at = datetime.now()
            self._save_to_db(self.queue[item_id])
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
    
    def get_ready_items_for_transcription(self) -> list[QueueItem]:
        """get items ready for transcription, excluding pending duplicates"""
        ready_statuses = {QueueStatus.CONVERTED, QueueStatus.SKIPPED}
        return [item for item in self.queue.values() if item.status in ready_statuses]
    
    def get_pending_duplicates(self) -> list[QueueItem]:
        """get all items pending duplicate resolution"""
        return [item for item in self.queue.values() if item.status == QueueStatus.PENDING_DUPLICATE]
    
    def remove_item(self, item_id: str) -> bool:
        if item_id in self.queue:
            item = self.queue[item_id]
            try:
                from wrappers.media_manager import cleanup_item_files
                cleanup_item_files(item)
            except ImportError:
                pass
            
            if self.db:
                self.db.delete_queue_item(item_id)
            
            del self.queue[item_id]
            if item_id in self.processing_order:
                self.processing_order.remove(item_id)
            print(f"removed item {item_id} from queue")
            return True
        return False
    
    def can_cancel_item(self, item_id: str) -> bool:
        """check if item can be cancelled (is in active processing states)"""
        item = self.get_item(item_id)
        if not item:
            return False
        active_states = {QueueStatus.QUEUED, QueueStatus.DOWNLOADING, QueueStatus.CONVERTING, QueueStatus.TRANSCRIBING}
        return item.status in active_states
    
    def can_remove_item(self, item_id: str) -> bool:
        """check if item can be removed (is in final states)"""
        item = self.get_item(item_id)
        if not item:
            return False
        final_states = {QueueStatus.COMPLETED, QueueStatus.FAILED, QueueStatus.CANCELLED, QueueStatus.SKIPPED}
        return item.status in final_states

    def remove_items(self, item_ids: list[str]) -> dict:
        """remove multiple items from queue, returns dict with counts"""
        result = {
            'removed': 0,
            'cancelled': 0,
            'not_found': 0,
            'cannot_remove': 0
        }
        
        for item_id in item_ids:
            item = self.get_item(item_id)
            if not item:
                result['not_found'] += 1
                continue
            
            if self.can_cancel_item(item_id):
                item.update_status(QueueStatus.CANCELLED, "cancelled by user")
                result['cancelled'] += 1
            elif self.can_remove_item(item_id):
                self.remove_item(item_id)
                result['removed'] += 1
            else:
                result['cannot_remove'] += 1
        
        return result
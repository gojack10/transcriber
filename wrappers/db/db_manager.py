import sqlite3
import threading
from pathlib import Path
from datetime import datetime, timedelta
import pytz
from typing import Optional, List, Dict, Any
from contextlib import contextmanager

class TranscriptionDB:
    def __init__(self, db_path: str = None):
        if db_path is None:
            from config import config
            db_path = config.get_db_path()
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(exist_ok=True)
        self._lock = threading.Lock()
        self._init_database()

    def _init_database(self):
        with self.get_connection() as conn:
            conn.execute("""
        CREATE TABLE IF NOT EXISTS transcriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            content TEXT NOT NULL,
            transcribed_time TEXT NOT NULL,
            queue_item_id TEXT,
            youtube_url TEXT
        );""")
            
            conn.execute("""
        CREATE TABLE IF NOT EXISTS queue_items (
            id TEXT PRIMARY KEY,
            file_path TEXT,
            url TEXT,
            video_title TEXT,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            error_message TEXT,
            pending_transcription TEXT
        );""")
            conn.commit()

    def format_pst_time(self, dt: datetime = None) -> str:
        if dt is None:
            dt = datetime.now(pytz.timezone("America/Los_Angeles"))
        return dt.strftime("%Y-%m-%d %H:%M:%S PST")
    
    def add_transcription(self, filename: str, content: str, queue_item_id: str, youtube_url: str = None):
        try:
            transcribed_time = self.format_pst_time()
            
            with self.get_connection() as conn:
                conn.execute("""
                INSERT INTO transcriptions (filename, transcribed_time, content, queue_item_id, youtube_url)
                VALUES (?, ?, ?, ?, ?);""", (filename, transcribed_time, content, queue_item_id, youtube_url))
                conn.commit()
                return True
        except Exception as e:
            print(f"error saving transcription: {e}")
            return False
        
    def get_transcription(self, filename: str):
        try:
            with self.get_connection() as conn:
                cursor = conn.execute("""
                SELECT content FROM transcriptions WHERE filename = ?;""", (filename,))
                transcription = cursor.fetchone()
                return transcription[0] if transcription else None
        except Exception as e:
            print(f"error getting transcription: {e}")
            return None
    
    def get_all_transcriptions(self, sort_by: str = "id", sort_order: str = "desc"):
        try:
            valid_columns = ["id", "filename"]
            valid_orders = ["asc", "desc"]
            
            if sort_by not in valid_columns:
                sort_by = "id"
            if sort_order not in valid_orders:
                sort_order = "desc"
                
            with self.get_connection() as conn:
                cursor = conn.execute(f"""
                SELECT id, filename, transcribed_time, queue_item_id, youtube_url FROM transcriptions 
                ORDER BY {sort_by} {sort_order.upper()};""")
                rows = cursor.fetchall()
                
                return [{
                    'id': row[0],
                    'filename': row[1], 
                    'transcribed_time': row[2],
                    'queue_item_id': row[3],
                    'youtube_url': row[4]
                } for row in rows]
        except Exception as e:
            print(f"error getting all transcriptions: {e}")
            return []
        
    def delete_transcription(self, transcription_id: int) -> bool:
        """delete a single transcription by id"""
        try:
            with self.get_connection() as conn:
                cursor = conn.execute("DELETE FROM transcriptions WHERE id = ?", (transcription_id,))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            print(f"error deleting transcription {transcription_id}: {e}")
            return False

    def delete_transcriptions(self, transcription_ids: List[int]) -> int:
        """delete multiple transcriptions by ids, returns number deleted"""
        try:
            if not transcription_ids:
                return 0
                
            placeholders = ','.join('?' * len(transcription_ids))
            with self.get_connection() as conn:
                cursor = conn.execute(f"DELETE FROM transcriptions WHERE id IN ({placeholders})", transcription_ids)
                conn.commit()
                return cursor.rowcount
        except Exception as e:
            print(f"error deleting transcriptions {transcription_ids}: {e}")
            return 0

    def transcription_exists(self, filename: str) -> bool:
        """check if a transcription with the given filename already exists"""
        try:
            with self.get_connection() as conn:
                cursor = conn.execute("SELECT 1 FROM transcriptions WHERE filename = ?", (filename,))
                return cursor.fetchone() is not None
        except Exception as e:
            print(f"error checking transcription existence: {e}")
            return False

    def youtube_url_exists(self, url: str) -> bool:
        """check if youtube url already has a transcription"""
        try:
            with self.get_connection() as conn:
                cursor = conn.execute("SELECT 1 FROM transcriptions WHERE youtube_url = ?", (url,))
                return cursor.fetchone() is not None
        except Exception as e:
            print(f"error checking youtube url existence: {e}")
            return False
    
    def get_youtube_url_info(self, url: str) -> Optional[Dict[str, Any]]:
        """get transcription info for a youtube url if it exists"""
        try:
            with self.get_connection() as conn:
                cursor = conn.execute("""
                SELECT filename, transcribed_time FROM transcriptions WHERE youtube_url = ?""", (url,))
                row = cursor.fetchone()
                if row:
                    return {
                        'url': url,
                        'video_title': row[0],
                        'added_time': row[1]
                    }
                return None
        except Exception as e:
            print(f"error getting youtube url info: {e}")
            return None

    # queue item management methods
    def save_queue_item(self, queue_item) -> bool:
        """save or update a queue item in the database"""
        try:
            with self.get_connection() as conn:
                conn.execute("""
                INSERT OR REPLACE INTO queue_items 
                (id, file_path, url, video_title, status, created_at, updated_at, error_message, pending_transcription)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    queue_item.id,
                    str(queue_item.file_path) if queue_item.file_path else None,
                    getattr(queue_item, 'url', None),
                    getattr(queue_item, 'video_title', None),
                    queue_item.status.value,
                    queue_item.created_at.isoformat(),
                    queue_item.updated_at.isoformat(),
                    queue_item.error_message,
                    str(getattr(queue_item, 'pending_transcription', None)) if getattr(queue_item, 'pending_transcription', None) else None
                ))
                conn.commit()
                return True
        except Exception as e:
            print(f"error saving queue item {queue_item.id}: {e}")
            return False

    def load_queue_items(self) -> List[Dict[str, Any]]:
        """load all queue items from database"""
        try:
            with self.get_connection() as conn:
                cursor = conn.execute("""
                SELECT id, file_path, url, video_title, status, created_at, updated_at, error_message, pending_transcription
                FROM queue_items ORDER BY created_at
                """)
                items = []
                for row in cursor.fetchall():
                    items.append({
                        'id': row[0],
                        'file_path': row[1],
                        'url': row[2],
                        'video_title': row[3],
                        'status': row[4],
                        'created_at': row[5],
                        'updated_at': row[6],
                        'error_message': row[7],
                        'pending_transcription': row[8]
                    })
                return items
        except Exception as e:
            print(f"error loading queue items: {e}")
            return []

    def delete_queue_item(self, item_id: str) -> bool:
        """delete a queue item from database"""
        try:
            with self.get_connection() as conn:
                cursor = conn.execute("DELETE FROM queue_items WHERE id = ?", (item_id,))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            print(f"error deleting queue item {item_id}: {e}")
            return False

    def cleanup_completed_queue_items(self) -> int:
        """remove completed/failed queue items older than 24 hours, returns count removed"""
        try:
            cutoff_time = (datetime.now() - timedelta(hours=24)).isoformat()
            with self.get_connection() as conn:
                cursor = conn.execute("""
                DELETE FROM queue_items 
                WHERE status IN ('completed', 'failed', 'cancelled') 
                AND updated_at < ?
                """, (cutoff_time,))
                conn.commit()
                return cursor.rowcount
        except Exception as e:
            print(f"error cleaning up queue items: {e}")
            return 0

    @contextmanager
    def get_connection(self):
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            try:
                yield conn
            finally:
                conn.close()
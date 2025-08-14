import sqlite3
import threading
from pathlib import Path
from datetime import datetime
import pytz
from typing import Optional, List, Dict, Any
from contextlib import contextmanager

class TranscriptionDB:
    def __init__(self, db_path: str = "/home/jack/llm/transcription/transcription.db"):
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

    @contextmanager
    def get_connection(self):
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            try:
                yield conn
            finally:
                conn.close()
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
            queue_item_id TEXT
        );""")
            conn.commit()

    def format_pst_time(self, dt: datetime = None) -> str:
        if dt is None:
            dt = datetime.now(pytz.timezone("America/Los_Angeles"))
        return dt.strftime("%Y-%m-%d %H:%M:%S PST")
    
    def add_transcription(self, filename: str, content: str, queue_item_id: str):
        try:
            transcribed_time = self.format_pst_time()
            
            with self.get_connection() as conn:
                conn.execute("""
                INSERT INTO transcriptions (filename, transcribed_time, content, queue_item_id)
                VALUES (?, ?, ?, ?);""", (filename, transcribed_time, content, queue_item_id))
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
        
    @contextmanager
    def get_connection(self):
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            try:
                yield conn
            finally:
                conn.close()
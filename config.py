"""
configuration management for transcription service
handles environment-specific settings and path configuration
"""
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  

class Config:
    def __init__(self):
        self.BASE_DIR = Path(__file__).parent.absolute()
        
        self.TEMP_DIR = Path(os.environ.get('TRANSCRIPTION_TEMP_DIR', self.BASE_DIR / '.temp'))
        self.DB_PATH = os.environ.get('TRANSCRIPTION_DB_PATH', str(self.BASE_DIR / 'transcription.db'))
        self.STATS_DIR = Path(os.environ.get('TRANSCRIPTION_STATS_DIR', self.BASE_DIR / '.stats'))
        self.WHISPER_CACHE_DIR = Path(os.environ.get('WHISPER_CACHE_DIR', self.BASE_DIR / 'whisper-cache'))
        
        self.HOST = os.environ.get('TRANSCRIPTION_HOST', 'localhost')
        self.PORT = int(os.environ.get('TRANSCRIPTION_PORT', '8080'))
        self.DEBUG = os.environ.get('TRANSCRIPTION_DEBUG', 'False').lower() == 'true'
        
        self.MAX_CONTENT_LENGTH = 500 * 1024 * 1024  # 500mb
        self.SECRET_KEY = os.environ.get('FLASK_SECRET_KEY', 'dev-key-change-in-production')
        
        # whisper model configuration
        self.WHISPER_MODEL = os.environ.get('WHISPER_MODEL', 'small.en')
        self.MAX_WORKERS = int(os.environ.get('TRANSCRIPTION_MAX_WORKERS', '3'))
        
        # create directories if they don't exist
        self._ensure_directories()
    
    def _ensure_directories(self):
        """create necessary directories"""
        self.TEMP_DIR.mkdir(exist_ok=True)
        self.STATS_DIR.mkdir(exist_ok=True)
        self.WHISPER_CACHE_DIR.mkdir(exist_ok=True)
    
    def get_temp_dir_str(self):
        """get temp directory as string for backward compatibility"""
        return str(self.TEMP_DIR)
    
    def get_db_path(self):
        """get database path"""
        return self.DB_PATH

config = Config()

import os
from wrappers.db.db_manager import TranscriptionDB

def test_db_manager():
    db = TranscriptionDB()
    db.add_transcription("test.ogg", "test transcription", "test queue item id")
    transcription = db.get_transcription("test.ogg")
    assert transcription is not None
    assert transcription == "test transcription"

if __name__ == "__main__":
    test_db_manager()
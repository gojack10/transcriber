import threading
import time
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import TranscriptionOrchestrator, trigger_media_processing
from server.api_server import run_server

def run_orchestrator():
    print("starting transcription orchestrator...")
    
    media_threads = trigger_media_processing()
    
    orchestrator = TranscriptionOrchestrator()
    try:
        orchestrator.run_orchestration()
    except KeyboardInterrupt:
        print("\nstopping orchestrator...")
        orchestrator.cleanup()
        
        print("waiting for media processing threads to complete...")
        for thread in media_threads:
            if thread.is_alive():
                thread.join(timeout=5)

def main():
    print("starting transcription automation server...")
    
    try:
        orchestrator_thread = threading.Thread(target=run_orchestrator, daemon=True)
        orchestrator_thread.start()
        
        time.sleep(1)
        
        print("starting http api server...")
        run_server(host='localhost', port=8080, debug=False)
        
    except KeyboardInterrupt:
        print("\nshutting down server...")
    finally:
        pass

if __name__ == '__main__':
    main()

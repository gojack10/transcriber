#!/usr/bin/env python3
"""
Test script to demonstrate the new queue-based transcription system
"""

import requests
import time
import json
import sys

BASE_URL = "http://192.168.51.100:8000"

def test_queue_system():
    print("=== Testing New Queue-Based Transcription System ===\n")
    
    # 1. Check initial status
    print("1. Checking initial status...")
    response = requests.get(f"{BASE_URL}/status")
    print(f"Status: {json.dumps(response.json(), indent=2)}\n")
    
    # 2. Check queue items
    print("2. Checking queue items...")
    response = requests.get(f"{BASE_URL}/queue_items")
    print(f"Queue: {json.dumps(response.json(), indent=2)}\n")
    
    # 3. Add a YouTube URL
    print("3. Adding YouTube URL to queue...")
    youtube_urls = ["https://www.youtube.com/watch?v=dQw4w9WgXcQ"]
    response = requests.post(f"{BASE_URL}/add_links", 
                           json={"urls": youtube_urls})
    print(f"Response: {json.dumps(response.json(), indent=2)}\n")
    
    # 4. Check queue items again
    print("4. Checking queue after adding YouTube URL...")
    response = requests.get(f"{BASE_URL}/queue_items")
    print(f"Queue: {json.dumps(response.json(), indent=2)}\n")
    
    # 5. Upload a custom video (simulate)
    print("5. Note: To upload a custom video, use:")
    print("curl -X POST http://192.168.51.100:8000/upload_custom_video \\")
    print("  -F \"file=@/path/to/your/video.mp4\" \\")
    print("  -F \"title=My Custom Video\"\n")
    
    # 6. Trigger transcription
    print("6. Triggering transcription process...")
    response = requests.post(f"{BASE_URL}/trigger_transcription")
    print(f"Response: {json.dumps(response.json(), indent=2)}\n")
    
    # 7. Monitor status
    print("7. Monitoring status (press Ctrl+C to stop)...")
    try:
        while True:
            response = requests.get(f"{BASE_URL}/status")
            status_data = response.json()
            print(f"\rStatus: {status_data['status']} | Progress: {status_data['progress']}", end="", flush=True)
            
            if status_data['status'] in ['completed', 'completed_with_errors']:
                print(f"\n\nFinal status: {json.dumps(status_data, indent=2)}")
                break
                
            time.sleep(2)
    except KeyboardInterrupt:
        print("\n\nMonitoring stopped by user.")
    
    # 8. Clear queue
    print("\n8. Clearing queue...")
    response = requests.post(f"{BASE_URL}/clear_list")
    print(f"Response: {json.dumps(response.json(), indent=2)}\n")
    
    print("=== Test Complete ===")

if __name__ == "__main__":
    test_queue_system() 
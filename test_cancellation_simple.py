"""
Simple tests for transcription cancellation functionality.
Tests the actual behavior without complex mocking.
"""

import pytest
from fastapi.testclient import TestClient
from transcriber import create_app

# Create test app
app = create_app()
client = TestClient(app)


class TestTranscriptionCancellation:
    
    def test_abort_no_active_task(self):
        """Test that abort returns idle when no task is running"""
        response = client.post("/abort_transcription")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "idle"
        assert "no active transcription" in data["message"].lower()
    
    def test_abort_endpoint_exists(self):
        """Test that the abort endpoint exists and responds"""
        response = client.post("/abort_transcription")
        assert response.status_code in [200, 400, 500]  # Any valid response
    
    def test_status_endpoint_after_abort(self):
        """Test that status endpoint works after abort"""
        # First, check initial status
        status_response = client.get("/status")
        assert status_response.status_code == 200
        
        # Then try to abort
        abort_response = client.post("/abort_transcription")
        assert abort_response.status_code == 200
        
        # Check status again
        status_response2 = client.get("/status")
        assert status_response2.status_code == 200
    
    def test_clear_queue_endpoint(self):
        """Test that clear endpoint works (basic sanity)"""
        response = client.post("/clear_list")
        assert response.status_code == 200
        assert "queue has been cleared" in response.json()["message"]
    
    def test_queue_items_endpoint(self):
        """Test that queue items endpoint works"""
        response = client.get("/queue_items")
        assert response.status_code == 200
        assert "items" in response.json()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
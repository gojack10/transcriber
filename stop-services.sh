#!/bin/bash

echo "stopping transcription services..."

# stop and remove containers
docker stop transcription_service transcriber-db 2>/dev/null || true
docker rm transcription_service transcriber-db 2>/dev/null || true

echo "services stopped successfully!" 
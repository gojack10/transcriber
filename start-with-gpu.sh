#!/bin/bash

# Source .env file if it exists
if [ -f .env ]; then
  export $(grep -v '^#' .env | xargs)
fi

# create network if it doesn't exist
echo "creating docker network..."
docker network create transcriber_app_network 2>/dev/null || true

# ensure the queue file exists as a regular file
[ -f video_queue.json ] || echo "[]" > video_queue.json

# start transcription service with GPU support
# first, start the database
echo "starting postgres database..."
docker run -d \
  --name transcriber-db \
  --restart unless-stopped \
  -e POSTGRES_USER=${DB_USER} \
  -e POSTGRES_PASSWORD=${DB_PASSWORD} \
  -e POSTGRES_DB=${DB_NAME} \
  -e PGDATA=/var/lib/postgresql/data/pgdata \
  -v /mnt/massstorage/transcription-db:/var/lib/postgresql/data/pgdata \
  -p 5432:5432 \
  --network transcriber_app_network \
  postgres:15

# wait a moment for database to start
echo "waiting for database to start..."
sleep 5

echo "starting transcription service with GPU support..."
docker run -d \
   --name transcription_service \
   --restart unless-stopped \
   --gpus all \
   -e NVIDIA_VISIBLE_DEVICES=all \
   -e NVIDIA_DRIVER_CAPABILITIES=compute,utility \
   -e DB_HOST=transcriber-db \
   -e DB_PORT=5432 \
  -e DB_NAME=${DB_NAME} \
  -e DB_USER=${DB_USER} \
  -e DB_PASSWORD=${DB_PASSWORD} \
  -e WHISPER_MODEL=${WHISPER_MODEL} \
  -e PYTHONUNBUFFERED=1 \
  -v $(pwd)/video_queue.json:/app/video_queue.json \
  -v $(pwd)/custom_videos:/app/custom_videos \
  -v $(pwd)/tmp:/app/tmp \
  -v $(pwd)/whisper-cache:/root/.cache/whisper \
  -p 8000:8000 \
  --network transcriber_app_network \
  transcription-service

echo "services started successfully!"
echo "transcription service: http://localhost:8000"
echo "database: localhost:5432" 
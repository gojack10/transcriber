#!/bin/bash

# create network if it doesn't exist
echo "creating docker network..."
docker network create transcriber_app_network 2>/dev/null || true

# start transcription service with GPU support
# first, start the database
echo "starting postgres database..."
docker run -d \
  --name transcriber-db \
  --restart unless-stopped \
  -e POSTGRES_USER=gojack10 \
  -e POSTGRES_PASSWORD=moso10 \
  -e POSTGRES_DB=transcriber_db \
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
  -e DB_NAME=transcriber_db \
  -e DB_USER=gojack10 \
  -e DB_PASSWORD=moso10 \
  -e WHISPER_MODEL=turbo \
  -e PYTHONUNBUFFERED=1 \
  -v $(pwd)/list.txt:/app/list.txt \
  -v $(pwd)/tmp:/app/tmp \
  -v $(pwd)/whisper-cache:/root/.cache/whisper \
  -p 8000:8000 \
  --network transcriber_app_network \
  transcription_test

echo "services started successfully!"
echo "transcription service: http://localhost:8000"
echo "database: localhost:5432" 
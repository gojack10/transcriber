# use an nvidia cuda runtime as a parent image
FROM nvidia/cuda:11.8.0-cudnn8-devel-ubuntu22.04

# set environment variables
ENV DB_HOST="host.docker.internal"
ENV DB_PORT="5432"
ENV DB_NAME="transcriber_db"
ENV DB_USER="gojack10"
ENV DB_PASSWORD="moso10"
ENV WHISPER_MODEL="base.en"
ENV PYTHONUNBUFFERED=1
# nvidia container toolkit environment variables
ENV NVIDIA_VISIBLE_DEVICES all
ENV NVIDIA_DRIVER_CAPABILITIES compute,utility
ENV LANG C.UTF-8
ENV LC_ALL C.UTF-8

# set the working directory in the container
WORKDIR /app

# install python 3.10 and other dependencies
RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    python3.10 \
    python3-pip \
    python3.10-venv \
    ffmpeg \
    git \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

# link python3 to python3.10
RUN ln -sf /usr/bin/python3.10 /usr/bin/python3 && \
    ln -sf /usr/bin/pip3 /usr/bin/pip

# copy the dependencies file to the working directory
COPY requirements.txt .

# install pytorch with cuda support first, then the rest of requirements
# ensure this torch version is compatible with whisper and cuda 11.8
# check whisper's torch dependency if issues arise
RUN pip install --no-cache-dir torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir yt-dlp

# copy the current directory contents into the container at /app
COPY . .

# make port 8000 available to the world outside this container
EXPOSE 8000

# define the command to run your app using uvicorn
CMD ["uvicorn", "transcriber:app", "--host", "0.0.0.0", "--port", "8000"] 
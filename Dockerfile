# use an nvidia cuda runtime as a parent image
FROM nvidia/cuda:12.1.1-cudnn8-devel-ubuntu22.04

# set environment variables (fixing legacy format warnings)
ENV DB_HOST="host.docker.internal"
ENV DB_PORT="5432"
ENV DB_NAME="transcriber_db"
ENV DB_USER="gojack10"
ENV DB_PASSWORD="moso10"
ENV WHISPER_MODEL="base.en"
ENV PYTHONUNBUFFERED=1
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8

# set the working directory in the container
WORKDIR /app

# Configure apt to use different mirrors and fix network issues
RUN echo "deb http://mirrors.kernel.org/ubuntu jammy main restricted universe multiverse" > /etc/apt/sources.list && \
    echo "deb http://mirrors.kernel.org/ubuntu jammy-updates main restricted universe multiverse" >> /etc/apt/sources.list && \
    echo "deb http://mirrors.kernel.org/ubuntu jammy-security main restricted universe multiverse" >> /etc/apt/sources.list && \
    echo "deb http://mirrors.kernel.org/ubuntu jammy-backports main restricted universe multiverse" >> /etc/apt/sources.list

# install python and other dependencies (Ubuntu 22.04 comes with Python 3.10 by default)
RUN apt-get update --fix-missing && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
    python3-dev \
    ffmpeg \
    git \
    tzdata \
    curl \
    wget \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# create symbolic links for python
RUN ln -sf /usr/bin/python3 /usr/bin/python && \
    ln -sf /usr/bin/pip3 /usr/bin/pip

# copy the dependencies file to the working directory
COPY requirements.txt .

# install pytorch with cuda support first, then the rest of requirements
# ensure this torch version is compatible with whisper and cuda 11.8
# check whisper's torch dependency if issues arise
RUN pip install --no-cache-dir torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir yt-dlp

# copy the current directory contents into the container at /app
COPY . .

# make port 8000 available to the world outside this container
EXPOSE 8000

# define the command to run your app using uvicorn
CMD ["uvicorn", "transcriber:app", "--host", "0.0.0.0", "--port", "8000"] 
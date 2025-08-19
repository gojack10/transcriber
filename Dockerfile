# use cuda 12.8 base image to match your environment
FROM nvidia/cuda:12.8.0-cudnn-devel-ubuntu22.04

# set non-interactive mode for apt
ENV DEBIAN_FRONTEND=noninteractive

# install python 3.12 and system dependencies
RUN apt-get update && apt-get install -y \
    software-properties-common \
    && add-apt-repository ppa:deadsnakes/ppa \
    && apt-get update && apt-get install -y \
    python3.12 \
    python3.12-venv \
    python3.12-dev \
    ffmpeg \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# install pip for python 3.12 using get-pip.py
RUN curl -sS https://bootstrap.pypa.io/get-pip.py | python3.12

# set python3.12 as default python
RUN update-alternatives --install /usr/bin/python python /usr/bin/python3.12 1
RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.12 1

WORKDIR /app

# create a virtual environment to isolate from system packages
RUN python3.12 -m venv /app/venv
ENV PATH="/app/venv/bin:$PATH"

# copy requirements with exact versions from your working venv
COPY requirements-docker.txt requirements.txt

# install exact package versions in the venv (this recreates your venv exactly)
RUN pip install --no-cache-dir -r requirements.txt

# install yt-dlp normally, then update it using yt-dlp -U
RUN pip install --no-cache-dir yt-dlp && yt-dlp -U

# copy application code
COPY . .

# create necessary directories
RUN mkdir -p .temp .stats whisper-cache

# expose port
EXPOSE 8080

# run the application
CMD ["python", "server/run_server.py"]

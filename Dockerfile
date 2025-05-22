# use an official python runtime as a parent image
FROM python:3.10-slim

# set environment variables for database connection (defaults)
# these can be overridden at docker run time
ENV DB_HOST="host.docker.internal"
ENV DB_PORT="5432"
ENV DB_NAME="transcriber_db"
ENV DB_USER="gojack10"
ENV DB_PASSWORD="moso10"
ENV WHISPER_MODEL="base.en" 
ENV PYTHONUNBUFFERED=1 

# set the working directory in the container
WORKDIR /app

# copy the dependencies file to the working directory
COPY requirements.txt .

# install any needed packages specified in requirements.txt
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    git \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir -r requirements.txt

# copy the current directory contents into the container at /app
COPY . .

# make port 8000 available to the world outside this container
EXPOSE 8000

# define the command to run your app using uvicorn
# this will run the fastapi app defined in transcriber.py
# ensure transcriber.py calls uvicorn.run() or is runnable by uvicorn transcriber:app
CMD ["uvicorn", "transcriber:app", "--host", "0.0.0.0", "--port", "8000"] 
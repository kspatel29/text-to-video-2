# Use Python 3.9 slim image as base
FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Install system dependencies required for video processing and building Python packages
RUN apt-get update && apt-get install -y \
    ffmpeg \
    build-essential \
    gcc \
    g++ \
    make \
    pkg-config \
    libcairo2-dev \
    libgirepository1.0-dev \
    libpango1.0-dev \
    libgdk-pixbuf2.0-dev \
    libglib2.0-dev \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Verify compilers are installed
RUN gcc --version && g++ --version

# Copy requirements file
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Create directory for video outputs
RUN mkdir -p outputs

# Expose port (Azure will override this with WEBSITES_PORT)
EXPOSE 5000

# Set environment variables for Flask
ENV FLASK_APP=server.py
ENV FLASK_ENV=production

# Create a startup script that handles Azure's port requirements
RUN echo '#!/bin/bash\n\
PORT=${WEBSITES_PORT:-5000}\n\
echo "Starting Flask app on port $PORT"\n\
python server.py --port $PORT\n\
' > /app/start.sh && chmod +x /app/start.sh

# Use the startup script
CMD ["/app/start.sh"]
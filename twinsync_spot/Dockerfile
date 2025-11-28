ARG BUILD_FROM
FROM ${BUILD_FROM}

# Install dependencies
RUN apk add --no-cache \
    gcc \
    musl-dev \
    libffi-dev \
    openssl-dev \
    ffmpeg

# Set working directory
WORKDIR /app

# Copy requirements first for caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY app/ ./app/
COPY run.sh /run.sh

# Make run script executable
RUN chmod a+x /run.sh

# Create data directory
RUN mkdir -p /data

# Expose port
EXPOSE 8099

# Run
CMD ["/run.sh"]

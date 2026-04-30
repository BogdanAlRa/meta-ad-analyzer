FROM apify/actor-python:3.12

# Install ffmpeg for video/audio processing
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# Install playwright browsers
RUN pip install playwright && playwright install chromium && playwright install-deps chromium

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . ./

CMD ["python3", "-m", "src.main"]

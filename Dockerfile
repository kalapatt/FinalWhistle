FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for scipy/xgboost
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app
COPY . .

CMD ["python", "live_updater.py"]

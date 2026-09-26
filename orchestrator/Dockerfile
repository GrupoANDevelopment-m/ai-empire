FROM python:3.11-slim

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl gcc g++ \
    && rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App
COPY . .

EXPOSE 8123

# Dev mode: hot reload via watchfiles
CMD ["uvicorn", "web.server:app", "--host", "0.0.0.0", "--port", "8123", "--reload", "--log-level", "info"]

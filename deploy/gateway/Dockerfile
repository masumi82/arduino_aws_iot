FROM python:3.11-slim

WORKDIR /app

# build context must be repo root (docker build -f deploy/gateway/Dockerfile .)
COPY gateway/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY gateway/ .

CMD ["python", "main.py"]

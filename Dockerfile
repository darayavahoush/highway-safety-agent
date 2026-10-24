FROM node:20-bookworm-slim AS frontend-builder

WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install OCR binary and English language model inside the Docker image.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng \
    && tesseract --version \
    && tesseract --list-langs \
    && tesseract --list-langs | grep -qx eng \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Re-verify OCR at runtime, then start the existing FastAPI application.
CMD ["sh", "-c", "tesseract --version && tesseract --list-langs && exec python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-10000}"]

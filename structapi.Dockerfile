# structapi — deterministic IS-code design API (no eve/node inside).
# Build:  docker build -f structapi.Dockerfile -t structapi:latest .
# Run:    docker run -p 8080:8080 -e STRUCTAPI_KEYS=<key> structapi:latest
# Cloud Run: deploy this image; set STRUCTAPI_KEYS via Secret Manager.
FROM python:3.12-slim

WORKDIR /app
COPY python/requirements.txt python/requirements-api.txt ./
RUN pip install --no-cache-dir -r requirements-api.txt

COPY python/iscodes ./iscodes
COPY python/structapi ./structapi

ENV MPLBACKEND=Agg PYTHONUNBUFFERED=1 PORT=8080
EXPOSE 8080
CMD ["sh", "-c", "uvicorn structapi.main:app --host 0.0.0.0 --port ${PORT}"]

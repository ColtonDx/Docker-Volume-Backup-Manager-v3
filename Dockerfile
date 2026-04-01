# ── Stage 1: Build frontend ──────────────────────────────────────────────────
FROM node:20-alpine AS frontend-build
WORKDIR /app
COPY package.json bun.lockb ./
RUN npm install
COPY index.html vite.config.ts tsconfig*.json tailwind.config.ts postcss.config.js components.json ./
COPY VERSION .
COPY public/ public/
COPY src/ src/
RUN npm run build

# ── Stage 2: Python backend ─────────────────────────────────────────────────
FROM python:3.12-slim

# Install rclone (optional) and libsqlcipher-dev (required for sqlcipher3 at-rest encryption).
# Note: libsqlcipher-dev is NOT purged — its .so is needed at runtime.
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl unzip libsqlcipher-dev && \
    curl -fsSL https://rclone.org/install.sh | bash || true && \
    apt-get purge -y curl unzip && \
    apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY backend/app/ app/

# Copy startup script (generates TLS cert if needed, then launches uvicorn)
COPY backend/start.py .

# Copy VERSION file for runtime version display
COPY VERSION .

# Copy built frontend into static dir served by FastAPI
COPY --from=frontend-build /app/dist /app/static

# Data directory for SQLite + temp backups
RUN mkdir -p /data /backups
ENV DATA_DIR=/data
ENV BACKUP_TEMP_DIR=/backups

EXPOSE 8000

CMD ["python", "start.py"]

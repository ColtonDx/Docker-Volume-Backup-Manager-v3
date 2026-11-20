# ── Stage 1: Build frontend ──────────────────────────────────────────────────
FROM node:22-alpine AS frontend-build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY index.html vite.config.ts tsconfig*.json tailwind.config.ts postcss.config.js components.json ./
COPY VERSION .
COPY public/ public/
COPY src/ src/
RUN npm run build

# ── Stage 2: Python backend ─────────────────────────────────────────────────
FROM python:3.12-slim

# Install rclone (pinned release, verified against its published SHA256) and
# libsqlcipher-dev (required for sqlcipher3 at-rest encryption).
# Note: libsqlcipher-dev is NOT purged — its .so is needed at runtime.
# RCLONE_VERSION is unset for the in-build smoke test because rclone reads it as an env var (--version).
# Checksums come from https://github.com/rclone/rclone/releases/download/v${RCLONE_VERSION}/SHA256SUMS
ARG RCLONE_VERSION=1.76.0
ARG RCLONE_SHA256_AMD64=b00f00b3266c3764413afe599d3ec316f6f43b3e0ea8a0bc1d186d2133e46df7
ARG RCLONE_SHA256_ARM64=ee169016675e23a69d77240565133ff7dbc9b33d16fa8f7053d4af39f1eaeb78
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends curl unzip ca-certificates libsqlcipher-dev; \
    case "$(dpkg --print-architecture)" in \
        amd64) rclone_arch=amd64; rclone_sha256="${RCLONE_SHA256_AMD64}" ;; \
        arm64) rclone_arch=arm64; rclone_sha256="${RCLONE_SHA256_ARM64}" ;; \
        *) echo "Unsupported architecture for rclone: $(dpkg --print-architecture)" >&2; exit 1 ;; \
    esac; \
    zip="rclone-v${RCLONE_VERSION}-linux-${rclone_arch}.zip"; \
    curl -fsSL -o "/tmp/${zip}" "https://github.com/rclone/rclone/releases/download/v${RCLONE_VERSION}/${zip}"; \
    echo "${rclone_sha256}  /tmp/${zip}" | sha256sum -c -; \
    unzip -j "/tmp/${zip}" "rclone-v${RCLONE_VERSION}-linux-${rclone_arch}/rclone" -d /usr/bin; \
    chmod 0755 /usr/bin/rclone; \
    rm -f "/tmp/${zip}"; \
    env -u RCLONE_VERSION rclone version; \
    apt-get purge -y curl unzip; \
    apt-get autoremove -y; \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python dependencies
COPY backend/requirements.txt .
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc && \
    pip install --no-cache-dir -r requirements.txt && \
    apt-get purge -y gcc && \
    apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/*

# Copy backend code
COPY backend/app/ app/

# Copy startup script (generates TLS cert if needed, then launches uvicorn)
COPY backend/start.py .

# Container healthcheck (probes /health over https self-signed, then http)
COPY backend/healthcheck.py .
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "healthcheck.py"]

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

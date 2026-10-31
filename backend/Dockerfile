FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install dependencies in their own layer, before copying the code, so a code
# change doesn't trigger a full reinstall. requirements.lock pins every
# package, including transitive ones, so each build gets identical versions.
COPY requirements.lock .
RUN pip install -r requirements.lock

# The code stays owned by root, and the app runs as an unprivileged user. If
# the app were compromised, the attacker couldn't modify the code or act as
# root inside the container.
RUN useradd --create-home --uid 10001 appuser
# The upload folder is the one place the app may write. A new Docker volume
# mounted here copies this ownership, so appuser can write to it.
RUN mkdir -p /data/uploads && chown appuser:appuser /data/uploads
COPY alembic.ini entrypoint.sh ./
COPY migrations ./migrations
COPY app ./app
RUN chmod 755 entrypoint.sh
USER appuser

EXPOSE 8000
ENTRYPOINT ["./entrypoint.sh"]

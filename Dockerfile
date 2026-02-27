# syntax=docker/dockerfile:1

# Use the official UV Python base image with Python 3.13 on Debian Bookworm
# UV is a fast Python package manager that provides better performance than pip
# We use the slim variant to keep the image size smaller while still having essential tools
ARG PYTHON_VERSION=3.13
FROM ghcr.io/astral-sh/uv:python${PYTHON_VERSION}-bookworm-slim AS base

# Keeps Python from buffering stdout and stderr to avoid situations where
# the application crashes without emitting any logs due to buffering.
ENV PYTHONUNBUFFERED=1

# Create a non-privileged user that the app will run under.
# See https://docs.docker.com/develop/develop-images/dockerfile_best-practices/#user
ARG UID=10001
RUN adduser \
    --disabled-password \
    --gecos "" \
    --home "/app" \
    --shell "/sbin/nologin" \
    --uid "${UID}" \
    appuser

# Install build dependencies required for Python packages with native extensions
# gcc: C compiler needed for building Python packages with C extensions
# python3-dev: Python development headers needed for compilation
# We clean up the apt cache after installation to keep the image size down
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    python3-dev \
  && rm -rf /var/lib/apt/lists/*

# Create a new directory for our application code
# And set it as the working directory
WORKDIR /app

# Copy just the dependency files first, for more efficient layer caching
COPY --chown=appuser:appuser pyproject.toml uv.lock ./
RUN mkdir -p src && chown -R appuser:appuser /app

# Install Python dependencies using UV's lock file
# --locked ensures we use exact versions from uv.lock for reproducible builds
# This creates a virtual environment and installs all dependencies
# Ensure your uv.lock file is checked in for consistency across environments
# Switch to appuser before installing to avoid needing chown later
USER appuser
RUN uv sync --locked

# Switch back to root to copy files, then set ownership
USER root

# Copy all remaining application files into the container
# This includes source code, configuration files, and dependency specifications
# (Excludes files specified in .dockerignore)
# Using --chown to set ownership during copy (much faster than chown -R later)
COPY --chown=appuser:appuser . .

# Switch to the non-privileged user for all subsequent operations
# This improves security by not running as root
USER appuser

# Pre-download any ML models or files the agent needs
# This ensures the container is ready to run immediately without downloading
# dependencies at runtime, which improves startup time and reliability
RUN uv run src/agent.py download-files

# Run the application using UV
# UV will activate the virtual environment and run the agent.
# The "start" command tells the worker to connect to LiveKit and begin waiting for jobs.
CMD ["uv", "run", "src/agent.py", "start"]

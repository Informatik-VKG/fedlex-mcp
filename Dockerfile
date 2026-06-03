# Multi-stage build for the Streamable-HTTP (cloud) deployment (SCALE-004).
# Stage 1 builds a wheel, stage 2 is a minimal non-root runtime image.

FROM python:3.12-slim AS builder
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir build && python -m build --wheel

FROM python:3.12-slim AS runtime
# Non-root user (UID >= 10000 per SEC-007 hardening guidance).
RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin appuser
COPY --from=builder /app/dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl && rm -f /tmp/*.whl

# Container runs HTTP transport, bound to all interfaces *inside the container*
# (0.0.0.0 only here, never as a code default — SEC-016).
ENV FEDLEX_TRANSPORT=streamable-http \
    FEDLEX_HOST=0.0.0.0 \
    PORT=8000
EXPOSE 8000
USER 10001

# Liveness: the TCP port accepts connections.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import os,socket; socket.create_connection(('127.0.0.1', int(os.environ.get('PORT','8000'))), 3)" || exit 1

# Use the module entrypoint (not the console script) so the env-driven
# transport selection in __main__ takes effect.
CMD ["python", "-m", "fedlex_mcp.server"]

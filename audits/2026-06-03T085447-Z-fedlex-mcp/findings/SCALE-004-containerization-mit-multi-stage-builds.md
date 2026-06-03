## Finding: SCALE-004 — Containerization mit Multi-Stage-Builds

**Severity:** medium
**Status:** Open
**Server:** fedlex-mcp
**Check-Reference:** SCALE-004
**PDF-Reference:** Sec 5.3
**Verifikations-Status:** fail

### Observed Behavior

- Cloud-deployed (Render), aber kein Dockerfile im Repo

### Gaps / Abweichung vom Standard

- Keine Multi-Stage-Containerisierung
- Kein non-root USER, kein HEALTHCHECK

### Risk Description

Container-Images für MCP-Server sind oft 800 MB – 1.5 GB gross, weil Build-Toolchains (gcc, Rust, npm-build-deps) im finalen Image bleiben. Multi-Stage-Builds trennen Build und Runtime: das finale Image enthält nur den fertigen Server plus minimale Runtime-Dependencies (typischerweise 80–150 MB). Vorteile über Image-Grösse hinaus: kleinere Angriffsfläche (kein gcc, kein curl, keine Test-Tools im Production-Image), schnellere Pull-Zeiten (relevant bei Auto-Scaling), weniger CVE-Treffer im Container-Scan.

### Remediation

```diff
- FROM python:3.11
- WORKDIR /app
- COPY . .
- RUN pip install -e .
- CMD ["python", "-m", "server"]
+ FROM python:3.11-slim AS builder
+ WORKDIR /build
+ COPY pyproject.toml .
+ COPY src/ ./src/
+ RUN pip install --no-cache-dir --user -e .
+
+ FROM python:3.11-slim AS runtime
+ COPY --from=builder /root/.local /root/.local
+ COPY src/ /app/src/
+ WORKDIR /app
+ ENV PATH=/root/.local/bin:$PATH PYTHONUNBUFFERED=1
+ USER nobody
+ HEALTHCHECK CMD curl -f http://localhost:8000/healthz || exit 1
+ CMD ["python", "-m", "server"]
```

### Effort Estimate

S — < 1 Tag.

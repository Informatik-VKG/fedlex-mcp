## Finding: OBS-006 — OpenTelemetry Distributed Tracing pro Tool-Call

**Severity:** medium
**Status:** Open
**Server:** fedlex-mcp
**Check-Reference:** OBS-006
**PDF-Reference:** Anhang B10
**Verifikations-Status:** fail

### Observed Behavior

- Kein OpenTelemetry SDK, kein Tracing

### Gaps / Abweichung vom Standard

- Kein TracerProvider/OTLP-Exporter
- Keine Span-Instrumentierung pro Tool-Call

### Risk Description

OBS-005 deckt Audit-Logs für SIEM-Integration ab — Security-fokussiert. OBS-006 ergänzt das auf der **Performance- und Behavior-Seite**: jeder Tool-Call wird als OpenTelemetry-Span erfasst, mit: - **Trace-ID** über die ganze LLM-Host → Gateway → Server → Backend-Kette - **Tool-Name** als Span-Name - **User-Identity** als Span-Attribut (aus `ctx.user_claims`) - **Latenz** der einzelnen Hop-Schritte - **Token-Count** falls Sampling involviert - **Backend-API-Latenzen** als Child-Spans Dieser Check ist `medium`, weil ohne Tracing zwar der Server funktioniert, aber drei wichtige Forensik- und …

### Remediation

### Schritt 1: SDK-Installation

```toml
# pyproject.toml
[project.dependencies]
"opentelemetry-api" = "^1.21"
"opentelemetry-sdk" = "^1.21"
"opentelemetry-exporter-otlp" = "^1.21"
"opentelemetry-instrumentation-httpx" = "^0.42b0"
```

### Schritt 2: Setup-Modul

```python
# src/server_name/observability.py
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.resources import Resource
# ...

def setup_tracing():
    resource = Resource.create({
        "service.name": os.environ.get("OTEL_SERVICE_NAME", "schulamt-mcp"),
        "deployment.environment": os.environ.get("ENVIRONMENT", "development"),
    })
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)
    HTTPXClientInstrumentor().instrument()
```

### Schritt 3: Decorator anwenden

`@traced_tool` als Standard auf alle Tool-Decorators stacken.

### Schritt 4: OTLP-Backend wählen

Für Schulamt-Kontext: Datadog (DSG-konform mit `DD_SITE=datadoghq.eu`), Grafana Tempo (selbst-gehostet, OpenBao-Compatible), oder Honeycomb (EU-Region).

### Effort Estimate

M — 1–3 Tage. SDK-Setup + Decorator + Backend-Konfiguration + Tests.

## Finding: OBS-003 — Structured Logging mit RFC 5424 Severity-Stufen

**Severity:** medium
**Status:** Open
**Server:** fedlex-mcp
**Check-Reference:** OBS-003
**PDF-Reference:** Sec 6.3
**Verifikations-Status:** fail

### Observed Behavior

- Keinerlei Logging im Code (kein logger/structlog/loguru), nicht in dependencies

### Gaps / Abweichung vom Standard

- Kein Structured Logger
- Keine RFC-5424-Severity-Stufen
- Kein bound context pro Tool-Call

### Risk Description

MCP-Server-Logs müssen strukturiert sein (JSON oder logfmt), nicht plaintext. Das ermöglicht Aggregation in Datadog/Splunk/Loki ohne Regex-Parsing, korrelierte Suche über Correlation-IDs, und konsistente Severity-Filterung. Der MCP-Standard nutzt RFC 5424's 8 Severity-Stufen: `debug`, `info`, `notice`, `warning`, `error`, `critical`, `alert`, `emergency`. Über das `notifications/message`-Event können Logs auch an den Client weitergereicht werden — der Client kann via `logging/setLevel` dynamisch filtern. Für Python ist `structlog` der Standard, für TypeScript `pino`.

### Remediation

```diff
- import logging
- logger = logging.getLogger(__name__)
+ import structlog
+ logger = structlog.get_logger("mcp.server")

  @mcp.tool()
  async def search(query: str, ctx):
-     logger.info(f"Searching for {query}")
-     result = await api.search(query)
-     logger.info(f"Got {len(result)} results")
+     log = logger.bind(tool="search", query=query, session=ctx.session_id)
+     log.info("tool_invoked")
+     result = await api.search(query)
+     log.info("tool_succeeded", count=len(result))
      return result
```

### Effort Estimate

S — < 1 Tag pro Server.

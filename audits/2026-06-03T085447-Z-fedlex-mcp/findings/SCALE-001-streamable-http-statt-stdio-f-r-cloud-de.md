## Finding: SCALE-001 — Streamable HTTP statt stdio für Cloud-Deployments

**Severity:** high
**Status:** Open
**Server:** fedlex-mcp
**Check-Reference:** SCALE-001
**PDF-Reference:** Sec 5.1
**Verifikations-Status:** partial

### Observed Behavior

- Cloud nutzt streamable-http (server.py:882), keine WebSocket-Implementierung

### Gaps / Abweichung vom Standard

- Transport-Selektion via CLI-Flag --http statt ENV-Var

### Risk Description

stdio-Transport ist für lokale Single-User-Sessions konzipiert: ein Subprozess, eine Stdin/Stdout-Pipe, ein Client. Cloud-Deployments mit Multi-User-Zugriff können stdio nicht sinnvoll bedienen — der TCP-Bruch killt die Pipe, kein Failover möglich. Streamable HTTP / SSE sind die Cloud-Standards 2026; sie unterstützen Reconnect via Event-IDs, Multi-User, Standard-HTTP-Infrastruktur. WebSocket-Implementierungen sind veraltet. Symptom bei Fehlkonfiguration: Server startet, Health-Check grün, aber Client-Verbindungen schlagen fehl. Häufig übersehen, weil viele Tutorials `transport="stdio"` als …

### Remediation

```diff
- mcp.run(transport="stdio")
+ transport = os.environ.get("MCP_TRANSPORT", "stdio")
+ if transport in ("sse", "streamable-http"):
+     mcp.settings.host = os.environ.get("MCP_HOST", "0.0.0.0")
+     mcp.settings.port = int(os.environ.get("MCP_PORT", "8000"))
+ mcp.run(transport=transport)
```

Plus Deployment-Config (Railway):

```toml
[deploy.environment]
MCP_TRANSPORT = "streamable-http"
MCP_HOST = "0.0.0.0"
MCP_PORT = "8000"
```

### Effort Estimate

S — < 1 Tag.

## Finding: ARCH-004 — Inversion of Control: Transport-agnostische Server-Logik

**Severity:** high
**Status:** Open
**Server:** fedlex-mcp
**Check-Reference:** ARCH-004
**PDF-Reference:** Sec 2.1
**Verifikations-Status:** partial

### Observed Behavior

- Dual-Transport stdio + streamable-http vorhanden (server.py:876-884)
- Tool-Handler sind transport-agnostisch: kein request./stdin-Zugriff, nur Pydantic-Params

### Gaps / Abweichung vom Standard

- Transport-Wahl via sys.argv-Flag statt ENV-Var/Pydantic-Settings
- Kein Settings-Objekt, keine lifespan-Funktion

### Risk Description

Die MCP-Spezifikation trennt strikt zwischen Data Layer (JSON-RPC 2.0, Tools/Resources/Prompts) und Transport Layer (stdio / Streamable HTTP / SSE). Der Best-Practice-Standard verlangt, dass die Geschäftslogik des Servers diese Trennung respektiert: Tool-Handler müssen **transport-agnostisch** sein. Derselbe `searchData()`-Tool-Handler muss identisch funktionieren, egal ob er via stdio (Claude Desktop) oder SSE (Cloud-Deployment) aufgerufen wird. **Warum:** 1. **Dual-Transport-Support:** Portfolio-Server müssen sowohl lokal (stdio) als auch in der Cloud (SSE) laufen. Ohne IoC braucht man zwei …

### Remediation

Migrationsweg von monolithischem Setup zu IoC:

```diff
+ from pydantic_settings import BaseSettings
+ from contextlib import asynccontextmanager
+
+ class Settings(BaseSettings):
+     transport: str = "stdio"
+     host: str = "127.0.0.1"
+     port: int = 8000
+
+ @asynccontextmanager
+ async def lifespan(server):
+     # Shared setup für alle Transports
+     server.state.http_client = httpx.AsyncClient(timeout=30)
+     try:
+         yield
+     finally:
+         await server.state.http_client.aclose()
+
- mcp = FastMCP("server")
+ settings = Settings()
+ mcp = FastMCP("server", lifespan=lifespan)

  @mcp.tool()
- async def search(query: str, request: Request):
-     ua = request.headers["User-Agent"]
-     ...
+ async def search(query: str, ctx: Context):
+     client_name = ctx.client_info.name
+     ...

  if __name__ == "__main__":
-     mcp.run(transport="stdio")
+     if settings.transport == "sse":
+         mcp.settings.host = settings.host
+         mcp.settings.port = settings.port
+     mcp.run(transport=settings.transport)
```

### Effort Estimate

M — 1–3 Tage. Refactoring der Transport-Auswahl, Migration aller `request`-Zugriffe auf `ctx`, Testing in beiden Modi.

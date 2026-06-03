## Finding: SDK-001 — FastMCP Lifespan via @asynccontextmanager + AsyncExitStack

**Severity:** high
**Status:** Open
**Server:** fedlex-mcp
**Check-Reference:** SDK-001
**PDF-Reference:** Sec 3.1
**Verifikations-Status:** fail

### Observed Behavior

- run_sparql erstellt httpx.AsyncClient pro Tool-Call (server.py:89)

### Gaps / Abweichung vom Standard

- Verletzt explizit 'Keine httpx.AsyncClient() pro Tool-Call'
- Keine @asynccontextmanager-lifespan, kein geteilter Client/Connection-Pool

### Risk Description

MCP-Server halten häufig Ressourcen, die über die einzelne Tool-Anfrage hinaus existieren: HTTP-Connection-Pools, DB-Pools, Redis-Verbindungen, gecachte Auth-Tokens, Pre-Computed-Indexes. Werden diese pro Tool-Call neu erzeugt, bricht die Performance ein. Werden sie gar nicht aufgeräumt, ergeben sich Resource-Leaks (offene TCP-Connections, dangling Cursor). FastMCP bietet das Lifespan-Pattern dafür: Eine `@asynccontextmanager`-Funktion erhält den FastMCP-Server, initialisiert Ressourcen vor dem ersten Request und räumt sie nach dem letzten Request sauber ab. Im Multi-Server-Setup (mehrere …

### Remediation

Migrationsweg:

```diff
+ from contextlib import asynccontextmanager
+ import httpx
+
+ @asynccontextmanager
+ async def lifespan(server):
+     server.state.http = httpx.AsyncClient(timeout=30)
+     try:
+         yield
+     finally:
+         await server.state.http.aclose()
+
- mcp = FastMCP("zurich-opendata")
+ mcp = FastMCP("zurich-opendata", lifespan=lifespan)

  @mcp.tool()
- async def search(query: str):
-     async with httpx.AsyncClient() as client:
-         return (await client.get(f"https://api/{query}")).json()
+ async def search(query: str, ctx):
+     return (await ctx.fastmcp.state.http.get(f"https://api/{query}")).json()
```

### Effort Estimate

S — < 1 Tag. Lifespan-Block + Tool-Refactoring + Tests.

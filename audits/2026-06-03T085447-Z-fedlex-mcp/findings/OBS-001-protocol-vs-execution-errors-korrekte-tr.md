## Finding: OBS-001 — Protocol vs. Execution Errors: korrekte Trennung

**Severity:** high
**Status:** Open
**Server:** fedlex-mcp
**Check-Reference:** OBS-001
**PDF-Reference:** Sec 6.1
**Verifikations-Status:** partial

### Observed Behavior

- handle_error faengt httpx-Fehler ab und liefert handlungsweisende Meldungen (server.py:118-136)

### Gaps / Abweichung vom Standard

- Execution-Errors werden als Plain-String zurueckgegeben, nicht als isError:true Tool-Result
- Keine Tests fuer Execution- bzw. Protocol-Error-Pfade

### Risk Description

Die MCP-Spezifikation fordert eine strikte Trennung zwischen zwei Fehler-Typen. Werden sie verwechselt, kann das LLM den Fehler nicht korrekt interpretieren und bricht in eine Halluzinations- oder Sackgassen-Schleife. | Fehler-Typ | Beispiele | Format | |---|---|---| | **Protocol Error** | Tool existiert nicht, Schema-Mismatch, JSON-Parsing-Fehler, interner Server-Crash beim Routing | Standard JSON-RPC Error Response (`{"jsonrpc": "2.0", "error": {...}}`) | | **Execution Error** | API-Ratenlimit, Datei nicht gefunden, ungültige Geschäfts-Parameter, Drittanbieter-API down | Tool-Result mit …

### Remediation

```diff
+ from mcp.types import TextContent
+
  @mcp.tool()
  async def query_database(query: str) -> dict:
-     # FAIL: alle Exceptions werden zu JSON-RPC-Errors
-     conn = await asyncpg.connect(DATABASE_URL)
-     return {"rows": await conn.fetch(query)}
+     try:
+         conn = await asyncpg.connect(DATABASE_URL)
+         try:
+             rows = await conn.fetch(query)
+             return {"rows": [dict(r) for r in rows]}
+         finally:
+             await conn.close()
+     except asyncpg.PostgresSyntaxError as e:
+         # Execution Error: Query-Problem ist Aufgabe des LLMs zu lösen
+         return {
+             "isError": True,
+             "content": [TextContent(
+                 type="text",
+                 text=f"SQL syntax error: {str(e)}. Try simplifying the query."
+             )],
+         }
+     except asyncpg.PostgresConnectionError:
+         # Protocol-nahe: Server ist degraded
+         raise McpError(code=-32603, message="Database temporarily unavailable")
```

### Effort Estimate

M — 1–3 Tage. Pro Tool muss der Error-Pfad reviewed werden. Bei vielen Tools (>10) entsprechend aufwändiger.

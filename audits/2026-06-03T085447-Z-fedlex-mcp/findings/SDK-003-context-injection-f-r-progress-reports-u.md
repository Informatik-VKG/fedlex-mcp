## Finding: SDK-003 — Context Injection für Progress Reports und Logging

**Severity:** medium
**Status:** Open
**Server:** fedlex-mcp
**Check-Reference:** SDK-003
**PDF-Reference:** Sec 3.1
**Verifikations-Status:** partial

### Observed Behavior

- Tools nutzen async/await korrekt

### Gaps / Abweichung vom Standard

- Kein ctx: Context-Parameter in irgendeinem Tool
- SPARQL-Calls bis 45s Timeout ohne ctx.report_progress
- Kein ctx.info/ctx.warning

### Risk Description

FastMCP bietet via `Context`-Parameter ein typsicheres Interface zu Server-Internals: Logging, Progress-Reports, Client-Info, Session-State, Sampling, Elicitation. Tools, die `ctx: Context` als Parameter deklarieren, bekommen dieses Objekt automatisch injiziert (Dependency Injection durch FastMCP). **Relevante Anwendungen:** - **Progress-Reports:** Bei lang laufenden Tools (>2s) sollte der Client Fortschritts-Events sehen — sonst Timeout oder UX-Bruch. - **Strukturiertes Logging:** `ctx.info()`, `ctx.debug()`, `ctx.warning()` werden über das MCP-Protokoll an den Client weitergeleitet …

### Remediation

Migrationsweg für ein langes Tool:

```diff
+ from mcp.server.fastmcp import Context

  @mcp.tool()
- async def export_all_records(format: str) -> dict:
-     records = await db.fetch_all()
-     for record in records:
-         await transform(record, format)
-     return {"count": len(records)}
+ async def export_all_records(format: str, ctx: Context) -> dict:
+     await ctx.info(f"Starting export in format={format}")
+     records = await db.fetch_all()
+     await ctx.info(f"Loaded {len(records)} records, transforming...")
+
+     transformed = []
+     for i, record in enumerate(records):
+         if i % 50 == 0:
+             await ctx.report_progress(
+                 progress=i,
+                 total=len(records),
+                 message=f"Transformed {i}/{len(records)}",
+             )
+         transformed.append(await transform(record, format))
+
+     await ctx.info(f"Export complete: {len(transformed)} records")
+     return {"count": len(transformed), "format": format}
```

### Effort Estimate

S — < 1 Tag. Pro Tool 10 Minuten + Tests.

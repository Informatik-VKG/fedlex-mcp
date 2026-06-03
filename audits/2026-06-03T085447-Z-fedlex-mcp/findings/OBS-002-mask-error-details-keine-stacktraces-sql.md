## Finding: OBS-002 — Mask Error Details: keine Stacktraces / SQL ans LLM

**Severity:** high
**Status:** Open
**Server:** fedlex-mcp
**Check-Reference:** OBS-002
**PDF-Reference:** Sec 6.2
**Verifikations-Status:** partial

### Observed Behavior

- handle_error gibt generische, gemappte Meldungen (kein Stacktrace)

### Gaps / Abweichung vom Standard

- FastMCP ohne mask_error_details=True initialisiert
- Fallback-Zweig f"Fehler: {type(e).__name__}: {e}" (server.py:136) kann interne Exception-Details ans LLM leaken

### Risk Description

Wenn Tool-Errors Stacktraces, SQL-Syntax, Datei-Pfade oder gar Credentials enthalten, fliesst dieser Inhalt in den LLM-Kontext und damit potentiell ins User-Sichtbare zurück. Das ist Information Disclosure: Angreifer mit User-Zugriff erfahren über provozierte Errors die Server-Architektur, DB-Schema, gemountete Pfade, sogar geleakte Tokens (z.B. in `Authorization`-Headern, die im Stacktrace landen). FastMCP bietet `mask_error_details=True`: Server-Errors werden auf eine generische Message reduziert (`"An error occurred"`), Original-Details landen nur im Server-Log. Trade-off: LLM kann nicht …

### Remediation

```diff
  mcp = FastMCP(
      "server",
+     mask_error_details=True,
  )

  @mcp.tool()
  async def search(query: str):
      try:
          return await db.search(query)
-     except Exception as e:
-         return {"error": str(e), "traceback": traceback.format_exc()}
+     except UserInputError as e:
+         return {"isError": True, "content": [
+             TextContent(type="text", text=f"Invalid input: {e.user_message}")
+         ]}
+     except Exception:
+         logger.exception("Unhandled error in search tool")
+         raise  # mask_error_details greift, generische Message ans LLM
```

### Effort Estimate

S — < 1 Tag pro Server.

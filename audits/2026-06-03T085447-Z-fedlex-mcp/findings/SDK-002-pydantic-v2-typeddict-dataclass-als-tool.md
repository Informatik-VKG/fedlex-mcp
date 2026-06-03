## Finding: SDK-002 — Pydantic v2 / TypedDict / Dataclass als Tool-Returns

**Severity:** medium
**Status:** Open
**Server:** fedlex-mcp
**Check-Reference:** SDK-002
**PDF-Reference:** Sec 3.1
**Verifikations-Status:** partial

### Observed Behavior

- Pydantic v2 als Input-Modelle mit Field-Constraints (server.py:149-217)

### Gaps / Abweichung vom Standard

- Tool-Returns sind -> str (Markdown), kein strukturierter Envelope mit source/provenance/results/count
- Keine Literal-Types fuer enumerable Status

### Risk Description

FastMCP wraps Tool-Returns automatisch in MCP-konformes Format — aber nur, wenn der Return-Typ strukturiert ist. Bei plain `dict` oder `str` muss FastMCP raten, welche Felder optional sind, welche Validierungen gelten, was passiert wenn Schema-Mismatches auftreten. Bei Pydantic-`BaseModel`, `TypedDict` oder `@dataclass` ist alles explizit und typgeprüft. Konkrete Vorteile: 1. **Automatische Schema-Generierung:** FastMCP exponiert das Output-Schema im `tools/list`-Manifest. Das LLM weiss damit, was es erwarten kann, und kann Folge-Calls präziser planen. 2. **Runtime-Validation:** Wenn der …

### Remediation

```diff
+ from pydantic import BaseModel, Field
+ from typing import Literal
+
+ class SearchResponse(BaseModel):
+     source: str = Field(default="DataSource Name — CC BY 4.0")
+     provenance: Literal["live_api", "cached", "weekly_dump"]
+     results: list[dict]
+     count: int

  @mcp.tool()
- async def search(query: str):
-     results = await api.search(query)
-     return {"results": results, "count": len(results)}
+ async def search(query: str, ctx) -> SearchResponse:
+     results = await api.search(query)
+     return SearchResponse(
+         provenance="live_api",
+         results=results,
+         count=len(results),
+     )
```

### Effort Estimate

S — < 1 Tag. Pro Tool 5–15 Minuten Refactoring + Tests.

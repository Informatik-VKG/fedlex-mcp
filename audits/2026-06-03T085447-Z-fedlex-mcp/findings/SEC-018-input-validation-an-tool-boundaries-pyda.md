## Finding: SEC-018 — Input-Validation an Tool-Boundaries (Pydantic strict / Zod)

**Severity:** high
**Status:** Open
**Server:** fedlex-mcp
**Check-Reference:** SEC-018
**PDF-Reference:** Sec 3 / Sec 4 (Defense-in-Depth)
**Verifikations-Status:** partial

### Observed Behavior

- Alle Tool-Args via Pydantic mit min/max_length, ge/le, extra=forbid (server.py:149-217)

### Gaps / Abweichung vom Standard

- strict=True nicht gesetzt
- keywords/sr_number ohne pattern-Whitelist -> fliessen ungeescaped in SPARQL (siehe SEC-004)

### Risk Description

Tool-Argumente kommen vom LLM — einer probabilistischen Quelle, die halluzinieren, formattieren-falsch oder von Prompt-Injection beeinflusst sein kann. Ohne strikte Input-Validation am Tool-Boundary werden invalide oder bösartige Inputs in die Geschäftslogik weitergereicht und können dort: 1. **Unerwartete Exceptions** auslösen → Error-Pfad könnte Information leaken (siehe OBS-002) 2. **Type Confusion** triggern → z.B. `user_id: int` aber LLM schickt String → SQL-Coercion-Bug 3. **Range-Violations** verursachen → z.B. negative Pagination-Limits → DB-Crash oder Memory-Explosion 4. …

### Remediation

### Schritt 1: Schema pro Tool extrahieren

```diff
+ from typing import Annotated
+ from pydantic import BaseModel, Field, StringConstraints
+
+ class SearchArgs(BaseModel):
+     model_config = {"strict": True, "extra": "forbid"}
+     query: Annotated[str, StringConstraints(min_length=2, max_length=200)]
+     limit: Annotated[int, Field(ge=1, le=100)] = 10

  @mcp.tool()
- async def search(query: str, limit: int = 10) -> dict:
+ async def search(args: SearchArgs, ctx: Context) -> dict:
-     return await db.search(query, limit=limit)
+     return await db.search(args.query, limit=args.limit)
```

### Schritt 2: ValidationError sauber behandeln

```python
from pydantic import ValidationError

@mcp.tool()
async def search(args: SearchArgs, ctx: Context) -> dict:
    try:
        # Pydantic validiert beim Parsing automatisch — kein Aufruf nötig
        # Falls manuell aus dict gebaut: SearchArgs.model_validate(raw_dict)
        return await db.search(args.query, limit=args.limit)
    except ValidationError as e:
        # Wird normal nicht erreicht (FastMCP fängt das ab),
        # aber Defense-in-Depth:
        return {
            "isError": True,
            "content": [TextContent(
                type="text",
                text=f"Invalid arguments: {e.errors()[0]['msg']}"
            )],
        }
```

### Schritt 3: Tests gegen Edge-Cases

```python
@pytest.mark.parametrize("invalid_args,expected_error", [
    ({"query": "a", "limit": 10}, "min_length"),       # zu kurz
    ({"query": "x"*500, "limit": 10}, "max_length"),   # zu lang
    ({"query": "test", "limit": 0}, "greater_than_or_equal"),
    ({"query": "test", "limit": 99999}, "less_than_or_equal"),
    ({"query": "test", "limit": 10, "evil": "field"}, "extra_forbidden"),
])
async def test_search_rejects_invalid(invalid_args, expected_error):
    with pytest.raises(ValidationError) as exc:
        SearchArgs.model_validate(invalid_args)
    assert any(expected_error in err["type"] for err in exc.value.errors())
```

### Effort Estimate

S — < 1 Tag pro Server bei wenigen Tools, M bei vielen Tools (10+).

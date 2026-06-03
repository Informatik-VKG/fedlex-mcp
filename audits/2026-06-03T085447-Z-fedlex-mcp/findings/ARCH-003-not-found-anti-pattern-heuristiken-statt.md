## Finding: ARCH-003 — «Not Found» Anti-Pattern: Heuristiken statt leerer Antworten

**Severity:** medium
**Status:** Open
**Server:** fedlex-mcp
**Check-Reference:** ARCH-003
**PDF-Reference:** Sec 2.2
**Verifikations-Status:** partial

### Observed Behavior

- Leere Ergebnisse liefern handlungsweisende Tipps statt nur [] (z.B. server.py:281-288)

### Gaps / Abweichung vom Standard

- Kein match_type-Feld (exact/fuzzy/none)
- Kein Fuzzy-/Suggestion-Mechanismus bei 0 Treffern

### Risk Description

LLMs reagieren empirisch nachweisbar empfindlich auf negativ-framing in Tool-Responses. Eine Antwort wie `"No results found"` oder `[]` ohne Kontext führt häufig zu einer von zwei Failure-Modes: 1. **Halluzination:** Das Modell konstruiert eine Antwort aus Trainingsdaten, statt zuzugeben, dass es keine Information hat. 2. **Sackgasse:** Das Modell bricht die Aufgabe ab, statt mit alternativen Strategien (verwandte Begriffe, andere Tools) weiterzumachen. Der Best-Practice-Standard fordert: Wenn ein Tool keine exakten Treffer findet, soll es **partielle / heuristische / verwandte Ergebnisse** …

### Remediation

```diff
  @mcp.tool()
  async def find_school(name: str) -> list:
      results = await db.find(name)
-     if not results:
-         return []
+     if not results:
+         fuzzy = await db.find_fuzzy(name, threshold=0.7)
+         suggestions = await db.popular_school_names_starting_with(name[:3])
+         return {
+             "results": fuzzy[:5],
+             "match_type": "fuzzy" if fuzzy else "none",
+             "note": (
+                 f"Keine exakten Treffer für '{name}'. "
+                 f"{'Ähnliche Schulen aufgeführt.' if fuzzy else ''} "
+                 f"Häufige Schulnamen: {', '.join(suggestions[:5])}"
+             ),
+         }
      return {"results": results, "match_type": "exact"}
```

### Effort Estimate

S — Pro Tool ~30 Minuten. Bei 10 Such-Tools: 1 Tag.

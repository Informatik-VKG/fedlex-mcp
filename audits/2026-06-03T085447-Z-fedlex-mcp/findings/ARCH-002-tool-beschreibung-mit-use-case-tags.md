## Finding: ARCH-002 — Tool-Beschreibung mit Use-Case-Tags

**Severity:** medium
**Status:** Open
**Server:** fedlex-mcp
**Check-Reference:** ARCH-002
**PDF-Reference:** Sec 2.2
**Verifikations-Status:** partial

### Observed Behavior

- Tool-Docstrings > 100 Zeichen, mit Args/Returns/Use-Case-Prosa

### Gaps / Abweichung vom Standard

- Keine strukturierten <use_case>/<important_notes>/<example>-Tags (0 Treffer)
- Beschreibungskontext steckt nur im Python-Docstring, nicht in description=

### Risk Description

LLMs wählen Tools nicht über exakte Namens-Treffer, sondern über semantische Embeddings der Tool-Beschreibung. Eine Beschreibung wie `"Searches database"` lässt das Modell zwischen drei `getX`-Tools rätseln. Eine Beschreibung mit explizitem Use-Case-Tag, Trigger-Phrasen und Negativ-Hinweisen («NICHT verwenden für…») reduziert Halluzinationen drastisch. Die Best-Practice-Konvention im PDF nutzt XML-artige Tags innerhalb der Description: - `<use_case>` — Wann soll das Tool verwendet werden? - `<important_notes>` — Caveats, Side-Effects, Limitierungen - `<example>` — Konkrete Beispiel-Inputs Das …

### Remediation

```diff
  @mcp.tool(
      name="searchEducationStats",
-     description="Search education statistics."
+     description=(
+         "Sucht in den städtischen Bildungsstatistiken nach Kennzahlen "
+         "(Klassengrösse, Lehrer-Schüler-Verhältnis, Anteil DaZ, etc.).\n\n"
+         "<use_case>Politische / journalistische Recherche, "
+         "Schulamts-interne Reportings, Pädagogik-Analysen.</use_case>\n\n"
+         "<important_notes>Daten werden quartalsweise aktualisiert. "
+         "Personendaten sind nicht abrufbar — nur aggregierte "
+         "Kennzahlen.</important_notes>"
+     ),
  )
```

### Effort Estimate

S — Pro Tool 5–10 Minuten. Bei 10 Tools: ~1 Tag.

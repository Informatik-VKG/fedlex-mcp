## Finding: OPS-003 — Phasenarchitektur: Read-only First, dann Write, dann Multi-Agent

**Severity:** high
**Status:** Open
**Server:** fedlex-mcp
**Check-Reference:** OPS-003
**PDF-Reference:** Anhang C4
**Verifikations-Status:** partial

### Observed Behavior

- Tools sind durchgaengig read-only (entspricht implizit Phase 1)

### Gaps / Abweichung vom Standard

- Keine explizite Phasen-Deklaration im README
- Kein Roadmap-File

### Risk Description

Der Anhang sagt klar: «Die häufigste Ursache von MCP-Sicherheitsvorfällen 2025/26 war: ‹Wir haben gleich Schreibzugriffe gebaut, weil es ging.›» Disziplin: jeder Server durchläuft drei Phasen. Übersprungene Phasen produzieren Sicherheits- und Compliance-Vorfälle. | Phase | Dauer | Zustand | Was wird gebaut | Was darf NICHT | |---|---|---|---|---| | **Phase 1** | Wochen | Read-only-Wrapper | Tools mit `readOnlyHint: true`, OAuth, Gateway davor, Doku, Tests | Kein Write, keine Compensating Actions, kein Multi-Agent | | **Phase 2** | Monate | Anreicherung | Semantic Layer, Identity Resolution, …

### Remediation

### Schritt 1: Phase-Audit pro Server

Pro Server im Portfolio:

| Frage | Antwort |
|---|---|
| Hat der Server destruktive Tools? | ja → mindestens Phase 3 |
| Hat der Server Semantic Layer / Federation? | ja → mindestens Phase 2 |
| Sonst | Phase 1 |

### Schritt 2: Phase-Sektion ins README

Mit Status-Tabelle wie im Pass-Pattern Modus 1.

### Schritt 3: Roadmap erstellen

Mit Phase-Voraussetzungen als Tasks. Falls aktueller Server in Phase 2 oder 3 ist und Phase-1-Voraussetzungen fehlen: Findings im Audit-Tracker dokumentieren, retroaktiv schliessen.

### Schritt 4: Phase-Gate als Notion-Workflow

In Notion-Audit-Tracker-Schema (`a2736a65-...`) ein Feld «Phase» (Single-Select: 1, 2, 3) mit klaren Übergangs-Anforderungen.

### Effort Estimate

S — < 1 Tag pro Server für Initial-Phase-Deklaration. M — Wochen für Phase-Übergänge mit allen Compensating-Action-Anforderungen.

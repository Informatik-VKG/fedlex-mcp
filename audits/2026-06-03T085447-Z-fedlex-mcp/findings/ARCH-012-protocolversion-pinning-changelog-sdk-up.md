## Finding: ARCH-012 — protocolVersion-Pinning + CHANGELOG + SDK-Update-Disziplin

**Severity:** medium
**Status:** Open
**Server:** fedlex-mcp
**Check-Reference:** ARCH-012
**PDF-Reference:** Anhang A9
**Verifikations-Status:** partial

### Observed Behavior

- CHANGELOG.md vorhanden

### Gaps / Abweichung vom Standard

- protocolVersion nicht explizit gepinnt
- Keine README-Sektion MCP Protocol Version
- Kein Dependabot/Renovate fuer SDK-Updates

### Risk Description

Die MCP-Spec hat in 13 Monaten vier Major-Updates erlebt (2024-11, 2025-03, 2025-06, 2025-11). Das ist eine ungewöhnlich hohe Velocity für einen Industriestandard. Konkrete Folgen für Server-Maintainer: 1. **Tool Annotations** kamen erst 2025-03-26 2. **OAuth Resource Server** mit RFC 8707 wurde erst 2025-06-18 verpflichtend 3. **WebSocket-Transport** wurde 2025-03 abgeschafft, durch Streamable HTTP ersetzt Wer die `protocolVersion` als «latest» (oder gar nicht) pinnt, riskiert dass: - Ein SDK-Update auf einer neuen Spec-Version den Server bricht (Client erwartet altes Protokoll) - …

### Remediation

### Schritt 1: protocolVersion pinnen

```diff
+ from importlib.metadata import version

  mcp = FastMCP(
      name="zh-education-mcp",
+     protocol_version="2025-06-18",
  )
```

### Schritt 2: CHANGELOG initialisieren

Wenn nicht vorhanden, mit Template starten und retroaktiv Major-Versionen dokumentieren (mindestens letzte 3).

### Schritt 3: Dependabot konfigurieren

```yaml
# .github/dependabot.yml
version: 2
updates:
  - package-ecosystem: "pip"
    directory: "/"
    schedule:
      interval: "monthly"
    open-pull-requests-limit: 5
```

### Schritt 4: Quartalsweise Spec-Review

Im Audit-Tracker (Notion) oder GitHub Issues ein recurring Reminder für quartalsweise Spec-Velocity-Review:

- Was hat sich an der MCP-Spec geändert seit letztem Release?
- Welche Server müssen ihre `protocolVersion` aktualisieren?
- Gibt es Compliance-relevante Spec-Änderungen?

### Effort Estimate

S — < 1 Tag pro Server. Pinning + CHANGELOG-Template + Dependabot-Setup.

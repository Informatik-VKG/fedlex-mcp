## Finding: SEC-022 — Tool-Hash-Pinning + Namespace-Präfix gegen Rug Pull

**Severity:** high
**Status:** Open
**Server:** fedlex-mcp
**Check-Reference:** SEC-022
**PDF-Reference:** Anhang B4
**Verifikations-Status:** partial

### Observed Behavior

- Alle Tools mit konsistentem Namespace-Praefix fedlex_

### Gaps / Abweichung vom Standard

- Kein Tool-Definition-Hash-Snapshot bei Releases
- Praefix nicht als FrozenSet erzwungen

### Risk Description

SEC-015 deckt **Tool-Poisoning** ab — bösartige Inhalte in Tool-Beschreibungen beim Onboarding. SEC-022 ergänzt das um zwei verwandte Angriffsklassen: **Rug Pull:** Server registriert beim Onboarding harmlose Tool-Beschreibungen. User stimmt zu. Nach erfolgreicher Approval ändert der Server seine Tool-Beschreibungen — z.B. fügt versteckte Instruktionen hinzu, die der LLM beim nächsten Aufruf befolgt. Klassischer Bait-and-Switch. **Cross-Server Tool Shadowing:** Ein bösartiger Server registriert ein Tool mit demselben Namen wie ein vertrauenswürdiger Server (z.B. beide haben …

### Remediation

### Schritt 1: Namespace-Audit

Server-Identity festlegen — typisch der Repo-Name als snake_case-Präfix:

| Repo | Namespace |
|---|---|
| `zh-education-mcp` | `zh_education` |
| `zurich-opendata-mcp` | `zurich_opendata` |
| `parlament-mcp` | `parlament_ch` |

### Schritt 2: Tool-Renaming

```diff
- @mcp.tool()
- async def search(query: str): ...
+ @mcp.tool(name="zh_education__search")
+ async def search(query: str): ...
```

Bei Renaming: Major-Version-Bump, da Tool-Namen Breaking-Changes sind.

### Schritt 3: Hash-Snapshot-Workflow

CI-Step wie im Pass-Pattern Modus 2. `tool-hashes.json` als Artefakt im Release.

### Schritt 4: Bei Update-Disziplin (Synergie zu ARCH-012)

CHANGELOG-Template um «Tool Definition Changes»-Sektion erweitern:

```markdown

### Effort Estimate

M — 1–3 Tage pro Server. Namespace-Renaming + Hash-Workflow + CHANGELOG-Updates.

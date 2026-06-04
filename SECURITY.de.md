# Sicherheitsrichtlinie & Sicherheitslage

[:gb: English Version](SECURITY.md)

`fedlex-mcp` wurde gegen den internen MCP-Best-Practice-Audit-Katalog
gehärtet. Dieses Dokument fasst die Sicherheitslage zusammen und dokumentiert die
**akzeptierten Risiken** für Kontrollen, die bewusst auf der Portfolio-/Gateway-Ebene
statt innerhalb dieses einzelnen Servers behandelt werden.

## Schwachstelle melden

Bitte eröffnen Sie ein privates Security Advisory im GitHub-Repository oder
kontaktieren Sie die in `README.md` genannte verantwortliche Person. Erstellen Sie
für ausnutzbare Schwachstellen **keine** öffentlichen Issues.

## Zusammenfassung der Sicherheitslage

Dies ist ein **rein lesender**, **PII-freier** MCP-Server für **öffentliche Open
Data**. Alle 7 Tools stellen ausschliesslich SPARQL-SELECT-Abfragen an den
Fedlex-Endpoint (`fedlex.data.admin.ch`). Bereits umgesetzte Härtungsmassnahmen:

| Bereich | Kontrolle |
|---|---|
| Egress | HTTPS-erzwungene Allow-List ausschliesslich für `fedlex.data.admin.ch`, mit IP-Block-Validierung gegen SSRF (SEC-004/021; siehe ADR 0001) |
| TLS | Verifizierung standardmässig aktiv; nur in einer `dev`-Umgebung deaktivierbar (SEC-005) |
| Binding | Netzwerk-Transporte binden standardmässig an `127.0.0.1` (SEC-016) |
| Transport | Streamable HTTP mit CORS, das nur `Mcp-Session-Id` exponiert (SDK-004) |
| Input | Pydantic-v2-Strict-Validierung + XML-Escaping an allen Grenzen (SEC-018) |
| Secrets | Nur Umgebungsvariablen, `.gitignore` schützt `.env`, keine hartcodierten Secrets (ARCH-005/SEC-013) |
| Fehler | Upstream-Antworten werden nach stderr geloggt, niemals an das Modell weitergegeben (OBS-002) |
| Stdout | Reserviert für den JSON-RPC-Stream; Logging fest auf stderr (OBS-004) |
| Tool-Allow-List | Serverseitige Default-Deny-Allow-List über `FEDLEX_ENABLED_TOOLS` (SEC-014) |
| Tool-Integrität | SHA-256-Tool-Hash-Pinning beim Start + in CI gegen `tool-definitions.lock.json` verifiziert (SEC-022) |

Der jüngste Audit-Lauf (`2026-06-03T100302-Z-fedlex-mcp`) meldet
**produktionsreif**: 41 bestanden · 0 fehlgeschlagen · 2 partiell (nicht
blockierend) · 1 n/a. Den vollständigen Bericht finden Sie unter `audits/`, die
Härtungshistorie in `CHANGELOG.md`.

## Akzeptierte Risiken (Kontrollen auf Portfolio-Ebene)

Die folgenden Audit-Prüfungen sind **bewusst nicht** vollständig innerhalb dieses
Servers implementiert. Es handelt sich um portfolioweite Belange, die am besten auf
einer MCP-Gateway-/Host-Ebene durchgesetzt werden; das Restrisiko ist hier gering, da
der Server rein lesend ist und nur einen einzigen vertrauenswürdigen
Open-Data-Anbieter erreicht.

Diese Entscheidungen sind formell in
[ADR 0002 — Authentication & gateway posture](docs/adr/0002-auth-and-gateway-posture.md)
festgehalten, mit den nachstehenden kompensierenden Kontrollen und
Re-Evaluierungs-Auslösern.

### SEC-009 — Session-Krypto-Bindung → nicht anwendbar (keine Authentifizierung)

**Status:** nicht anwendbar — siehe ADR 0002.
Es gibt keine Benutzeridentität, an die eine Session gebunden werden könnte:
`fedlex-mcp` stellt öffentliche Open Data ohne Authentifizierung bereit. Die Bindung
einer Session an einen validierten OAuth-`sub`-Claim ist erst sinnvoll, sobald eine
Authentifizierung existiert.

### SEC-015 — Pre-Flight-Erkennung von Tool-Poisoning

**Status:** akzeptiertes Risiko (Portfolio-Ebene) — siehe ADR 0002 — mit lokaler Schutzmassnahme.
Tool-Poisoning (bösartige Tool-Beschreibungen / Rug-Pulls) ist ein Lieferketten- und
Host-seitiges Problem. Die Tool-Definitionen dieses Servers sind versionskontrolliert,
im Repository verfasst und werden per PR geprüft; es gibt keine dynamische/entfernte
Tool-Registrierung. Lokal erkennt **SEC-022 Tool-Hash-Pinning**
(`tool-definitions.lock.json`) jegliche Veränderung der Tool-Oberfläche beim Start und
in CI. Die serverübergreifende Poisoning-Erkennung bleibt eine Gateway-/Host-
Verantwortung, die auf Portfolio-Ebene verfolgt wird.

## Re-Evaluierungs-Auslöser

Diese Akzeptanzen sollten neu bewertet werden, falls der Server jemals:

- **Schreib**-Funktionalität erhält oder beginnt, **PII** zu verarbeiten, oder
- ein **Authentifizierungs**-Modell hinzufügt (dann SEC-009 umsetzen: gebundene,
  TTL-versehene, serverseitig invalidierbare Session-IDs und Re-Audit vor dem Merge), oder
- Tools **dynamisch** / aus entfernten Quellen registriert, oder
- hinter einem gemeinsamen MCP-Gateway aggregiert wird (dann das Tool-Allow-Listing
  und die Tool-Poisoning-Erkennung des Gateways aktivieren).

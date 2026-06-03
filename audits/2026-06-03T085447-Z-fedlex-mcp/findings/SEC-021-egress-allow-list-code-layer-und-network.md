## Finding: SEC-021 — Egress-Allow-List: Code-Layer und Network-Layer

**Severity:** high
**Status:** Open
**Server:** fedlex-mcp
**Check-Reference:** SEC-021
**PDF-Reference:** Anhang B5 + B12
**Verifikations-Status:** partial

### Observed Behavior

- De-facto Egress auf genau einen fixen Host (fedlex.data.admin.ch)

### Gaps / Abweichung vom Standard

- Keine explizite frozenset-Allow-List im Code
- Keine Network-Layer-Egress-Policy / docs/network-egress.md

### Risk Description

SEC-004 (SSRF-Prevention) blockiert Requests an interne IP-Ranges. SEC-021 ergänzt das auf der **anderen Seite**: welche externen Ziele darf der Server überhaupt erreichen? Defense-in-Depth verlangt zwei Layer: **1. Code-Layer Allow-List:** Im Server-Code wird vor jedem ausgehenden HTTP-Request geprüft, ob die Ziel-Domain in einer expliziten Allow-Liste steht. Verhindert versehentliche oder durch Prompt-Injection getriggerte Kontakte zu nicht-autorisierten Domains. **2. Network-Layer Egress Control:** Auf Cloud-Ebene (AWS Security Groups, Azure NSG, Cloudflare WARP, Kubernetes …

### Remediation

### Schritt 1: Allow-List-Inventar

Pro Server alle ausgehenden HTTP-Hosts identifizieren:

```bash
grep -rE 'https://[a-z0-9.-]+' src/ | \
  sed -E 's/.*https:\/\/([a-z0-9.-]+).*/\1/' | sort -u
```

Resultat: minimale Allow-Liste.

### Schritt 2: Code-Layer einbauen

Wie Pass-Pattern Modus 1.

### Schritt 3: Network-Layer einbauen

Bei Kubernetes: NetworkPolicy wie oben. Bei AWS: Security Group mit egress-Rules. Bei Cloudflare WARP: Zero-Trust-Policy.

### Schritt 4: Tests gegen Regression

```python
async def test_egress_blocked_to_non_allowlisted_host():
    with pytest.raises(PermissionError, match="not in allow-list"):
        await fetch_external_data("https://evil.example.com/", mock_ctx())


async def test_egress_allowed_to_allowlisted_host():
    # Mock-Response, kein echter Network-Call
    with respx.mock:
        respx.get("https://opendata.swiss/api/...").respond(200, json={"ok": True})
        result = await fetch_external_data("https://opendata.swiss/api/...", mock_ctx())
        assert result["ok"]
```

### Effort Estimate

M — 1–3 Tage. Code-Layer-Allow-List + Network-Policy + Doku + Tests.

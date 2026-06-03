## Finding: SEC-004 — SSRF-Prevention: HTTPS-Enforcement + IP-Blocklisting

**Severity:** critical
**Status:** Open
**Server:** fedlex-mcp
**Check-Reference:** SEC-004
**PDF-Reference:** Sec 4.4
**Verifikations-Status:** partial

### Observed Behavior

- Ausgehender Endpoint ist fixe HTTPS-Konstante SPARQL_ENDPOINT (server.py:39); User-Input bildet NIE die URL -> SSRF nicht ausnutzbar

### Gaps / Abweichung vom Standard

- Keine explizite HTTPS/IP-Blocklist-Validierung
- WICHTIGER: keywords/sr_number werden ungeescaped per f-string in SPARQL-Query interpoliert (z.B. server.py:270-272) -> SPARQL-Injection-Vektor (ein " bricht aus dem FILTER aus); Impact gering (read-only, oeffentliche Daten), aber Korrektheits-/Robustheitsrisiko

### Risk Description

Server-Side Request Forgery (SSRF) entsteht, wenn ein MCP-Server URLs aus User-Input (oder LLM-generierten Args) direkt an HTTP-Clients weitergibt. Ein Angreifer kann den Server dann zwingen, beliebige interne Adressen abzurufen — insbesondere die Cloud-Metadata-Endpunkte. **Kritische Targets:** | Target | IP/Range | Risiko | |---|---|---| | AWS IMDS | `169.254.169.254` | EC2-Credentials, IAM-Rollen-Token | | GCP Metadata | `169.254.169.254` (Header `Metadata-Flavor: Google`) | Service-Account-Token | | Azure IMDS | `169.254.169.254` (Header `Metadata: true`) | Managed-Identity-Token | | …

### Remediation

Volles Pattern oben. Zusätzlich für Defense-in-Depth:

### Container-Level Egress-Filtering

```yaml
# Kubernetes NetworkPolicy
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: mcp-server-egress
spec:
  podSelector:
    matchLabels:
      app: mcp-server
  policyTypes:
    - Egress
  egress:
    - to:
        - ipBlock:
            cidr: 0.0.0.0/0
            except:
              - 10.0.0.0/8
              - 172.16.0.0/12
              - 192.168.0.0/16
              - 169.254.0.0/16
              - 127.0.0.0/8
      ports:
        - protocol: TCP
          port: 443
```

### IMDSv2 statt IMDSv1 (AWS-spezifisch)

Falls auf AWS deployed: IMDSv2 mit Hop-Limit 1 erzwingen (verhindert SSRF auch bei Code-Bug).

```bash
aws ec2 modify-instance-metadata-options \
  --instance-id i-xxx \
  --http-tokens required \
  --http-put-response-hop-limit 1
```

### Effort Estimate

M — 1–3 Tage. Egress-Proxy-Setup + URL-Validation-Layer + Tests.

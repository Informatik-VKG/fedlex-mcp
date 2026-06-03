## Finding: ARCH-005 — Keine Hardcoded Secrets: Env-Vars / Secret Manager only

**Severity:** critical
**Status:** Open
**Server:** fedlex-mcp
**Check-Reference:** ARCH-005
**PDF-Reference:** Sec 2.1
**Verifikations-Status:** partial

### Observed Behavior

- Keine hardcoded Secrets im Code (Server benoetigt keinerlei Credentials)
- Kein os.environ-Secret-Loading noetig (No-Auth-Server)

### Gaps / Abweichung vom Standard

- Kein .gitignore im Repo vorhanden (.env waere nicht ignoriert)
- Kein CI-Secret-Scan (gitleaks/trufflehog)
- Reales Leak-Risiko jedoch gering, da keine Secrets existieren

### Risk Description

Hardcoded Secrets (API-Keys, Passwörter, Tokens, Connection-Strings, Encryption-Keys) im Source-Code sind die häufigste vermeidbare Sicherheitsschwäche in MCP-Server-Repositories. Sobald das Repo öffentlich ist (oder versehentlich öffentlich wird), oder ein Mitarbeiter aus dem Team ausscheidet, sind alle Secrets kompromittiert. GitHub's Secret-Scanning fängt einen Teil davon ab — aber: (1) nicht alle Pattern werden erkannt, (2) Custom-API-Keys (z.B. interne Schulamt-APIs) sind unbekannt, (3) selbst nach Erkennung ist der Schlüssel bereits im Git-Verlauf und muss neu ausgestellt werden. …

### Remediation

### Schritt 1: Bestehende Secrets identifizieren und ersetzen

```bash
# Lokale Suche (vor jeglichem Push)
gitleaks detect --source . --verbose

# Falls schon committed: History-Rewrite ZUSÄTZLICH zur Schlüssel-Rotation
# Wichtig: rotation FIRST, history-rewrite zweitrangig
```

### Schritt 2: Migration zu Pydantic-Settings

```python
# Vorher
API_KEY = "sk-1234..."

# Nachher
from pydantic import SecretStr
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    api_key: SecretStr
    model_config = {"env_file": ".env", "extra": "forbid"}

settings = Settings()
# Im Code: settings.api_key.get_secret_value()
```

### Schritt 3: `.env.example` mit Platzhaltern

```bash
# .env.example (committet)
API_KEY=replace-with-real-key
DATABASE_URL=postgresql://user:pass@localhost/dbname
OAUTH_CLIENT_SECRET=at-least-32-characters-long-secret

# .env (NICHT committet, in .gitignore)
API_KEY=sk-actual-real-key
...
```

### Schritt 4: Production-Secret-Manager (höhere Reife)

| Plattform | Mechanismus |
|---|---|
| Railway | Project-Variables (verschlüsselt at-rest) |
| Render | Environment-Groups |
| Kubernetes | `Secret`-Objects + `secretKeyRef` in Pod-Spec |
| Self-Hosted | HashiCorp Vault, AWS Secrets Manager (EU-Region!), GCP Secret Manager |

```python
# AWS Secrets Manager (EU-Region für DSG, siehe CH-001)
import boto3
import json

def load_secret(name: str) -> dict:
    client = boto3.client("secretsmanager", region_name="eu-central-1")
    response = client.get_secret_value(SecretId=name)
    return json.loads(response["SecretString"])

secrets = load_secret("schulamt-mcp/production")
api_key = secrets["api_key"]
```

### Schritt 5: CI-Scan einrichten

Siehe Modus 5 oben.

### Schritt 6: Pre-Commit-Hook lokal

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/gitleaks/gitleaks
    rev: v8.18.0
    hooks:
      - id: gitleaks
```

```bash
pre-commit install
# Verhindert Commits mit erkannten Secrets lokal
```

### Effort Estimate

S–M — Bei sauberem Repo: < 1 Tag (Settings-Migration + CI-Setup). Bei Repo mit Secret-Leak in History: 2–3 Tage (Rotation aller Schlüssel, History-Rewrite, Audit aller Forks/Clones).

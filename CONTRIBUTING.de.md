# Mitwirken an fedlex-mcp

[:gb: English Version](CONTRIBUTING.md)

Vielen Dank für Ihr Interesse an einem Beitrag! Dieser Server ist Teil des [Swiss Public Data MCP Portfolios](https://github.com/malkreide).

---

## Probleme melden

Nutzen Sie [GitHub Issues](https://github.com/malkreide/fedlex-mcp/issues), um Fehler zu melden oder Funktionen vorzuschlagen.

Bitte geben Sie an:
- Python-Version und Betriebssystem
- Vollständige Fehlermeldung oder Beschreibung des unerwarteten Verhaltens
- Schritte zur Reproduktion

---

## Pull Requests

1. Forken Sie das Repository
2. Erstellen Sie einen Feature-Branch: `git checkout -b feat/ihr-feature`
3. Nehmen Sie Ihre Änderungen vor und ergänzen Sie Tests
4. Stellen Sie sicher, dass alle Tests bestehen: `PYTHONPATH=src pytest tests/ -m "not live"`
5. Committen Sie nach [Conventional Commits](https://www.conventionalcommits.org/): `feat: neues Tool hinzufügen`
6. Pushen Sie und öffnen Sie einen Pull Request gegen `main`

---

## Code-Stil

- Python 3.11+
- [Ruff](https://github.com/astral-sh/ruff) für Linting und Formatierung
- Type Hints für alle öffentlichen Funktionen erforderlich
- Tests für neue Tools erforderlich (`tests/test_server.py`)
- Den bestehenden FastMCP-/Pydantic-v2-Mustern in `server.py` folgen

---

## Datenquelle

Dieser Server nutzt den öffentlichen Fedlex-SPARQL-Endpoint — keine Authentifizierung erforderlich.

| Quelle | Dokumentation |
|--------|--------------|
| Fedlex SPARQL | [fedlex.data.admin.ch](https://fedlex.data.admin.ch/) |
| JOLux-Ontologie | [Fedlex-Datenmodell](https://fedlex.data.admin.ch/) |

Wenn Sie neue SPARQL-Abfragen hinzufügen, prüfen Sie diese zuerst manuell gegen den Endpoint und behandeln Sie Randfälle (fehlende optionale Felder, Timeout bei breiten Abfragen).

---

## Lizenz

Mit Ihrem Beitrag erklären Sie sich damit einverstanden, dass Ihre Beiträge unter der [MIT-Lizenz](LICENSE) lizenziert werden.

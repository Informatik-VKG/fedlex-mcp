"""Unit tests for fedlex-mcp server (non-live)."""
from __future__ import annotations

import pytest


@pytest.mark.parametrize("sr_number", ["101", "210.10", "172.021"])
def test_sr_number_format_valid(sr_number: str) -> None:
    """SR-Nummern im korrekten Format werden akzeptiert."""
    # Einfacher Regex-Sanity-Check ohne Live-API-Aufruf
    import re
    pattern = r"^\d{3}(\.\d+)*$"
    assert re.match(pattern, sr_number), f"Ungültiges SR-Format: {sr_number}"


def test_server_imports() -> None:
    """Server-Modul lässt sich importieren."""
    import importlib
    mod = importlib.import_module("fedlex_mcp.server")
    assert hasattr(mod, "main"), "main() nicht gefunden"


# Live-Tests (werden in CI übersprungen via: pytest -m 'not live')
@pytest.mark.live
def test_live_sparql_endpoint() -> None:
    """Live-Test gegen den echten Fedlex-SPARQL-Endpoint."""
    pass  # Platzhalter für echte Live-Tests

"""Unit tests for fedlex-mcp server.

Network is mocked with respx so the suite is fully offline (CI: pytest -m
'not live'). A single live smoke test against the real SPARQL endpoint is
marked `live` and skipped by default.

Tools return a structured ``FedlexResponse`` envelope (SDK-002): assertions
check ``.results`` / ``.match_type`` / ``.count`` for structure and ``.markdown``
for the human-readable rendering.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import httpx
import pytest
import respx
from pydantic import ValidationError

from fedlex_mcp import server
from fedlex_mcp.server import (
    GetLawBySrInput,
    GetLawHistoryInput,
    GetRecentPublicationsInput,
    GetUpcomingChangesInput,
    Language,
    SearchGazetteInput,
    SearchLawsInput,
    SearchTreatiesInput,
    sparql_escape,
)

ENDPOINT = server.SPARQL_ENDPOINT


def _sparql_response(bindings: list[dict]) -> httpx.Response:
    return httpx.Response(200, json={"results": {"bindings": bindings}})


def _binding(**fields: str) -> dict:
    return {k: {"value": v} for k, v in fields.items()}


# ---------------------------------------------------------------------------
# Pure-function unit tests
# ---------------------------------------------------------------------------

def test_sparql_escape_neutralises_quote_breakout() -> None:
    assert sparql_escape('foo" } INJECT') == 'foo\\" } INJECT'


def test_sparql_escape_handles_backslash_and_newline() -> None:
    assert sparql_escape("a\\b\nc") == "a\\\\b\\nc"


def test_status_label_known_and_unknown() -> None:
    assert "In Kraft" in server.status_label(server.STATUS_IN_FORCE)
    assert server.status_label("https://x/vocabulary/enforcement-status/9") == "(9)"


def test_fedlex_url_rewrites_data_uri() -> None:
    url = server.fedlex_url("https://fedlex.data.admin.ch/eli/cc/235.1", "fr")
    assert url == "https://www.fedlex.admin.ch/eli/cc/235.1/fr"


def test_assert_host_allowed_blocks_foreign_host() -> None:
    server.assert_host_allowed(ENDPOINT)  # allow-listed -> no raise
    with pytest.raises(PermissionError):
        server.assert_host_allowed("https://evil.example.com/x")


# ---------------------------------------------------------------------------
# Input validation (SEC-018)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad", ['a" } INJECT', "back\\slash", "brace{", "<tag>"])
def test_keywords_pattern_rejects_injection(bad: str) -> None:
    with pytest.raises(ValidationError):
        SearchLawsInput(keywords=bad)


@pytest.mark.parametrize("good", ["Datenschutz", "CO2-Gesetz", "Müller", "EU/EFTA"])
def test_keywords_pattern_accepts_legitimate_terms(good: str) -> None:
    assert SearchLawsInput(keywords=good).keywords == good


@pytest.mark.parametrize("bad", ["1; DROP", '235" .', "abc", "235,1"])
def test_sr_number_pattern_rejects_malformed(bad: str) -> None:
    with pytest.raises(ValidationError):
        GetLawBySrInput(sr_number=bad)


@pytest.mark.parametrize("good", ["101", "235.1", "412.10", "0.101"])
def test_sr_number_pattern_accepts_valid(good: str) -> None:
    assert GetLawBySrInput(sr_number=good).sr_number == good


def test_extra_fields_forbidden() -> None:
    with pytest.raises(ValidationError):
        SearchLawsInput(keywords="Datenschutz", unexpected="x")


def test_limit_out_of_range_rejected() -> None:
    with pytest.raises(ValidationError):
        SearchLawsInput(keywords="Datenschutz", limit=999)


# ---------------------------------------------------------------------------
# Tool happy-paths — structured envelope (SDK-002)
# ---------------------------------------------------------------------------

@respx.mock
@pytest.mark.asyncio
async def test_search_laws_happy() -> None:
    respx.get(ENDPOINT).mock(return_value=_sparql_response([
        _binding(ca="https://fedlex.data.admin.ch/eli/cc/235.1",
                 title="Bundesgesetz über den Datenschutz", titleShort="DSG",
                 srNumber="235.1", inForceStatus=server.STATUS_IN_FORCE),
    ]))
    resp = await server.fedlex_search_laws(SearchLawsInput(keywords="Datenschutz"))
    assert resp.match_type == "exact"
    assert resp.count == 1
    assert resp.results[0]["sr_number"] == "235.1"
    assert resp.results[0]["title_short"] == "DSG"
    assert resp.results[0]["url"].startswith("https://www.fedlex.admin.ch/")
    assert resp.source.startswith("Fedlex")
    assert "DSG" in resp.markdown


@respx.mock
@pytest.mark.asyncio
async def test_search_laws_empty_envelope() -> None:
    respx.get(ENDPOINT).mock(return_value=_sparql_response([]))
    resp = await server.fedlex_search_laws(SearchLawsInput(keywords="zzzznope"))
    assert resp.match_type == "none"
    assert resp.count == 0
    assert resp.results == []
    assert "match_type: none" in resp.markdown


@respx.mock
@pytest.mark.asyncio
async def test_get_law_by_sr_happy() -> None:
    respx.get(ENDPOINT).mock(return_value=_sparql_response([
        _binding(ca="https://fedlex.data.admin.ch/eli/cc/101",
                 title="Bundesverfassung", titleShort="BV", srNumber="101",
                 inForceStatus=server.STATUS_IN_FORCE, entryDate="2000-01-01"),
    ]))
    resp = await server.fedlex_get_law_by_sr(GetLawBySrInput(sr_number="101"))
    assert resp.count == 1
    assert resp.results[0]["title"] == "Bundesverfassung"
    assert "Bundesverfassung" in resp.markdown


@respx.mock
@pytest.mark.asyncio
async def test_get_recent_publications_happy() -> None:
    respx.get(ENDPOINT).mock(return_value=_sparql_response([
        _binding(act="https://fedlex.data.admin.ch/eli/oc/2026/1",
                 title="Neue Verordnung", pubDate="2026-05-01"),
    ]))
    resp = await server.fedlex_get_recent_publications(GetRecentPublicationsInput(days=30))
    assert resp.results[0]["publication_date"] == "2026-05-01"
    assert "Neue Verordnung" in resp.markdown


@respx.mock
@pytest.mark.asyncio
async def test_get_upcoming_changes_happy() -> None:
    respx.get(ENDPOINT).mock(return_value=_sparql_response([
        _binding(ca="https://fedlex.data.admin.ch/eli/cc/999",
                 title="Künftiges Gesetz", titleShort="KG", srNumber="999",
                 entryDate="2026-12-01"),
    ]))
    resp = await server.fedlex_get_upcoming_changes(GetUpcomingChangesInput(days_ahead=90))
    assert resp.results[0]["entry_date"] == "2026-12-01"
    assert "Künftiges Gesetz" in resp.markdown


@respx.mock
@pytest.mark.asyncio
async def test_search_gazette_happy() -> None:
    respx.get(ENDPOINT).mock(return_value=_sparql_response([
        _binding(act="https://fedlex.data.admin.ch/eli/fga/2024/1",
                 title="Botschaft zur Berufsbildung", pubDate="2024-03-01"),
    ]))
    resp = await server.fedlex_search_gazette(SearchGazetteInput(keywords="Berufsbildung", year=2024))
    assert resp.count == 1
    assert "Berufsbildung" in resp.markdown


@respx.mock
@pytest.mark.asyncio
async def test_get_law_history_happy() -> None:
    respx.get(ENDPOINT).mock(return_value=_sparql_response([
        _binding(ca="https://fedlex.data.admin.ch/eli/cc/235.1/2023",
                 title="DSG", srNumber="235.1", entryDate="2023-09-01",
                 inForceStatus=server.STATUS_IN_FORCE),
        _binding(ca="https://fedlex.data.admin.ch/eli/cc/235.1/1993",
                 title="DSG", srNumber="235.1", entryDate="1993-07-01",
                 inForceStatus=server.STATUS_NO_LONGER_FORCE),
    ]))
    resp = await server.fedlex_get_law_history(GetLawHistoryInput(sr_number="235.1"))
    assert resp.count == 2
    assert {r["version"] for r in resp.results} == {1, 2}
    assert "Versionsgeschichte" in resp.markdown


@respx.mock
@pytest.mark.asyncio
async def test_search_treaties_happy() -> None:
    respx.get(ENDPOINT).mock(return_value=_sparql_response([
        _binding(ca="https://fedlex.data.admin.ch/eli/cc/0.101",
                 title="EMRK", srNumber="0.101", entryDate="1974-11-28"),
    ]))
    resp = await server.fedlex_search_treaties(SearchTreatiesInput(keywords="EMRK"))
    assert resp.results[0]["sr_number"] == "0.101"


# ---------------------------------------------------------------------------
# Error handling (OBS-001 / OBS-002) — masked, structured error envelope
# ---------------------------------------------------------------------------

@respx.mock
@pytest.mark.asyncio
async def test_http_400_returns_error_envelope() -> None:
    respx.get(ENDPOINT).mock(return_value=httpx.Response(400, text="boom"))
    resp = await server.fedlex_search_laws(SearchLawsInput(keywords="Datenschutz"))
    assert resp.match_type == "error"
    assert "HTTP 400" in resp.markdown
    assert "boom" not in resp.markdown


@respx.mock
@pytest.mark.asyncio
async def test_connect_error_is_masked() -> None:
    respx.get(ENDPOINT).mock(side_effect=httpx.ConnectError("dns fail"))
    resp = await server.fedlex_search_laws(SearchLawsInput(keywords="Datenschutz"))
    assert resp.match_type == "error"
    assert "Verbindung zu Fedlex" in resp.markdown
    assert "dns fail" not in resp.markdown


def test_handle_error_generic_does_not_leak_repr() -> None:
    out = server.handle_error("fedlex_search_laws", ValueError("secret-internal-detail"))
    assert "secret-internal-detail" not in out
    assert out.startswith("Fehler:")


# ---------------------------------------------------------------------------
# Config / wiring / observability
# ---------------------------------------------------------------------------

def test_shared_client_default_is_none_outside_lifespan() -> None:
    assert server._http_client is None


def test_settings_defaults_are_safe() -> None:
    assert server.settings.transport == "stdio"
    assert server.settings.host == "127.0.0.1"  # no 0.0.0.0 default (SEC-016)


def test_egress_allow_list_is_frozen() -> None:
    assert isinstance(server.ALLOWED_EGRESS_HOSTS, frozenset)
    assert server.FEDLEX_DATA_HOST in server.ALLOWED_EGRESS_HOSTS


def test_structured_logger_available() -> None:
    assert server.log is not None
    assert hasattr(server.log, "info")


def test_tracing_disabled_by_default() -> None:
    """OBS-006: OpenTelemetry is a no-op unless explicitly configured."""
    assert server._tracer is None


def test_server_imports() -> None:
    assert hasattr(server, "mcp")


@respx.mock
@pytest.mark.asyncio
async def test_tool_accepts_ctx_none() -> None:
    respx.get(ENDPOINT).mock(return_value=_sparql_response([
        _binding(ca="https://fedlex.data.admin.ch/eli/cc/101", title="BV", srNumber="101"),
    ]))
    resp = await server.fedlex_search_laws(SearchLawsInput(keywords="Verfassung"), ctx=None)
    assert resp.count == 1


@pytest.mark.parametrize("sr_number", ["101", "210.10", "172.021"])
def test_sr_number_format_valid(sr_number: str) -> None:
    assert re.match(server.SR_NUMBER_PATTERN, sr_number)


# ---------------------------------------------------------------------------
# Tool-definition hash pinning (SEC-022)
# ---------------------------------------------------------------------------

def test_tool_definitions_match_lock() -> None:
    """The live tool definitions must match the committed lock file. If this
    fails, a tool changed — regenerate with scripts/snapshot_tools.py and note
    it in CHANGELOG.md (rug-pull guard)."""
    lock_path = Path(__file__).resolve().parent.parent / "tool-definitions.lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    live = asyncio.run(server.compute_tool_signature_hash())
    assert live == lock["sha256"], (
        "Tool definitions drifted from tool-definitions.lock.json. "
        "Run: PYTHONPATH=src python scripts/snapshot_tools.py"
    )


# ---------------------------------------------------------------------------
# Tool allow-list (SEC-014) — default-deny via FEDLEX_ENABLED_TOOLS
# ---------------------------------------------------------------------------

def test_tool_allowlist_default_exposes_all() -> None:
    names = {t.name for t in asyncio.run(server.mcp.list_tools())}
    assert len(names) == 7


def test_tool_allowlist_env_default_deny() -> None:
    """With FEDLEX_ENABLED_TOOLS set, only listed tools are registered.

    Runs in a subprocess so the module-load-time allow-list does not leak into
    the rest of the suite.
    """
    code = (
        "import asyncio;from fedlex_mcp import server as s;"
        "print(sorted(t.name for t in asyncio.run(s.mcp.list_tools())))"
    )
    env = {
        **os.environ,
        "FEDLEX_ENABLED_TOOLS": "fedlex_search_laws,fedlex_get_law_by_sr",
        "PYTHONPATH": "src",
    }
    out = subprocess.check_output([sys.executable, "-c", code], env=env, text=True)
    assert "fedlex_search_laws" in out
    assert "fedlex_get_law_by_sr" in out
    assert "fedlex_search_treaties" not in out


# ---------------------------------------------------------------------------
# Live smoke test (skipped in CI via: pytest -m 'not live')
# ---------------------------------------------------------------------------

@pytest.mark.live
@pytest.mark.asyncio
async def test_live_sparql_endpoint() -> None:
    resp = await server.fedlex_get_law_by_sr(GetLawBySrInput(sr_number="101", language=Language.DE))
    assert "101" in resp.markdown

"""Unit tests for fedlex-mcp server.

Network is mocked with respx so the suite is fully offline (CI: pytest -m
'not live'). A single live smoke test against the real SPARQL endpoint is
marked `live` and skipped by default.
"""
from __future__ import annotations

import re

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
    """Build a SPARQL-results+json HTTP response from a list of bindings."""
    return httpx.Response(200, json={"results": {"bindings": bindings}})


def _binding(**fields: str) -> dict:
    """Shorthand: {"key": {"value": v}} for each kwarg."""
    return {k: {"value": v} for k, v in fields.items()}


# ---------------------------------------------------------------------------
# Pure-function unit tests
# ---------------------------------------------------------------------------

def test_sparql_escape_neutralises_quote_breakout() -> None:
    """A double quote / backslash must be escaped, not passed through raw."""
    escaped = sparql_escape('foo" } INJECT')
    assert escaped == 'foo\\" } INJECT'


def test_sparql_escape_handles_backslash_and_newline() -> None:
    assert sparql_escape("a\\b\nc") == "a\\\\b\\nc"


def test_status_label_known_and_unknown() -> None:
    assert "In Kraft" in server.status_label(server.STATUS_IN_FORCE)
    assert server.status_label("https://x/vocabulary/enforcement-status/9") == "(9)"


def test_fedlex_url_rewrites_data_uri() -> None:
    url = server.fedlex_url("https://fedlex.data.admin.ch/eli/cc/235.1", "fr")
    assert url == "https://www.fedlex.admin.ch/eli/cc/235.1/fr"


# ---------------------------------------------------------------------------
# Input validation (SEC-018) — patterns reject injection / malformed input
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
# Tool happy-paths (respx-mocked SPARQL)
# ---------------------------------------------------------------------------

@respx.mock
@pytest.mark.asyncio
async def test_search_laws_happy() -> None:
    respx.get(ENDPOINT).mock(return_value=_sparql_response([
        _binding(ca="https://fedlex.data.admin.ch/eli/cc/235.1",
                 title="Bundesgesetz über den Datenschutz", titleShort="DSG",
                 srNumber="235.1", inForceStatus=server.STATUS_IN_FORCE),
    ]))
    out = await server.fedlex_search_laws(SearchLawsInput(keywords="Datenschutz"))
    assert "SR 235.1" in out
    assert "DSG" in out
    assert "In Kraft" in out
    assert "Quelle: Fedlex" in out


@respx.mock
@pytest.mark.asyncio
async def test_search_laws_empty_gives_actionable_hint() -> None:
    respx.get(ENDPOINT).mock(return_value=_sparql_response([]))
    out = await server.fedlex_search_laws(SearchLawsInput(keywords="zzzznope"))
    assert "Keine Erlasse" in out
    assert "Tipps" in out


@respx.mock
@pytest.mark.asyncio
async def test_get_law_by_sr_happy() -> None:
    respx.get(ENDPOINT).mock(return_value=_sparql_response([
        _binding(ca="https://fedlex.data.admin.ch/eli/cc/101",
                 title="Bundesverfassung", titleShort="BV", srNumber="101",
                 inForceStatus=server.STATUS_IN_FORCE, entryDate="2000-01-01"),
    ]))
    out = await server.fedlex_get_law_by_sr(GetLawBySrInput(sr_number="101"))
    assert "Bundesverfassung" in out
    assert "BV" in out


@respx.mock
@pytest.mark.asyncio
async def test_get_recent_publications_happy() -> None:
    respx.get(ENDPOINT).mock(return_value=_sparql_response([
        _binding(act="https://fedlex.data.admin.ch/eli/oc/2026/1",
                 title="Neue Verordnung", pubDate="2026-05-01"),
    ]))
    out = await server.fedlex_get_recent_publications(GetRecentPublicationsInput(days=30))
    assert "Neue Verordnung" in out
    assert "2026-05-01" in out


@respx.mock
@pytest.mark.asyncio
async def test_get_upcoming_changes_happy() -> None:
    respx.get(ENDPOINT).mock(return_value=_sparql_response([
        _binding(ca="https://fedlex.data.admin.ch/eli/cc/999",
                 title="Künftiges Gesetz", titleShort="KG", srNumber="999",
                 entryDate="2026-12-01"),
    ]))
    out = await server.fedlex_get_upcoming_changes(GetUpcomingChangesInput(days_ahead=90))
    assert "Künftiges Gesetz" in out
    assert "2026-12-01" in out


@respx.mock
@pytest.mark.asyncio
async def test_search_gazette_happy() -> None:
    respx.get(ENDPOINT).mock(return_value=_sparql_response([
        _binding(act="https://fedlex.data.admin.ch/eli/fga/2024/1",
                 title="Botschaft zur Berufsbildung", pubDate="2024-03-01"),
    ]))
    out = await server.fedlex_search_gazette(SearchGazetteInput(keywords="Berufsbildung", year=2024))
    assert "Botschaft zur Berufsbildung" in out


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
    out = await server.fedlex_get_law_history(GetLawHistoryInput(sr_number="235.1"))
    assert "Versionsgeschichte" in out
    assert "1993-07-01" in out and "2023-09-01" in out


@respx.mock
@pytest.mark.asyncio
async def test_search_treaties_happy() -> None:
    respx.get(ENDPOINT).mock(return_value=_sparql_response([
        _binding(ca="https://fedlex.data.admin.ch/eli/cc/0.101",
                 title="EMRK", srNumber="0.101", entryDate="1974-11-28"),
    ]))
    out = await server.fedlex_search_treaties(SearchTreatiesInput(keywords="EMRK"))
    assert "0.101" in out


# ---------------------------------------------------------------------------
# Error handling (OBS-001 / OBS-002) — no internal details leak to the LLM
# ---------------------------------------------------------------------------

@respx.mock
@pytest.mark.asyncio
async def test_http_400_returns_friendly_message() -> None:
    respx.get(ENDPOINT).mock(return_value=httpx.Response(400, text="boom"))
    out = await server.fedlex_search_laws(SearchLawsInput(keywords="Datenschutz"))
    assert "HTTP 400" in out
    assert "boom" not in out  # upstream body must not leak


@respx.mock
@pytest.mark.asyncio
async def test_connect_error_is_masked() -> None:
    respx.get(ENDPOINT).mock(side_effect=httpx.ConnectError("dns fail"))
    out = await server.fedlex_search_laws(SearchLawsInput(keywords="Datenschutz"))
    assert "Verbindung zu Fedlex" in out
    assert "dns fail" not in out


def test_handle_error_generic_does_not_leak_repr() -> None:
    out = server.handle_error(ValueError("secret-internal-detail"))
    assert "secret-internal-detail" not in out
    assert out.startswith("Fehler:")


# ---------------------------------------------------------------------------
# Config / wiring
# ---------------------------------------------------------------------------

def test_shared_client_default_is_none_outside_lifespan() -> None:
    """The shared client is created by the lifespan, not at import time."""
    assert server._http_client is None


def test_settings_defaults_are_safe() -> None:
    assert server.settings.transport == "stdio"
    assert server.settings.host == "127.0.0.1"  # no 0.0.0.0 default (SEC-016)


def test_egress_allow_list_is_frozen() -> None:
    assert isinstance(server.ALLOWED_EGRESS_HOSTS, frozenset)
    assert server.FEDLEX_DATA_HOST in server.ALLOWED_EGRESS_HOSTS


def test_server_imports() -> None:
    assert hasattr(server, "mcp")


@pytest.mark.parametrize("sr_number", ["101", "210.10", "172.021"])
def test_sr_number_format_valid(sr_number: str) -> None:
    """SR numbers in correct format match the documented pattern."""
    assert re.match(server.SR_NUMBER_PATTERN, sr_number)


# ---------------------------------------------------------------------------
# Live smoke test (skipped in CI via: pytest -m 'not live')
# ---------------------------------------------------------------------------

@pytest.mark.live
@pytest.mark.asyncio
async def test_live_sparql_endpoint() -> None:
    """Hits the real Fedlex endpoint; run with: pytest -m live."""
    out = await server.fedlex_get_law_by_sr(GetLawBySrInput(sr_number="101", language=Language.DE))
    assert "101" in out

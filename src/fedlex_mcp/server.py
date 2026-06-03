"""
Fedlex MCP Server
=================
MCP server für das Schweizer Bundesrecht via den Fedlex SPARQL-Endpoint.
Ermöglicht Zugriff auf die Systematische Rechtssammlung (SR), Amtliche
Sammlung (AS), Bundesblatt (BBl) und Staatsverträge.

Datenquelle: https://fedlex.data.admin.ch
Lizenz: Freie Wiederverwendung gemäss fedlex.admin.ch/de/broadcasters

JOLux-Datenmodell (verifiziert):
  - jolux:ConsolidationAbstract  →  SR-Eintrag (Abstract über alle Versionen)
    └─ jolux:isRealizedBy  →  jolux:Expression (sprachspez. Fassung)
       ├─ jolux:title               Vollständiger Titel
       ├─ jolux:titleShort          Abkürzung (z.B. "DSG", "BV")
       └─ jolux:historicalLegalId   SR-Nummer (z.B. "235.1")
  - jolux:Act  →  Einzelpublikation in AS (eli/oc/) oder BBl (eli/fga/)
  - jolux:inForceStatus:
       .../0  In Kraft
       .../1  Nicht mehr in der SR publiziert
       .../3  Nicht mehr in Kraft

Transport: Dual — stdio (lokal) und Streamable HTTP (Cloud/Render.com),
wählbar über die Umgebungsvariable FEDLEX_TRANSPORT (stdio | streamable-http).

MCP Protocol Version: ausgehandelt vom mcp-SDK (>=1.3.0); siehe README-Sektion
"MCP Protocol Version".
"""

import json
import os
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum

import httpx
import structlog
from mcp.server.fastmcp import Context, FastMCP
from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# ---------------------------------------------------------------------------
# Konstanten
# ---------------------------------------------------------------------------

SPARQL_ENDPOINT = "https://fedlex.data.admin.ch/sparqlendpoint"
FEDLEX_BASE_URL = "https://www.fedlex.admin.ch"
FEDLEX_DATA_HOST = "fedlex.data.admin.ch"
REQUEST_TIMEOUT = 45
MAX_RESULTS_DEFAULT = 20
MAX_RESULTS_LIMIT = 100

# Defense-in-depth: der Server spricht ausschliesslich diesen einen Endpoint an
# (SEC-021 Egress-Allow-List auf Code-Ebene).
ALLOWED_EGRESS_HOSTS = frozenset({FEDLEX_DATA_HOST})

# Whitelist-Pattern für Freitext-Suchbegriffe (SEC-018). Erlaubt Buchstaben
# (inkl. Umlaute/Akzente via Unicode-\w), Ziffern, Leerzeichen und gängige
# Interpunktion — aber keine Anführungszeichen, Backslashes oder geschweiften
# Klammern, mit denen man aus einem SPARQL-Literal ausbrechen könnte.
KEYWORD_PATTERN = r"^[\w\s.\-'’(),:/&+]+$"
# SR-Nummern: nur Zifferngruppen, durch Punkte getrennt (z.B. 101, 235.1, 0.101).
SR_NUMBER_PATTERN = r"^\d{1,3}(\.\d+)*$"

LANG_SUFFIX = {"de": "/de", "fr": "/fr", "it": "/it", "rm": "/rm"}

STATUS_IN_FORCE = "https://fedlex.data.admin.ch/vocabulary/enforcement-status/0"
STATUS_NOT_PUBLISHED = "https://fedlex.data.admin.ch/vocabulary/enforcement-status/1"
STATUS_NO_LONGER_FORCE = "https://fedlex.data.admin.ch/vocabulary/enforcement-status/3"

STATUS_LABELS = {
    STATUS_IN_FORCE: "✅ In Kraft",
    STATUS_NOT_PUBLISHED: "⚠️ Nicht mehr in SR publiziert",
    STATUS_NO_LONGER_FORCE: "❌ Nicht mehr in Kraft",
}

FEDLEX_SOURCE = "\n---\n*Quelle: Fedlex, Schweizerische Bundeskanzlei (fedlex.admin.ch)*"

# ---------------------------------------------------------------------------
# Strukturiertes Logging (OBS-003)
# ---------------------------------------------------------------------------
# JSON-Logs gehen bewusst auf STDERR — bei stdio-Transport ist STDOUT exklusiv
# für das JSON-RPC-Protokoll reserviert (OBS-004).

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    logger_factory=structlog.WriteLoggerFactory(file=sys.stderr),
    cache_logger_on_first_use=True,
)
log = structlog.get_logger("fedlex_mcp")

# ---------------------------------------------------------------------------
# Konfiguration (Settings statt globaler Module-Vars — ARCH-004)
# ---------------------------------------------------------------------------


class Settings(BaseSettings):
    """Laufzeit-Konfiguration, vollständig über Env-Vars steuerbar.

    Transport-Wahl, Host/Port und CORS-Origins kommen aus der Umgebung, damit
    derselbe Code lokal (stdio) und in der Cloud (streamable-http) läuft, ohne
    Code-Fork.
    """

    model_config = SettingsConfigDict(env_prefix="FEDLEX_", extra="ignore")

    transport: str = "stdio"  # stdio | streamable-http
    host: str = "127.0.0.1"
    port: int = 8000
    # Kommagetrennte Origin-Liste; in Produktion explizit setzen, kein "*".
    allowed_origins: str = "http://localhost,http://127.0.0.1"


settings = Settings()

# ---------------------------------------------------------------------------
# Geteilte Infrastruktur
# ---------------------------------------------------------------------------


class Language(StrEnum):
    """Offizielle Landessprachen der Schweizerischen Eidgenossenschaft."""

    DE = "de"
    FR = "fr"
    IT = "it"
    RM = "rm"


@dataclass
class AppContext:
    """Über den Lifespan geteilte Ressourcen."""

    client: httpx.AsyncClient


# Ein einziger, über den Server-Lifecycle geteilter HTTP-Client (SDK-001).
# Wird im Lifespan erstellt und sauber geschlossen — kein Client pro Tool-Call.
_http_client: httpx.AsyncClient | None = None


@asynccontextmanager
async def lifespan(_server: FastMCP) -> AsyncIterator[AppContext]:
    """Erstellt den geteilten HTTP-Client und schliesst ihn beim Shutdown."""
    global _http_client
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        _http_client = client
        log.info("lifespan_start", shared_http_client=True)
        try:
            yield AppContext(client=client)
        finally:
            _http_client = None
            log.info("lifespan_stop")


async def _trace(ctx: Context | None, tool: str, **fields: object) -> None:
    """Loggt einen Tool-Aufruf strukturiert (OBS-003) und — falls ein MCP-Context
    vorhanden ist — auch an den Client zurück (SDK-003)."""
    log.info("tool_call", tool=tool, **fields)
    if ctx is not None:
        try:
            await ctx.info(f"{tool}: Anfrage an Fedlex SPARQL")
        except Exception:  # pragma: no cover - Context ohne aktive Session
            pass


async def _fail(ctx: Context | None, tool: str, e: Exception) -> str:
    """Einheitlicher Fehler-Pfad: maskierte Meldung + ctx.error (SDK-003 / OBS-002)."""
    msg = handle_error(tool, e)
    if ctx is not None:
        try:
            await ctx.error(msg)
        except Exception:  # pragma: no cover - Context ohne aktive Session
            pass
    return msg


def sparql_escape(value: str) -> str:
    """Escaped einen String für die sichere Interpolation in ein SPARQL-Literal.

    Verhindert das Ausbrechen aus doppelt-gequoteten SPARQL-Literalen
    (SEC-004 / SEC-018). Wird zusätzlich zur Pydantic-Pattern-Validierung als
    Defense-in-Depth angewandt.
    """
    return (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )


async def run_sparql(query: str, client: httpx.AsyncClient | None = None) -> list[dict]:
    """Führt SPARQL-Abfrage gegen den Fedlex-Endpoint aus, gibt Bindings zurück.

    Nutzt standardmässig den über den Lifespan geteilten Client. Fällt nur dann
    auf einen Ad-hoc-Client zurück, wenn kein Lifespan aktiv ist (z.B. in
    isolierten Skripten/Tests).
    """
    active = client or _http_client
    if active is not None:
        return await _execute_sparql(active, query)
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as tmp:
        return await _execute_sparql(tmp, query)


async def _execute_sparql(client: httpx.AsyncClient, query: str) -> list[dict]:
    response = await client.get(
        SPARQL_ENDPOINT,
        params={"query": query, "format": "application/sparql-results+json"},
        headers={"Accept": "application/sparql-results+json"},
    )
    response.raise_for_status()
    return response.json().get("results", {}).get("bindings", [])


def val(binding: dict, key: str, default: str = "") -> str:
    """Extrahiert sicher den String-Wert aus einem SPARQL-Binding."""
    entry = binding.get(key)
    return entry.get("value", default) if entry else default


def fedlex_url(uri: str, lang: str = "de") -> str:
    """Wandelt Fedlex-Daten-URI in lesbare fedlex.admin.ch-URL um."""
    if uri.startswith("https://fedlex.data.admin.ch/"):
        path = uri.replace("https://fedlex.data.admin.ch", "")
        return f"{FEDLEX_BASE_URL}{path}/{lang}"
    return uri


def status_label(status_uri: str) -> str:
    """Gibt lesbares Label für einen Enforcement-Status-URI zurück."""
    return STATUS_LABELS.get(status_uri, f"({status_uri.split('/')[-1]})")


def handle_error(tool: str, e: Exception) -> str:
    """Einheitliche, handlungsweisende Fehlermeldungen.

    Interne Exception-Details werden ausschliesslich serverseitig geloggt und
    nie an das LLM zurückgegeben (OBS-001 / OBS-002).
    """
    log.warning("tool_error", tool=tool, error_type=type(e).__name__, detail=str(e))
    if isinstance(e, httpx.HTTPStatusError):
        code = e.response.status_code
        if code == 400:
            return "Fehler: Ungültige SPARQL-Abfrage (HTTP 400). Suchparameter überprüfen."
        if code == 429:
            return "Fehler: Rate Limit erreicht. Bitte kurz warten und erneut versuchen."
        if code == 503:
            return "Fehler: Fedlex vorübergehend nicht verfügbar. Später erneut versuchen."
        return f"Fehler: HTTP {code} vom Fedlex-Endpoint."
    if isinstance(e, (httpx.TimeoutException, httpx.ReadTimeout)):
        return (
            "Fehler: Timeout beim Fedlex-Endpoint. "
            "Komplexe SPARQL-Abfragen können länger dauern — bitte erneut versuchen."
        )
    if isinstance(e, httpx.ConnectError):
        return "Fehler: Verbindung zu Fedlex fehlgeschlagen. Internetverbindung prüfen."
    return "Fehler: Unerwarteter Fehler beim Abruf vom Fedlex-Endpoint. Bitte erneut versuchen."


def result_header(count: int, desc: str) -> str:
    """Standardisierter Ergebnisheader."""
    return f"## Fedlex — {desc}\n**Treffer:** {count}\n\n"


def no_match_hint(tips: str) -> str:
    """Maschinenlesbarer Hinweis bei leeren Resultaten (ARCH-003): markiert den
    match_type explizit, damit das LLM nicht halluziniert, sondern verfeinert."""
    return f"\n\n_(match_type: none — keine Treffer)_\n\n{tips}"


# ---------------------------------------------------------------------------
# Server-Initialisierung
# ---------------------------------------------------------------------------

mcp = FastMCP(
    "fedlex_mcp",
    instructions=(
        "MCP-Server für das Schweizer Bundesrecht (Fedlex). "
        "Zugriff auf die Systematische Rechtssammlung (SR), "
        "Amtliche Sammlung (AS), Bundesblatt (BBl) und Staatsverträge. "
        "Alle Daten stammen vom SPARQL-Endpoint der Schweizerischen Bundeskanzlei."
    ),
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# Input-Modelle
# ---------------------------------------------------------------------------


class SearchLawsInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra="forbid")
    keywords: str = Field(
        ...,
        description="Suchbegriff(e) im Erlasstittel, z.B. 'Volksschule', 'Datenschutz', 'Berufsbildung'",
        min_length=2, max_length=200, pattern=KEYWORD_PATTERN,
    )
    language: Language = Field(default=Language.DE, description="Sprache: 'de', 'fr', 'it', 'rm'")
    in_force_only: bool = Field(default=True, description="Nur gültige Erlasse (Standard: True)")
    limit: int = Field(default=MAX_RESULTS_DEFAULT, ge=1, le=MAX_RESULTS_LIMIT,
                       description=f"Maximale Trefferzahl (1–{MAX_RESULTS_LIMIT})")


class GetLawBySrInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    sr_number: str = Field(
        ...,
        description="SR-Nummer, z.B. '101' (BV), '235.1' (DSG), '412.10' (BBG), '170.32' (VG)",
        min_length=1, max_length=20, pattern=SR_NUMBER_PATTERN,
    )
    language: Language = Field(default=Language.DE)


class GetRecentPublicationsInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    days: int = Field(default=30, ge=1, le=365, description="Letzte N Tage (Standard: 30)")
    language: Language = Field(default=Language.DE)
    limit: int = Field(default=MAX_RESULTS_DEFAULT, ge=1, le=MAX_RESULTS_LIMIT)


class GetUpcomingChangesInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    days_ahead: int = Field(default=90, ge=1, le=365, description="Vorausschau in Tagen (Standard: 90)")
    language: Language = Field(default=Language.DE)
    limit: int = Field(default=MAX_RESULTS_DEFAULT, ge=1, le=MAX_RESULTS_LIMIT)


class SearchGazetteInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    keywords: str = Field(
        ...,
        description="Suchbegriff im BBl-Titel, z.B. 'Berufsbildung', 'Datenschutz', 'Volksinitiative'",
        min_length=2, max_length=200, pattern=KEYWORD_PATTERN,
    )
    language: Language = Field(default=Language.DE)
    year: int | None = Field(default=None, ge=1999, le=2030,
                              description="Optional: Nur dieses Publikationsjahr (z.B. 2024)")
    limit: int = Field(default=MAX_RESULTS_DEFAULT, ge=1, le=MAX_RESULTS_LIMIT)


class GetLawHistoryInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    sr_number: str = Field(
        ...,
        description="SR-Nummer, z.B. '235.1' (DSG), '412.10' (BBG), '101' (BV)",
        min_length=1, max_length=20, pattern=SR_NUMBER_PATTERN,
    )
    language: Language = Field(default=Language.DE)


class SearchTreatiesInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    keywords: str | None = Field(
        default=None,
        description="Suchbegriff im Titel, z.B. 'Bildung', 'EU', 'Datenschutz'. Ohne Begriff: neueste Verträge.",
        max_length=200, pattern=KEYWORD_PATTERN,
    )
    language: Language = Field(default=Language.DE)
    limit: int = Field(default=MAX_RESULTS_DEFAULT, ge=1, le=MAX_RESULTS_LIMIT)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool(
    name="fedlex_search_laws",
    description=(
        "Durchsucht die Systematische Rechtssammlung (SR) des Bundes nach Erlasstiteln "
        "und liefert SR-Nummer, Abkürzung, Status und Link.\n"
        "<use_case>Juristische/verwaltungsbezogene Recherche: konsolidiertes Bundesrecht "
        "(Gesetze, Verordnungen, Vereinbarungen) per Stichwort finden.</use_case>\n"
        "<important_notes>Sucht nur im Titel, nicht im Volltext. Standardmässig nur in "
        "Kraft stehende Erlasse (in_force_only=true). Für aufgehobene Erlasse "
        "in_force_only=false setzen. Max. 100 Treffer.</important_notes>\n"
        "<example>keywords='Datenschutz', language='de'</example>"
    ),
    annotations={
        "title": "Erlasse der Systematischen Rechtssammlung (SR) suchen",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def fedlex_search_laws(params: SearchLawsInput, ctx: Context | None = None) -> str:
    """Durchsucht die Systematische Rechtssammlung (SR) des Bundes nach Erlasstiteln."""
    lang = params.language.value
    suffix = LANG_SUFFIX[lang]
    kw = params.keywords.lower()
    await _trace(ctx, "fedlex_search_laws", lang=lang, in_force_only=params.in_force_only)

    in_force_filter = (
        f'\n  ?ca jolux:inForceStatus <{STATUS_IN_FORCE}> .'
        if params.in_force_only else ""
    )

    query = f"""
PREFIX jolux: <http://data.legilux.public.lu/resource/ontology/jolux#>
SELECT DISTINCT ?ca ?title ?titleShort ?srNumber ?inForceStatus WHERE {{
  ?ca a jolux:ConsolidationAbstract ;
      jolux:isRealizedBy ?expr .
  ?expr jolux:title ?title .
  OPTIONAL {{ ?expr jolux:titleShort ?titleShort . }}
  OPTIONAL {{ ?expr jolux:historicalLegalId ?srNumber . }}
  OPTIONAL {{ ?ca jolux:inForceStatus ?inForceStatus . }}
  FILTER(STRENDS(STR(?expr), "{suffix}"))
  FILTER(STRSTARTS(STR(?ca), "https://fedlex.data.admin.ch/eli/cc/"))
  FILTER(CONTAINS(LCASE(STR(?title)), "{sparql_escape(kw)}"))
  {in_force_filter}
}} ORDER BY ?srNumber
LIMIT {params.limit}
"""

    try:
        bindings = await run_sparql(query)

        if not bindings:
            return (
                f"Keine Erlasse für **'{params.keywords}'** gefunden "
                f"[{lang.upper()}, nur gültige: {params.in_force_only}]."
                + no_match_hint(
                    "**Tipps:** Allgemeineren Begriff verwenden | "
                    "`in_force_only=false` für aufgehobene Erlasse | "
                    "Auf Deutsch suchen (vollständigste Abdeckung)"
                )
            )

        out = result_header(len(bindings), f"SR-Suche '{params.keywords}' [{lang.upper()}]")
        for b in bindings:
            uri = val(b, "ca")
            title = val(b, "title", "(kein Titel)")
            short = val(b, "titleShort")
            sr_num = val(b, "srNumber", "–")
            status_uri = val(b, "inForceStatus")
            st = status_label(status_uri) if status_uri else "–"
            url = fedlex_url(uri, lang)

            short_display = f" ({short})" if short else ""
            out += f"### SR {sr_num}: {title}{short_display}\n"
            out += f"- **Status:** {st}\n"
            out += f"- **Link:** [{url}]({url})\n\n"

        out += FEDLEX_SOURCE
        return out

    except Exception as e:
        return await _fail(ctx, "fedlex_search_laws", e)


def _format_law_detail(
    b: dict, sr: str, lang: str, suffix: str, successor: dict | None = None,
) -> str:
    """Formatiert die Detailansicht eines Erlasses als Markdown."""
    uri = val(b, "ca")
    title = val(b, "title", "(kein Titel)")
    short = val(b, "titleShort", "–")
    sr_num = val(b, "srNumber", sr)
    status_uri = val(b, "inForceStatus")
    entry_date = val(b, "entryDate", "–")
    url = fedlex_url(uri, lang)
    st = status_label(status_uri) if status_uri else "–"

    out = f"## SR {sr_num}: {title}\n\n"
    out += "| Feld | Wert |\n|---|---|\n"
    out += f"| **Vollständiger Titel** | {title} |\n"
    out += f"| **Abkürzung** | {short} |\n"
    out += f"| **SR-Nummer** | {sr_num} |\n"
    out += f"| **Status** | {st} |\n"
    out += f"| **Inkrafttreten (aktuelle Fassung)** | {entry_date} |\n"
    out += f"| **Sprache** | {lang.upper()} |\n"
    out += f"\n**Direktlink:** [{url}]({url})\n"
    out += f"\n**Daten-URI:** `{uri}`\n"

    if successor:
        s_uri = val(successor, "ca")
        s_title = val(successor, "title", "(kein Titel)")
        s_short = val(successor, "titleShort", "–")
        s_sr = val(successor, "srNumber", "–")
        s_entry = val(successor, "entryDate", "–")
        s_url = fedlex_url(s_uri, lang)
        out += "\n---\n### ⚠️ Nachfolge-Erlass (in Kraft)\n\n"
        out += "| Feld | Wert |\n|---|---|\n"
        out += f"| **Vollständiger Titel** | {s_title} |\n"
        out += f"| **Abkürzung** | {s_short} |\n"
        if s_sr != "–":
            out += f"| **SR-Nummer** | {s_sr} |\n"
        out += f"| **Inkrafttreten** | {s_entry} |\n"
        out += "| **Status** | ✅ In Kraft |\n"
        out += f"\n**Direktlink:** [{s_url}]({s_url})\n"

    out += FEDLEX_SOURCE
    return out


@mcp.tool(
    name="fedlex_get_law_by_sr",
    description=(
        "Ruft einen Bundeserlass anhand seiner SR-Nummer ab (Detailansicht mit "
        "Titel, Abkürzung, Status, Inkrafttreten, Link).\n"
        "<use_case>Wenn die SR-Nummer bekannt ist (z.B. aus fedlex_search_laws) und "
        "vollständige Metadaten zu einem Erlass gebraucht werden.</use_case>\n"
        "<important_notes>Bei aufgehobenen Erlassen wird — sofern auffindbar — der "
        "Nachfolge-Erlass mitgeliefert. SR-Nummer mit Punkt trennen (235.1).</important_notes>\n"
        "<example>sr_number='235.1'</example>"
    ),
    annotations={
        "title": "Erlass nach SR-Nummer abrufen",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def fedlex_get_law_by_sr(params: GetLawBySrInput, ctx: Context | None = None) -> str:
    """Ruft einen Bundeserlass anhand seiner SR-Nummer ab (Detailansicht)."""
    lang = params.language.value
    suffix = LANG_SUFFIX[lang]
    sr = params.sr_number.strip()
    await _trace(ctx, "fedlex_get_law_by_sr", lang=lang, sr_number=sr)

    query = f"""
PREFIX jolux: <http://data.legilux.public.lu/resource/ontology/jolux#>
SELECT DISTINCT ?ca ?title ?titleShort ?srNumber ?inForceStatus ?entryDate WHERE {{
  ?ca a jolux:ConsolidationAbstract ;
      jolux:isRealizedBy ?expr .
  ?expr jolux:title ?title ;
        jolux:historicalLegalId ?srNumber .
  OPTIONAL {{ ?expr jolux:titleShort ?titleShort . }}
  OPTIONAL {{ ?ca jolux:inForceStatus ?inForceStatus . }}
  OPTIONAL {{ ?ca jolux:dateEntryInForce ?entryDate . }}
  FILTER(STRENDS(STR(?expr), "{suffix}"))
  FILTER(STR(?srNumber) = "{sparql_escape(sr)}")
}} ORDER BY DESC(?entryDate)
LIMIT 10
"""

    try:
        bindings = await run_sparql(query)

        if not bindings:
            return (
                f"Kein Erlass mit SR-Nummer **{sr}** gefunden [{lang.upper()}]."
                + no_match_hint(
                    "**Mögliche Ursachen:**\n"
                    "- SR-Nummer falsch (Punkt als Trennzeichen: '235.1', nicht '235,1')\n"
                    "- Erlass in dieser Sprache nicht vorhanden\n"
                    "- Erlass aufgehoben (mit `in_force_only=false` in `fedlex_search_laws` suchen)"
                )
            )

        # Bevorzuge den gültigen Erlass (In Kraft) gegenüber aufgehobenen Fassungen,
        # da mehrere ConsolidationAbstract-Einträge dieselbe SR-Nummer teilen können
        # (z.B. altes DSG von 1992 und revidiertes nDSG von 2020 unter SR 235.1).
        in_force = [b for b in bindings if val(b, "inForceStatus") == STATUS_IN_FORCE]
        b = in_force[0] if in_force else bindings[0]
        status_uri = val(b, "inForceStatus")

        # Wenn der Erlass nicht mehr in Kraft ist, Nachfolge-Erlass suchen.
        # Einige revidierte Erlasse (z.B. nDSG 2020) haben in Fedlex keine
        # historicalLegalId, sind aber über den Kurztitel (titleShort) auffindbar.
        successor = None
        if status_uri == STATUS_NO_LONGER_FORCE:
            short_name = val(b, "titleShort")
            if short_name:
                succ_query = f"""
PREFIX jolux: <http://data.legilux.public.lu/resource/ontology/jolux#>
SELECT DISTINCT ?ca ?title ?titleShort ?srNumber ?inForceStatus ?entryDate WHERE {{
  ?ca a jolux:ConsolidationAbstract ;
      jolux:isRealizedBy ?expr ;
      jolux:inForceStatus <{STATUS_IN_FORCE}> .
  ?expr jolux:title ?title ;
        jolux:titleShort ?titleShort .
  OPTIONAL {{ ?expr jolux:historicalLegalId ?srNumber . }}
  OPTIONAL {{ ?ca jolux:dateEntryInForce ?entryDate . }}
  FILTER(STRENDS(STR(?expr), "{suffix}"))
  FILTER(STRSTARTS(STR(?ca), "https://fedlex.data.admin.ch/eli/cc/"))
  FILTER(STR(?titleShort) = "{sparql_escape(short_name)}")
}} LIMIT 1
"""
                succ_bindings = await run_sparql(succ_query)
                if succ_bindings:
                    successor = succ_bindings[0]

        return _format_law_detail(b, sr, lang, suffix, successor)

    except Exception as e:
        return await _fail(ctx, "fedlex_get_law_by_sr", e)


@mcp.tool(
    name="fedlex_get_recent_publications",
    description=(
        "Ruft die neuesten Publikationen der Amtlichen Sammlung (AS) ab.\n"
        "<use_case>Regelmässiges Monitoring von Rechtsänderungen — was wurde in den "
        "letzten N Tagen neu publiziert oder geändert?</use_case>\n"
        "<important_notes>Liefert Erstpublikationen (AS), nicht den konsolidierten "
        "Stand. Zeitfenster über `days` (1–365).</important_notes>\n"
        "<example>days=30, language='de'</example>"
    ),
    annotations={
        "title": "Neueste Bundesrechtspublikationen (AS) abrufen",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def fedlex_get_recent_publications(
    params: GetRecentPublicationsInput, ctx: Context | None = None
) -> str:
    """Ruft die neuesten Publikationen der Amtlichen Sammlung (AS) ab."""
    lang = params.language.value
    suffix = LANG_SUFFIX[lang]
    since_date = (date.today() - timedelta(days=params.days)).isoformat()
    await _trace(ctx, "fedlex_get_recent_publications", lang=lang, days=params.days)

    query = f"""
PREFIX jolux: <http://data.legilux.public.lu/resource/ontology/jolux#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
SELECT DISTINCT ?act ?title ?pubDate WHERE {{
  ?act a jolux:Act ;
       jolux:isRealizedBy ?expr ;
       jolux:publicationDate ?pubDate .
  ?expr jolux:title ?title .
  FILTER(STRENDS(STR(?expr), "{suffix}"))
  FILTER(xsd:date(?pubDate) >= "{since_date}"^^xsd:date)
}} ORDER BY DESC(?pubDate)
LIMIT {params.limit}
"""

    try:
        bindings = await run_sparql(query)

        if not bindings:
            return (
                f"Keine Publikationen in den letzten {params.days} Tagen gefunden [{lang.upper()}]."
                + no_match_hint("**Tipp:** `days` erhöhen, z.B. `days=90`.")
            )

        out = result_header(len(bindings), f"AS-Publikationen seit {since_date} [{lang.upper()}]")
        for b in bindings:
            uri = val(b, "act")
            title = val(b, "title", "(kein Titel)")
            pub_date = val(b, "pubDate", "–")
            url = fedlex_url(uri, lang)
            out += f"### {pub_date}\n**{title}**\n[{url}]({url})\n\n"

        out += FEDLEX_SOURCE
        return out

    except Exception as e:
        return await _fail(ctx, "fedlex_get_recent_publications", e)


@mcp.tool(
    name="fedlex_get_upcoming_changes",
    description=(
        "Ruft Erlasse ab, die in den nächsten N Tagen in Kraft treten.\n"
        "<use_case>Proaktives Rechtsmonitoring für Verwaltung und Schulen: welche "
        "Gesetze werden bald wirksam (Datenschutz, Bildung, Regulierung)?</use_case>\n"
        "<important_notes>Berücksichtigt nur künftige Inkraftsetzungen (dateEntryInForce "
        "> heute). Fenster über `days_ahead` (1–365).</important_notes>\n"
        "<example>days_ahead=90</example>"
    ),
    annotations={
        "title": "Bevorstehende Rechtsänderungen abrufen",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def fedlex_get_upcoming_changes(
    params: GetUpcomingChangesInput, ctx: Context | None = None
) -> str:
    """Ruft Erlasse ab, die in den nächsten N Tagen in Kraft treten."""
    lang = params.language.value
    suffix = LANG_SUFFIX[lang]
    today = date.today().isoformat()
    future = (date.today() + timedelta(days=params.days_ahead)).isoformat()
    await _trace(ctx, "fedlex_get_upcoming_changes", lang=lang, days_ahead=params.days_ahead)

    query = f"""
PREFIX jolux: <http://data.legilux.public.lu/resource/ontology/jolux#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
SELECT DISTINCT ?ca ?title ?titleShort ?srNumber ?entryDate WHERE {{
  ?ca a jolux:ConsolidationAbstract ;
      jolux:isRealizedBy ?expr ;
      jolux:dateEntryInForce ?entryDate .
  ?expr jolux:title ?title .
  OPTIONAL {{ ?expr jolux:titleShort ?titleShort . }}
  OPTIONAL {{ ?expr jolux:historicalLegalId ?srNumber . }}
  FILTER(STRENDS(STR(?expr), "{suffix}"))
  FILTER(STRSTARTS(STR(?ca), "https://fedlex.data.admin.ch/eli/cc/"))
  FILTER(xsd:date(?entryDate) > "{today}"^^xsd:date)
  FILTER(xsd:date(?entryDate) <= "{future}"^^xsd:date)
}} ORDER BY ASC(?entryDate)
LIMIT {params.limit}
"""

    try:
        bindings = await run_sparql(query)

        if not bindings:
            return (
                f"Keine bevorstehenden Rechtsänderungen in den nächsten "
                f"{params.days_ahead} Tagen [{lang.upper()}]."
                + no_match_hint("**Tipp:** `days_ahead` erhöhen, z.B. `days_ahead=180`.")
            )

        out = result_header(
            len(bindings), f"Bevorstehende Änderungen bis {future} [{lang.upper()}]"
        )
        for b in bindings:
            uri = val(b, "ca")
            title = val(b, "title", "(kein Titel)")
            short = val(b, "titleShort")
            sr_num = val(b, "srNumber", "–")
            entry = val(b, "entryDate", "–")
            url = fedlex_url(uri, lang)

            short_display = f" ({short})" if short else ""
            sr_display = f"SR {sr_num}" if sr_num != "–" else "SR –"
            out += f"### 📅 {entry} — {sr_display}: {title}{short_display}\n"
            out += f"[{url}]({url})\n\n"

        out += FEDLEX_SOURCE
        return out

    except Exception as e:
        return await _fail(ctx, "fedlex_get_upcoming_changes", e)


@mcp.tool(
    name="fedlex_search_gazette",
    description=(
        "Durchsucht das Bundesblatt (BBl) nach amtlichen Publikationen.\n"
        "<use_case>Politisches Frühwarnsystem: Botschaften des Bundesrates, "
        "Parlaments- und Volksinitiativen, Vernehmlassungen.</use_case>\n"
        "<important_notes>BBl ≠ konsolidiertes Recht — für geltende Gesetze "
        "`fedlex_search_laws` nutzen. Optional auf ein Jahr einschränken.</important_notes>\n"
        "<example>keywords='Berufsbildung', year=2024</example>"
    ),
    annotations={
        "title": "Im Bundesblatt (BBl) suchen",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def fedlex_search_gazette(params: SearchGazetteInput, ctx: Context | None = None) -> str:
    """Durchsucht das Bundesblatt (BBl) nach amtlichen Publikationen."""
    lang = params.language.value
    suffix = LANG_SUFFIX[lang]
    kw = params.keywords.lower()
    await _trace(ctx, "fedlex_search_gazette", lang=lang, year=params.year)

    year_filter = (
        f'FILTER(STRSTARTS(STR(?pubDate), "{params.year}"))'
        if params.year else ""
    )

    query = f"""
PREFIX jolux: <http://data.legilux.public.lu/resource/ontology/jolux#>
SELECT DISTINCT ?act ?title ?pubDate WHERE {{
  ?act a jolux:Act ;
       jolux:isRealizedBy ?expr ;
       jolux:publicationDate ?pubDate .
  ?expr jolux:title ?title .
  FILTER(STRENDS(STR(?expr), "{suffix}"))
  FILTER(STRSTARTS(STR(?act), "https://fedlex.data.admin.ch/eli/fga/"))
  FILTER(CONTAINS(LCASE(STR(?title)), "{sparql_escape(kw)}"))
  {year_filter}
}} ORDER BY DESC(?pubDate)
LIMIT {params.limit}
"""

    try:
        bindings = await run_sparql(query)

        yr_txt = f" ({params.year})" if params.year else ""
        if not bindings:
            return (
                f"Keine BBl-Publikation für **'{params.keywords}'**{yr_txt} [{lang.upper()}]."
                + no_match_hint(
                    "**Tipps:** Allgemeineren Begriff verwenden | "
                    "Jahr weglassen | `fedlex_search_laws` für konsolidiertes Recht"
                )
            )

        out = result_header(
            len(bindings), f"BBl-Suche '{params.keywords}'{yr_txt} [{lang.upper()}]"
        )
        for b in bindings:
            uri = val(b, "act")
            title = val(b, "title", "(kein Titel)")
            pub_date = val(b, "pubDate", "–")
            url = fedlex_url(uri, lang)
            out += f"### {pub_date}\n**{title}**\n[{url}]({url})\n\n"

        out += FEDLEX_SOURCE
        return out

    except Exception as e:
        return await _fail(ctx, "fedlex_search_gazette", e)


@mcp.tool(
    name="fedlex_get_law_history",
    description=(
        "Ruft die Versionsgeschichte (alle konsolidierten Fassungen) eines Erlasses ab.\n"
        "<use_case>Nachvollziehen, wann welche Fassung galt — z.B. alte vs. revidierte "
        "Gesetzesfassung (DSG 235.1: 1992 vs. nDSG 2020).</use_case>\n"
        "<important_notes>Sortiert nach Inkrafttreten absteigend, max. 50 Fassungen. "
        "SR-Nummer mit Punkt trennen.</important_notes>\n"
        "<example>sr_number='235.1'</example>"
    ),
    annotations={
        "title": "Versionsgeschichte eines Erlasses abrufen",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def fedlex_get_law_history(params: GetLawHistoryInput, ctx: Context | None = None) -> str:
    """Ruft die Versionsgeschichte (alle konsolidierten Fassungen) eines Erlasses ab."""
    lang = params.language.value
    suffix = LANG_SUFFIX[lang]
    sr = params.sr_number.strip()
    await _trace(ctx, "fedlex_get_law_history", lang=lang, sr_number=sr)

    query = f"""
PREFIX jolux: <http://data.legilux.public.lu/resource/ontology/jolux#>
SELECT DISTINCT ?ca ?title ?srNumber ?entryDate ?inForceStatus WHERE {{
  ?ca a jolux:ConsolidationAbstract ;
      jolux:isRealizedBy ?expr .
  ?expr jolux:title ?title ;
        jolux:historicalLegalId ?srNumber .
  OPTIONAL {{ ?ca jolux:dateEntryInForce ?entryDate . }}
  OPTIONAL {{ ?ca jolux:inForceStatus ?inForceStatus . }}
  FILTER(STRENDS(STR(?expr), "{suffix}"))
  FILTER(STR(?srNumber) = "{sparql_escape(sr)}")
}} ORDER BY DESC(?entryDate)
LIMIT 50
"""

    try:
        bindings = await run_sparql(query)

        if not bindings:
            return (
                f"Keine Versionsgeschichte für SR-Nummer **{sr}** [{lang.upper()}]."
                + no_match_hint("**Tipp:** SR-Nummer mit `fedlex_get_law_by_sr` überprüfen.")
            )

        title_sample = val(bindings[0], "title", sr)
        out = f"## Versionsgeschichte: {title_sample}\n"
        out += f"**SR {sr}** | {lang.upper()}\n\n"
        out += "| Fassung | Inkrafttreten | Status | Link |\n"
        out += "|---|---|---|---|\n"

        for i, b in enumerate(bindings):
            uri = val(b, "ca")
            entry = val(b, "entryDate", "–")
            status_uri = val(b, "inForceStatus")
            url = fedlex_url(uri, lang)
            st = status_label(status_uri) if status_uri else "–"
            out += f"| v{len(bindings) - i} | {entry} | {st} | [→]({url}) |\n"

        out += FEDLEX_SOURCE
        return out

    except Exception as e:
        return await _fail(ctx, "fedlex_get_law_history", e)


@mcp.tool(
    name="fedlex_search_treaties",
    description=(
        "Sucht internationale Staatsverträge der Schweiz (SR-Nummern beginnen mit '0.').\n"
        "<use_case>Recherche zu bi-/multilateralen Abkommen: EU-Bilaterale, "
        "Doppelbesteuerung, Europarats-Konventionen (Datenschutz, Menschenrechte).</use_case>\n"
        "<important_notes>Ohne Suchbegriff werden die neuesten Verträge gelistet. "
        "Sucht nur im Titel.</important_notes>\n"
        "<example>keywords='Datenschutz'</example>"
    ),
    annotations={
        "title": "Staatsverträge der Schweiz suchen",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def fedlex_search_treaties(params: SearchTreatiesInput, ctx: Context | None = None) -> str:
    """Sucht internationale Staatsverträge der Schweiz (SR-Nummern beginnen mit '0.')."""
    lang = params.language.value
    suffix = LANG_SUFFIX[lang]
    await _trace(ctx, "fedlex_search_treaties", lang=lang, has_keywords=bool(params.keywords))

    kw_filter = (
        f'FILTER(CONTAINS(LCASE(STR(?title)), "{sparql_escape(params.keywords.lower())}"))'
        if params.keywords else ""
    )

    query = f"""
PREFIX jolux: <http://data.legilux.public.lu/resource/ontology/jolux#>
SELECT DISTINCT ?ca ?title ?srNumber ?entryDate WHERE {{
  ?ca a jolux:ConsolidationAbstract ;
      jolux:isRealizedBy ?expr .
  ?expr jolux:title ?title ;
        jolux:historicalLegalId ?srNumber .
  OPTIONAL {{ ?ca jolux:dateEntryInForce ?entryDate . }}
  FILTER(STRENDS(STR(?expr), "{suffix}"))
  FILTER(STRSTARTS(STR(?srNumber), "0."))
  {kw_filter}
}} ORDER BY ?srNumber
LIMIT {params.limit}
"""

    try:
        bindings = await run_sparql(query)

        kw_txt = f"'{params.keywords}'" if params.keywords else "alle"
        if not bindings:
            return (
                f"Keine Staatsverträge für {kw_txt} [{lang.upper()}]."
                + no_match_hint("**Tipp:** Suchbegriff anpassen oder weglassen.")
            )

        out = result_header(len(bindings), f"Staatsverträge {kw_txt} [{lang.upper()}]")
        for b in bindings:
            uri = val(b, "ca")
            title = val(b, "title", "(kein Titel)")
            sr_num = val(b, "srNumber", "–")
            entry = val(b, "entryDate", "–")
            url = fedlex_url(uri, lang)
            out += f"### SR {sr_num}: {title}\n"
            out += f"- **Inkrafttreten:** {entry}\n"
            out += f"- **Link:** [{url}]({url})\n\n"

        out += FEDLEX_SOURCE
        return out

    except Exception as e:
        return await _fail(ctx, "fedlex_search_treaties", e)


# ---------------------------------------------------------------------------
# Resources
# ---------------------------------------------------------------------------


@mcp.resource("fedlex://sr/{sr_number}")
async def get_sr_resource(sr_number: str) -> str:
    """Ressource: Erlass der SR per SR-Nummer (Deutsch)."""
    return await fedlex_get_law_by_sr(
        GetLawBySrInput(sr_number=sr_number, language=Language.DE)
    )


@mcp.resource("fedlex://info")
async def get_server_info() -> str:
    """Ressource: Metadaten und Capabilities des Fedlex MCP Servers."""
    return json.dumps(
        {
            "name": "Fedlex MCP Server",
            "version": "1.0.0",
            "description": "Zugriff auf das Schweizer Bundesrecht via Fedlex SPARQL",
            "sparql_endpoint": SPARQL_ENDPOINT,
            "data_source": FEDLEX_BASE_URL,
            "license": "Freie Wiederverwendung (kommerziell und andere Zwecke)",
            "tools": [
                "fedlex_search_laws",
                "fedlex_get_law_by_sr",
                "fedlex_get_recent_publications",
                "fedlex_get_upcoming_changes",
                "fedlex_search_gazette",
                "fedlex_get_law_history",
                "fedlex_search_treaties",
            ],
            "languages": ["de", "fr", "it", "rm"],
            "data_model": "JOLux Ontology — jolux:ConsolidationAbstract + jolux:Expression",
        },
        ensure_ascii=False,
        indent=2,
    )


# ---------------------------------------------------------------------------
# Entry point — Dual Transport (Settings-/Env-gesteuert, ARCH-004 / SCALE-001)
# ---------------------------------------------------------------------------


def _run_http() -> None:
    """Startet den Streamable-HTTP-Transport mit CORS (SDK-004).

    CORS exponiert den `Mcp-Session-Id`-Header, ohne den Browser-basierte
    MCP-Clients keine Folge-Requests an dieselbe Session schicken können.
    """
    import uvicorn
    from starlette.middleware.cors import CORSMiddleware

    origins = [o.strip() for o in settings.allowed_origins.split(",") if o.strip()]

    app = mcp.streamable_http_app()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Mcp-Session-Id"],
        expose_headers=["Mcp-Session-Id"],
    )

    host = os.environ.get("FEDLEX_HOST", settings.host)
    port = settings.port
    for i, arg in enumerate(sys.argv):
        if arg == "--port" and i + 1 < len(sys.argv):
            port = int(sys.argv[i + 1])
    # Cloud-Plattformen (Render etc.) geben den Port via $PORT vor.
    port = int(os.environ.get("PORT", port))
    log.info("http_start", host=host, port=port, cors_origins=origins)
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    use_http = settings.transport in ("streamable-http", "http", "sse") or "--http" in sys.argv
    if use_http:
        _run_http()
    else:
        mcp.run()

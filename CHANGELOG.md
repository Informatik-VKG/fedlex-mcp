# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added (Sprint 2 audit remediation)
- **Structured logging** with `structlog` — JSON to stderr, per-call bound
  context (`OBS-003`, keeps stdout clean for stdio per `OBS-004`).
- **MCP `Context` injection** in all tools (`ctx.info`/`ctx.error`) for
  client-visible progress and error reporting (`SDK-003`).
- **Use-case tags** (`<use_case>`/`<important_notes>`/`<example>`) in every tool
  description to improve LLM tool selection (`ARCH-002`).
- Empty results now carry a `match_type: none` marker (`ARCH-003`).
- `.gitignore` and a gitleaks secret-scan CI workflow (`ARCH-005`).
- `.github/dependabot.yml` (monthly pip + actions updates) and a README
  "MCP Protocol Version" section (`ARCH-012`).
- README "Project Phase" section declaring Phase 1 / read-only (`OPS-003`).
- Multi-stage, non-root `Dockerfile` + `.dockerignore` (`SCALE-004`).

### Changed
- **Shared HTTP client via FastMCP lifespan** — a single `httpx.AsyncClient` is now
  created once per server lifecycle instead of per tool call (audit `SDK-001`).
- **Settings/env-driven transport** — transport, host, port and CORS origins are
  configured via `Settings` / `FEDLEX_*` env vars instead of an `argv` flag
  (`ARCH-004`, `SCALE-001`). The `--http` flag still works for backward compatibility.

### Added
- **CORS for Streamable HTTP** exposing the `Mcp-Session-Id` header, required for
  browser-based MCP clients (`SDK-004`).
- **Input hardening** — `keywords`/`sr_number` now carry whitelist patterns and all
  user input is escaped before SPARQL interpolation, closing a query-injection
  vector (`SEC-004`, `SEC-018`).
- **Code-layer egress allow-list** (`ALLOWED_EGRESS_HOSTS`) and stderr logging
  (`SEC-021`, `OBS-004`).
- **Real test suite** — 40 offline `respx`-mocked unit tests (tools, validation,
  error masking) plus a `live` smoke test (`OPS-001`).

### Fixed
- Error handler no longer echoes raw exception detail to the LLM; internals are
  logged server-side only (`OBS-001`, `OBS-002`).

## [0.1.0] - 2026-03-31

### Added
- Initial release
- **7 tools**: `fedlex_search_laws`, `fedlex_get_law_by_sr`, `fedlex_get_recent_publications`, `fedlex_get_upcoming_changes`, `fedlex_search_gazette`, `fedlex_get_law_history`, `fedlex_search_treaties`
- **2 resources**: `fedlex://sr/{sr_number}`, `fedlex://info`
- SPARQL-powered access to Fedlex linked data endpoint
- 4 language support (de, fr, it, rm)
- Dual transport: stdio (Claude Desktop) + Streamable HTTP (cloud/Render.com)
- GitHub Actions CI (Python 3.11, 3.12, 3.13)
- Bilingual documentation (EN/DE)

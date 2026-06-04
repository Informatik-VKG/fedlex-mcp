# Security Policy & Posture

[:de: Deutsche Version](SECURITY.de.md)

`fedlex-mcp` was hardened against the internal MCP best-practice audit
catalogue. This document summarises the security posture and records the
**accepted-risk** decisions for controls that are deliberately handled at the
portfolio/gateway layer rather than inside this single server.

## Reporting a vulnerability

Please open a private security advisory on the GitHub repository, or contact the
maintainer listed in `README.md`. Do not file public issues for exploitable
vulnerabilities.

## Posture summary

This is a **read-only**, **no-PII**, **public-open-data** MCP server. All 7
tools only issue SPARQL SELECT queries against the Fedlex endpoint
(`fedlex.data.admin.ch`). Hardening already in place:

| Area | Control |
|---|---|
| Egress | HTTPS-enforced allow-list to `fedlex.data.admin.ch` only, with IP-block validation against SSRF (SEC-004/021; see ADR 0001) |
| TLS | Verification on by default; only disablable in a `dev` environment (SEC-005) |
| Binding | Network transports default to `127.0.0.1` (SEC-016) |
| Transport | Streamable HTTP with CORS exposing only `Mcp-Session-Id` (SDK-004) |
| Input | Pydantic v2 strict validation + XML escaping at all boundaries (SEC-018) |
| Secrets | Env-vars only, `.gitignore` guards `.env`, no hardcoded secrets (ARCH-005/SEC-013) |
| Errors | Upstream bodies logged to stderr, never forwarded to the model (OBS-002) |
| Stdout | Reserved for the JSON-RPC stream; logging pinned to stderr (OBS-004) |
| Tool allow-list | Server-side, default-deny allow-list via `FEDLEX_ENABLED_TOOLS` (SEC-014) |
| Tool integrity | SHA-256 tool-hash pinning verified at startup + in CI against `tool-definitions.lock.json` (SEC-022) |

The latest audit run (`2026-06-03T100302-Z-fedlex-mcp`) reports
**production-ready**: 41 pass · 0 fail · 2 partial (non-blocking) · 1 n/a.
See `audits/` for the full report and `CHANGELOG.md` for the hardening history.

## Accepted risks (portfolio-level controls)

The following audit checks are **not** fully implemented inside this server by
design. They are portfolio-wide concerns best enforced at an MCP gateway / host
layer, and the residual risk here is low because the server is read-only and
only reaches a single trusted public-data provider.

These decisions are formally recorded in
[ADR 0002 — Authentication & gateway posture](docs/adr/0002-auth-and-gateway-posture.md),
with the compensating controls and re-evaluation triggers below.

### SEC-009 — Session crypto-binding → N/A (no auth)

**Status:** not applicable — see ADR 0002.
There is no user identity to bind a session to: `fedlex-mcp` exposes public open
data with no authentication. Binding a session to a validated OAuth `sub` claim
is only meaningful once authentication exists.

### SEC-015 — Pre-flight tool-poisoning detection

**Status:** accepted risk (portfolio-level) — see ADR 0002 — with a local guard in place.
Tool-poisoning (malicious tool descriptions / rug-pulls) is a supply-chain and
host-side concern. This server's tool definitions are version-controlled,
authored in-repo, and reviewed via PR; there is no dynamic/remote tool
registration. Locally, **SEC-022 tool-hash pinning**
(`tool-definitions.lock.json`) detects any drift in the tool surface at startup
and in CI. Cross-server poisoning detection remains a gateway/host
responsibility tracked at the portfolio level.

## Re-evaluation triggers

These acceptances should be revisited if the server ever:

- gains **write** capability or starts processing **PII**, or
- adds an **authentication** model (then implement SEC-009: bound, TTL'd,
  server-side-invalidated session IDs and re-audit before merge), or
- registers tools **dynamically** / from remote sources, or
- is aggregated behind a shared MCP gateway (then enable the gateway's tool
  allow-listing and tool-poisoning detection).

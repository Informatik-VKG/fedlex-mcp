# ADR 0001 — Egress allow-list, lethal-trifecta posture, DNS-rebinding risk

**Status:** Accepted · **Date:** 2026-06-03

Context comes from the `mcp-audit-skill` audit (SEC-019, SEC-021, SEC-005).

## Context

`fedlex-mcp` is a read-only MCP server over public open data. It makes outbound
HTTP requests to exactly one host — the Fedlex SPARQL endpoint — and exposes no
write, send, or filesystem capabilities.

## Decision

### Egress allow-list (SEC-021)
Outbound traffic is constrained at the code layer to a single host via
`ALLOWED_EGRESS_HOSTS = frozenset({"fedlex.data.admin.ch"})`. `assert_host_allowed()`
is called before every request in `_execute_sparql`. The host set is a frozenset
(not runtime-mutable). A network-layer egress policy (NetworkPolicy / security
group) SHOULD additionally be applied at deploy time, but is out of repo scope.

### Lethal trifecta (SEC-019)
The "lethal trifecta" is: (1) access to private data, (2) ability to exfiltrate /
externally communicate, (3) exposure to untrusted content. This server holds at
most **one** leg:
- **Private data:** none — all data is public Fedlex open data.
- **Exfiltration:** none — it only *reads* from one fixed endpoint; it never
  sends user-controlled data outward.
- **Untrusted content:** it processes public legal text only.

No two legs co-occur, so the trifecta risk is not present. Adding any
write/send capability MUST trigger a re-audit before merge.

### DNS rebinding (SEC-005) — accepted risk
Full DNS pinning (resolve-once + connect-by-IP with SNI/Host preserved) is **not**
implemented. Rationale: the only egress target is a single, fixed, trusted
government endpoint reached over HTTPS with standard certificate validation; the
practical DNS-rebinding/TOCTOU risk is negligible. The `assert_host_allowed`
check provides defense-in-depth at the hostname layer. This risk is revisited if
the server ever talks to user-supplied or multiple hosts.

## Consequences

- Egress is auditable and fails closed for any non-allow-listed host.
- The trifecta assessment is documented and must be re-evaluated on capability
  changes.
- DNS-rebinding hardening is deferred deliberately, with a clear trigger to
  revisit.

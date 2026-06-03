# Deployment

`fedlex-mcp` is read-only over public open data and ships with two deployment
shapes.

## 1. Single instance (default)

stdio (Claude Desktop) or a single Streamable-HTTP process (e.g. Render). No
sticky routing or shared session store is needed because all sessions live in
one process. This is the recommended shape for the current scope.

```bash
# stdio
python -m fedlex_mcp.server
# Streamable HTTP
FEDLEX_TRANSPORT=streamable-http FEDLEX_HOST=0.0.0.0 PORT=8000 python -m fedlex_mcp.server
```

## 2. Horizontally scaled (multi-instance)

When you run more than one replica, MCP Streamable-HTTP sessions must stick to
the replica that created them (the session manager is in-process). Two
ready-to-use edge configs are provided:

| File | Resolves | How |
|---|---|---|
| [`deploy/kubernetes.yaml`](../deploy/kubernetes.yaml) | **SCALE-002/003**, **SCALE-006**, **SEC-007** | nginx Ingress routes by `Mcp-Session-Id` (`upstream-hash-by: $http_mcp_session_id`) with cookie-affinity fallback; resource requests/limits; hardened `securityContext`. |
| [`deploy/haproxy.cfg`](../deploy/haproxy.cfg) | **SCALE-002/003** | stick-table keyed on `Mcp-Session-Id`, 100k entries, 24h TTL, health-checked failover. |

If you prefer stateless replicas over sticky routing, put a shared session
store (Redis / Cloudflare Durable Objects) in front — but for this server's
load profile, sticky routing is simpler and sufficient.

## Container hardening (SEC-007)

The [`Dockerfile`](../Dockerfile) builds a non-root (`UID 10001`), slim,
multi-stage image. The Kubernetes manifest adds the runtime controls:

- `runAsNonRoot: true`, `allowPrivilegeEscalation: false`
- `readOnlyRootFilesystem: true` (+ a `tmpfs` `/tmp`)
- `capabilities.drop: ["ALL"]`, `seccompProfile: RuntimeDefault`

## Resource limits (SCALE-006)

CPU/memory **requests < limits** (burst-friendly) are set in the manifest. For
workloads with many concurrent outbound SPARQL calls, raise the file-descriptor
budget (`ulimit -n >= 4096`) via the container runtime / pod settings.

## Auth & gateway posture

Authentication, per-team tool allow-listing and tool-poisoning detection are
covered in [ADR 0002](adr/0002-auth-and-gateway-posture.md). The server ships a
defense-in-depth tool allow-list:

```bash
# default-deny: expose only these two tools
FEDLEX_ENABLED_TOOLS="fedlex_search_laws,fedlex_get_law_by_sr" python -m fedlex_mcp.server
```

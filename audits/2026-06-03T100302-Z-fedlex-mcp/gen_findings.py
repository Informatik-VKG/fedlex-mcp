#!/usr/bin/env python3
"""Generate finding docs for fail/partial checks from verification-results + catalog.

Reads the canonical verification-results.json (evidence + gaps per check) and
pulls Title / Description / Remediation / Effort straight from the catalog
check files, so nothing is hallucinated. One file per fail/partial check,
named <CHECK-ID>-<slug>.md as build_report.py expects.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

AUDIT_DIR = Path(__file__).resolve().parent
CHECKS_DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/mcp-audit-skill/checks")
FINDINGS_DIR = AUDIT_DIR / "findings"
FINDINGS_DIR.mkdir(exist_ok=True)

vr = json.loads((AUDIT_DIR / "verification-results.json").read_text(encoding="utf-8"))
summary = json.loads((AUDIT_DIR / "summary.json").read_text(encoding="utf-8"))
expected = summary["findings"]["expected_ids"]


def frontmatter(text: str) -> dict:
    m = re.search(r"^---\n(.*?)\n---", text, re.DOTALL)
    fm = {}
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                fm[k.strip()] = v.strip().strip('"')
    return fm


def section(text: str, name: str) -> str:
    m = re.search(rf"^## {re.escape(name)}\n(.*?)(?=^## |\Z)", text, re.DOTALL | re.MULTILINE)
    return m.group(1).strip() if m else ""


def slug(title: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return s[:40]


for cid in expected:
    chk = (CHECKS_DIR / f"{cid}.md").read_text(encoding="utf-8")
    fm = frontmatter(chk)
    title = fm.get("title", cid)
    severity = fm.get("severity", "")
    pdf_ref = fm.get("pdf_ref", "")
    res = vr["results"][cid]
    status = res["status"]
    evidence = res.get("evidence", [])
    gaps = res.get("gaps", [])

    desc = section(chk, "Description")
    remediation = section(chk, "Remediation")
    effort = section(chk, "Effort")

    # keep description short
    desc_short = " ".join(desc.split())
    if len(desc_short) > 600:
        desc_short = desc_short[:600].rsplit(" ", 1)[0] + " …"

    ev_md = "\n".join(f"- {e}" for e in evidence) or "- (keine)"
    gap_md = "\n".join(f"- {g}" for g in gaps) or "- (keine)"

    doc = f"""## Finding: {cid} — {title}

**Severity:** {severity}
**Status:** Open
**Server:** fedlex-mcp
**Check-Reference:** {cid}
**PDF-Reference:** {pdf_ref}
**Verifikations-Status:** {status}

### Observed Behavior

{ev_md}

### Gaps / Abweichung vom Standard

{gap_md}

### Risk Description

{desc_short}

### Remediation

{remediation if remediation else '_Remediation aus Check-File generisch — siehe Katalog ' + cid + '._'}

### Effort Estimate

{effort if effort else 'S'}
"""
    out = FINDINGS_DIR / f"{cid}-{slug(title)}.md"
    out.write_text(doc, encoding="utf-8")
    print(f"wrote {out.name}")

print(f"\n{len(expected)} finding docs generated.")

#!/usr/bin/env python3
"""One-off: save weekly LinkedIn MCP + Google raw for 2026-08-25 run."""
import json
from pathlib import Path

RUNS = Path(__file__).resolve().parent
ROOT = RUNS.parent

# MCP responses captured from CallDynamicTool (period=past-week)
linkedin_payload = {
    "period_days": 7,
    "queries": []
}

# Load from inline - we'll write MCP files separately
for fname, meta in [
    ("mcp-li-q01-ai-engineer-latam.json", {"query": "ai engineer latam", "role_keyword": "ai engineer", "region": "latam"}),
    ("mcp-li-q02-ai-engineer-worldwide.json", {"query": "ai engineer worldwide", "role_keyword": "ai engineer", "region": "worldwide"}),
    ("mcp-li-q03-agent-engineer-latam.json", {"query": "agent engineer latam", "role_keyword": "agent engineer", "region": "latam"}),
    ("mcp-li-q04-agent-engineer-worldwide.json", {"query": "agent engineer worldwide", "role_keyword": "agent engineer", "region": "worldwide"}),
    ("mcp-li-q05-agentic-engineer-latam.json", {"query": "agentic engineer latam", "role_keyword": "agentic engineer", "region": "latam"}),
    ("mcp-li-q06-agentic-engineer-worldwide.json", {"query": "agentic engineer worldwide", "role_keyword": "agentic engineer", "region": "worldwide"}),
]:
    p = RUNS / fname
    if p.exists():
        block = dict(meta)
        block["mcp_response"] = json.loads(p.read_text())
        linkedin_payload["queries"].append(block)

out = RUNS / "linkedin-raw-2026-08-25T14-25.json"
out.write_text(json.dumps(linkedin_payload, indent=2, ensure_ascii=False) + "\n")
print("linkedin raw:", out, "queries:", len(linkedin_payload["queries"]))

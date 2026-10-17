#!/usr/bin/env python3
"""Read-only search planning and evidence gates; search remains a host tool."""
import importlib.util
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[4]
spec = importlib.util.spec_from_file_location(
    "public_research", ROOT / ".agents/skills/work-context/scripts/research.py")
research = importlib.util.module_from_spec(spec)
spec.loader.exec_module(research)
Error = research.Error
TIERS = ("builtin", "official", "community", "github")


def require(condition, message="invalid_request"):
    if not condition:
        raise Error(message)


def strings(value, maximum=12):
    return (isinstance(value, list) and len(value) <= maximum and
            all(research.text(x) for x in value))


def sources(value, as_of):
    # Reuse reference/date/URL validation. This checks metadata, not the web evidence.
    research.validate({"as_of": as_of, "scope": "Evidence metadata",
                       "sources": value, "findings": [],
                       "coverage": {"direct": [], "adjacent": [], "counter": [], "gaps": []}})
    return {x["id"] for x in value}


def refs(value, ids, required=False):
    return (strings(value) and len(value) == len(set(value)) and
            all(x in ids for x in value) and (bool(value) or not required))


def locator(value):
    require(research.text(value), "invalid_locator")
    try:
        u = urlsplit(value)
        require(u.scheme in {"https", "http"} and u.hostname and
                not u.username and not u.password, "invalid_locator")
        return (u.scheme.lower(), u.hostname.lower(), u.port,
                u.path.rstrip("/"), u.query)
    except ValueError:
        raise Error("invalid_locator")


def plan(req):
    require(set(req) == {"action", "task", "host"})
    require(research.text(req["task"], 300) and research.text(req["host"], 100))
    task, host = req["task"], req["host"]
    return {"ok": True, "search_order": list(TIERS), "stages": [
        {"tier": "builtin", "query": f"Inspect enabled {host} capabilities for: {task}"},
        {"tier": "official", "query": f"{host} {task} official plugin skill MCP"},
        {"tier": "community", "query": f"{task} skill MCP registry"},
        {"tier": "github", "query": f"{task} agent skill MCP in:name,description,readme"}],
        "max_initial_candidates": 5, "network_executed": False,
        "note": "Send only a public task description. Adapt query language. Stop when a sufficient existing capability is verified."}


def evaluate(req):
    require(set(req) == {"action", "host", "as_of", "sources", "candidates"})
    require(research.text(req["host"], 100))
    ids = sources(req["sources"], req["as_of"])
    candidates = req["candidates"]
    require(isinstance(candidates, list) and len(candidates) <= 8)
    seen, locations, results = set(), set(), []
    keys = {"id", "name", "tier", "kind", "fit", "compatibility", "account", "cost",
            "license", "permissions", "data_flow", "source_ids", "checks", "blockers", "locator"}
    for c in candidates:
        require(isinstance(c, dict) and set(c) == keys, "invalid_candidate")
        require(all(research.text(c[k]) for k in ("id", "name", "fit", "license", "data_flow")), "invalid_candidate")
        require(c["id"] not in seen, "duplicate_candidate")
        seen.add(c["id"])
        location = locator(c["locator"])
        require(location not in locations, "duplicate_locator")
        locations.add(location)
        require(isinstance(c["tier"], str) and c["tier"] in TIERS, "invalid_candidate")
        require(isinstance(c["kind"], str) and c["kind"] in {"builtin", "skill", "plugin", "mcp", "application", "framework"}, "invalid_candidate")
        require(isinstance(c["compatibility"], str) and c["compatibility"] in {"tested", "documented", "unknown", "incompatible"}, "invalid_candidate")
        require(isinstance(c["account"], str) and c["account"] in {"existing", "new", "none", "unknown"}, "invalid_candidate")
        require(isinstance(c["cost"], str) and c["cost"] in {"existing_quota", "free_software", "paid", "unknown"}, "invalid_candidate")
        require(strings(c["permissions"]) and strings(c["blockers"]) and refs(c["source_ids"], ids, True), "invalid_candidate")
        checks = c["checks"]
        required_checks = {"identity", "entrypoint", "license", "dependencies", "permissions", "data_flow"}
        require(isinstance(checks, dict) and set(checks) == required_checks, "invalid_candidate")
        require(all(refs(v, ids) for v in checks.values()), "invalid_candidate")
        missing = sorted(k for k, v in checks.items() if not v)
        if c["account"] == "unknown": missing.append("account")
        if c["cost"] == "unknown": missing.append("cost")
        if c["compatibility"] == "unknown": missing.append("compatibility")
        status = ("blocked" if c["blockers"] or c["compatibility"] == "incompatible" else
                  "needs_review" if missing else "ready_for_user_choice")
        results.append({**c, "review_status": status, "missing": missing,
                        "installed": False, "evidence_verified": False})
    # A reviewable working option precedes an unverified official listing.
    order = {"ready_for_user_choice": 0, "needs_review": 1, "blocked": 2}
    results.sort(key=lambda c: (order[c["review_status"]], TIERS.index(c["tier"]),
                               c["account"] == "new", c["cost"] == "paid", c["id"]))
    return {"ok": True, "host": req["host"], "candidates": results, "executed": False,
            "note": "Order is evidence readiness then source preference, not a measured fit score. Host must verify claims and explain tradeoffs."}


def company(req):
    require(set(req) == {"action", "as_of", "scope", "sources", "companies"})
    require(research.text(req["scope"]))
    ids = sources(req["sources"], req["as_of"])
    require(isinstance(req["companies"], list) and len(req["companies"]) <= 40)
    seen = set()
    for c in req["companies"]:
        require(isinstance(c, dict) and set(c) == {"name", "entity_scope", "relationships", "claims", "gaps"}, "invalid_company")
        require(research.text(c["name"]) and research.text(c["entity_scope"]) and c["name"] not in seen, "invalid_company")
        seen.add(c["name"])
        require(strings(c["gaps"]) and isinstance(c["relationships"], list) and len(c["relationships"]) <= 4, "invalid_company")
        types = set()
        for rel in c["relationships"]:
            require(isinstance(rel, dict) and set(rel) == {"type", "status", "source_ids"}, "invalid_relationship")
            require(isinstance(rel["type"], str) and rel["type"] in {"event_sponsor", "technical_partner", "osaka_attendance", "osaka_prize"}, "invalid_relationship")
            require(rel["type"] not in types, "duplicate_relationship")
            types.add(rel["type"])
            require(isinstance(rel["status"], str) and rel["status"] in {"documented", "unknown"}, "invalid_relationship")
            require(refs(rel["source_ids"], ids, rel["status"] == "documented"), "invalid_relationship")
        require(isinstance(c["claims"], list) and len(c["claims"]) <= 12, "invalid_company")
        for claim in c["claims"]:
            require(isinstance(claim, dict) and set(claim) == {"kind", "topic", "text", "source_ids"}, "invalid_company")
            require(isinstance(claim["kind"], str) and claim["kind"] in {"fact", "inference"} and isinstance(claim["topic"], str) and claim["topic"] in {"business", "product", "direction", "fit"}, "invalid_company")
            require(research.text(claim["text"]) and refs(claim["source_ids"], ids, True), "invalid_company")
    return {"ok": True, "company_count": len(seen), "evidence_verified": False,
            "note": "A source reference cannot prove attendance or prize eligibility; host must read event-specific evidence."}


def handle(req):
    require(isinstance(req, dict) and isinstance(req.get("action"), str))
    if req["action"] == "plan": return plan(req)
    if req["action"] == "evaluate": return evaluate(req)
    if req["action"] == "validate_companies": return company(req)
    raise Error("invalid_request")


def main():
    try:
        raw = sys.stdin.buffer.read(262145)
        require(len(raw) <= 262144)
        result = handle(json.loads(raw))
    except (ValueError, UnicodeError):
        result = {"ok": False, "error": "invalid_json"}
    except Error as exc:
        result = {"ok": False, "error": str(exc)}
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())

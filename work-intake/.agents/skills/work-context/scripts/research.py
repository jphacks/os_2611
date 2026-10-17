#!/usr/bin/env python3
"""Plan/validate public research. Host supplies search and language understanding."""
import importlib.util
import json
import os
from pathlib import Path
import sys
from datetime import date
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[4]
spec = importlib.util.spec_from_file_location(
    "local_intake", ROOT / ".agents/skills/work-intake/scripts/intake.py")
intake = importlib.util.module_from_spec(spec)
spec.loader.exec_module(intake)
Error = intake.IntakeError
LIMIT = 65536


def text(value, limit=2000):
    return isinstance(value, str) and 0 < len(value.strip()) <= limit


def day(value):
    if not isinstance(value, str):
        raise Error("invalid_report")
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise Error("invalid_report")
    if parsed.isoformat() != value:
        raise Error("invalid_report")
    return parsed


def validate(report):
    if not isinstance(report, dict) or set(report) != {
            "as_of", "scope", "sources", "findings", "coverage"}:
        raise Error("invalid_report")
    as_of = day(report["as_of"])
    if as_of > date.today() or not text(report["scope"]):
        raise Error("invalid_report")
    sources = report["sources"]
    if not isinstance(sources, list) or len(sources) > 12:
        raise Error("invalid_report")
    ids, urls = set(), set()
    for source in sources:
        if not isinstance(source, dict) or set(source) != {
                "id", "title", "url", "accessed_at", "published_at"}:
            raise Error("invalid_report")
        if not all(text(source[k]) for k in ("id", "title", "url")):
            raise Error("invalid_report")
        try:
            url = urlsplit(source["url"])
            valid_url = (url.scheme in {"https", "http"} and url.hostname and
                         not url.username and not url.password)
        except ValueError:
            valid_url = False
        if not valid_url or source["id"] in ids or source["url"] in urls:
            raise Error("invalid_report")
        if day(source["accessed_at"]) > as_of:
            raise Error("invalid_report")
        if source["published_at"] is not None and day(source["published_at"]) > as_of:
            raise Error("invalid_report")
        ids.add(source["id"])
        urls.add(source["url"])
    findings = report["findings"]
    if not isinstance(findings, list) or len(findings) > 20:
        raise Error("invalid_report")
    for finding in findings:
        if not isinstance(finding, dict) or set(finding) != {
                "kind", "text", "source_ids", "relevance"}:
            raise Error("invalid_report")
        if (not isinstance(finding["kind"], str) or
                finding["kind"] not in {"fact", "inference", "question"} or
                not text(finding["text"]) or not text(finding["relevance"]) or
                not isinstance(finding["source_ids"], list) or
                any(not isinstance(i, str) or i not in ids for i in finding["source_ids"]) or
                (finding["kind"] != "question" and not finding["source_ids"])):
            raise Error("invalid_report")
    coverage = report["coverage"]
    if not isinstance(coverage, dict) or set(coverage) != {"direct", "adjacent", "counter", "gaps"}:
        raise Error("invalid_report")
    if not all(isinstance(v, list) and len(v) <= 10 and all(text(x) for x in v)
               for v in coverage.values()):
        raise Error("invalid_report")
    if len(json.dumps(report, ensure_ascii=False).encode()) > LIMIT:
        raise Error("invalid_report")
    return report


def plan(context):
    allowed = {"audience", "organization", "sector", "role", "major", "topics",
               "financial_context_required"}
    if not isinstance(context, dict) or set(context) - allowed:
        raise Error("invalid_context")
    audience = context.get("audience")
    if not isinstance(audience, str) or audience not in {
            "worker", "student", "freelancer", "manager", "owner", "general"}:
        raise Error("invalid_context")
    for key in ("organization", "sector", "role", "major"):
        if key in context and not text(context[key], 200):
            raise Error("invalid_context")
    topics = context.get("topics", [])
    if (not isinstance(topics, list) or len(topics) > 4 or
            not all(text(topic, 150) for topic in topics) or
            type(context.get("financial_context_required", False)) is not bool):
        raise Error("invalid_context")
    org = context.get("organization", "")
    subject = " ".join(context.get(k, "") for k in ("sector", "role", "major")).strip()
    topic = " ".join(topics) or subject
    anchor = " ".join(p for p in (subject, topic) if p).strip() or "業務改善"
    searches = []
    if org:
        searches.append({"purpose": "public_background", "query":
                         f'{org} {context.get("major", "")} 公式 ' +
                         ("学科 学修支援" if audience == "student" else "事業 サービス")})
    searches.extend([
        {"purpose": "direct", "query": f"日本 {anchor} " +
         ("学修 公開資料" if audience == "student" else "実務 改善 公式")},
        {"purpose": "adjacent", "query": f"日本 {topic or subject or '働き方'} 制度 変更 支援"},
        {"purpose": "counter", "query": f"{anchor} 課題 限界 注意点 研究"},
    ])
    financial = context.get("financial_context_required", False)
    if financial:
        searches[-2] = {"purpose": "financial_task", "query": f"{org or subject} 決算 有価証券報告書 公式"}
    return {"ok": True, "audience": audience, "searches": searches,
            "financial_context_required": financial,
            "max_initial_searches": 4, "max_sources": 6,
            "note": "Queries use public context only; host performs live search and verification."}


def read(directory):
    intake.check_directory(directory)
    path = directory / "research.json"
    if path.is_symlink():
        raise Error("unsafe_path")
    if not path.exists():
        return {"revision": 0, "report": None}
    if not path.is_file() or path.stat().st_size > LIMIT:
        raise Error("invalid_state")
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
        if (not isinstance(state, dict) or set(state) != {"revision", "report"} or
                type(state["revision"]) is not int or state["revision"] < 0):
            raise Error("invalid_state")
        if state["report"] is not None:
            validate(state["report"])
        return state
    except (ValueError, UnicodeError, Error):
        raise Error("invalid_state")


def compare(previous, current):
    def keys(report):
        return {(f["kind"], f["text"]) for f in report["findings"]} if report else set()
    old, new = keys(previous), keys(current)
    return {"added": [{"kind": k, "text": t} for k, t in sorted(new - old)],
            "not_in_latest": [{"kind": k, "text": t} for k, t in sorted(old - new)],
            "unchanged_count": len(old & new),
            "interpretation": "Text differences require host review; absence is not retraction."}


def handle(req, directory=None):
    if not isinstance(req, dict) or not isinstance(req.get("action"), str):
        raise Error("invalid_request")
    action = req["action"]
    allowed = {"plan": {"action", "context"}, "validate": {"action", "report"},
               "compare": {"action", "report"}, "status": {"action"},
               "save": {"action", "report", "confirmed", "expected_revision"},
               "clear": {"action", "confirmed", "expected_revision"}}
    if action not in allowed or set(req) != allowed[action]:
        raise Error("invalid_request")
    if action == "plan":
        return plan(req["context"])
    if action in {"validate", "compare", "save"}:
        validate(req["report"])
    if action == "validate":
        return {"ok": True, "source_count": len(req["report"]["sources"]),
                "finding_count": len(req["report"]["findings"]),
                "evidence_verified": False}
    directory = Path(directory) if directory is not None else ROOT / ".private"
    if action == "status":
        return {"ok": True, "state": read(directory)}
    if action == "compare":
        return {"ok": True, "diff": compare(read(directory)["report"], req["report"])}
    if req["confirmed"] is not True:
        raise Error("consent_required")
    if type(req["expected_revision"]) is not int or req["expected_revision"] < 0:
        raise Error("invalid_request")
    intake.check_directory(directory)
    directory.mkdir(mode=0o700, parents=False, exist_ok=True)
    os.chmod(directory, 0o700)
    lock = directory / ".research-lock"
    try:
        fd = os.open(str(lock), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        raise Error("busy")
    try:
        os.close(fd)
        state = read(directory)
        if state["revision"] != req["expected_revision"]:
            raise Error("revision_conflict")
        report = req["report"] if action == "save" else None
        diff = compare(state["report"], report) if report else None
        state = {"revision": state["revision"] + 1, "report": report}
        intake.write_state(directory, state, filename="research.json")
        return {"ok": True, "revision": state["revision"], "diff": diff}
    finally:
        lock.unlink()


def main():
    try:
        raw = sys.stdin.buffer.read(LIMIT + 1)
        if len(raw) > LIMIT:
            raise Error("invalid_request")
        try:
            req = json.loads(raw)
        except (ValueError, UnicodeError):
            raise Error("invalid_request")
        result = handle(req)
    except Error as error:
        result = {"ok": False, "error": str(error)}
    except OSError:
        result = {"ok": False, "error": "storage_unavailable"}
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Dependency-free local state adapter. Natural language belongs to the host."""
import json
import os
from pathlib import Path
import sys
import tempfile
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[4]
FIELDS = frozenset(("role", "context", "goals", "tasks", "friction", "tools",
                    "constraints", "output_preferences", "language", "work_style",
                    "organization", "sector", "department", "major", "year"))
QUESTION_FIELDS = FIELDS - {"friction", "goals", "language"}
MAX_BYTES = 65536


class IntakeError(Exception):
    pass


def empty():
    return {"schema_version": 1, "revision": 0, "paused": False,
            "profile": {}, "changes": [], "updated_at": None}


def valid_profile(profile):
    return (isinstance(profile, dict) and set(profile) <= FIELDS and
            all(isinstance(v, str) and 0 < len(v.strip()) <= 2000
                for v in profile.values()))


def check_directory(directory):
    if directory.is_symlink() or (directory.exists() and not directory.is_dir()):
        raise IntakeError("unsafe_path")


def read_state(directory):
    check_directory(directory)
    path = directory / "state.json"
    if path.is_symlink():
        raise IntakeError("unsafe_path")
    if not path.exists():
        return empty()
    if not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise IntakeError("invalid_state")
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
        if (not isinstance(state, dict) or set(state) != set(empty()) or
                type(state.get("schema_version")) is not int or state["schema_version"] != 1 or
                type(state.get("revision")) is not int or state["revision"] < 0 or
                type(state.get("paused")) is not bool or
                not valid_profile(state.get("profile")) or
                not isinstance(state.get("changes"), list) or
                len(state["changes"]) > 20 or
                not (state.get("updated_at") is None or
                     isinstance(state["updated_at"], str))):
            raise IntakeError("invalid_state")
        for change in state["changes"]:
            if (not isinstance(change, dict) or
                    set(change) != {"at", "action", "fields"} or
                    not isinstance(change["at"], str) or
                    not isinstance(change["action"], str) or
                    change["action"] not in {"apply", "forget", "pause", "resume"} or
                    not isinstance(change["fields"], list) or
                    any(not isinstance(f, str) or f not in FIELDS
                        for f in change["fields"])):
                raise IntakeError("invalid_state")
        return state
    except (ValueError, UnicodeError, TypeError):
        raise IntakeError("invalid_state")


def validate_request(req):
    if (not isinstance(req, dict) or not isinstance(req.get("action"), str) or
            req.get("action") not in {
            "status", "assess", "apply", "forget", "pause", "resume", "reset"}):
        raise IntakeError("invalid_request")
    action = req["action"]
    allowed = {"action"} if action in {"status", "assess"} else {
        "action", "confirmed", "expected_revision"}
    if action == "assess":
        allowed.update({"profile", "questions_asked", "memory", "memory_status", "needed_fields", "asked_fields", "declined_fields"})
        if (not valid_profile(req.get("profile", {})) or
                type(req.get("questions_asked")) is not int or
                not 0 <= req["questions_asked"] <= 3):
            raise IntakeError("invalid_request")
        if req.get("memory_status", "not_checked") not in ("not_checked", "checked", "unavailable", "disabled"):
            raise IntakeError("invalid_request")
        for key in ("needed_fields", "asked_fields", "declined_fields"):
            if key in req:
                value = req[key]
                if (not isinstance(value, list) or len(value) > len(FIELDS) or
                        any(not isinstance(field, str) or field not in QUESTION_FIELDS for field in value) or
                        len(set(value)) != len(value)):
                    raise IntakeError("invalid_request")
        if "memory" in req:
            memory = req["memory"]
            if (not isinstance(memory, dict) or set(memory) != {"profile", "source"} or
                    not valid_profile(memory["profile"]) or
                    memory["source"] not in ("host_provided", "user_authorized_file")):
                raise IntakeError("invalid_request")
    if action == "apply":
        allowed.add("profile")
        if not valid_profile(req.get("profile")) or not req["profile"]:
            raise IntakeError("invalid_request")
    if action == "forget":
        allowed.add("fields")
        fields = req.get("fields")
        if (not isinstance(fields, list) or not fields or
                any(not isinstance(f, str) or f not in FIELDS for f in fields)):
            raise IntakeError("invalid_request")
    if set(req) - allowed:
        raise IntakeError("invalid_request")
    if action not in {"status", "assess"}:
        if req.get("confirmed") is not True:
            raise IntakeError("consent_required")
        if type(req.get("expected_revision")) is not int or req["expected_revision"] < 0:
            raise IntakeError("invalid_request")


def write_state(directory, state, filename="state.json"):
    data = json.dumps(state, ensure_ascii=False, indent=2) + "\n"
    if len(data.encode("utf-8")) > MAX_BYTES:
        raise IntakeError("invalid_request")
    fd, temp_path = tempfile.mkstemp(prefix=".state-", dir=str(directory))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, directory / filename)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def handle(req, directory=None):
    validate_request(req)
    directory = Path(directory) if directory is not None else ROOT / ".private"
    if req["action"] == "status":
        return {"ok": True, "state": read_state(directory)}
    if req["action"] == "assess":
        state = read_state(directory)
        if state["paused"]:
            return {"ok": True, "mode": "paused", "next_field": None,
                    "revision": state["revision"]}
        if req.get("memory_status", "not_checked") == "not_checked":
            return {"ok": True, "mode": "recall", "next_field": None,
                    "reason": "check_host_memory_before_questions", "revision": state["revision"]}
        memory = req.get("memory", {}).get("profile", {})
        profile, origins, conflicts = dict(memory), {k: "host_memory" for k in memory}, []
        for origin, values in (("saved_profile", state["profile"]), ("current_turn", req.get("profile", {}))):
            for key, value in values.items():
                if key in profile and profile[key] != value:
                    conflicts.append({"field": key, "preferred_source": origin, "other_source": origins[key]})
                profile[key], origins[key] = value, origin
        # Do not pair an explicitly new task with a previous task's friction.
        current = req.get("profile", {})
        if ("tasks" in current and "friction" not in current and
                current["tasks"] != (state["profile"].get("tasks") or memory.get("tasks"))):
            profile.pop("friction", None)
            origins.pop("friction", None)
        # Only task-relevant missing facts may prompt a question. Already known,
        # asked or declined facts never restart an intake loop. Lists are temporary.
        needed = req.get("needed_fields", ["tasks"])
        skipped = set(req.get("asked_fields", [])) | set(req.get("declined_fields", []))
        missing = [field for field in needed if not profile.get(field) and field not in skipped]
        question = missing[0] if missing and req["questions_asked"] < 3 else None
        next_step = ("ask_concrete_question" if question else "use_current_activity" if profile.get("tasks")
                     else "use_known_context" if profile else "show_guided_example")
        reason = ("missing_concrete_fact" if question else "question_limit" if missing else
                  "activity_known" if profile.get("tasks") else "use_available_context")
        return {"ok": True, "mode": "ask" if question else "ready", "reason": reason,
                "next_field": question, "next_step": next_step,
                "revision": state["revision"], "profile_for_this_turn": profile,
                "context_sources": origins, "conflicts": conflicts,
                "memory_persisted": False, "memory_status": req["memory_status"],
                "opportunity_status": "reported" if profile.get("friction") else "to_discover",
                "unsaved_fields": sorted(k for k, v in req.get("profile", {}).items()
                                         if state["profile"].get(k) != v)}
    check_directory(directory)
    directory.mkdir(mode=0o700, parents=False, exist_ok=True)
    os.chmod(directory, 0o700)
    lock = directory / ".lock"
    try:
        fd = os.open(str(lock), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        raise IntakeError("busy")
    try:
        os.close(fd)
        state = read_state(directory)
        if req["expected_revision"] != state["revision"]:
            raise IntakeError("revision_conflict")
        action = req["action"]
        before = dict(state["profile"])
        changed = []
        if action == "apply":
            if state["paused"]:
                raise IntakeError("paused")
            changed = sorted(k for k, v in req["profile"].items()
                             if state["profile"].get(k) != v.strip())
            state["profile"].update({k: v.strip() for k, v in req["profile"].items()})
        elif action == "forget":
            changed = sorted(set(req["fields"]) & set(state["profile"]))
            for field in changed:
                del state["profile"][field]
        elif action in {"pause", "resume"}:
            desired = action == "pause"
            if state["paused"] == desired:
                return {"ok": True, "changed_fields": [], "state": state}
            state["paused"] = desired
        else:
            changed = sorted(before)
            state = dict(empty(), revision=state["revision"])
        if action in {"apply", "forget"} and not changed:
            return {"ok": True, "changed_fields": [], "state": state}
        stamp = datetime.now(timezone.utc).isoformat()
        state["revision"] += 1
        state["updated_at"] = stamp
        if action != "reset":
            state["changes"] = (state["changes"] + [
                {"at": stamp, "action": action, "fields": changed}])[-20:]
        write_state(directory, state)
        return {"ok": True, "changed_fields": changed, "state": state}
    finally:
        lock.unlink()


def main():
    try:
        data = sys.stdin.buffer.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise IntakeError("invalid_request")
        try:
            req = json.loads(data)
        except (ValueError, UnicodeError):
            raise IntakeError("invalid_request")
        result = handle(req)
    except IntakeError as error:
        result = {"ok": False, "error": str(error)}
    except OSError:
        result = {"ok": False, "error": "storage_unavailable"}
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())

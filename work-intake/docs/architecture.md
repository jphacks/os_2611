# Architecture and implementation references

0.2 uses the existing host model and tool loop for semantic decisions. A small
standard-library controller implements task state, exact action scopes, real I/O,
operation evidence, freshness checks and recoverable checkpoints. No imported
agent framework, independent inference service or persistent background worker.

The host may alternate internal material reads, public investigation, hypotheses,
experiments and feedback. Decisions are not occupation-specific or predetermined.
The local journal supports this interaction; it does not understand language or
certify model judgments. Host-reported external evidence remains explicitly such.

## External engineering inspection, 2026-10-17

Inspected primary source:
https://github.com/langchain-ai/langgraph/blob/main/libs/checkpoint-sqlite/langgraph/checkpoint/sqlite/__init__.py

Relevant structures: thread-scoped checkpoint records, parent_checkpoint_id,
get_tuple lookup and separately associated pending writes. Repository root license
was inspected via GitHub: MIT, copyright LangChain Inc. No code copied, no LangGraph
package installed. The project's own implementation is independent.

Adopted narrowly: task-scoped SQLite persistence; a separate attempt/result event
pair committed around actual side effects; reasoning checkpoints with parent IDs.
The additional restore_checkpoint operation deliberately restores only reasoning,
not permissions or disk, because blindly replaying a command after a restart can
repeat a real external effect. Regression tests exercise this distinction.

Rejected importing the full framework: the current host already supplies model
orchestration; a separate graph runtime adds installation and configuration without
solving the missing local task/evidence binding. This choice can change if real
future requirements justify it.

AISafetyHot-Hub reference inspected:
https://github.com/wuyoscar/AISafetyHot-Hub/blob/main/skills/aisafety-brief/SKILL.md
https://github.com/wuyoscar/AISafetyHot-Hub/blob/main/docs/agent.md

Adopted design distinction, not code: task instructions must point to concrete
callable capabilities. In this package that is work.py. Public source aggregators
may be useful per task but are not installed by default or universal requirements.

Launcher reference checked on 2026-10-17:
https://learn.chatgpt.com/docs/reference/commands (codex://threads/new, path, prompt;
composer is prefilled, not automatically sent).
https://code.claude.com/docs/en/cli-reference (interactive prompt).

## Limits

The host remains responsible for actual authorization, external source interpretation
and semantic quality. No cryptographic attestation, process sandbox, universal memory
bridge, built-in search index or scheduler. SQLite data is local and unencrypted.
External networking depends on host controls; HTTPS address checks are not a complete
SSRF isolation solution. Production multi-user concurrency is outside this release.

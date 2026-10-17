---
name: work-intake
description: Improve current study, research, employment, freelance or engineering work using actual materials, external discovery and capability integration. Use when starting or resuming the work assistant, adapting AI tools to a task, or absorbing a useful agent/repository architecture. Uses a real local task journal and I/O runtime; not a mandatory profile questionnaire.
---

# Host-native work assistance

Locate the installation root: this file is at `.agents/skills/work-intake/SKILL.md`.
Read `docs/runtime.md` at that root for the exact JSON tool interface. Run `work.py`
with an absolute path from the current host shell. Do not open a nested AI session
if already in a conversation.

Briefly introduce the purpose in the user's language once. Reuse current relevant
conversation/memory/materials. Call `list`, then `resume` when an existing task
matches; otherwise `create` using the actual work root, goal, output and concrete
criteria. Never default to analyzing the assistant's installation directory.
If the actual task is developing this agent, its source root is appropriate.

Use the returned task, source changes, pending attempts and unanswered questions
as decision context. The host model chooses the next useful action; there is no
fixed intake → research → recommendation order. Internal material, external
findings, attempts and user feedback can change both the goal interpretation and
the next action. `reflect` records facts, inferences and candidate decisions with
provenance. `update` stores revised work goals and next actions.

Use `question` only for a concrete missing fact that changes the work; record the
answer/decline. Skip known, asked or refused information. Do not force a profile,
a pain point, a generic example or a technical choice. Optional legacy personal
profile storage is separate from ordinary task progress.

For each operation use actual tools, not invented observations:
- `read` reads named work materials and hashes them. Use host document tools for
  binary formats. Save only useful references and summaries.
- Use enabled host tools first. For external discovery use actual host search and
  original-source reading; `observe` stores real references with host-reported
  provenance. The local HTTPS `fetch` is for public exact URLs, not a search engine.
  If blocked, use actual host search if available, without claiming direct fetch.
- Prefer existing capabilities. Investigate repositories and relevant source,
  dependencies, license, cost and compatibility before choosing what to absorb.
  `reflect` candidate records distinguish proposed/selected/rejected/integrated;
  those labels are judgments and never constitute execution proof.
- Register an exact `grant` from current user authorization before local I/O.
  Reuse grants for the same task/scope. Do not request consent again unnecessarily.
  For arbitrary processes inspect the argv and scope: the runtime is not a sandbox.
- Execute through `act` with `write` or `run`, or use more appropriate real host
  tools and record them honestly. Controlled writes need the current hash before
  overwriting and retain a before image for recovery.
- Use `verify` to re-read actual output and check rows, columns, content or hashes;
  use meaningful host tests as needed. Then `complete` with its verification IDs.
  Never turn a supplied receipt into a successful remote connection/schedule.

After failures choose a new approach or retry with a concrete changed-evidence
reason. Read the actual error; do not repeat indefinitely. Checkpoint reasoning
before uncertain changes; restore reasoning without replaying effects. On resume,
inspect changed materials and interrupted actions. Preserve work when a capability
is unavailable, continue independent tasks and explain the exact limit.

Deliver the actual work result in plain language, with useful original citations,
what changed, how verified and any remaining limit. Installation, repository
search and engineering knowledge are implementation details, not prerequisites
for a user. Experienced users can receive deep integrations; nobody must keep
using this project once they can work independently.

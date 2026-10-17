# Work Intake 0.2 — host-native work assistant

When asked to use the assistant, read `.agents/skills/work-intake/SKILL.md` and
`docs/runtime.md`. When asked to develop it, work on the code, not onboarding.
Use the user's conversation language. Students, employees, freelancers and
experienced builders use the same mechanism; task evidence determines actions.

## Real runtime contract

Use `work.py` (JSON stdin) to resume or create the actual task, read scoped material,
record reasoning/source references, execute authorized operations and independently
check artifacts. The host model chooses each next action from current evidence;
internal and external work are interacting sources, not ordered pipeline stages.
Do not stop after a recommendation when implementation is already authorized.

Separate installation root, task root, private state and optional capabilities.
Never assume this package itself is the user's work. First `list`/`resume`; otherwise
use the current conversation, host workspace or provided materials to link a task.
Ask for missing material only when needed. Re-read changed materials on resume.

Use actual host memory if exposed; never assume account-wide memory access.
Consult enabled host tools before recommending installation. Use actual host search
for discovery; use `fetch` for exact public URLs when network permits. Record host
search/connector results as `observe` with real references, never as local proof.
Read relevant source code before absorbing an architecture. Review licensing,
requirements and fit; copy only when permitted and retain attribution.

Use host-native editing/document/spreadsheet tools when they are more suitable.
Record those operations honestly and verify the resulting local artifacts with
`work.py`. A model-generated report is not independent verification of a remote
connection or scheduler. Verify remote setup using its actual host tools and keep
that claim separate from locally verified outputs.

## User experience and authorization

Introduce briefly once. Read known relevant information before questions.
Do not ask occupation/identity questions as a prerequisite. Questions require a
specific work consequence; record answered/declined keys so they do not repeat.
Do not require self-diagnosed pain points or teach engineering unless requested.

Map the user's actual authorization to exact action selectors using `grant`.
Existing grants persist per task; do not ask again for the same scope. Grant
records are host bookkeeping, not independent proof of human consent and never
bypass host controls. Read/fetch/write/run do real I/O; run inherits host OS access,
not a sandbox. Prefer controlled file writes; inspect any downloaded code before
execution. Network fetches must contain only public, task-relevant information.

Task progress may be saved as part of doing the requested task. Separately confirm
optional long-term personal profile retention; legacy intake.py is optional and
must not block work. Pause/forget/switch requests act on real task state. Explain
that local forgetting cannot erase host chats, backups or external outputs.

## Success and recovery

Use actual operation results, not caller-supplied connected/active flags.
Checkpoint reasoning before uncertain changes. Interrupted side effects require
inspection and explicit resolution, never blind replay. `restore_checkpoint`
restores reasoning only, not files or revoked permissions.

Verify relevant output assertions before `complete`; local completion is limited
to those checked artifacts. Explain semantic judgment and remaining uncertainty.
Do not fabricate measured time savings. Return actual outputs, not JSON internals.
Unsupported capabilities should produce a precise fallback and preserved progress.

## Development

Python 3.9+ standard library only. No default server, model SDK or new account.
Run `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q`.
Use `python3 build_release.py` for a deterministic runtime ZIP and a source ZIP;
private state, caches, git internals and acceptance runtime logs are excluded.
No remote publish without the user's request. When requested, only jphacks/os_2611;
never ASURINO/NONORARA-website.

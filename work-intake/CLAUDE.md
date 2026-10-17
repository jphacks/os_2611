# Project instructions for Claude Code

@AGENTS.md

Use the same canonical workflow and Python helpers as Codex. Claude Code project
skills under `.claude/skills/` are small entry adapters pointing to `.agents/skills/`;
read the referenced canonical SKILL.md completely before acting. Do not resolve
scripts relative to the adapter: run the scripts in the canonical package.

Identify the current host as Claude Code in plans and observations. Never reuse
an example's Codex tool observations as evidence of Claude Code capabilities.
Use the actual tools and authorization controls enabled in this session. If live
search is unavailable, explain it without inventing results or installing a search
tool. Apply the user's language and the same no-extra-account defaults.

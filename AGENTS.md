# Agent Operating Instructions

This repository uses a milestone-driven workflow. The authoritative project-control files are:

- `AGENTS.md`
- `project/current.md`
- `project/roadmap.md`
- `project/history.md`

## Required Session Flow

Every agent session must:

1. Read `AGENTS.md`.
2. Read `project/current.md`.
3. Consult only the relevant parts of `project/roadmap.md` and `project/history.md`.
4. Inspect the minimum repository surface needed for the active milestone.
5. Implement and validate the active milestone completely.
6. Iterate on failures until the milestone is complete or a genuine blocker is proven.
7. Update project-control documents before finishing.
8. Leave a concise final handoff suitable for pasting into ChatGPT.
9. Use GitHub checkpoints for coherent, validated repository states according to the repository Git policy below.

There must be exactly one active implementation milestone in `project/current.md`.

## Token-Efficient Work Rules

- Keep authoritative state in the four project-control files only.
- Do not duplicate the same instructions across many files.
- Keep `project/current.md` short, explicit, and executable.
- Keep roadmap entries concise.
- Prefer machine-readable structured artifacts over long prose.
- Prefer exact file paths and commands over exploratory narration.
- Inspect files selectively rather than recursively reading the entire repository.
- Use targeted searches such as `rg` before opening files.
- Avoid rereading unchanged project-control documents within one session.
- Run focused tests during iteration and complete required validation only before completion.
- Keep command logs on disk instead of pasting large outputs into model context.
- Summarize long tool output and reference its saved path.
- Keep agent roles and provider prompts modular so only relevant instructions are loaded.
- Avoid speculative abstractions and unused framework code.
- Do not create separate agents merely for role-playing; use an agent only when it has distinct permissions, context, or validation responsibility.

## Completion Rules

When a milestone is completed:

1. Record the completed work in `project/history.md`.
2. Update `project/roadmap.md`.
3. Replace `project/current.md` with the next concrete milestone.
4. Include that next milestone in the final handoff.

Do not leave `project/current.md` ambiguous or containing several possible next tasks.

## Repository Boundaries

- Do not modify files outside this repository.
- Never modify Git configuration outside this repository.
- Never create or change a remote unless explicitly instructed.
- Never force-push or rewrite published history.
- Never commit secrets, virtual environments, generated run artifacts, logs, caches, or temporary repositories.
- Create commits only at coherent, validated checkpoints.
- Use concise conventional-style commit messages.
- Push after each checkpoint commit when a configured GitHub remote exists.
- Do not push failing work to the default branch.
- Every completed milestone must end with all intended files committed and pushed.
- Record the final commit hash and pushed branch in the milestone handoff.
- Keep generated outputs under ignored paths such as `.rtl-agent/`, `.venv/`, or test temporary directories.

## Final Handoff Template

```text
STATUS: COMPLETE | BLOCKED
MILESTONE: <name>

SUMMARY:
<brief result>

IMPLEMENTED:
- ...

VALIDATION:
- `<command>` — PASS/FAIL

GIT:
- Branch: <branch>
- Commits: <short hashes and messages>
- Push: PASS/FAIL with remote name

KEY FILES:
- ...

ARCHITECTURAL DECISIONS:
- ...

KNOWN LIMITATIONS:
- ...

NEXT MILESTONE:
<exact title and objective copied from project/current.md>
```

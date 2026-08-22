# BlingMUD Agent Instructions

This repository is collaborative space for humans and agents.

Follow these rules when working here:

- Always begin by reviewing what is already in place, what still needs doing, and what known bugs exist.
- Never assume something is implemented until you have verified it in the codebase.
- Always fix known bugs first unless explicitly told not to.
- Always review for potential bugs, including security issues, before starting new feature work.
- Do not patch blindly from assumptions.
- After any implementation or bugfix commit, update `AI_ROADMAP.md` and `TODO.md` before moving on.
- Do not leave the roadmap or TODO stale; future agents rely on them to know what is actually done.
- Prefer small, reviewable changes over large rewrites.
- Keep content work, engine work, and AI architecture work separate where possible.
- Preserve unrelated user changes unless the user asks otherwise.
- Do not revert user work just because it looks incomplete.
- Use `apply_patch` for file edits.
- Do not use destructive commands unless the user explicitly authorizes them.
- Run the complete suite through `python3 run_tests.py`, which enforces a 30-second subprocess timeout; the normal suite takes under one second, so exit status 124 indicates a regression or deadlock that must be investigated rather than left running. Do not bypass the watchdog with a raw discovery command.

Repository documents:

- `AI_ROADMAP.md` is the agent-facing long-form implementation plan.
- `TODO.md` is the human-dev patch list for smaller, reviewable changes.
- Keep `AI_ROADMAP.md` current when the implementation changes in meaningful ways.
- Keep `TODO.md` focused on patchable work and bug fixes.

Workflow expectations:

- For bug fixes, start with the bug and its nearest surrounding behavior, then add regression coverage if practical.
- For feature work, check `AI_ROADMAP.md` first so the implementation matches the intended architecture.
- For AI, NPC, persistence, and room-scheduling changes, review the roadmap before making code changes.
- For any new significant subsystem, document the decision in `AI_ROADMAP.md` and keep `TODO.md` aligned at a higher level.
- When a change lands, reconcile all three docs: `AI_ROADMAP.md`, `TODO.md`, and this file.

Project-specific guidance:

- Preserve the distinction between real implemented behavior and planned content.
- Treat Brave Sir Knight as the baseline example for NPC behavior design.
- Route new NPC decision logic through `NPCBehavior`; do not add new direct NPC hook overrides that bypass the shared behavior contract.
- New behaviors should return validated `NPCAction` instances; preserve ordered multi-action output and do not let remote or data-driven behavior broadcast unvalidated text directly.
- Define reusable local state machines through `FSMBehavior`; validate state graphs and use trusted callable conditions rather than `eval` or executable configuration strings.
- Brave Sir Knight is migrated to `BraveSirKnightBehavior(FSMBehavior)`: five top-level states are data-backed, complex state-local sequences use trusted handlers, behavior state/content live on the behavior object, and the `BraveSirKnight` NPC is a thin world-entity wrapper.
- Treat `tests/test_brave_sir_knight.py` as a required characterization contract. Any Knight or FSM change must preserve the verified patrol, greeting, chore, resource, dialogue, memory, farewell, timing, invalid-state, empty-room, and concurrency behavior unless the user explicitly requests a behavior change; if so, update the tests and all three living documents deliberately.
- Keep random/content selection algorithms bounded. Never use retry-until-different loops for NPC output; one-entry pools and deterministic test sources must complete safely.
- Player speech and emotes reach NPCs through the room notification methods; preserve that delivery path when changing chat or command handling.
- Keep the codebase compatible with the current threaded telnet architecture unless the roadmap says otherwise.
- If a change affects persistence, NPC brains, room triggers, or AI fallback, be careful to preserve save/load and failure-mode behavior.
- OpenRouter and every other LLM provider are optional enhancements: missing or invalid provider configuration must disable remote calls cleanly, never prevent startup, and never stop the MUD or its NPCs from working locally.
- Every LLM-capable NPC must have a complete FSM or simpler fallback, and tests must cover operation with no API key and no network.
- Never hard-code, commit, prompt with, display, or ordinarily log provider API keys or other secrets.
- Treat raised callback exceptions and non-returning callbacks as different failure modes: exceptions are currently isolated, but a non-returning trusted behavior can still occupy the sequential global ticker until the scheduler gains cooperative deadlines or equivalent isolation.
- Password hashes use salted PBKDF2-SHA256; preserve verification and successful-login migration for legacy SHA-256 records until a deliberate migration removes that compatibility path.
- Do not describe the current plain Telnet connection as secure transport, even though stored password hashing has been hardened.

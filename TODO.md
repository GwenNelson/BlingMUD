=== BlingMUD TODO ===

This file is the human-dev patch list.

Use AI_ROADMAP.md for the full agent-oriented implementation plan.
Use this file for small, reviewable patches, bug fixes, and incremental pull requests.

Priority rules for human patches:
- Fix known bugs first.
- Prefer small, reviewable changes.
- Keep content and engine changes separate where possible.
- If a feature touches NPC brains, persistence, or AI, check the roadmap first.
- After any meaningful implementation, update `AI_ROADMAP.md` and this file so the two documents stay aligned.

Known bugs / first fixes

☒ Fix the command dispatcher bug in `Session.handle_command` where `session` is referenced instead of `self`.
☒ Fix the wearable-slot bug in `Item.__init__` where `worn_where` is ignored and all wearable items become `Head`.
☒ Add regression tests for both issues.
☒ Replace persistent unsalted SHA-256 password hashes with salted PBKDF2-SHA256 and migrate legacy hashes after successful authentication.
☒ Restrict the admin hash file to owner-only permissions.
☒ Unregister removed NPCs from the global NPC manager.
☒ Replace Brave Sir Knight's unbounded retry-until-different dialogue loop with bounded selection and regression coverage for degenerate randomness and one-entry pools.
☒ Bound concurrency-test waits and provide `run_tests.py` as a 30-second watchdog around the normally sub-second test suite.
☒ Reject Unicode terminal/bidirectional controls in structured NPC output and make detached behavior ticks inert.
☒ Prevent backwards wall-clock adjustments from increasing Brave Sir Knight's fire strength.
☒ Bound `NPCManager.stop()` so server shutdown cannot wait forever on a stuck ticker callback, and allow stop-before-start safely.
☒ Correct unsafe README language that described unencrypted Telnet as secure.
☒ Confine test temporary files to a repository-local, non-symlinked `.test-tmp` directory.
☒ Bound client input so a connection cannot grow an in-memory line indefinitely.
☒ Reject oversized stored password hashes and excessive PBKDF iteration counts before expensive work.
☐ Continue reviewing for obvious bugs and security issues before each new feature patch.

Core engine

☒ Formalize current player save/load as bounded version-1 JSON with safe legacy-empty migration.
☒ Keep auth decisions out of gameplay state; in particular, never persist or restore session admin privilege.
☐ Add encrypted transport or a secure front end before treating login as safe over untrusted networks.
☒ Save supported player state on logout before removing the player from their final room, while preserving the previous snapshot if serialization fails.
☐ Add periodic autosave without adding an unbounded or uninterruptible background process.
☐ Add persistent IDs and templates for rooms, items, and world objects where needed.
  ☒ Add stable room IDs and a strict template whitelist for the currently persistable pimp hat and royal possum bottle cap.
  ☐ Register each future persistent item explicitly as its content patch lands; never deserialize arbitrary class names.
☐ Add room-aware NPC activity so empty rooms do not keep ticking.

NPCs

☒ Add a shared NPC behavior contract for enter, leave, speech, emote, and tick events.
☒ Deliver player speech and `/me` events to NPC behaviors.
☒ Isolate NPC callback failures so one broken behavior does not stop room event delivery or the global ticker.
☐ Ensure a non-returning trusted NPC callback cannot stall every later NPC in the sequential global ticker; design this with the room-aware scheduler and avoid leaking replacement threads.
☒ Route Brave Sir Knight's existing FSM through the shared behavior contract without changing his intended behavior.
☒ Add validated, ordered speech/emote actions as structured behavior output.
☐ Add reusable behavior implementations so a single NPC can be:
  ☒ simple random chatter
  ☒ deterministic data-backed FSM
  ☐ FSM with optional LLM assistance
☒ Re-express Brave Sir Knight's state machine through `FSMBehavior`, with a thin NPC entity and behavior-owned state/content.
☒ Add a comprehensive Brave Sir Knight characterization suite covering all states, chore paths, greetings, farewells, memory, timing, invalid-state recovery, empty-room behavior, random output branches, and concurrent decisions.
☒ Add the Suspicious Alley bin-possum encounter with local FSM behavior, safe hat tribute, speech reactions, and one-per-player keepsakes.
☐ Make NPC memory structured and optional.
☐ Add fallback from LLM to FSM when the provider is unavailable.
☐ Make OpenRouter configuration optional: missing or incomplete keys/settings must disable remote calls without preventing startup.
☐ Require every LLM-capable NPC to declare an FSM or simpler local fallback.
☐ Test that the complete MUD remains playable with no API key, no network, exhausted AI budget, and sustained provider failure.
☐ Keep API keys out of source control, prompts, admin output, and ordinary logs.
☐ Add OpenRouter support behind a local adapter, with validation and a circuit breaker.
☐ Add token/budget gating so low-priority NPCs stay on simpler behavior.

OpenRouter implementation is deferred until the user explicitly authorizes it again. Local NPC and fallback work may continue without it.

Admin / ops

☐ Add commands for inspecting room activity, NPC mode, NPC memory, and brain health.
☐ Add commands to force NPC mode changes for debugging.
☐ Add logging around login, save/load, NPC decisions, and AI fallback.
☐ Add safe reload/debug tools where they do not risk player state.

Commands / UX

☐ Implement or improve `/tell`.
☐ Implement or improve `/hug`.
☐ Implement or improve `/flirt`.
☐ Improve help and tab completion.
☐ Make room-local verbs and NPC-specific interactions easier to define.

Village content

☐ Add Val's Hella Holler as the tavern hub.
☐ Add Val as the barkeep NPC with jokes, drink service, teleport-style attention, and cat defense.
☐ Add the magical horn / drink creation system with explicit item effects.
☐ Add the Village Green, the Hanging Tree canopy, acorn harvesting, Wisps, and the low-acorn falling-acorn hazard.
☐ Add Master Corbel, Acorn Goblets, and Acorn Mash.
☐ Add the Smithereens, Eisele, and Tackdriver.
☐ Add Ceridwen's cottage, the herb garden, the rare weed unlock, and disorientation effects.
☐ Add the Temple of the Self, mirror reflection, Self-Actualized, and stat respec.
☐ Add the Wisp Mother and village consequences for attacking her.

Future

☐ Quests
☐ Combat polish
☐ Web client
☐ ANSI colours
☐ Scripting API

Notes for human contributors

- Before patching a system described in AI_ROADMAP.md, check the roadmap so the patch matches the intended architecture.
- If you finish a significant feature here, update AI_ROADMAP.md afterwards so the agent roadmap stays current, and update this file so it still reflects reality.
- If you discover a new bug, move it near the top of this file and fix it before moving on.
- Prefer leaving design-heavy work to the roadmap and keeping this file focused on patchable, reviewable tasks.

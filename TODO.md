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
☐ Continue reviewing for obvious bugs and security issues before each new feature patch.

Core engine

☐ Formalize player save/load so character state is versioned and stable.
☐ Keep auth data and gameplay state separate in the implementation.
☐ Add encrypted transport or a secure front end before treating login as safe over untrusted networks.
☐ Add autosave or logout-save for player state.
☐ Add persistent IDs and templates for rooms, items, and world objects where needed.
☐ Add room-aware NPC activity so empty rooms do not keep ticking.

NPCs

☒ Add a shared NPC behavior contract for enter, leave, speech, emote, and tick events.
☒ Deliver player speech and `/me` events to NPC behaviors.
☒ Isolate NPC callback failures so one broken behavior does not stop room event delivery or the global ticker.
☒ Route Brave Sir Knight's existing FSM through the shared behavior contract without changing his intended behavior.
☐ Add reusable behavior implementations so a single NPC can be:
  ☐ simple random chatter
  ☐ deterministic FSM
  ☐ FSM with optional LLM assistance
☐ Re-express Brave Sir Knight's procedural state machine using the reusable FSM implementation once it exists.
☐ Make NPC memory structured and optional.
☐ Add fallback from LLM to FSM when the provider is unavailable.
☐ Add OpenRouter support behind a local adapter, with validation and a circuit breaker.
☐ Add token/budget gating so low-priority NPCs stay on simpler behavior.

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

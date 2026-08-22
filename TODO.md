=== BlingMUD TODO ===

This file is the human-dev patch list.

Use AI_ROADMAP.md for the full agent-oriented implementation plan.
Use this file for small, reviewable patches, bug fixes, and incremental pull requests.

Priority rules for human patches:
- Fix known bugs first.
- Prefer small, reviewable changes.
- Keep content and engine changes separate where possible.
- If a feature touches NPC brains, persistence, or AI, check the roadmap first.
- After any meaningful implementation, update `AGENTS.md`, `AI_ROADMAP.md`, and this file so all three documents stay aligned.

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
☒ Make room enter/leave idempotent and clear stale `player.room` references on successful departure.
☒ Prevent normal item creation, rewards, taking, and dropping from exceeding the persistence inventory bound or the room-item bound; preserve one-time rewards and finite shared resources when inventory is full.
☒ Make `/get possum` recognize the revealed NPC as non-takeable, and accept implicit item-first, `item to possum`, and `possum item` offer grammar without bypassing transfer checks.
☒ Prevent a kicked/closed gameplay worker from executing one command that was already queued when the session stopped.
☐ Continue reviewing for obvious bugs and security issues before each new feature patch.

Core engine

☒ Formalize player save/load as bounded version-2 JSON with safe migrations from version 1 and legacy empty state.
☒ Track transactional SQLite migrations with `PRAGMA user_version`, preserve existing rows, and reject databases newer than the runtime.
☒ Keep auth decisions out of gameplay state; in particular, never persist or restore session admin privilege.
☒ Warn prominently at startup and before authentication that Telnet is plaintext; suppress password echo and hidden-input redraw without claiming this protects network traffic.
☒ Record the accepted residual risk: the listener remains public by default and TLS is deliberately outside the current implementation plan, so operators must control network exposure.
☒ Save supported player state on logout before removing the player from their final room, while preserving the previous snapshot if serialization fails.
☒ Move socket accept/read/write, login input, timeouts, and queued output to `selectors.DefaultSelector` while preserving one sequential gameplay worker per authenticated player and the existing `Session` API.
☒ Bound the server to 64 total, 32 pre-auth, 32 authenticated, and 8 per-IP connections; bound each output queue to 256 KiB and each authenticated input queue to 64 lines.
☒ Use a two-worker, 16-pending authentication pool; throttle five failures per IP/account over five minutes and three validated account creations per IP/hour.
☒ Disconnect pre-auth clients after 120 idle seconds; warn authenticated players with BEL at ten hours and save/disconnect them at twelve hours, resetting idle state on input.
☒ Replace both input paths with one bounded incremental Telnet/UTF-8 parser covering fragmented negotiation/subnegotiation, escaped IAC, CR-LF/CR-NUL/LF, Unicode backspace, unsafe terminal/bidi controls, and explicit Tab events.
☒ Add 60-second autosave that compares bounded serialized snapshots, skips busy state locks without blocking selector I/O, and submits changed characters only.
☒ Route selector-era character writes through one 64-key bounded, per-player coalescing persistence writer; retry after failures and wait for a queued final snapshot on disconnect.
☒ Make immediate persistence-queue rejection notify bookkeeping callbacks so rejected character/world snapshots remain retryable.
☒ Give graceful shutdown one ten-second gameplay/persistence deadline and report workers or writes that do not finish instead of waiting indefinitely.
☐ Add persistent IDs and templates for rooms, items, and world objects where needed.
  ☒ Add stable room IDs and a strict template whitelist for the currently persistable pimp hat, royal possum bottle cap, giant acorn, Val's healing potion, Valkyrie mead, and horn-born special.
  ☐ Register each future persistent item explicitly as its content patch lands; never deserialize arbitrary class names.
☒ Add room-aware NPC activity snapshots and make the global manager skip detached and empty-room NPCs regardless of behavior type.
☒ Make ticker stop prompt and restartable, while refusing replacement if a previous ticker is still alive.

NPCs

☒ Add a shared NPC behavior contract for enter, leave, speech, emote, and tick events.
☒ Deliver player speech and `/me` events to NPC behaviors.
☒ Isolate NPC callback failures so one broken behavior does not stop room event delivery or the global ticker.
☒ Isolate every NPC behind one lazy bounded actor worker so a non-returning trusted callback selects inert fallback for only that NPC, cannot stall later recipients, and never causes replacement-thread leaks.
☒ Route Brave Sir Knight's existing FSM through the shared behavior contract without changing his intended behavior.
☒ Add validated, ordered speech/emote actions as structured behavior output.
☐ Add reusable behavior implementations so a single NPC can be:
  ☒ simple random chatter
  ☒ deterministic data-backed FSM
  ☐ FSM with optional LLM assistance
☒ Re-express Brave Sir Knight's state machine through `FSMBehavior`, with a thin NPC entity and behavior-owned state/content.
☒ Add a comprehensive Brave Sir Knight characterization suite covering all states, chore paths, greetings, farewells, memory, timing, invalid-state recovery, empty-room behavior, random output branches, and concurrent decisions.
☒ Add the Suspicious Alley bin-possum encounter with local FSM behavior, safe hat tribute in both natural command orders, accurate `/get` feedback, speech reactions, and one-per-player keepsakes.
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

☒ Add admin-only `/shutdown now`, `/kick`, `/heal`, `/save`, and `/adminstatus`, with confirmation/bounds, graceful output draining, shared health/save paths, and non-admin help/completion filtering.
☒ Add bounded `/adminstatus rooms` and `/adminstatus npcs` views for activity, behavior mode, actor fallback, queues, and errors.
☐ Extend admin inspection to future structured NPC memory, LLM budgets, and brain health after those systems exist.
☐ Add commands to force NPC mode changes for debugging.
☒ Add bounded, control-safe JSON-lines operational logging for login/rate limits, connection and server lifecycle, character/world save/load, room-local triggers, NPC decisions/failures, and admin actions; redact secret-like fields and omit chat, prompts, command arguments, admin reason text, action text, serialized state, exception messages, and tracebacks.
☐ Extend the same structured event contract to future LLM calls, budget decisions, circuit-breaker changes, health probes, and local fallback/recovery without ever logging provider keys or prompt/response content by default.
☐ Add safe reload/debug tools where they do not risk player state.

Commands / UX

☐ Implement or improve `/tell`.
☐ Implement or improve `/hug`.
☐ Implement or improve `/flirt`.
☒ Add validated global and room-local command specs, generate list/detail help from live availability, and drive bounded command-token completion from Tab events.
☒ Canonicalize exact aliases and unique prefixes, filter admin-only candidates, and use expected-text compare-and-replace so delayed completion cannot overwrite newer input.
☒ Dispatch ordinary room commands before globals, but reserve `admin`, `shutdown`, `kick`, `heal`, `save`, `adminstatus`, `quit`, and `exit` so rooms can never intercept them.
☒ Reject duplicate global primary names or aliases atomically instead of silently replacing a registered command.
☒ Add `/unequip <item or slot>` with `/remove` alias, preserving inventory and applying the item's unequip hook exactly once.
☐ Extend completion to safe argument candidates only where a future command explicitly declares a bounded provider.
☐ Make room-local verbs and NPC-specific interactions easier to define.

Village content

☒ Add the initial Val's Hella Holler tavern north of the Village Green, with the faithful room architecture, horn, cats, and social interaction hooks.
☒ Add initial local-FSM Val behavior with jokes, drink service, teleport-style attention, injury/intoxication awareness, Wisp-harm awareness, and cat defense.
☒ Add three bounded, persistent horn drink templates with explicit healing/intoxication effects and an always-available healing-potion path.
☐ Extend the horn from its fixed healing/mead/impossible-special mapping to bounded custom drink names, descriptions, provenance, and optional effects without accepting executable or unbounded generated state.
☐ Add food, currency/prices, tavern regular memory, and richer bloodied/exhausted observations.
☒ Centralize bounded damage/healing/intoxication changes; make falling acorns deal one damage and Val's cats deal five through the shared API.
☒ Add non-destructive zero-health collapse to Town Square, retaining carried/equipped items and fabulousness while clearing intoxication, restoring one health, and letting Val recognize a recent collapse.
☒ Decay online intoxication by one point per whole minute without blocking selector I/O or allowing backwards clocks to increase it.
☒ Persist recent-collapse state and a bounded wall-clock status timestamp in character schema version 2; decay intoxication safely across offline time without allowing backwards-clock increases.
☒ Add the initial Village Green and Hanging Tree canopy with `/up`/`/down`, day/night Wisp descriptions, both acorn harvest verbs, bounded giant-acorn supply, and a room-aware low-harvest bonking hazard.
☒ Persist bounded acorn supply/danger/harvest totals and Wisp ward/absence/harm state across restarts using strict version-1 world JSON and a one-key asynchronous writer.
☐ Make canopy supply renewable across time without enabling unbounded item creation.
☐ Add Master Corbel, Acorn Goblets, and Acorn Mash.
☐ Add the Smithereens, Eisele, and Tackdriver.
☐ Add Ceridwen's cottage, the herb garden, the rare weed unlock, and disorientation effects.
☐ Add the Temple of the Self, mirror reflection, Self-Actualized, and stat respec.
☒ Add the non-verbal Wisp Mother with examine, one-hit protection, removal, prolonged darkness, recovery, and shared harm state.
☒ Make Val react to Wisp Mother harm through shared runtime state when the next player enters the tavern.
☐ Make the remaining villagers react to the now-durable Wisp Mother harm consequence.

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

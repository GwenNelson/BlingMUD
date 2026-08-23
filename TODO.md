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

☒ Investigate and fix contradictory account messages where registration reports an existing name but login reports no such user: unify username canonicalization, repair safe stale account keys during schema-v3 migration, reject collisions without data loss, normalize the database path at startup, and add bounded admin database identity diagnostics.

☐ On production, compare the `/adminstatus` database path/realpath/device/inode output and authentication timestamps across all server processes or frontends; confirm the affected user is reaching the same database instance after deployment.

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
☒ Require the same 12–4096 character password bounds in the admin-password setter as in account creation, and make the setter import-safe for regression tests.
☒ Replace the authentication executor's unbounded `shutdown(wait=True)` with two fixed daemon workers, queued-work cancellation, and a one-second shared join deadline so a stuck auth/database job cannot hold shutdown forever.
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
☒ Add bounded GMCP option-201 negotiation, Core identity/subscription/Ping handling, change-suppressed character snapshots, and mapper-ready `Room.Info` with permanent numeric production-room IDs.
☒ Keep slash commands while accepting only bare look and standard movement tokens for Mudlet generic-mapper/speedwalk compatibility; provide `/say` for literal reserved-word speech.
☒ Print non-empty exits on one conventional line so Mudlet's bundled text-trigger generic mapper captures the actual directions instead of an empty `Exits:` header.
☒ Add 60-second autosave that compares bounded serialized snapshots, skips busy state locks without blocking selector I/O, and submits changed characters only.
☒ Route selector-era character writes through one 64-key bounded, per-player coalescing persistence writer; retry after failures and wait for a queued final snapshot on disconnect.
☒ Make immediate persistence-queue rejection notify bookkeeping callbacks so rejected character/world snapshots remain retryable.
☒ Give graceful shutdown one ten-second gameplay/persistence deadline and report workers or writes that do not finish instead of waiting indefinitely.
☒ Add persistent IDs and templates for rooms, items, and world objects where needed.
  ☒ Add stable room IDs and a strict template whitelist for the currently persistable pimp hat, royal possum bottle cap, giant acorn, Val's healing potion, Valkyrie mead, and horn-born special.
☒ Register each future persistent item explicitly as its content patch lands; never deserialize arbitrary class names. Rare Weed is now an explicit whitelisted template.
☒ Add room-aware NPC activity snapshots and make the global manager skip detached and empty-room NPCs regardless of behavior type.
☒ Make ticker stop prompt and restartable, while refusing replacement if a previous ticker is still alive.
☒ Add no-listener selector integration tests for real readiness, fragmented Telnet input/output, hidden-password authentication through the bounded worker pool, graceful output drain, and fake-clock idle close; capability-skip only where the host explicitly denies local socketpair writes.

NPCs

☒ Add a shared NPC behavior contract for enter, leave, speech, emote, and tick events.
☒ Deliver player speech and `/me` events to NPC behaviors.
☒ Isolate NPC callback failures so one broken behavior does not stop room event delivery or the global ticker.
☒ Isolate every NPC behind one lazy bounded actor worker so a non-returning trusted callback selects inert fallback for only that NPC, cannot stall later recipients, and never causes replacement-thread leaks.
☒ Route Brave Sir Knight's existing FSM through the shared behavior contract without changing his intended behavior.
☒ Add validated, ordered speech/emote actions as structured behavior output.
☒ Add reusable behavior implementations so a single NPC can be:
  ☒ simple random chatter
  ☒ deterministic data-backed FSM
  ☒ FSM with optional LLM assistance
☒ Re-express Brave Sir Knight's state machine through `FSMBehavior`, with a thin NPC entity and behavior-owned state/content.
☒ Add a comprehensive Brave Sir Knight characterization suite covering all states, chore paths, greetings, farewells, memory, timing, invalid-state recovery, empty-room behavior, random output branches, and concurrent decisions.
☒ Add the Suspicious Alley bin-possum encounter with local FSM behavior, safe hat tribute in both natural command orders, accurate `/get` feedback, speech reactions, and one-per-player keepsakes.
☒ Make NPC memory structured and optional; Knight traveller memory is capped at 64 entries with bounded snapshots.
☒ Add local-authoritative fallback from advisory LLM work to the existing NPC behavior when the provider is unavailable or invalid.
☒ Preserve wrapper-owned fallback bindings during NPC behavior installation and replacement.
☒ Make OpenRouter configuration optional and explicitly enabled by `BLINGMUD_OPENROUTER_ENABLED`; missing configuration starts with no AI runtime or key read.
☒ Require every LLM-capable NPC to declare an FSM or simpler local fallback, and constrain advisory responses to validated local choice indices.
☒ Test that the complete MUD remains playable with no API key or network; local-world coverage passes. Startup and unavailable-provider Knight chat use the local response. Established LLM speech suppresses canned output, with exact fallback on admission rejection, provider failure, or a five-second deadline and stale-response rejection.
☒ Keep API keys out of source control, prompts, admin output, and ordinary logs.
☒ Add OpenRouter support behind a bounded paid-first adapter with catalogue validation, a hard one-dollar daily reservation cap, free-model fallback, rotation, per-model cooldowns, bounded responses, redirect rejection, owner-only key validation, and circuit-breaker fallback.
☒ Fix paid routing price units, prefer a reliable inexpensive instruction model, persist the UTC-day budget, and prove a real Knight query reaches `llm_fsm` only after a validated response.
☒ Make paid prompt reservations tokenizer-independent and fail an over-limit persisted OpenRouter ledger closed at the one-dollar daily cap instead of reopening spend.
☒ Add ignored owner-only raw OpenRouter request/response audit logging without authorization headers or API-key leakage, and fail closed to local FSM before calls that cannot reserve a complete audit pair.
☒ Make OpenRouter dialogue use the bounded Knight/Val persona templates, speaker identity, and three-exchange conversational context; withhold canned candidate text from speech prompts to stop generic parroting, and preserve the intent-aware FSM farewell as the exact fallback rather than simultaneous live output.
☒ Give Val a bounded generic speech fallback so every ordinary utterance reaches local dialogue without AI and supplies a validated OpenRouter reply slot in live advisory mode.
☒ Add bounded global, room, and per-NPC advisory request budgets so low-priority NPCs stay on simpler behavior when capacity is exhausted.

OpenRouter implementation is explicitly authorized. Live paid completion and free-model discovery have been verified with the local provider; unavailable, exhausted, cooling-down, or over-budget models must still fall back locally.

Admin / ops

☒ Add admin-only `/shutdown now`, `/kick`, `/heal`, `/save`, and `/adminstatus`, with confirmation/bounds, graceful output draining, shared health/save paths, and non-admin help/completion filtering.
☒ Add bounded `/adminstatus rooms` and `/adminstatus npcs` views for activity, behavior mode, local behavioral fallback, actor fallback, queues, and errors; never label a healthy actor's empty watchdog state as the NPC fallback.
☒ Add bounded admin-only `/adminai` status, refresh, circuit-clear, enable/disable, and per-NPC local/advisory controls, including `/adminai enable knight advisory` syntax.
☒ Make global advisory disable and per-NPC local mode reject queued or in-flight remote speech and release the exact FSM fallback.
☒ Reject contradictory `/adminai disable <npc> advisory` syntax instead of interpreting a disable operation as advisory mode.
☒ Extend admin inspection to bounded LLM runtime budgets, brain admission/mode health, and metadata-only NPC state counts; raw memory inspection remains intentionally excluded.
☒ Add commands to force wrapped NPC mode changes for debugging.
☒ Add bounded, control-safe JSON-lines operational logging for login/rate limits, connection and server lifecycle, character/world save/load, room-local triggers, NPC decisions/failures, and admin actions; redact secret-like fields and omit chat, prompts, command arguments, admin reason text, action text, serialized state, exception messages, and tracebacks.
☒ Extend the same structured event contract to LLM advisory failures/catalogue refreshes, bounded budgets, and admin AI controls without logging provider keys or prompt/response content.
☒ Add safe bounded AI inspection/mode/debug tools where they do not risk player state; template reload remains future work.

Commands / UX

☒ Implement or improve `/tell` with bounded, control-safe private delivery that rejects sessions already closing.
☒ Implement or improve `/hug` as a bounded room-local player interaction.
☒ Implement or improve `/flirt` through Val's bounded room-local response.
☒ Add validated global and room-local command specs, generate list/detail help from live availability, and drive bounded command-token completion from Tab events.
☒ Canonicalize exact aliases and unique prefixes, filter admin-only candidates, and use expected-text compare-and-replace so delayed completion cannot overwrite newer input.
☒ Dispatch ordinary room commands before globals, but reserve `admin`, `shutdown`, `kick`, `heal`, `save`, `adminstatus`, `adminai`, `quit`, and `exit` so rooms can never intercept them.
☒ Reject duplicate global primary names or aliases atomically instead of silently replacing a registered command.
☒ Add `/unequip <item or slot>` with `/remove` alias, preserving inventory and applying the item's unequip hook exactly once.
☐ Extend completion to safe argument candidates only where a future command explicitly declares a bounded provider.
☒ Make room-local verbs and NPC-specific interactions easier to define through validated `Room.command_specs` and local `on_command` handlers.

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
☒ Announce the Green becoming safe only on the harvest that actually clears acorn danger; give later finite harvests accurate Corbel-oriented feedback.
☐ Make canopy supply renewable across time without enabling unbounded item creation.
☒ Add Master Corbel's local-FSM turnery, fixed-price giant-acorn trade/crafting, persistent Acorn Goblets that Val can fill, bounded Acorn Mash food, persistent bounded coins, and the Green-to-Holler loop.
☒ Preserve and display the contained Val drink's real effect message when drinking from a reusable Acorn Goblet.
☒ Register diagonal movement commands and aliases so advertised northeast/northwest/southeast/southwest exits are directly traversable.
☒ Guarantee bare `/look` and `/l` show the full room and all exits in every room, while preserving targeted room-local look behavior such as the Temple mirror.
☒ Add an all-room user-expectation audit for reachability, reciprocal/direct exits, complete look output, claimed command aliases, and representative valid feature dispatch.
☒ Add stateful full-dispatch journeys for the possum, Ceridwen, acorn economy, Val consumables, persistence, Wisp harm, collapse, and Temple recovery.
☐ Add the Smithereens, Eisele, and Tackdriver. (Initial bounded smithy room, Eisele FSM, scrap browse, and Tackdriver examine/listen/talk interactions are implemented; buying and commissions remain.)
☐ Add Ceridwen's cottage, the herb garden, the rare weed unlock, and disorientation effects. (Rare Weed harvesting and bounded runtime-local give-to-Ceridwen experimental stock are implemented; durable unlock and confusion mechanics remain.)
☒ Make Ceridwen's advertised `/give weed` command return bounded syntax feedback for missing or invalid targets instead of falling through as unknown.
☒ Make Ceridwen's post-unlock salve, antitoxin, and repeated-weed feedback reflect the actual runtime shelf state.
☒ Make the herb garden's examination text stop advertising its finite rare weed after the patch has been harvested.
☐ Add the Temple of the Self, mirror reflection, Self-Actualized, and stat respec. (Initial safe room, reflection, recovery, and Tome interactions are implemented; respec remains gated.)
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

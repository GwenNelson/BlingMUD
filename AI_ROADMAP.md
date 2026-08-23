# BlingMUD Roadmap

Agent instructions

- Do not patch blindly from assumptions.
- Always begin by reviewing what is already in place, what still needs doing, and what known bugs exist.
- Never assume something is implemented until it has been verified in the codebase.
- Always fix any known bugs first unless explicitly told not to.
- Always review for potential bugs, including security issues, before moving on to new work.
- After any implementation commit, update this roadmap and `TODO.md` so they still match reality.
- If you finish a significant item, mark what is now implemented versus what remains planned; do not leave the roadmap stale.

Summary

- I reviewed the codebase first so the plan is anchored in what already exists rather than in the email ideas alone.
- The original engine fixes, generic local NPC behaviors, Brave Sir Knight migration, minimum character persistence, room-aware heartbeat scheduling, possum encounter, Green/canopy slice, initial Val/tavern slice, core admin operations, bounded structured operational logging, and the schema-v3 account-key consistency fix are now implemented. The account incident still requires production verification of the database identity/path before any content or OpenRouter work resumes.
- This plan is meant to be a living document you can keep on disk and revisit over multiple sessions.

First fixes

- [done] Fix the command dispatcher bug in [blingmud.py:695](</home/gwen/codex-stuff/BlingMUD/blingmud.py#L695>) where `Session.handle_command` uses `session` instead of `self`; this is now corrected in the current codebase.
- [done] Fix the wearable-slot bug in [core.py:55](</home/gwen/codex-stuff/BlingMUD/core.py#L55>) where `Item.__init__` ignored the `worn_where` argument and forced every wearable into `Head`; this is now corrected in the current codebase.
- [done] Add regression tests for both issues before doing broader refactors so the same mistakes do not slip back in.
- [done] Replace persistent unsalted SHA-256 password storage with salted PBKDF2-SHA256 hashes, while accepting and automatically upgrading legacy user and admin hashes after successful authentication.
- [done] Write `admin.hash` with owner-only permissions and compare password digests using constant-time comparison.
- [done] Unregister NPCs from `NPCManager` when they leave a room so removed NPCs do not remain in the global tick list indefinitely.
- [done] Remove Brave Sir Knight's unbounded retry-until-different dialogue loop; degenerate random sources and one-entry pools now complete in bounded time without losing immediate-repeat suppression when alternatives exist.
- [done] Bound the Knight concurrency test's barrier and thread joins, and add `run_tests.py` as the required 30-second subprocess watchdog so a regression cannot silently consume a CPU core indefinitely.
- [done] Make random and FSM behaviors tolerate being detached or moved during a tick, reject Unicode terminal and bidirectional controls in structured NPC output, and prevent a backwards wall-clock adjustment from increasing the Knight's fire strength.
- [done] Make `NPCManager.stop()` and per-NPC actor shutdown use finite joins and safely tolerate being called before startup; a non-returning callback is isolated to one permanently inert actor without a replacement-thread leak.
- [done] Align gameplay item creation with persistence bounds: cap player inventories and room item lists, reject take/drop/bling/reward/harvest/order operations safely at the boundary, and do not consume one-time rewards or finite shared resources when a player cannot carry the result.
- [done] Apply the account system's 12–4096 character password bounds to the admin-password setter, retain owner-only hash writes, and make the script import-safe for direct regression coverage.
- [done] Remove the authentication executor's unbounded shutdown wait. The same two-worker/16-pending public pool now uses fixed daemon workers, cancels queued authentication on close, waits at most one shared second, and reports a still-running job without spawning a replacement.

What exists vs what is still planned

- Implemented now: the first-fix engine bugs above, prominent plaintext-Telnet warnings at startup and before authentication, deliberate hidden-input echo/redraw suppression, selector-owned sockets/pre-auth/timeouts/output, bounded authentication workers/rate limits/finite shutdown, no-listener socketpair and fake-clock integration coverage, one sequential gameplay worker per authenticated player, one shared incremental Telnet/UTF-8 parser with safe command-token completion, validated global/room command specs and generated help, room-first ordinary dispatch with protected safety/admin names and duplicate-registration rejection, item/slot-aware `/unequip` with `/remove` alias, admin-only confirmed shutdown/output-preserving kick/shared-API heal/focused-or-bulk save/bounded status views, bounded JSON-lines operational events for authentication/connection/server/admin/persistence/room/NPC metadata with conservative redaction and exception-type-only failures, 60-second dirty-only character and shared-world autosave, separate bounded/coalescing character and one-key world writers with final saves inside the ten-second graceful deadline, callback-complete queue rejection, transactional SQLite schema migrations through version 2, bounded character JSON v2 with v1/legacy migration and six whitelisted items, durable recent-collapse/status timestamps and safe offline intoxication decay, strict version-1 world JSON for acorn/Wisp state, matching gameplay inventory/room-item limits, centralized bounded damage/healing/intoxication APIs, one-damage falling acorns, five-damage Val cats, non-destructive zero-health collapse/return to Town Square, recent-collapse recognition by Val, non-blocking one-point-per-minute online intoxication decay, NPC-manager removal cleanup, explicit room activity snapshots, global hot-room-only NPC heartbeat selection, restartable/event-stoppable ticker lifecycle, per-NPC bounded actor isolation with inert timeout fallback and no replacement workers, the shared NPC behavior/event-dispatch contract, Unicode-control-safe structured NPC actions, reusable local random and data-backed FSM behaviors, Brave Sir Knight's migration onto `FSMBehavior`, bounded non-repeating dialogue selection, detached-room tick safety, the stateful Suspicious Alley bin-possum encounter, the first Village Green/Hanging Tree/Wisp Mother slice, the initial Val's Hella Holler/Val/fixed-drink slice, and regression coverage for all of them.
- Still planned: richer status effects, renewable but bounded village ecology, advanced admin brain/memory/mode/reload tools, richer custom horn drinks/food/prices/regulars, and the remaining village content from the email threads. The advisory wrapper now supports one-use choice-index hints for approved local candidate pools, Knight traveller memory is structured and capped at 64 entries, and explicit version-1 Knight/Val snapshots persist through schema v4. Corbel's local-FSM turnery, fixed acorn trade/crafting, bounded coins, persistent Goblets/Mash, and Val goblet filling are implemented; production multi-process/database identity verification remains outstanding. TLS and encrypted transport are explicitly excluded from this implementation plan; the residual plaintext risk is accepted and must remain honestly documented.
- Future agents must keep this section current whenever they land meaningful implementation work; if they do not, the roadmap will drift out of sync with reality.
- OpenRouter is now explicitly authorized and partly implemented: the optional adapter rejects redirects and insecure keys, validates the live catalogue within a 2 MiB bound, accepts only bounded free text models, rotates with cooldown fallback, and runs through a finite advisory runtime with global, room, and NPC request budgets. Brave Sir Knight and Val remain local-authoritative wrappers with choice-index hints and durable bounded snapshots. Live catalogue refresh succeeds with the configured key; live completion can exhaust the current free pool and falls back locally. Remaining local work is admin controls and the remaining village content.

NPC architecture

- Implemented foundation: `NPCBehavior` owns the common enter, leave, speech, emote, and tick contract; `NPC` delegates those hooks through one lazy bounded `NPCActor`; rooms deliver speech and emote observations; raised callback failures are isolated while the actor remains usable; behavior output can contain ordered validated say/emote/damage `NPCAction` objects; `SimpleRandomBehavior` provides timed local chatter and optional event reactions; and `FSMBehavior` provides validated named states, ordered enter/exit/transition actions, event transitions, conditional branches, active-room timers, trusted state-local handlers, controlled state selection, and inspectable timing state.
- [done: callback isolation] Each NPC has one daemon actor and at most 16 queued jobs. Tick jobs coalesce. Normal decisions get one second; all recipients are scheduled before a shared wait, so a non-returning callback cannot prevent later NPCs from deciding. Deadline breach closes that actor, rejects/drains work, records diagnostics, and selects an inert fallback without creating a replacement thread. The trusted Python thread cannot be forcibly killed and may remain daemon-stuck until process exit; this is explicitly contained rather than misrepresented as cancellation.
- [done: lock-safe actions] Actor workers only run decision logic and normalize actions. The waiting caller performs each action tuple exactly once, preventing an actor from deadlocking on a session state lock already held by the gameplay thread.
- Brave Sir Knight is now migrated: `BraveSirKnight` is a thin world entity backed by `BraveSirKnightBehavior(FSMBehavior)`. Its five validated top-level states are data-backed, while the character's complex state-local patrol, greeting, water, fire, and wood sequences run as trusted FSM handlers and return structured `NPCAction` output. This is an intentional hybrid rather than a claim that every chore substep is declarative.
- The migration is guarded by a dedicated characterization suite covering identity and resources, timing and empty-room behavior, every state and resource-priority branch, random and directional dialogue pools, repeat suppression, first/returning/Lady Gwen greetings, complete chore sequences and failure paths, memory and farewells, no-op observations, invalid-state recovery, and concurrent action-buffer isolation. Preserve these observable behaviors unless a deliberate product change also updates the tests and roadmap.
- Still planned in this layer: additional validated action types as game mechanics require them, optional structured memory, activation/deactivation events, and the `llm_fsm` advisory wrapper.
- [done: local behavior stage] Extract a generic NPC behavior contract from the existing Brave Sir Knight implementation and provide reusable simple-random and deterministic FSM modes; the LLM-assisted wrapper remains planned.
- [done: migration stage] Brave Sir Knight now runs as `BraveSirKnightBehavior(FSMBehavior)` with a validated five-state graph, behavior-owned state/content, trusted state-local handlers for its detailed sequences, structured action output, and a thin `NPC` entity wrapper.
- [done] Make “random utterance NPCs” the simplest possible behavior class: `SimpleRandomBehavior` supports weighted ambient speech/emote pools, timed output, optional local event reactions, no state machine, and no LLM.
- [done: engine stage] Make FSM NPCs data-backed: `FSMBehavior` validates state graphs, targets, timers, actions, trusted callable conditions, and trusted handlers without evaluating configuration strings.
- Make LLM NPCs an optional wrapper, not the authority: the LLM should propose structured actions and text, while the engine still validates them against the NPC’s current state and allowed event set.
- Keep the current `on_player_enter`, `on_player_leave`, `on_say`, `on_emote`, and `tick` hooks, but route them through a single behavior interface so each NPC can choose its execution style.
- Preserve NPC memory as structured data, but keep it separate from behavior so a simple NPC can have no memory and a tavern NPC can have rich memory without special-casing the engine.

OpenRouter and failover

- OpenRouter must be entirely optional. On startup and configuration reload, check for the API key and all required provider settings before constructing or enabling the remote brain client.
- Read secrets from deployment configuration such as environment variables or an ignored local secrets file; never hard-code an API key, commit it, include it in prompts, expose it through admin output, or write it to ordinary logs.
- If the API key or any required OpenRouter setting is absent, empty, malformed, or explicitly disabled, mark the provider as `disabled_by_config`, make no remote requests, and run every affected NPC through its declared FSM or simpler local fallback.
- An LLM-capable NPC definition is invalid unless it also declares a complete local fallback behavior. Content loading should reject or safely downgrade definitions that would become unusable without the provider.
- The server, login flow, rooms, commands, persistence, NPC event delivery, and all required game mechanics must start and remain functional with no LLM configuration, no network access, exhausted budget, or a sustained provider outage.
- Add a central brain client in the server process that talks to OpenRouter asynchronously so gameplay threads never block directly on remote calls.
- Use config-driven model tiers rather than hard-coded model names: a cheap tier for casual chatter, a mid tier for more nuanced dialogue, and a premium tier only for rare, high-value interactions.
- Gate all OpenRouter usage behind a health-checked circuit breaker: on timeout, 429, 5xx, invalid JSON, or schema mismatch, mark the remote brain unhealthy and fail over to FSM-only mode.
- Re-enable LLM mode only after a successful probe call, not immediately after the first failure.
- Make the LLM output structured JSON events only, never freeform text, so it can emit multiple actions per turn and the engine can still validate item creation, movement, speech, and emotes.
- Keep the OpenRouter prompt assembly explicit: role prompt, room snapshot, nearby players, NPC memory summary, current FSM state, allowed actions, and token budget.
- Make the “brain selection” decision cost-aware and priority-aware: simple NPCs never consume LLM calls unless explicitly marked as LLM-capable.

NPC scheduling and room activity

- Move NPC ticking to a room-aware scheduler so empty rooms do not burn CPU or token budget.
- Treat a room as active only when at least one player is present; when the room is empty, suspend all NPC ticks and remote-brain calls for that room.
- Wake a room immediately when a player enters, speaks, emotes, or otherwise interacts with the room.
- Keep any purely code-driven world timers separate from NPC brains so ambient world effects can continue without spending LLM budget.
- Add a priority policy for LLM-capable NPCs based on complexity, interaction volume, and room popularity.
- Use a weighted score such as complexity + recent interactions + current room occupancy + room popularity, then divide by estimated token cost so the most important and most-used NPCs get expensive brain time first.
- Cap per-NPC and per-room token budgets so one busy location cannot starve the rest of the world.
- Default lower-priority NPCs to FSM mode whenever budget is tight, while higher-priority NPCs retain LLM access.
- [done: local heartbeat layer] Rooms expose locked activity snapshots with current occupancy, visits, valid player interactions, and last-activity time. Duplicate lifecycle calls are inert, stale players cannot inject NPC room events, and successful leave clears the player's room reference.
- [done: local heartbeat layer] `NPCManager` now snapshots only registered NPCs that are still members of rooms with players and rechecks eligibility immediately before each tick. Detached and cold-room NPCs therefore receive zero global heartbeat calls regardless of behavior type.
- [done: ticker lifecycle] The ticker waits on a stop event rather than an unconditional sleep, can restart after a complete stop, and refuses to create a replacement while an earlier ticker thread remains alive.
- [remaining safety limit] Trusted Python cannot be forcibly terminated. A timed-out actor is permanently inert and never replaced; the one old worker may remain daemon-stuck until process exit. Do not add replacement workers, asynchronous exception injection, or unbounded queues as a false cancellation mechanism.

Persistence and character state

- Keep the current SQLite account store, but formalize player state as a versioned JSON blob rather than a loose prototype payload.
- Preserve the existing login table shape for compatibility, but treat the player state column as a first-class serialized character snapshot with migration/version metadata.
- [done] Save character state on logout and every 60 seconds when its serialized snapshot changed, so ordinary disconnects do not lose all progress since login.
- Serialize room ID, inventory, equipment, stats, status effects, quest flags, and NPC relationship/memory data explicitly rather than trying to pickle live objects. Never serialize authenticated session admin privilege as character state.
- Add a player-state repository layer so loading/saving a character does not depend on session code.
- Add migrations for future schema evolution so new fields can be added without breaking old characters.
- Keep auth data and gameplay state separate in the design, even if they initially live in the same SQLite database.
- Password storage now uses salted PBKDF2-SHA256 and upgrades legacy SHA-256 hashes after a successful login; this is implemented, but Telnet transport remains unencrypted and must not be treated as secure authentication over an untrusted network.
- [done: migration layer] `player_state.py` owns strict version-2 JSON for room ID, fabulousness, maximum/current health, intoxication, recent-respawn state, a bounded wall-clock status timestamp, inventory, and equipment. Version-1 documents migrate in memory with safe defaults and no invented offline interval; legacy `{}` also migrates safely. Version-2 restores subtract one intoxication point per whole offline minute, clamp at zero, and preserve a future timestamp when the wall clock moves backwards.
- [done: database migrations] SQLite uses transactional `PRAGMA user_version` migrations through schema version 3. The migration creates/preserves the account and world-state tables idempotently, repairs only unambiguous stale canonical account keys, keeps existing account rows, and refuses collisions or a database from a newer runtime rather than downgrading it.
- [done: shared-world layer] `world_state.py` owns strict version-1 JSON for finite acorn supply/danger/harvest totals and Wisp ward/absence/harm state. The document has a 4 KiB limit, exact keys, finite range and consistency checks, atomic restore, and one known SQLite key. A separate one-key coalescing writer saves dirty snapshots every 60 seconds and at graceful shutdown; room/NPC presence is reconciled after load.
- [done: minimum layer] Current item restoration is an explicit `pimp_hat` / `royal_possum_bottle_cap` / `giant_acorn` / `val_healing_potion` / `valkyrie_mead` / `horn_born_special` template whitelist with bounded payload, inventory, equipment, stat, password, and input sizes. Gameplay acquisition paths share the same 100-item inventory bound, room item lists have a separate 100-item bound, unknown templates and inconsistent equipment fail closed, and no save data controls imports or class names.
- [done: minimum layer] Successful logins restore the last known room, with removed/unknown rooms falling back to the starting room. Disconnect saves before room removal, and a failed or lossy save leaves the previous database state intact while cleanup continues.
- [security invariant] Admin privilege remains session-only and is deliberately absent from character JSON; never turn a gameplay save into an authentication or authorization source.
- [done: autosave layer] Selector maintenance triggers a 60-second pass, but each session state lock is acquired non-blockingly so autosave cannot stall network I/O. Busy sessions are skipped until the next pass. Changed snapshots are compared against the last submitted JSON and queued; identical snapshots produce no database write.
- [done: one writer] A single daemon persistence worker accepts at most 64 pending player keys, coalesces multiple pending snapshots for the same lowercase name to the newest full snapshot, reports failures to the session so later passes retry, and never grows an unbounded task queue.
- [done: final save/shutdown] Disconnect waits up to ten seconds for its final or already-pending snapshot before leaving the room. Process shutdown closes sockets to wake gameplay workers, gives all gameplay joins and persistence flush/stop one shared ten-second deadline, and reports rather than waits forever on a stuck worker/write.
- Still required here: more item templates as real content lands and eventual structured quest/relationship fields when those systems actually exist. Every later schema change must add an explicit migration and advance the documented version deliberately.

Connection and session runtime

- [done: selector layer] `selectors.DefaultSelector` owns the listener, accept/read/write readiness, pre-auth line delivery, idle checks, and per-connection output queues. Unauthenticated sockets no longer create threads.
- [done: understandable gameplay layer] `Session.send`, `prompt`, `read_line`, `move`, `handle_command`, and `disconnect` retain their sequential API. Exactly one daemon gameplay worker is started only after a player is authenticated and inserted into the active-session table.
- [done: bounded authentication] Password hashing and login database work run in a two-worker pool with at most sixteen pending jobs. Completion returns to the selector thread before a connection changes authentication state.
- [done: bounded authentication shutdown] The pool is implemented as two fixed daemon workers rather than an executor with an unconditional wait. Close rejects new work, cancels queued work through ordinary completion callbacks, gives active workers one shared second to finish, and logs a timeout if trusted database/hash work remains stuck; it never leaks replacement workers.
- [done: resource policy] Limits are 64 total connections, 32 pre-auth connections, 32 authenticated players, 8 connections per source IP, 64 queued authenticated input lines, and 256 KiB queued output per connection. Overflow disconnects instead of growing memory indefinitely.
- [done: abuse/idle policy] Five failures for one IP/account pair within five minutes block that pair; one IP may claim three validated account creations per hour. Pre-auth idle timeout is 120 seconds. Authenticated users receive BEL at ten idle hours and are saved/disconnected at twelve; any received input resets the idle timer.
- [done: deployment configuration] `BLINGMUD_HOST` and `BLINGMUD_PORT` configure the listener, retain `0.0.0.0:4000` defaults, and fail startup on malformed values.
- [done: parser layer] Selector and blocking compatibility input share `TelnetInputParser`. It incrementally decodes fragmented UTF-8, strips fragmented WILL/WONT/DO/DONT negotiation and SB/SE subnegotiation, treats escaped IAC as data, collapses CR-LF and CR-NUL, accepts LF, removes one decoded codepoint per backspace, drops terminal/bidirectional controls, and enforces character bounds without retaining excess input.
- [done: event primitive] Tab produces a bounded `TabInputEvent` carrying the current input instead of terminating the line, and `Session` receives it on its sequential worker for command-aware handling.
- [done: command specifications] Every registered global command now validates its name, aliases, slash-prefixed usage and non-empty summary at import. The Alley, canopy, Green and Holler expose equivalent `Room.command_specs`, and `/help` list/detail output is generated from specs visible to the current player.
- [done: command completion] Tab completion operates only on the initial slash-command token, hides admin-only specs from non-admins, canonicalizes exact aliases, completes unique names, extends a common canonical prefix, or lists finite candidates. Parser replacement checks the exact text that generated Tab before mutating, so delayed events cannot overwrite newer input. Argument completion remains deliberately unimplemented.
- [done: dispatch precedence] Ordinary `Room.on_command` handlers run before global fallbacks, including room aliases, and room specs take matching help/completion precedence. The reserved names `admin`, `shutdown`, `kick`, `heal`, `save`, `adminstatus`, `quit`, and `exit` bypass rooms even if room code tries to claim them.
- [done: registry safety] Global registration validates complete metadata and checks every normalized primary name/alias before mutating `COMMANDS`; any collision raises and leaves the registry unchanged.
- [done: equipment UX] `/unequip <item or slot>` and its `/remove` alias resolve a case-insensitive slot before an equipped item name, apply the item's trusted unequip hook once, delete the equipment mapping, preserve inventory membership, notify the player, and broadcast the removal.
- [done: no-listener integration] Real selector readiness is covered with unnamed local socket pairs for fragmented Telnet read/echo, hidden-password selector authentication through the actual bounded pool, output-draining graceful shutdown, and fake-clock idle closure. Tests have finite pumps and teardown, never call `bind()`/`serve_forever()`/`main()`, and capability-skip only when a host explicitly denies local socketpair writes.

Admin and operational tooling

- [done: core operations] `/shutdown now [reason]` requires explicit confirmation, announces to active sessions, closes the listener, allows up to one second to drain queued output, then reaches the existing ten-second gameplay/final-character/final-world shutdown path. `/kick <player> [reason]` refuses self-kick, announces before output-preserving close, and leaves saving to normal disconnect. Reasons are 200-character/control-safe text.
- [done: bounded intervention] `/heal [player] [amount|full]` acquires the target state lock for at most one second and uses `Player.heal`; `/save [player|all|world]` can wait up to two seconds for a focused save while `all` queues character/world snapshots non-blockingly. Waiting session saves now bound state-lock acquisition as well as writer completion.
- [done: current inspection] `/adminstatus` shows bounded connection/session/schema/NPC/persistence/status counters; `rooms` lists at most 20 room activity records and `npcs` lists at most 20 NPC room/mode/fallback/queue/error records. Admin output contains no auth material or provider secrets, and all five commands are hidden from non-admin help/completion.
- Add admin inspection for structured NPC memory, current LLM budget use, and brain health when those systems exist.
- Add a way to force an NPC between random, FSM, and LLM modes for debugging.
- Add commands to reload NPC definitions and content without restarting the server.
- Add a command to force brain failover and another to force a health probe, so the fallback path can be tested live.
- Add a safe player-state inspection and reset tool for debugging corrupted saves.
- [done: local operations] `operational_log.py` writes bounded JSON-lines events for authentication/rate limiting, connection/server lifecycle, persistence, room-local triggers, NPC decisions/failures, and admin actions. Controls are neutralized, secret-like field names are redacted, reserved metadata is protected, and sink failures cannot break gameplay. Exception events contain only a type. Logs deliberately omit passwords/hashes, chat/emotes, prompts, command arguments, admin reason text, NPC output, and serialized state.
- Extend that event contract to future LLM calls, budget decisions, circuit-breaker transitions, health probes, fallback, and recovery. Provider keys and prompt/response content must remain absent by default.
- Keep the server MOTD and session-only admin password flow. Core status reporting is implemented; later diagnostics must retain the current bounds and secret-redaction invariant.

Faithful implementation of the email content

- Build the village as a cohesive zone with the Village Green as the central hub and the existing rooms connected into that map rather than replacing everything at once.
- Keep the current starter content alive as regression/test scaffolding, but connect the new village layout into the same world so the new material can be reached naturally.
- Implemented starter-content expansion: the Suspicious Alley now contains a hidden, local-FSM bin possum revealed through `/search bin`; it rejects unsafe or unsuitable offerings, accepts a pimp hat through implicit item-first, `item to possum`, or `possum item` grammar, becomes friendly, reacts to room speech, and awards each player one harmless bottle-cap keepsake through `/pet possum`. Generic `/take` and `/get` recognize its visible aliases and accurately report that an NPC is not an item. This encounter uses no network or LLM service.
- Treat the following room-and-NPC designs as a faithful implementation target, not a rough inspiration.

Val’s Hella Holler, per-location checklist

- Room identity:
  - cozy, crowded tavern
  - sturdy river-rock construction
  - tiled roof
  - warm fireplaces
  - candles in glass
  - private booths
  - a raised bard platform
  - a huge carved tree-trunk bar
  - shelves of exotic bottles
  - cats everywhere
- Room mechanics:
  - food and drink prices should be favourable to real adventurers
  - the tavern should feel socially active even when only one player is present
  - drink ordering should support intentionally impossible fantasy drinks
  - the room should allow joke delivery and warm tavern banter
- Val:
  - refugee Valkyrie from Asgard
  - short for Valkyrie
  - happy to have escaped endless battlefield duty
  - simultaneously behind the bar, serving tables, and handling requests
  - capable of one-room “teleport” style service by way of duplicates / magical omnipresence
  - able to tell short off-colour jokes on request
  - able to notice injury, exhaustion, drunkenness, or bloodied gear
  - able to protect the tavern by calling on the cats if attacked or seriously threatened
- Val response requirements:
  - support serving a drink
  - support telling a joke
  - support moving attention or service across the room
  - support summoning cats
  - support emitting more than one event in one response
- Horn / drink requirements:
  - magical cow horn behind the bar
  - can conceptually produce any drink ingredient
  - drink must still become a concrete in-engine item
  - drinks must carry explicit effects, including healing and intoxication
  - always-allowed healing potion path should remain explicit and reliable
- [done: initial slice] The Holler is connected north of the Green and includes the river-rock/tile/fire/candle/booth/platform/tree-bar/bottle/cat identity. Val is a local `FSMBehavior` with Asgard-refugee lore, bounded jokes, horn service, cosmetic same-room omnipresence, injury/intoxication notices, ordered multi-action output, Wisp-harm awareness, and non-lethal cat defense. This path has no provider configuration or network dependency.
- [done: initial drink mechanics] `/order` maps healing concepts, ordinary alcohol concepts, and all other bounded concepts to three fixed concrete persistent items. `/drink` applies clamped health/intoxication effects through the central player APIs, consumes successful drinks, preserves alcohol refused at maximum intoxication, and leaves healing potion available at maximum intoxication. Online intoxication now decays by one point per whole minute through non-blocking selector maintenance. All current drinks are on the house because currency does not exist yet.
- [done: initial health consequence] Variable damage is centralized. Falling giant acorns deal one damage and Val's cats deal five. Reaching zero collapses the player without deleting possessions or fabulousness, clears intoxication, restores one health, returns them to Town Square, and marks a recent respawn that Val recognizes once. Injury is the at-or-below-half-health condition and clears only after healing above half health.
- [remaining fidelity] Fixed Corbel prices, Acorn Mash, bounded coins, and reusable Goblet filling are implemented. Still add bounded regular/recent-order/bad-behaviour memory, exhaustion and bloodied-gear signals, richer intoxication side effects, and safe custom drink payloads with names/descriptions/provenance. Durable offline intoxication decay is now part of character schema version 3. The current impossible request becomes a fixed `horn-born special`; cosmetic duplicate service does not create multiple Val NPCs.

Village Green, per-location checklist

- Room identity:
  - central outdoor commons
  - enormous floating tree above it
  - ground-level hub for all neighbouring village content
  - visually transformed at night by Wisps
- Room mechanics:
  - day/night room description changes
  - Wisps act as ambient light source at night
  - acorn harvest counter governs ground-level hazard intensity
  - low harvest state produces occasional falling-acorn bonks
  - staircase / route upward into the canopy
- Failure / consequence:
  - if the acorn economy is neglected, idle players in the Green get lightly punished by the environment
  - the hazard should be funny, not oppressive
- [done: initial slice] The Green is connected west of the existing Town Square and up to a separate canopy room. It has injected/testable day/night descriptions, visible night Wisps, a hidden room-aware falling-acorn heartbeat, and a shared danger counter reduced by canopy harvests.
- [current bound] The initial canopy has twelve runtime acorns and allows one giant acorn to be carried at a time, preventing unbounded item creation. The first Corbel economy turns those acorns into fixed-price coins or reusable Goblets; renewable supply remains planned.

Master Corbel / Turner shop, per-location checklist

- NPC identity:
  - village woodworker and turner
  - sits on the edge of the Village Green rather than inside the tavern or smithy
  - practical artisan, not a magical being
- NPC mechanics:
  - buys giant acorns from players
  - turns acorn shells into ornate goblets
  - sells Acorn Goblets as a useful tavern-adjacent item
  - sells Acorn Mash as a cheap popular food
- World integration:
  - Acorn Goblets should be explicitly useful at Val’s tavern
  - the goblets should support carrying or holding Val’s impossible drink creations
  - the acorn economy should meaningfully connect the canopy harvest loop to the tavern loop

Acorn Goblet / Acorn Mash loop

- Acorn Goblet:
  - crafted or sold by Master Corbel
  - should feel ornate and practical at the same time
  - should exist as an inventory item with real tavern utility
  - should connect the player’s harvest work to Val’s drink service
- Acorn Mash:
  - cheap, common food
  - should be one of the village’s simple staple consumables
  - should make the Village Green economy feel lived in, not just quest-like

Floating Hanging Tree canopy, per-location checklist

- Room identity:
  - canopy traversal zone
  - no trunk visible from below
  - roots hang downward in impossible fashion
  - large leaves, acorns, rope rungs, steps, and bridges
- Room mechanics:
  - harvesting acorns should be a real action
  - both `harvest acorn` and `gather acorn` should work
  - harvesting should produce a heavy giant acorn item
  - harvesting should reduce the danger state below
  - the canopy should feel precarious but navigable
- Failure / consequence:
  - traversal should be risky enough to matter, but not so punishing that players avoid the loop entirely

Wisp Mother, per-location checklist

- NPC identity:
  - ambient guardian rather than conversational actor
  - a slightly larger faint blue orb near the base of the staircase
  - non-verbal by default
- NPC mechanics:
  - examine should produce a warm pulse or similar response
  - attack should cause disappearance / removal
  - removal should darken the Village Green for a prolonged period
  - the zone should react socially to harm against her
- Failure / consequence:
  - attacking the Wisp Mother should have obvious village consequences, not merely personal combat consequences
- [done: initial slice] The non-verbal Mother can be looked at or examined for a warm pulse, protected with a one-hit Wisp ward, removed by violence, and restored after a thirty-minute runtime darkness period. Her loss immediately darkens the Green, broadcasts village horror, and increments shared harm state for later NPC reactions.
- [partly done consequence] Val consumes the shared harm count on the next tavern arrival and responds with anger plus a cat reaction. Other villagers still need reactions, and the runtime darkness/acorn ecology still needs durable world-state persistence before it can survive restart.

The Smithereens, per-location checklist

- Room identity:
  - indoor smithy
  - hot forge
  - smoke, charcoal, iron, sulfur
  - clutter of scrap and old equipment
  - polished custom weapons and armour behind the counter
  - vibrating anvil as ambience
- Room mechanics:
  - scrap browsing should show discounted, random, low-to-mid-tier metal gear
  - scrap browsing should be immediate and useful, not hidden behind multiple menus
  - commission/customization should be a tiered menu
  - players should be able to pick a base item, then stats, then pay a level-sensitive fee
- Eisele:
  - slightly built but competent blacksmith
  - practical, neutral, professional vendor
  - buys metal loot from players
  - sells custom weapons and plate armour
  - acts as the smithy’s buy/sell/value authority

Tackdriver, per-location checklist

- NPC/object identity:
  - a forged hammer with star-flecked ore and blinking eye-like inlays
  - attached object mob, not a conventional humanoid
  - socially opinionated and ideologically loud
- NPC mechanics:
  - idle commentary while Eisele is working
  - `examine hammer` response
  - `listen hammer` response
  - `talk hammer` / `ask hammer about society` infodump
  - should feel like a living talking tool
- Content requirements:
  - keep the socialist / labour / means-of-production flavour intact
  - the hammer’s voice should be comic but committed

Ceridwen’s Cottage, per-location checklist

- Room identity:
  - dim earthy cottage
  - smells of crushed mint, dried lavender, swamp root, herbs, and potion fumes
  - bundles of herbs on the walls and hanging from beams
  - casks of fermenting potions
  - a big bubbling cauldron / stew pot
- Room mechanics:
  - ambient echo events should periodically fire
  - green vapor face effect
  - clawed paw / spoon slap effect
  - the room should function as a healing and magic vendor space

Ceridwen, per-location checklist

- NPC identity:
  - eccentric older herbalist
  - dirt under the fingernails
  - leaves in her hair
  - sharp, no-nonsense temperament
- NPC mechanics:
  - sell healing salves
  - sell antitoxins
  - sell basic stat-boosting potions
  - unlock experimental high-tier potions if the rare weed is presented
- Unlock design:
  - rare weed should come from the garden hazard zone
  - the unlock should be meaningful and not trivial
  - the menu should change after the unlock, not just display extra flavour text

Overgrown Herb Garden, per-location checklist

- Room identity:
  - chaotic outdoor labyrinth
  - towering thorns
  - nightshades
  - glowing flora
  - heavy pollen and fumes
  - disorienting, slightly toxic atmosphere
- Room mechanics:
  - permanent confusion flag or equivalent
  - movement redirection / looping logic
  - players may have to issue movement commands multiple times to escape
  - exiting should leave a temporary disoriented status effect
  - rare weed harvest target should exist here
- Failure / consequence:
  - the garden should punish unprepared players with confusion, not with opaque instant death

Temple of the Self, per-location checklist

- Room identity:
  - unadorned archway
  - perfect still water floor mirror
  - mirrored walls
  - skylight with natural light
  - silver-bound book on a marble pedestal
- Room mechanics:
  - `look mirror` / `examine water` should reflect the player’s own custom description
  - `sit` and `meditate` should be fast recovery / regeneration actions
  - room should be a strict safe zone
  - room should host the respec / character rebuild interaction
- Respec design:
  - explicitly self-directed
  - framed as reforge self / alter stats / reshape destiny
  - should be safe, readable, and not need a priest or other external authority

Tome of Indulgence, per-location checklist

- Object identity:
  - silver-bound book on the pedestal
  - lore object, not just a decoration
- Object mechanics:
  - `read book` returns a philosophy snippet about self-ownership, conscience, and authority over one’s own flesh
  - the text should be stable enough for players to recognise

The Temple’s stat-allocation / respec font

- Interaction requirements:
  - looking into the pool should open the rebuild menu
  - typing `reforge self` or `alter stats` should trigger the character rebuild flow
  - the temple should be the canonical place for stat redistribution
- Safety requirements:
  - respec should not be abusable in a free endless loop
  - the system should have clear rules for cost, cooldown, or gating

NPC memory / social systems, per-location checklist

- Tavern memory should hold a bounded set of regulars, recent drinks, and bad behaviour.
- Memory should support:
  - who is a regular
  - what they usually order
  - whether they were injured, drunk, or exhausted last time
  - whether they were rude or hostile
- Memory should roll up into short-term labels like:
  - just now
  - earlier today
  - earlier this week
  - last week
- The memory model should feed both roleplay and brain selection.

Detailed room interaction acceptance criteria

- A future agent should treat the following as concrete acceptance tests for the content pass:
  - the tavern can serve a generated drink and speak in the same turn
  - the Green can become darker at night and brighter with Wisps
  - acorn harvesting changes a visible world state
  - the smithy can show browseable scrap
  - Eisele can commission a custom item
  - Tackdriver can be examined and can deliver an infodump
  - Ceridwen can unlock experimental potion stock via the rare weed
  - the herb garden can confuse movement
  - the Temple of the Self can show the player their own self-description
  - respec can be triggered from the temple
  - the Wisp Mother can be examined, protected, and lost with consequences

Failure modes to preserve

- If LLM is unavailable, all of the above content should still work in simpler scripted or FSM form.
- If a room is empty, it should not consume remote brain budget.
- If a player tries to exploit drink buffs or stat buffs, the engine should clamp or cut them off.
- If the room or NPC implementation is partial, the content should degrade gracefully rather than crash.

Implementation order by system

- Persistence and login:
  - stabilize user save/load
  - version character state
  - [done] add dirty-only 60-second autosave and final logout save through one bounded writer
  - keep auth and gameplay state distinct
- Core NPC engine:
  - [done: contract stage] abstract the behavior interface
  - [done: migration stage] migrate Brave Sir Knight onto the reusable FSM while preserving his observable behavior
  - [done] add simple random NPC behavior
  - [done: engine stage] add reusable FSM NPC behavior
- LLM layer:
  - add OpenRouter adapter
  - define structured JSON event output
  - add validation and failover
  - add circuit breaker and health probing
- Scheduler and budgeting:
  - make hot/cold room state explicit
  - stop ticking empty rooms
  - add priority scoring and token budgets
- Admin/ops:
  - add inspection commands
  - add mode switching and reload tools
  - add logging and diagnostics
- Village content:
  - Val’s Hella Holler
  - Village Green and Hanging Tree
  - Smithereens and Tackdriver
  - Ceridwen and the herb garden
  - Temple of the Self
  - Wisp Mother and related consequences
- Tests and polish:
  - regression coverage for the first bugs
  - NPC failover tests
  - room activity tests
  - content interaction tests

Definitions

- Hot room: a room with at least one player present, eligible to run NPC heartbeats, ambient reactions, and LLM consults.
- Cold room: a room with no players present, where NPC activity should be suspended unless the room has non-NPC world state that must continue.
- Brain provider: the component that decides how an NPC produces behavior output, such as simple random chatter, FSM logic, or LLM assistance.
- Fallback mode: the non-LLM behavior path used when the remote provider is unavailable, unhealthy, or too expensive for the current priority.
- Priority score: a budget input used to decide which NPCs get LLM access first based on complexity, room popularity, active interaction, and estimated token cost.
- Regular: a player the NPC has seen repeatedly enough to remember by name, recent behavior, and preferred orders or interactions.
- Structured event output: JSON describing concrete in-engine actions such as say, emote, spawn item, hand item over, or switch state, rather than freeform prose alone.

Implementation order

- Phase 1: [done] fix the concrete engine/security bugs, deliver versioned player persistence through version 2, save/load on login and disconnect, and add bounded dirty-only periodic autosave.
- Phase 2: [done] the generic behavior system, Brave Sir Knight migration, room activity metrics, global empty-room heartbeat suspension, and bounded per-NPC callback isolation are complete.
- Phase 3: add OpenRouter integration, circuit breaker failover, structured JSON output, and priority budgeting for LLM-capable NPCs.
- Phase 4: [partly done] core shutdown/kick/heal/save/status, room/NPC actor inspection, and bounded local operational logging are implemented; future NPC mode, LLM health/budget, memory, safe-reset, and reload controls remain.
- Phase 5: implement the village content as data-driven rooms, NPCs, items, room triggers, and status effects.
- Phase 6: add tests and regression coverage for the new architecture and the email-driven gameplay.

Test plan

- Regression test the `handle_command` bug and the wearable-slot bug directly.
- Preserve the Brave Sir Knight characterization suite as a migration and future-refactor contract: it must cover every top-level state, chore sequence, greeting and farewell branch, resource decision, directional observation pool, memory behavior, invalid-state recovery, timing rule, empty-room rule, and concurrent event isolation.
- Run the suite through `python3 run_tests.py`, retain its finite subprocess watchdog, and require every test-level barrier, condition wait, and thread join to have its own finite timeout.
- Verify that an empty room causes no NPC ticks and no OpenRouter calls.
- The local scheduler tests now prove that custom behaviors, not just built-in random/FSM behaviors, receive no heartbeat while detached or in empty rooms; they also cover room activity accounting, stale-event rejection, idempotent lifecycle events, cleared room references, prompt stop, clean restart, and refusal to replace a still-live ticker.
- Actor-isolation tests prove a timed-out callback cannot prevent a later NPC tick, switches only that actor to inspectable inert fallback, never creates a replacement worker, keeps actor/mailbox shutdown finite, and rejects work beyond the 16-job bound. Every test releases its artificial blocker and confirms the worker exits.
- The initial Green tests cover world wiring, `/up` and `/down`, day/night descriptions, hidden hazard actors, bounded `harvest acorn` and `gather acorn`, visible danger reduction, one-health bonks only while danger remains, giant-acorn persistence, and Wisp Mother examine/protect/harm/darkness/recovery behavior.
- The initial Holler tests cover world wiring and faithful visual details; Val's local FSM identity, speech triggers, bounded joke/lore/flirt/call/examine paths, injury/intoxication/recent-collapse and shared Wisp-harm reactions, multi-action horn service, all three drink mappings and effects, intoxication refusal, five-damage cat defense through the shared collapse path, and unrelated-command pass-through.
- Health/status tests cover input validation, health/intoxication clamps, the exact half-health injury boundary, non-destructive collapse state and relocation, whole-minute online and offline decay, recent-collapse round trips, version-1 migration without invented elapsed time, invalid timestamp rejection, and backwards-clock safety.
- Item-limit regressions prove that full inventories and rooms do not lose items, equipment effects, possum reward entitlement, or finite acorn supply; `/bling`, `/take`, `/drop`, canopy harvest, possum rewards, and Val orders all stop at the relevant bound.
- Verify that a populated room wakes NPCs correctly and that LLM calls are only made for eligible NPCs.
- Verify failover from LLM to FSM on timeout, invalid JSON, or OpenRouter errors, and verify restoration after a healthy probe.
- Verify priority ordering by simulating multiple active NPCs with different complexity and popularity scores.
- Verify save/load round-trips for character state, inventory, equipment, and status effects.
- The implemented minimum-layer tests now cover room/inventory/equipment/stat round trips including health, maximum health, intoxication, and all six item templates; legacy empty state and older version-1 health defaults; corrupt/oversized/unknown/inconsistent state rejection; safe room fallback; versioned new accounts; login restoration; logout ordering; failed-save preservation; session-only admin state; bounded input; and bounded password work. General status effects remain unimplemented and therefore are still a future test target.
- Shared-world tests cover version/range/size/exact-key/consistency rejection, atomic restoration, acorn and Wisp round trips, SQLite initialization/update, Wisp actor reconciliation, dirty-only asynchronous saves, immediate queue rejection callbacks, and successful retry.
- Admin tests cover privilege-gated generated metadata, shutdown confirmation and announcement, output-draining control, bounded kick reasons, shared healing clamps, focused/world/bulk save behavior, status views, and finite player-state-lock acquisition before a waiting save.
- Operational-log tests cover JSON framing, field/line bounds, control neutralization, secret-field redaction, protected metadata, broken sinks, exception-message omission, and the invariant that admin reason text never enters an action event.
- Authentication-shutdown tests hold one worker deliberately, prove queued work is cancelled, prove shutdown returns within its finite deadline, release the worker, and prove clean final teardown. Admin-password tests prove mismatch/short/oversized input never writes and valid input uses the protected hash writer.
- No-listener integration tests drive selector I/O, Telnet framing, the real auth pool, hidden password input, graceful output drain, and idle closure through unnamed local socket pairs and fake clocks. A restrictive host may report the three socketpair cases skipped only after an explicit `PermissionError` capability probe.
- Verify the new room interactions from the email: `harvest acorn`, `browse scrap`, `talk eisele`, `read book`, `look mirror`, and the Wisp Mother / Val reaction paths.
- Verify that the new content does not break the existing Crossroads and Fabulous Chamber demo rooms.

Assumptions

- Keep the current hybrid model: selector-owned network I/O and pre-auth state, bounded authentication workers, and one sequential gameplay thread per authenticated player. Do not introduce an asyncio/framework rewrite or a separate AI microservice unless a later explicit design change justifies it.
- Default to keeping the current Town Square as the entry point initially, then connect the new village hub into it as part of the content rollout.
- Keep using SQLite for persistence.
- Keep the current codebase’s existing rooms and NPCs as regression fixtures while the new system lands.
- Treat this document as the canonical living plan file you can save on disk and revise over multiple sessions.

Detailed architecture notes

NPC behavior model

- Every NPC should declare a behavior type explicitly:
  - `simple_random`: emits ambient speech/emotes from a weighted pool, with optional reactions to player entry, leave, say, and emote events.
  - `fsm`: runs a named finite-state machine with state-local enter/exit handlers, transitions, timers, and event-triggered branches.
  - `llm_fsm`: behaves like an FSM first, but may consult an LLM as an advisory layer when the room is active and budget permits.
- The engine should not treat “LLM NPC” as a separate species. It should treat it as an FSM-capable NPC with an optional brain provider.
- The reusable FSM is now portable enough to host Brave Sir Knight as a behavior-owned, data-backed top-level state graph; trusted handlers remain the supported extension point for character-specific multi-step mechanics.
- The behavior API should expose:
  - room activation and deactivation
  - player enter / leave
  - speech / emote observation
  - tick / heartbeat
  - decision output
  - memory update
  - fallback to non-LLM mode
- [done for speech/emotes] Output from behaviors is expressed as ordered, validated actions rather than raw return strings. Extend the action schema only as new engine-supported mechanics require it.

OpenRouter usage

- OpenRouter should be treated as an implementation detail behind a local brain adapter.
- Provider configuration should have an explicit enabled/disabled result. Missing credentials or incomplete settings mean locally disabled, not a startup error and not a reason to retry network calls.
- Configuration validation should distinguish `disabled_by_config` from runtime states such as `healthy`, `rate_limited`, and `circuit_open`, while all non-healthy states select local NPC behavior.
- The adapter should be responsible for:
  - prompt assembly
  - request throttling
  - timeouts
  - retries where appropriate
  - circuit breaker state
  - response parsing
  - schema validation
- Prompt content should be minimal and structured:
  - NPC identity and temperament
  - current FSM state
  - recent room events
  - nearby players and observations
  - memory summary
  - allowed verbs and output event types
  - hard budget ceiling
- The model should be forbidden from inventing game objects, verbs, or world mechanics that the engine does not already support.
- If the model wants to “do” something unsupported, the engine should ignore that branch and continue with a valid fallback action.

Room activity and cost control

- Only rooms with current player presence should be “hot.”
- A hot room may run:
  - NPC heartbeats
  - ambient echoes
  - LLM consults for eligible NPCs
  - immediate room reactions to player speech or emotes
- A cold room should be inert except for persistent world state updates that are not tied to NPC brain usage.
- Popularity should be a measurable room property, not just a vibe:
  - current player count
  - recent player visit count
  - number of interactions in a rolling window
  - whether the room is a hub, shop, or event location
- LLM budget priority should favor:
  - NPCs that are central to the current zone’s identity
  - NPCs with many nearby interactions
  - NPCs with high character complexity
  - NPCs in popular rooms with active players
- Lower priority NPCs should still function, but via FSM or random chatter, not via token-heavy LLM calls.

Persistence model

- Character save data should be split into stable groups:
  - identity and auth metadata
  - core stats
  - inventory and equipment
  - room location
  - status effects
  - social memory and NPC relationships
  - progression / flags / quests
  - non-authority gameplay roles or flags, if later required; never authenticated session admin status
- Save files should be versioned and migration-friendly so that future features like quests, status effects, and custom drinks can be added without breaking old characters.
- The save layer should own serialization details; gameplay code should ask for “save this player” and not care about the database format.

Faithful content expansion

- The email content should be kept emotionally and mechanically faithful, not merely summarized.
- That means:
  - Val should feel like a warm, formidable, overextended tavern Valkyrie who can be everywhere at once.
  - The smithy should feel like a working forge with a magical-socialist talking hammer and a practical blacksmith who buys loot.
  - Ceridwen should feel like a cranky herbalist with a dangerous but useful back garden.
  - The temple should feel like self-reflection rather than worship.
  - The tree canopy should feel vertical, risky, and alive with light.

Val's Hella Holler, in detail

- The tavern is a social center, not just a shop room.
- It should be visually and mechanically distinct:
  - river rock walls
  - tiled roof
  - warm fireplaces
  - candlelight in glass
  - central busy tables
  - private booths
  - a raised bard platform
  - a long carved tree-trunk bar
  - shelves of bottles and kegs
  - cats everywhere
- Val should be written as:
  - short for Valkyrie
  - refugee from Asgard
  - tired of endless battlefield duty
  - loud, cheerful, and physically dangerous if provoked
  - always willing to joke
  - always willing to serve
  - always willing to protect the tavern and its regulars
- Val should have a “magical horn” that can generate any drink ingredient or drink concept the player can imagine, but the engine should still materialize it as a concrete drink item with explicit effects.
- The tavern’s economy should reflect Val benefiting from real adventurers passing through, so she gives better prices to the player base than a normal vendor would.
- The tavern cats are not decoration only; they are the enforcement mechanism when Val is genuinely angered.

Val response model

- Val’s response schema should support multiple events in a single turn.
- A single response may include:
  - creating a drink item
  - placing it on the bar
  - handing it to the player
  - speaking a line
  - telling a joke
  - teleporting a duplicate to another table
  - escalating to cat defense
- The engine should allow “say plus action” in one turn, not force one or the other.
- A tavern interaction should be able to feel dynamic even if it is driven by simple scripted output under the hood.

Drink system details

- Drinks should be objects with:
  - generated name
  - generated description
  - ingredient provenance or conceptual flavor
  - restorative effects
  - intoxication value
  - optional special side effects
- The healing potion path should be always available and explicit.
- Alcohol-heavy drinks should create measurable negative side effects so the tavern does not become a free-stat exploit.
- Drink generation should be deterministic enough to be debugged, even if the exact flavor text is whimsical.
- Implemented first slice: `Drink` applies explicit clamped health and intoxication changes. `ValHealingPotion`, `ValkyrieMead`, and `HornBornSpecial` are fixed, whitelisted templates that survive save/load; the healing potion remains usable when alcohol is refused at the intoxication ceiling. This is a safe mechanical foundation, not yet the requested generated-name/description/provenance system.
- Remaining drink work: define a bounded serializable custom-drink schema, deterministic concept normalization, allowed effect tables, richer intoxication status effects, Acorn Goblet integration, food, and a real price/economy layer. Never persist raw model output or allow a generated concept to select classes, code, unbounded text, or arbitrary stat changes.

Village Green and Hanging Tree

- The Village Green should be the primary open-air hub below the floating tree.
- At day, it should feel broad and green and strange; at night, the Wisps should transform it into an eerie illuminated commons.
- The impossible tree should have no trunk and hang roots downward.
- Acorns should be large enough to feel absurd and useful.
- When the acorn-harvest counter is too low, idle players in the Green should occasionally get bonked by falling acorns as a recurring environmental joke and hazard.
- The staircase into the canopy should feel precarious but traversable.

Wisp Mother details

- The Wisp Mother should not speak.
- Her communication should be visual and reactive:
  - gentle pulse on examine
  - warmth or glow when acknowledged
  - disappearance if attacked
- The design intent is that harming her has a real community consequence:
  - the Green loses light
  - villagers are angry
  - the zone becomes less safe and less welcoming

Smithy and Tackdriver

- The Smithereens should look and feel like a blacksmith’s working room rather than a sterile shop.
- Scrap browsing should expose junk and salvage as a rotating discount stock.
- The commission menu should let players pick a base item, then tune stats, then pay a level-sensitive gold cost.
- Eisele should be practical and neutral, not mystical.
- Tackdriver should feel like a talking ideological hammer embedded in the shop’s ambience.
- The hammer’s behavior should be object-like: comments from the tool itself, triggered by interaction or ambient work.
- The hammer should be able to deliver a genuine ideological infodump if asked about society.

Ceridwen and the herb garden

- Ceridwen’s cottage should smell like dried herbs, swamp root, lavender, and growing trouble.
- The room should have ambient weirdness:
  - green vapor faces
  - a clawed paw snapping out of the cauldron
  - a spooned slap from Ceridwen when the pot misbehaves
- The herb garden should feel like a maze and a hazard.
- The confusion effect should be mechanical, not merely descriptive:
  - movement can loop
  - a player can get turned around
  - escape should not be immediate and guaranteed
- The rare weed should be a real gate to Ceridwen’s experimental menu.

Temple of the Self

- The temple should be silent, reflective, and intentionally anti-authoritarian in flavor.
- The mirrored water should show the player’s own identity, not some priestly judgment.
- Meditation should be a fast recovery and stabilization mechanic.
- Respec should be framed as self-rebuilding:
  - reforge self
  - alter stats
  - reshape destiny
- The temple should be safe, but not boring: it should be the canonical place for self-redistribution and identity reflection.

NPC memory expectations

- Memory should support regulars, favorites, and grudges.
- The tavern should remember:
  - recent drink orders
  - whether a player is a regular
  - whether they were rude
  - whether they were injured or exhausted last time
  - whether they were ever hostile
- Memory should decay intelligently:
  - very recent
  - earlier today
  - earlier this week
  - last week
  - older than that can collapse into summary or disappear
- Memory is not just for roleplay; it is a budget input for deciding whether an LLM consultation is worth spending.

Implementation checkpoints for a new agent

- First, make the codebase safe and boring:
  - fix the obvious bugs
  - make persistence real
  - make saves versioned
- Second, separate behavior from content:
  - NPC type
  - NPC state machine
  - NPC brain provider
  - room trigger system
- Third, add the OpenRouter path:
  - structured output
  - validation
  - fallback
  - circuit breaker
- Fourth, implement the email content exactly in the world model:
  - tavern
  - smithy
  - herb shop
  - temple
  - hanging tree
  - their NPCs
  - their mechanical hooks
- Fifth, keep iterating on fidelity and polish.

What “faithful” means here

- Faithful does not mean copying the emails verbatim into the game.
- It means preserving:
  - each room’s tone
  - each NPC’s role
  - each special interaction
  - the feel of the zone relationships
  - the practical engine hook behind each fantasy beat
- Whenever a location has a playful concept, the implementation should still make it mechanically real.
- Whenever an NPC is supposed to react to players, the engine should have a concrete observation and response path for that reaction.
- Whenever the emails imply multiple outputs from one interaction, the engine should support multiple output events from one NPC turn.

Handoff guidance for future sessions

- A future agent should use this file as the source of truth for what to build, not as a vague wishlist.
- If the implementation diverges from these notes, the next agent should treat the divergence as a deliberate product choice and document it.
- If a feature is too big for one pass, prefer landing the engine primitive first and the content second.
- Always preserve the distinction between:
  - real implemented behavior
  - planned content
  - design intent from the emails
  - fallback behavior when AI is unavailable

What exists vs what is still planned

- Existing today:
  - selector-owned Telnet sockets, pre-auth input/timeouts, and bounded queued output
  - a bounded two-worker authentication pool and selector-driven login/character creation state machine
  - finite authentication-pool shutdown with queued-work cancellation, one shared second for active daemon workers, and no replacement-worker leak
  - bounded, control-safe JSON-lines operational metadata for login/rate limits, connections, startup/shutdown, persistence, room triggers, NPC decisions/failures, and admin actions, with secret-field redaction and no transcript/state/exception-message logging
  - one sequential gameplay worker per authenticated player, preserving the simple `Session` API
  - hard total/pre-auth/authenticated/per-IP connection limits, login/account-creation rate limits, and pre-auth plus 10h/12h authenticated idle policy
  - 60-second dirty-only character autosave through one 64-key coalescing persistence writer, with retryable failures and a shared ten-second graceful-shutdown deadline
  - SQLite user table with serialized state
  - salted PBKDF2-SHA256 password hashes with successful-login migration from the legacy unsalted format
  - room objects with exits, items, players, and NPC lists
  - command registry
  - Brave Sir Knight as a rich `FSMBehavior`-backed NPC with five data-backed top-level states and trusted handlers for its detailed state-local sequences
  - a shared NPC behavior contract for enter, leave, speech, emote, and tick events
  - room delivery of player speech and emotes to NPC behaviors
  - validated, ordered speech/emote action output from NPC behaviors
  - reusable timed random chatter and event reactions with no LLM dependency
  - reusable data-backed FSM states, event transitions, timers, conditions, ordered actions, and state snapshots
  - a dedicated Brave Sir Knight characterization suite preserving his patrol, greeting, chore, resource, dialogue, memory, farewell, timing, recovery, and concurrency behavior across the migration
  - Crossroads and Fabulous Chamber demo content
  - a stateful Suspicious Alley bin-possum encounter with local commands, a two-state FSM, both natural offer orders, accurate non-takeable NPC feedback, safe item transfer, one-per-player rewards, and no LLM dependency
  - an initial Village Green and Hanging Tree canopy with shared bounded runtime state, day/night Wisp lighting, harvestable persistent giant acorns, room-aware falling-acorn hazards, and a non-verbal protectable Wisp Mother whose loss darkens the Green
  - an initial Val's Hella Holler north of the Green, with faithful tavern scenery, a complete local-FSM Val, fixed multi-action horn service, jokes/lore/attention/cat-defense interactions, and a first cross-room reaction to Wisp Mother harm
  - bounded health and intoxication mechanics plus three concrete persistent Val drink templates, with healing/alcohol effects and a global `/drink` command
  - shared hard limits for player inventories and room item lists, enforced by current take/drop/creation/reward/harvest/order paths so normal play cannot produce an unsaveable oversized inventory
  - simple item/equipment model
  - NPC removal that also unregisters the NPC from the global manager
- Still planned:
  - optional safe argument completion providers; command-token help and completion are implemented
  - future version migrations and schemas for general status effects, quests, relationships, and custom drinks; character schema v2, durable initial world ecology, and 60-second dirty-only autosave are implemented
  - [done] bounded per-NPC isolation and inert fallback for a trusted callback that never returns
  - OpenRouter integration and LLM failover, deferred until explicitly re-authorized by the user
  - budgeted NPC priority system
  - advanced admin NPC-memory/LLM-budget/brain-health/mode/reload controls; core shutdown/kick/heal/save/status and room/NPC actor inspection are implemented
  - the remaining email-driven village content, including Corbel's acorn economy, Val's food/prices/regular memory and richer horn output, remaining Wisp reactions, and durable shared world state
  - broader data-driven room/NPC event schemas for authoring; operational room-trigger and NPC-decision metadata is implemented
  - content data loading / world authoring layer
  - no in-repository TLS work: plaintext Telnet remains an explicitly accepted residual risk that operators must control and warnings must describe honestly

- Future agents must update this section every time they complete or partially complete one of the planned systems above.
- Do not leave this section stale: if a future run changes persistence, NPC architecture, or village content, it must be reflected here before handing work off again.

Milestone spec

Milestone 1: stabilize the current engine

- Fix the command dispatcher bug and the wearable-slot bug first.
- Add tests for both bugs.
- [done] Formalize player state serialization so saves and loads are stable and bounded.
- [done] Add explicit player-state migrations: legacy empty data and version 1 now restore through strict version 2 with durable status timing.
- [done] Add a minimal save on logout, performed before the player leaves their final room.
- [done] Add an autosave pass without blocking selector I/O or destabilizing the sequential gameplay-worker model.
- [done] Add no-listener selector integration coverage and remove the auth executor's unbounded shutdown wait.

Milestone 2: generalize NPC behavior

- [done: foundation] Extract behavior modes into a shared abstraction and route all existing NPC hooks through it.
- [done: migration stage] Preserve Brave Sir Knight's behavior while moving him onto `FSMBehavior`; keep his five top-level states data-backed and his complex state-local sequences in trusted handlers unless a later change deliberately redesigns them.
- [done] Add basic random-chatter NPC support.
- [done: engine stage] Add data-backed FSM support, including trusted handlers for complex state-local mechanics.
- [done] Make the engine expose enter/leave/say/emote/tick events through one contract.
- Add NPC memory as structured state rather than ad hoc fields.

Milestone 3: add LLM support with fallback

- Add optional provider configuration loading and validation; prove that an entirely absent OpenRouter configuration starts normally and makes zero provider calls.
- Add the local brain adapter that can talk to OpenRouter.
- Define the JSON event output contract.
- Add validation and a circuit breaker.
- Add failover from LLM to FSM when the provider is unhealthy.
- Add re-probe logic to return to LLM mode only after recovery.
- Ensure the fallback path is the default path for cold rooms and low-priority NPCs.
- Add tests for missing keys, incomplete configuration, explicit disablement, no network, exhausted budget, provider errors, and recovery; all failure cases must leave the MUD playable through local behavior.

Milestone 4: add scheduler and priority logic

- [done] Make room activity explicit through locked occupancy/visit/interaction snapshots.
- [done] Stop global NPC heartbeat calls in empty rooms for every behavior type.
- [done: local events] Wake rooms through immediate player enter/say/emote delivery; stale non-member events are rejected.
- [done] Bound trusted callbacks with one finite-mailbox actor per NPC; timeout selects inert fallback and forbids replacement-thread leaks.
- Add popularity and complexity scoring.
- Budget LLM use per room and per NPC.
- Prioritize valuable, visible, and crowded NPCs.

Milestone 5: add admin and persistence tooling

- [done: current systems] Add bounded admin views for room activity, NPC behavior/actor state, connections, sessions, schema, persistence, and status decay.
- [done: core operations] Add confirmed graceful shutdown, output-preserving kick, shared-API heal, and focused/bulk/world save commands.
- Add admin views for future budgets, structured memory, and brain health.
- Add NPC mode switching for debugging.
- Add save inspection and safe reset tools.
- [partly done] Bounded structured logging covers current authentication, connection/server lifecycle, persistence, room-local command triggers, NPC decisions/failures, and admin actions. Add future LLM budget/provider/fallback/recovery transitions when that subsystem is explicitly authorized, while continuing to omit prompt and response content.
- Add world reload commands where safe.

Milestone 6: implement the email content faithfully

- [done: initial slice] Build Val’s Hella Holler and Val with faithful room identity, a complete local FSM, fixed persistent drinks, shared Wisp-harm awareness, and bounded room-local interaction verbs. Food/prices, structured regular memory, richer observations, and safe custom horn-drink payloads remain.
- [done: initial slice] Build the Village Green and Hanging Tree with traversal, bounded harvest mechanics, danger reduction, and persistent giant-acorn items.
- Build the smithy and Eisele.
- Build Tackdriver.
- Build Ceridwen’s cottage and the herb garden.
- Build the Temple of the Self.
- [done: initial slice] Build the Wisp Mother and local acorn hazard loop; village-wide NPC reactions and durable world-state persistence remain.
- [partly done] Add the drink, scrap, respec, confusion, and mirror systems that make the content mechanically real. The fixed-template health/intoxication drink foundation is implemented; custom drinks and every non-drink system remain.

Room-by-room content expansion

Val’s Hella Holler

- The tavern should be the warm, noisy, social heart of the zone.
- The architecture should be obvious and vivid:
  - sturdy river rock walls
  - tile roof
  - central open room
  - wall booths for privacy
  - a long carved tree-trunk bar
  - kegs beneath shelves of exotic bottles
  - a raised bard platform
  - candles in glass providing warm amber light
  - cats on chairs, rafters, and tables
- The bar should feel like a place where impossible drinks are normal.
- The room should imply that adventurers are feeding the tavern’s energy, so the venue can afford to be generous.
- The tavern should not be a static “shop room”; it should feel like a living social hub.
- [implemented first slice] The connected room includes every listed visual anchor, Val's active local FSM and timed social emote, bounded commands for orders/jokes/lore/flirt/call/examine/attack, and fixed on-the-house drink service. A true economy, food, performances, and persistent regular activity remain planned.

Val

- Val should read as:
  - a Valkyrie refugee from Asgard
  - bored of battlefield cycles
  - happy to run a tavern instead
  - loud, warm, funny, and dangerous
- She should be able to:
  - serve drinks
  - tell jokes
  - move attention across the room as if she is in many places at once
  - notice when someone is hurt or exhausted
  - protect the tavern with cats if threatened
- Her joke responses should be short, slightly off-color, and voice-consistent with a Norse tavern keeper.
- Her drink service should always be grounded in the magical horn concept, even if the engine represents the drink as a concrete item.
- [implemented first slice] Val is a thin NPC around `ValBehavior(FSMBehavior)`. She can emit multiple validated actions, recognizes conversational cues, notices current health/intoxication, reacts to shared Wisp harm, and uses cats for non-lethal defense. `/call val` represents her magical omnipresence cosmetically; it does not spawn duplicate NPCs.

The Village Green

- The Green should be the zone’s central outdoor commons.
- It should be visually dominated by the Hanging Tree above it.
- At day it should feel broad, green, and strange.
- At night the Wisps should become the defining feature, turning it into a luminous, uncanny commons.
- The acorn hazard is part of the humor and the ecology:
  - if the harvest counter is too low
  - idle players occasionally get bonked
  - the event should be light but memorable

The Hanging Tree canopy

- The canopy should feel like a dangerous but rewarding vertical traversal space.
- It should have hand-carved steps, rope rungs, and bridges.
- It should be the place where players actively relieve pressure on the green by harvesting acorns.
- Harvesting should produce a tangible giant acorn item.
- The loop should feel like a village ecology:
  - harvest too little and the ground is dangerous
  - harvest enough and the village is safer

The Wisp Mother

- The Wisp Mother should be an ambient guardian rather than a standard NPC.
- She should be mostly wordless.
- Her emotional presence should be expressed through pulse, glow, and reaction.
- If destroyed or removed, the Green’s lighting and mood should degrade noticeably.

The Smithereens

- The smithy should be a busy, smoky, practical workroom.
- The scrap pile should act as a browseable discount market.
- The custom commission menu should feel like a proper crafting negotiation rather than a simple one-click buy.
- Eisele should feel like a competent professional who is happy to buy loot from dungeons.

Eisele

- Eisele should be grounded and direct.
- She should not need high-fantasy theatrics.
- Her role is to anchor the smithy’s economy and give the player a place to unload salvage.
- The shop should make sense as a place to convert dungeon junk into real value.

Tackdriver

- Tackdriver should be a “special object NPC” rather than a conventional humanoid.
- The hammer’s commentary should happen while Eisele works or when the player inspects it.
- It should be able to deliver ambient ideological commentary and an explicit lecturing mode.

Ceridwen’s Cottage

- The cottage should feel overgrown, herbal, pungent, and slightly dangerous.
- It should be a place where a pot is always bubbling and something in the room is always trying to be funny or malicious.
- The cottage and the garden should work together:
  - cottage = vendor and herbal home base
  - garden = hazard and reagent source

The Herb Garden

- The garden should be a confusion maze, not merely a room with flavor text.
- It should make navigation unreliable in a way the player can understand and work around.
- The reward for enduring it is the rare weed that unlocks Ceridwen’s higher-end stock.

The Temple of the Self

- The temple should reject external authority in favor of internal agency.
- The mirror / pool should be the core interaction.
- The respec system should feel like self-authorship.
- The room should provide a safe but potent place to rework a build.

Expanded future-agent notes

- Future agents should treat the “what exists vs what is still planned” section as a mandatory maintenance item.
- If they finish something or partially replace it, they must edit that section before handing work back.
- If they add a new major system, they must add it to the milestone spec and to the existing/planned section.
- If they discover the codebase already contains a partial version of a planned system, they should move that feature into “existing today” and note the limitation separately.

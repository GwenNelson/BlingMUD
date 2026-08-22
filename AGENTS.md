# BlingMUD Agent Instructions

This repository is collaborative space for humans and agents.

Follow these rules when working here:

- Always begin by reviewing what is already in place, what still needs doing, and what known bugs exist.
- Never assume something is implemented until you have verified it in the codebase.
- Always fix known bugs first unless explicitly told not to.
- Always review for potential bugs, including security issues, before starting new feature work.
- Do not patch blindly from assumptions.
- After any implementation or bugfix commit, update `AGENTS.md`, `AI_ROADMAP.md`, and `TODO.md` before moving on.
- Do not leave the roadmap or TODO stale; future agents rely on them to know what is actually done.
- Prefer small, reviewable changes over large rewrites.
- Keep content work, engine work, and AI architecture work separate where possible.
- Preserve unrelated user changes unless the user asks otherwise.
- Do not revert user work just because it looks incomplete.
- Use `apply_patch` for file edits.
- Do not use destructive commands unless the user explicitly authorizes them.
- Run the complete suite through `python3 run_tests.py`, which enforces a 30-second subprocess timeout; the normal suite takes only a few seconds, so exit status 124 indicates a regression or deadlock that must be investigated rather than left running. Do not bypass the watchdog with a raw discovery command.
- Keep test-created files under the repository-local `.test-tmp` directory; reject symlinked or escaping temp paths rather than risking writes elsewhere.

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
- The global `NPCManager` is the authoritative heartbeat gate: it must tick only registered NPCs that are still present in a room with at least one player. Keep direct enter/say/emote reactions immediate, reject stale-player room events, and do not move cold-room checks back into only selected behavior implementations.
- Preserve room lifecycle idempotence: duplicate enter/leave calls must not emit duplicate NPC events, successful leave must clear `player.room`, and activity counters should advance only for actual visits and interactions.
- A timed-out ticker stop must never be followed by a replacement thread while the previous ticker remains alive. Restart is allowed only after the old thread has actually stopped; do not solve stuck callbacks by leaking replacement threads.
- Every NPC callback is serialized through that NPC's lazy `NPCActor`: one daemon worker, a 16-job finite mailbox, tick coalescing, and a one-second decision deadline. Rooms and the manager schedule every recipient before waiting against a shared deadline, so one callback cannot prevent later NPCs from running. A timed-out actor closes intake, drains queued jobs with errors, exposes `fallback_mode: inert`, and is never replaced even if its trusted Python callback remains stuck. Normal stopped actors may restart only after their prior worker exits.
- NPC actor workers decide and validate action tuples; the waiting room/manager/gameplay thread performs each tuple exactly once. Preserve this split so actor callbacks do not deadlock by trying to acquire a session state lock held by the gameplay thread. Keep actor shutdown bounded and release every deliberately blocking test callback before teardown.
- Put small location-specific verbs in `Room.on_command()` and return `False` for unrelated commands so global dispatch and other rooms remain unaffected.
- Preserve generic `/take`/`/get` feedback for visible NPC aliases: a visible NPC must be recognized as non-takeable instead of reported absent. The possum offer parser deliberately accepts implicit item-first, `item to possum`, and `possum item` forms; all forms must reach the same locked inventory/equipment transfer checks.
- Village content shares bounded state through one `VillageState` object across the Green, canopy, and later village rooms. Its acorn ecology and Wisp ward/absence/harm fields are now durable through strict version-1 `world_state.py` JSON in the single known `world_state` SQLite row. Keep the schema explicit, byte/range/consistency bounded, atomically validated before restore, and synchronized with room NPC membership after load. Register future world fields deliberately rather than serializing objects or arbitrary dictionaries.
- Keep ambient hazard actors hidden from ordinary room occupant lists, room-aware through `NPCManager`, locally deterministic in tests, and mechanically bounded. Giant-acorn creation is capped by finite canopy supply and one-at-a-time carrying, and every new persistent content item must be added explicitly to the player-state template whitelist.
- The Wisp Mother is deliberately non-verbal. Preserve examine/protect/harm behavior through light and emote actions, and keep the shared `wisp_harmed_count` available for Val and later villagers to react to without introducing remote AI.
- Val's initial implementation is deliberately local-only: `ValBehavior` is a complete `FSMBehavior`, consumes shared Wisp-harm state on the next tavern arrival, and must remain functional without configuration, network access, or an LLM. Her horn currently maps bounded player concepts to three fixed, persistent drink templates; do not describe that first slice as arbitrary generated-item persistence.
- Keep player inventories and room item collections within their shared hard limits on every acquisition, reward, take, drop, and item-creation path. A full inventory must not consume a one-time reward or shared finite resource, and a full room must not remove or unequip the item a player tried to drop.
- Preserve the hybrid session architecture: one selector owns all sockets and pre-auth input, a two-worker bounded pool owns login hashing/database jobs, and only authenticated players get one easy-to-follow sequential gameplay thread. Do not reintroduce a thread per unauthenticated socket or replace the public `Session` API with an asyncio/framework rewrite.
- The authentication pool is two fixed daemon workers with capacity for only 16 queued jobs beyond active work. Queued work is cancelled at close, worker joins have a one-second shared deadline, and a stuck authentication/database job must be reported and abandoned as a daemon rather than blocking shutdown or spawning a replacement. Preserve selector-thread callback delivery and the existing `submit(function, callback, *arguments)` API.
- Keep connection, per-IP, pre-auth, authenticated-player, auth-work, input, and output bounds finite. Preserve the 120-second pre-auth timeout and the authenticated 10-hour warning/12-hour save-and-disconnect policy unless a deliberate operational change updates tests and all living documents.
- Route both selector and direct compatibility input through `TelnetInputParser`. Preserve incremental UTF-8, fragmented WILL/WONT/DO/DONT and SB/SE handling, escaped IAC, CR-LF/CR-NUL/LF normalization, codepoint-aware backspace, terminal/bidi-control filtering, character bounds, and explicit `TabInputEvent` delivery.
- Every registered global command must declare a non-empty summary and valid `CommandSpec`; room-local verbs must be listed in the room's `command_specs`. Generate help and command-token completion from those specs rather than adding another hand-maintained command list.
- Tab completion may replace input only through expected-text compare-and-replace. Never let a delayed Tab event clobber bytes typed after the event, reveal admin-only command names to non-admins, or complete hidden password input.
- Preserve dispatch precedence: ordinary room commands and aliases run before global fallbacks, while `admin`, `shutdown`, `kick`, `heal`, `save`, `adminstatus`, `quit`, and `exit` always bypass room code. Room specs may not claim any reserved name.
- `/shutdown`, `/kick`, `/heal`, `/save`, and `/adminstatus` are session-admin-only. Preserve `/shutdown now [reason]` confirmation and its one-second output-drain request before the existing ten-second save/worker shutdown; never bypass the common final-save path. Kick must announce before requesting output-preserving close, refuse self-kick, and rely on ordinary disconnect saving. Heal must use the shared health API under a one-second target state-lock bound. Save supports one character, `all`, and `world`; bulk save queues non-blockingly.
- After `read_line()` returns, the gameplay loop must re-check `session.running` before dispatch. This prevents a command already queued at kick, idle close, or shutdown time from executing after the session has lost permission to continue.
- Admin arguments and reasons are length bounded and reject terminal/bidirectional controls. Admin status may expose bounded operational counters, room activity, NPC behavior/actor mode, and ordinary errors, but must never expose password hashes, provider keys, secrets, prompts, or unbounded memory. Non-admin help and completion must continue hiding every admin-only command.
- Route production operational events through `operational_log.py`. Its JSON-lines records are field-count, field-length, and total-line bounded; terminal/bidirectional and other Unicode control characters are replaced; secret-like field names are redacted; reserved metadata cannot be replaced; sink failures are swallowed; and exception events record only the exception type, never its message or traceback.
- Keep logs useful without turning them into a transcript. Authentication, connection, persistence, room-trigger, NPC-decision/failure, admin-action, and server-lifecycle metadata may be logged, but never log passwords, password hashes, API keys, authorization headers, prompts, player chat/emotes, command arguments, admin reason text, NPC speech/action text, or serialized character/world state. An admin reason is represented only by `reason_supplied`; an NPC decision records only bounded identity/mode/location/action-count metadata.
- The normal test runner sets `BLINGMUD_SUPPRESS_OPERATIONAL_LOG=1` to keep test output deterministic. Logging tests must use a private sink or temporarily enable the singleton explicitly and restore it afterward. Do not use this test-only switch to disable production diagnostics by default.
- Global command registration is atomic and duplicate primary names or aliases are errors. Never restore silent registry overwrite behavior; it can unexpectedly replace safety or admin commands.
- Preserve `/unequip` and `/remove` as the same global command. It accepts either an equipped item name or slot (slot first, case-insensitive), invokes `on_unequip()` exactly once, removes only the equipment mapping, and leaves the item in inventory.
- If a change affects persistence, NPC brains, room triggers, or AI fallback, be careful to preserve save/load and failure-mode behavior.
- Player saves are versioned JSON handled by `player_state.py`: keep payloads and collections bounded, instantiate items only through the explicit template whitelist (currently pimp hat, royal possum bottle cap, giant acorn, Val's healing potion, Valkyrie mead, and horn-born special), reject lossy saves, and fall back safely when stored state is malformed. Version 2 is current; version 1 and legacy `{}` migrate in memory and are rewritten by the next changed/final save. Never replace this with pickle, dynamic imports, or arbitrary class names from save data.
- Health, maximum health, intoxication, recent-respawn state, and the bounded status timestamp are clamped gameplay values in version-2 character state. Route ordinary damage, healing, and intoxication increases through `Player.take_damage()`, `Player.heal()`, and `Player.add_intoxication()`; session-aware damage must use `Session.damage_player()` so zero health always invokes the common collapse path. Collapse retains inventory, equipment, and fabulousness, clears intoxication, restores one health, marks the player recently respawned, and returns them to the starting Town Square. Injury remains observable through the at-or-below-half-health threshold and clears only above half health.
- Intoxication decays by one point per whole minute online and offline. Online maintenance uses monotonic elapsed time and a non-blocking session state-lock attempt; restore uses the persisted bounded wall-clock timestamp. Backwards clocks must never add intoxication or move the stored status baseline backwards.
- Administrative privilege is authenticated per session and must not be restored from character JSON. Persisted equipment must refer to an item in the persisted inventory, and room locations must resolve through the current world's room IDs or fall back to the starting room.
- Save character state before removing a disconnecting player from their room so the last valid room ID is retained. Save failures must preserve the prior database snapshot and must not prevent session/room cleanup.
- Preserve the 60-second dirty-snapshot autosave path: never block selector I/O waiting for a player state lock, coalesce pending snapshots per lowercase player name, and route all selector-era character writes through the single bounded persistence writer. Disconnect must wait for an already-submitted final snapshot before room cleanup.
- A waiting character save must spend its finite timeout on both player-state-lock acquisition and writer completion. Never restore an unbounded blocking lock acquisition ahead of the advertised save/disconnect/admin timeout.
- Shared world state has its own one-key bounded writer and dirty-only 60-second coordinator, plus a final save inside the same ten-second shutdown deadline. Immediate writer rejection must complete both the receipt and bookkeeping callback so callers can report failure and retry; never leave a rejected snapshot marked as submitted.
- Graceful shutdown has one ten-second deadline for authenticated gameplay workers and persistence flush/stop. Do not add an unbounded join, create replacement writers after timeout, or silently claim a timed-out save was durable.
- OpenRouter and every other LLM provider are optional enhancements: missing or invalid provider configuration must disable remote calls cleanly, never prevent startup, and never stop the MUD or its NPCs from working locally.
- OpenRouter implementation is currently deferred and requires fresh, explicit user authorization; do not add provider code merely because it remains on the roadmap.
- Every LLM-capable NPC must have a complete FSM or simpler fallback, and tests must cover operation with no API key and no network.
- Never hard-code, commit, prompt with, display, or ordinarily log provider API keys or other secrets.
- Treat raised callback exceptions and non-returning callbacks as different failure modes: ordinary exceptions are reported while the actor remains usable; a deadline breach permanently selects inert fallback for that actor instance. Python cannot safely kill a stuck thread, so never create a replacement worker for an unresponsive actor or claim the stuck trusted code itself was terminated.
- Password hashes use salted PBKDF2-SHA256; preserve verification and successful-login migration for legacy SHA-256 records until a deliberate migration removes that compatibility path.
- Account creation and `set_admin_pw.py` share the 12–4096 character password bounds. The admin setter must remain import-safe, must not write on mismatch or invalid length, and must continue using `write_admin_password_hash()` for owner-only file permissions.
- SQLite schema changes are ordered through `PRAGMA user_version`; schema version 2 is current. Migrations are idempotent and transactional, preserve existing account rows, and refuse a database newer than the runtime instead of guessing or downgrading it.
- Keep input and password-work bounds intact: client lines are finite, stored hash fields are size-checked, and untrusted PBKDF iteration counts must be rejected before key derivation.
- Do not describe the current plain Telnet connection as secure transport, even though stored password hashing has been hardened.
- Preserve the prominent plaintext-Telnet warning at startup and before authentication. The server deliberately suppresses password echo and hidden-input redraw, but client display cannot be guaranteed and network traffic remains unencrypted.
- TLS is deliberately outside the current implementation plan. Do not quietly add it or claim the accepted public-listener default is secure.
- Selector integration tests must never bind a listener or launch `blingmud.main()`. Use unnamed local socket pairs, fake clocks, finite polling, and unconditional teardown. A host that raises `PermissionError` for the socketpair probe may skip those integration cases; do not broadly swallow other socket/test failures or use elevated permissions merely to defeat that host policy.

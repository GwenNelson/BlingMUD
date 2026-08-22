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
- The immediate priority is to fix the two concrete engine bugs that are already present, then refactor the NPC layer around a generic behavior model, then add persistence/admin plumbing, and only after that wire in the email-driven village content.
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
- [done] Make `NPCManager.stop()` use a finite join and safely tolerate being called before startup, so shutdown cannot wait forever on a stuck ticker callback; runtime isolation of a non-returning callback remains a scheduler task.

What exists vs what is still planned

- Implemented now: the first-fix engine bugs above, stronger password storage with legacy migration, NPC-manager removal cleanup, the shared NPC behavior/event-dispatch contract, Unicode-control-safe structured speech/emote actions, reusable local random and data-backed FSM behaviors, Brave Sir Knight's migration onto `FSMBehavior`, bounded non-repeating dialogue selection, detached-room tick safety, the stateful Suspicious Alley bin-possum encounter, and regression coverage for all of them.
- Still planned: optional structured NPC memory, the `llm_fsm` advisory wrapper and OpenRouter failover, room-aware global scheduling, gameplay-state persistence hardening, admin tooling, transport security, and the village content from the email threads.
- Future agents must keep this section current whenever they land meaningful implementation work; if they do not, the roadmap will drift out of sync with reality.
- OpenRouter remains design-only and explicitly deferred; implementation requires a later, explicit user authorization.

NPC architecture

- Implemented foundation: `NPCBehavior` now owns the common enter, leave, speech, emote, and tick contract; `NPC` delegates those hooks to its bound behavior; rooms now deliver speech and emote observations; raised callback failures are isolated from other event recipients and ticker participants; behavior output can contain one or more validated speech/emote `NPCAction` objects; `SimpleRandomBehavior` provides timed local chatter and optional event reactions; and `FSMBehavior` provides validated named states, ordered enter/exit/transition actions, event transitions, conditional branches, active-room timers, trusted state-local handlers, controlled state selection, and inspectable timing state.
- Known limitation: trusted local NPC callbacks still execute sequentially on the global ticker, so code that never returns can stall later NPC ticks even though raised exceptions are isolated. Avoid unbounded behavior code now; the room-aware scheduler milestone must add cooperative execution deadlines, busy-state suppression, or equivalent isolation without spawning unlimited replacement threads.
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

Persistence and character state

- Keep the current SQLite account store, but formalize player state as a versioned JSON blob rather than a loose prototype payload.
- Preserve the existing login table shape for compatibility, but treat the player state column as a first-class serialized character snapshot with migration/version metadata.
- Save character state on logout and add periodic autosave so a disconnect does not lose progress.
- Serialize room ID, inventory, equipment, stats, status effects, quest flags, admin flags, and NPC relationship/memory data explicitly rather than trying to pickle live objects.
- Add a player-state repository layer so loading/saving a character does not depend on session code.
- Add migrations for future schema evolution so new fields can be added without breaking old characters.
- Keep auth data and gameplay state separate in the design, even if they initially live in the same SQLite database.
- Password storage now uses salted PBKDF2-SHA256 and upgrades legacy SHA-256 hashes after a successful login; this is implemented, but Telnet transport remains unencrypted and must not be treated as secure authentication over an untrusted network.

Admin and operational tooling

- Add admin commands to inspect room activity, NPC mode, NPC memory, current budget use, and brain health.
- Add a way to force an NPC between random, FSM, and LLM modes for debugging.
- Add commands to reload NPC definitions and content without restarting the server.
- Add a command to force brain failover and another to force a health probe, so the fallback path can be tested live.
- Add a safe player-state inspection and reset tool for debugging corrupted saves.
- Improve logging around login, save/load, room triggers, NPC decisions, LLM calls, and fallback events.
- Keep the server MOTD and basic admin password flow, but move toward clearer admin status reporting and safer diagnostics.

Faithful implementation of the email content

- Build the village as a cohesive zone with the Village Green as the central hub and the existing rooms connected into that map rather than replacing everything at once.
- Keep the current starter content alive as regression/test scaffolding, but connect the new village layout into the same world so the new material can be reached naturally.
- Implemented starter-content expansion: the Suspicious Alley now contains a hidden, local-FSM bin possum revealed through `/search bin`; it rejects unsafe or unsuitable offerings, accepts an explicitly offered pimp hat, becomes friendly, reacts to room speech, and awards each player one harmless bottle-cap keepsake through `/pet possum`. This encounter uses no network or LLM service.
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
  - add autosave and logout save
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

- Phase 1: fix the two concrete bugs, formalize player state persistence, and add the minimum save/load layer.
- Phase 2: [partial] the generic NPC behavior system and Brave Sir Knight migration are complete; the room-aware global scheduler with empty-room suspension remains planned.
- Phase 3: add OpenRouter integration, circuit breaker failover, structured JSON output, and priority budgeting for LLM-capable NPCs.
- Phase 4: add admin/ops commands for NPC mode control, health checks, state inspection, and reloads.
- Phase 5: implement the village content as data-driven rooms, NPCs, items, room triggers, and status effects.
- Phase 6: add tests and regression coverage for the new architecture and the email-driven gameplay.

Test plan

- Regression test the `handle_command` bug and the wearable-slot bug directly.
- Preserve the Brave Sir Knight characterization suite as a migration and future-refactor contract: it must cover every top-level state, chore sequence, greeting and farewell branch, resource decision, directional observation pool, memory behavior, invalid-state recovery, timing rule, empty-room rule, and concurrent event isolation.
- Run the suite through `python3 run_tests.py`, retain its finite subprocess watchdog, and require every test-level barrier, condition wait, and thread join to have its own finite timeout.
- Verify that an empty room causes no NPC ticks and no OpenRouter calls.
- Verify that a populated room wakes NPCs correctly and that LLM calls are only made for eligible NPCs.
- Verify failover from LLM to FSM on timeout, invalid JSON, or OpenRouter errors, and verify restoration after a healthy probe.
- Verify priority ordering by simulating multiple active NPCs with different complexity and popularity scores.
- Verify save/load round-trips for character state, inventory, equipment, and status effects.
- Verify the new room interactions from the email: `harvest acorn`, `browse scrap`, `talk eisele`, `read book`, `look mirror`, and the Wisp Mother / Val reaction paths.
- Verify that the new content does not break the existing Crossroads and Fabulous Chamber demo rooms.

Assumptions

- Keep the current threaded telnet server model for now; do not introduce a separate AI microservice unless the in-process OpenRouter client proves too awkward.
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
  - admin status
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
  - threaded telnet server
  - basic login / character creation flow
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
  - a stateful Suspicious Alley bin-possum encounter with local commands, a two-state FSM, safe item transfer, one-per-player rewards, and no LLM dependency
  - simple item/equipment model
  - NPC removal that also unregisters the NPC from the global manager
- Still planned:
  - persistent character state versioning and autosave
  - empty-room suspension and room-aware scheduling
  - OpenRouter integration and LLM failover, deferred until explicitly re-authorized by the user
  - budgeted NPC priority system
  - admin inspection/control commands
  - the whole email-driven village content set
  - structured room/NPC event schemas
  - content data loading / world authoring layer
  - encrypted client transport or a secure front end for authentication outside trusted networks

- Future agents must update this section every time they complete or partially complete one of the planned systems above.
- Do not leave this section stale: if a future run changes persistence, NPC architecture, or village content, it must be reflected here before handing work off again.

Milestone spec

Milestone 1: stabilize the current engine

- Fix the command dispatcher bug and the wearable-slot bug first.
- Add tests for both bugs.
- Formalize player state serialization so saves and loads are stable.
- Add a version field to player state data.
- Add a minimal save on logout.
- Add an autosave pass if practical without destabilizing the current threaded model.

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

- Make room activity explicit.
- Stop NPC ticking in empty rooms.
- Wake rooms on player presence or interaction.
- Add popularity and complexity scoring.
- Budget LLM use per room and per NPC.
- Prioritize valuable, visible, and crowded NPCs.

Milestone 5: add admin and persistence tooling

- Add admin views for room state, NPC state, budgets, and brain health.
- Add NPC mode switching for debugging.
- Add save inspection and safe reset tools.
- Add logging for all important state transitions.
- Add world reload commands where safe.

Milestone 6: implement the email content faithfully

- Build Val’s Hella Holler and Val.
- Build the Village Green and Hanging Tree.
- Build the smithy and Eisele.
- Build Tackdriver.
- Build Ceridwen’s cottage and the herb garden.
- Build the Temple of the Self.
- Build the Wisp Mother and the acorn hazard loop.
- Add the drink, scrap, respec, confusion, and mirror systems that make the content mechanically real.

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

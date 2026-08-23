# BlingMUD Content and Free-Only NPC AI Roadmap

  ## Summary

  Implement the next content in two major phases:

  1. Complete the village content and economy, beginning with Master Corbel, Acorn Goblets, Acorn Mash, and the Green-to-Holler gameplay loop.
  2. Add optional OpenRouter-backed NPC intelligence, beginning with Brave Sir Knight, while preserving his existing FSM behaviour exactly whenever AI is unavailable, unsuitable, or fails.

  The MUD must remain fully playable without an API key, network access, or LLM service. openrouter.key must remain local-only, contain only the raw key, be ignored by Git, never appear in logs or prompts, and never be committed.

  Before every implementation phase, review the current code, known bugs, security risks, and “implemented versus planned” sections in AGENTS.md, AI_ROADMAP.md, and TODO.md. Never assume a feature exists until verified. The account-key incident is fixed locally by schema-v3 canonical-key repair and absolute database-path diagnostics, but production deployment must still compare `/adminstatus` database path, realpath, device, and inode across every server process or frontend before content work is deployed.

  ## Phase 0: Audit and repository safety

  - Re-run the existing test suite and static inspections before changing behaviour.
  - Review known unfinished or half-implemented areas first; fix confirmed bugs before adding features unless explicitly overridden.
  - Preserve schema version 3 account safety: use `canonical_username()` for account/session keys, repair only unambiguous stale `username_lower` values transactionally, and fail closed on canonical collisions.
  - Add openrouter.key to .gitignore before any provider code reads it.
  - Verify that:
      - Git does not track the key.
      - Git reports it as ignored.
      - no test, log, status command, exception, prompt, or admin output can reveal it.
      - no command reads or prints its contents during ordinary tests.

  - Add a safe configuration status model:
      - disabled_by_config
      - key_missing
      - catalogue_unavailable
      - no_free_models
      - healthy
      - rate_limited
      - circuit_open
      - temporarily_exhausted

  - Preserve the current simple layout, session API, selector ownership, one gameplay worker per authenticated player, bounded NPC actors, and no actual server launch during verification.

  ## Phase 1: Corbel and the acorn economy — implemented

  Master Corbel now runs as a local FSM in a turnery west of the Green. Giant acorns can be traded for five bounded persistent coins or crafted directly into reusable persistent Acorn Goblets; goblets can be filled by Val without consuming the vessel. Corbel sells Goblets for eight coins and healing Acorn Mash for two. Character-state version 3 adds bounded coins and explicitly persists only the three fixed Val drink templates inside Goblets. Keep all these operations atomic and bounded.

  ### Master Corbel

  Add Master Corbel as a local FSM NPC using the existing FSMBehavior contract.

  Corbel should:

  - occupy the intended village workshop/shop location;
  - buy giant acorns from players;
  - turn acorn shells into Acorn Goblets;
  - sell or trade goblets and Acorn Mash;
  - explain the relationship between the canopy, acorns, goblets, mash, and Val’s tavern;
  - use bounded inventory and bounded dialogue;
  - remain functional with no LLM or network dependency.

  The behaviour should be deterministic and testable. It should not create unbounded objects or money.

  ### Economy and persistence

  Introduce the smallest persistent economy needed for the content:

  - add a bounded integer coin balance to character state;
  - default missing balances safely during migration;
  - reject negative, non-integer, excessively large, or malformed values;
  - perform purchases, sales, and trades atomically;
  - enforce inventory capacity and room-item limits;
  - preserve existing item whitelist and versioned-save rules;
  - ensure failed transactions leave both player and world state unchanged.

  Use fixed prices initially. Do not introduce arbitrary player-created item classes, dynamic imports, pickle, or unbounded generated descriptions.

  ### Acorn Goblet

  Add a persistent, whitelisted Acorn Goblet item.

  It should:

  - be obtainable from Corbel;
  - be carryable and usable at Val’s Hella Holler;
  - support holding a bounded Val drink result;
  - preserve its contents across save/load using explicit templates only;
  - reject malformed or oversized contents;
  - never duplicate drinks or goblets through repeated commands.

  ### Acorn Mash

  Add Acorn Mash as a bounded, whitelisted consumable or trade item according to the existing email design.

  Its effects must:

  - be explicit and clamped;
  - use the existing health/intoxication/status APIs;
  - be safe at health and intoxication limits;
  - be persisted only through the item whitelist;
  - have deterministic tests for use, failure, inventory limits, and save/load.

  ### Green-to-Holler loop

  Complete and test the intended loop:

  1. Harvest a giant acorn from the Village Green.
  2. Take it to Corbel.
  3. Trade or process it into a goblet and/or mash.
  4. Use the result at Val’s Hella Holler.
  5. Observe the resulting health, intoxication, inventory, and dialogue changes.
  6. Confirm all limits survive restart and malformed-save handling.

  Add any missing room commands with normal room-first precedence. Global commands must remain fallback-only where a room defines the same command.

  ## Phase 2: Generic LLM/FSM architecture — implemented foundation

  `AdvisoryFSMBehavior` wraps an existing behavior without replacing its state or output, emits a bounded structured frame only in occupied rooms, and delegates every failure to the exact local result. Explicitly enabled worlds wrap Brave Sir Knight and Val; disabled worlds construct no runtime and do not read the key. The current provider transport rejects redirects and insecure key files, validates the live catalogue within a bounded 2 MiB response, and accepts only free text models with the parameters required by its JSON-only request.

  ### Core adapter

  Add a reusable LLMFSMBehavior or equivalent adapter around existing local behaviours.

  The adapter must:

  - use the existing NPCBehavior, FSMBehavior, NPCAction, and NPCActor contracts;
  - treat the local FSM as authoritative;
  - ask the LLM only to choose among explicitly generated, validated local candidates;
  - never allow the LLM to invent arbitrary commands, state names, targets, damage, items, or persistence data;
  - preserve exact local fallback behaviour when the LLM is disabled or fails;
  - support both simple random NPCs and stateful FSM NPCs, even though the first integrations are FSM-based;
  - expose inspectable mode/status for administrators without exposing credentials.

  The local behaviour should produce a bounded decision frame containing:

  - current FSM state;
  - eligible transitions;
  - eligible action candidates;
  - nearby player names or safe identifiers;
  - bounded room description;
  - relevant bounded NPC memory;
  - current interaction and popularity signals;
  - maximum output length and action count.

  The LLM response must be structured JSON and validated against that decision frame. Invalid, incomplete, unsafe, late, or contradictory responses must be discarded and replaced by the local FSM decision.

  ### Brave Sir Knight migration

  Use npcs/brave_sir_knight.llm as the starting template, but revise it to describe the actual migrated FSM and permitted structured actions.

  Preserve:

  - his five current top-level states;
  - patrol, greeting, water, fire, and wood sequences;
  - existing dialogue and emote style;
  - Gwen-specific lore and character identity;
  - threat, flirt, worship, and peacefulness rules;
  - existing resource and memory behaviour;
  - current action ordering and timing where tests already define them.

  Refactor only where necessary so decision generation and state mutation are separable:

  1. Generate a bounded local candidate decision.
  2. Optionally allow the LLM to select one permitted candidate.
  3. Validate the result.
  4. Commit the selected transition and side effects exactly once.
  5. Fall back to the existing local selection if any step fails.

  The fallback path must pass the existing characterization suite unchanged, including patrol, greetings, chores, resource handling, dialogue, memory, timing, invalid-state handling, detached-room safety, empty-room inactivity, and
  concurrency behaviour.

  The LLM must not become the source of truth for Knight state. It may influence selection among existing FSM choices, but it must not radically rewrite his personality or behaviour.

  ### Val integration

  After Brave Sir Knight is stable, integrate Val through the same generic adapter.

  Preserve Val’s local behaviour when AI is unavailable:

  - tavern identity and omnipresence;
  - horn service;
  - fixed drink mappings;
  - health and intoxication reactions;
  - Wisp-harm awareness;
  - cat defence;
  - recent-collapse recognition;
  - multi-action responses;
  - bounded room-local commands.

  Val should be the first additional NPC because she exercises the new economy and drink content. The Wisp Mother should remain deliberately non-verbal and local unless a later design explicitly changes that constraint.

  ## Phase 3: OpenRouter provider

  ### Configuration and secret handling

  Use the local file:

  openrouter.key

  Requirements:

  - raw key only;
  - no JSON wrapper, comments, or labels;
  - never committed;
  - ignored by Git;
  - read only when provider use is explicitly enabled;
  - reject missing, blank, oversized, or malformed content;
  - never echo the key or include it in exception text;
  - never send it to an LLM prompt;
  - never write it to operational logs, save files, crash reports, or admin status output.

  Use safe defaults for endpoint, timeouts, request size, and concurrency. Permit non-secret local configuration overrides only if they remain bounded and do not undermine the free-only rule.

  ### Dynamic free-model discovery

  Use OpenRouter’s model catalogue rather than hard-coded model names. OpenRouter documents GET /api/v1/models and exposes model pricing fields, modality, context length, and supported parameters. Its pricing object includes prompt,
  completion, request, reasoning, and other charge dimensions; a value of "0" represents free pricing. (OpenRouter model catalogue documentation (https://openrouter.ai/docs/api/api-reference/models/get-model), pricing and model
  metadata (https://openrouter.ai/docs/guides/overview/models))

  Only accept models where every applicable billing field is exactly zero:

  - prompt price;
  - completion price;
  - request price;
  - reasoning price;
  - web-search price;
  - image price;
  - cache-read/write prices;
  - any newly introduced charge field that the parser does not understand must cause rejection rather than accidental paid use.

  Also require:

  - text input and text output support;
  - sufficient context length for the bounded prompt;
  - chat-completion support;
  - no tool use, browsing, image generation, or other billable features;
  - no paid fallback routing.

  Do not trust a :free suffix alone. Pricing metadata is authoritative for eligibility.

  ### Rotation and exhaustion

  Maintain a bounded in-memory free-model pool:

  - sort eligible models by deterministic priority;
  - prefer models with recent successful calls;
  - rotate models fairly;
  - temporarily circuit-break models after timeout, rate limit, server error, malformed response, schema failure, or explicit exhaustion;
  - retry another eligible free model only within a small per-decision attempt limit;
  - never retry indefinitely;
  - never fall back to a paid model;
  - when every eligible model is unavailable, rate-limited, exhausted, or cooling down, immediately use the local FSM.

  “Runs out” means the current free pool has no usable model or the configured free request budget is exhausted. It must never mean spending credits on a paid model.

  Refresh the catalogue at startup and at a bounded periodic interval. Refresh failures retain the last known safe pool temporarily, but never invent models or assume a model remains free after its pricing data becomes unavailable.

  ### Chat requests

  Use OpenRouter’s chat-completions endpoint with bounded request bodies and explicit response limits. (OpenRouter chat-completion documentation (https://openrouter.ai/docs/api/api-reference/chat/send-chat-completion-request))

  Each request should include:

  - the NPC template;
  - current bounded FSM state;
  - candidate actions/transitions;
  - safe room and interaction context;
  - bounded recent memory;
  - strict JSON output instructions;
  - maximum response tokens;
  - no tools;
  - no external browsing;
  - no hidden or arbitrary commands.

  The provider client must use an injectable transport so tests can simulate responses without network access.

  ## Phase 4: Scheduling, prioritization, and failure behaviour

  ### Empty-room suppression

  No LLM request may be made for an NPC in a room with no players.

  This must apply to:

  - heartbeat ticks;
  - scheduled ambient decisions;
  - queued provider work;
  - delayed completions;
  - catalogue-driven retries.

  When the last player leaves, cancel or discard pending NPC AI work for that room unless it is already completing safely; its result must not produce gameplay output in an empty room.

  Direct player interaction may activate an NPC request only while the player is present.

  ### Priority scoring

  Calculate a bounded priority score from:

  - room occupancy;
  - recent player interactions;
  - room popularity over a bounded time window;
  - NPC complexity;
  - whether the NPC is central to the current interaction;
  - recent successful AI use;
  - remaining global and per-NPC budget;
  - fairness age since the NPC last received an AI opportunity.

  Use priority only to choose among eligible free-model requests. It must not override safety, room activity, per-NPC limits, or FSM validity.

  Reserve capacity for interactive requests so ambient NPCs cannot starve a player speaking directly to an NPC.

  ### Shared provider pool

  Use a small bounded shared provider worker pool rather than one network thread per request.

  Requirements:

  - fixed maximum worker count;
  - bounded queue;
  - bounded request timeout;
  - bounded response size;
  - no blocking of authenticated player workers;
  - no blocking of the existing NPC actor beyond a short handoff;
  - cancellation or stale-result rejection when the room becomes empty;
  - graceful shutdown before the existing finite shutdown deadline;
  - no background process or unbounded thread creation.

  The existing gameplay and session APIs should remain essentially unchanged.

  ## Phase 5: Administration and observability

  Add safe admin-only inspection and control after the provider foundation is stable.

  Potential operations:

  - inspect provider enabled/disabled state;
  - inspect free-model count and health state;
  - inspect NPC mode: local, advisory, unavailable, circuit-open;
  - reload the catalogue;
  - disable or re-enable AI without restarting the MUD;
  - clear circuit breakers;
  - inspect bounded request counters and failure categories;
  - reload NPC templates only from approved local files;
  - force an NPC back to local FSM mode;
  - save or inspect bounded NPC state.

  Admin output must show identifiers, counters, and status names only. It must never show API keys, raw prompts, full player text, or sensitive exception details.

  Persist only necessary NPC state:

  - FSM state;
  - bounded resource counters;
  - bounded recent-memory entries;
  - timestamps;
  - mode and health metadata only where useful;
  - no raw LLM transcripts by default;
  - no provider credentials;
  - no unbounded conversation history.

  Use versioned, validated JSON with safe migrations, as with player state.

  ## Test and acceptance plan

  All existing tests must continue to pass before and after each stage.

  ### Content tests

  - Corbel room placement and command precedence.
  - Acorn purchase, sale, processing, and failed transaction atomicity.
  - Goblet and mash inventory limits.
  - Drink and mash health/intoxication effects.
  - Save/load and migration of coins and new items.
  - Malformed, oversized, negative, and duplicate economy data.
  - Full Green-to-Holler loop.
  - Restart persistence and bounded world state.

  ### Brave Sir Knight tests

  - Existing characterization suite remains authoritative.
  - Local fallback produces the same actions, state transitions, timing, resource changes, and dialogue.
  - Valid LLM candidate selection changes only permitted choices.
  - Invalid JSON, unknown state, unknown action, invalid target, excessive text, control characters, contradictory transition, timeout, and provider failure all use the exact local fallback.
  - LLM cannot cause arbitrary damage, item creation, teleportation, persistence mutation, or command execution.
  - Empty-room and detached-room paths make no provider request.

  ### Provider tests

  - Missing key disables provider without network access.
  - Blank or malformed key is rejected safely.
  - openrouter.key is ignored and never staged.
  - Paid models are rejected.
  - Models with any non-zero or unknown billing field are rejected.
  - Free model rotation is deterministic and fair.
  - 429, timeout, 5xx, malformed catalogue, malformed JSON, schema failure, and exhausted-model responses circuit-break correctly.
  - All-free-model exhaustion falls back to FSM.
  - Catalogue refresh updates the pool safely.
  - Recovery after cooldown restores provider use.
  - No paid request is ever generated.
  - No real OpenRouter calls occur in the test suite; a separate authorized synthetic probe may validate the live catalogue and free-pool fallback without player data.

  ### Scheduling tests

  - Empty rooms generate no NPC provider work.
  - Leaving a room invalidates pending AI results.
  - Popular rooms receive priority within bounded fairness rules.
  - Direct interaction outranks ambient activity.
  - Provider queue and worker counts remain bounded.
  - Player/session responsiveness is unaffected by provider delays.
  - Shutdown terminates provider workers within the existing deadline.

  ### Security and regression checks

  - git status --ignored confirms openrouter.key is ignored.
  - A staged-file guard rejects any attempt to stage it.
  - Logs and admin output contain no key or raw prompt.
  - Static checks reject dynamic code execution and unsafe save deserialization.
  - No actual MUD server is launched during verification.
  - Every command and test run remains bounded to the agreed runtime limit.

  ## Documentation and delivery order

  Implement in reviewable commits:

  1. Corbel, economy, Goblets, Mash, persistence, and tests.
  2. Generic LLM/FSM decision-frame interfaces and Brave Sir Knight fallback-preserving refactor.
  3. OpenRouter key protection, provider catalogue, free-only filtering, rotation, circuit breakers, and fake-transport tests.
  4. Brave Sir Knight advisory integration and full characterization regression suite.
  5. Val integration, prioritization, room suppression, provider pool, admin inspection, and persistence refinements.

  After every meaningful implementation:

  - update AGENTS.md;
  - update AI_ROADMAP.md;
  - update TODO.md;
  - explicitly revise the “what exists versus what is still planned” section;
  - verify the three documents agree with the code;
  - review for bugs and security issues before committing.

  Never commit openrouter.key, even when committing the provider implementation.

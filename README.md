# BlingMUD

This is a silly little MUD engine i'm coding primarily for chatautism.com after getting nostalgic for our old CoffeeMUD instance.

It's not meant for huge scaling, it's a "just for fun" project, silly pull requests are accepted, especially if deeply autistic or deeply queer - ideally both.

This project is unapologetically "woke" and will make a point of asking new  users for pronouns - because there's an obvious practical use for that, and people who find pronouns offensive are stupid fucks who need to get a grip.

At some point we'll have at least one NPC who is a parody of the typical antiwoke moron too.

Again, this is not at all a serious project - other than in terms of security.

## Contribution policy

Pull requests accepted if they're silly, autistic as fuck, queer as fuck, gloriously camp, or fix a serious security problem.

The only time we'll accept a PR from someone who's got the typical "antiwoke" attitude is if it solves a security problem - otherwise please fuck off.

## Boring technical stuff

Implemented for Python 3.11 and newer, while deliberately keeping an old-school, plain coding style. There is no real attempt at huge-scale optimization: it is meant for small communities who want a silly fun thing.

One selector owns listening, socket reads, socket writes, login input, timeouts, and bounded output queues. Unauthenticated connections do not receive a thread. Password hashing and login database work use a two-worker bounded pool; after authentication, each player receives one straightforward sequential gameplay thread. `Session.send()`, `prompt()`, and `read_line()` keep the easy-to-follow gameplay model without letting idle login sockets create unlimited threads.

Input passes through one shared incremental Telnet/UTF-8 parser in both selector and blocking-compatibility modes. It handles fragmented option negotiation and subnegotiation, escaped IAC, CR-LF, CR-NUL, bare LF, fragmented Unicode, Unicode-aware backspace, finite character counts, and explicit Tab events. Terminal and bidirectional control characters are discarded. Tab completion behavior is layered on those events by the command system.

GMCP is available as Telnet option 201. After `IAC DO GMCP`, clients may identify themselves with `Core.Hello` and subscribe with `Core.Supports.Set`, `.Add`, or `.Remove`. BlingMUD currently publishes subscription-aware `Char.Name`, `Char.Vitals`, `Char.StatusVars`, `Char.Status`, and mapper-ready `Room.Info`; it also answers `Core.Ping`. Messages and retained subnegotiations are capped at 16 KiB, subscriptions at 64 packages, and unchanged state snapshots are suppressed. Each production room has a permanent positive GMCP number in addition to its persistence-facing string `room_id`; released numbers must not be reassigned.

Global and room-local commands declare validated usage, aliases and summaries through `CommandSpec`. `/help` is generated from the commands actually available to the player, and `/help <command or alias>` shows focused help. Pressing Tab while typing the slash-command token canonicalizes an exact alias, completes a unique command, extends a shared prefix, or lists the finite matching command names. Compare-and-replace prevents a delayed Tab event from overwriting newer typing; arguments are deliberately not completed yet.

Ordinary room-local commands override a global command of the same name or alias, allowing a location to give a verb special meaning. Safety and administrative names always bypass rooms: `admin`, `shutdown`, `kick`, `heal`, `save`, `adminstatus`, `adminai`, `say`, `quit`, and `exit`. Global command registration rejects duplicate primary names or aliases atomically instead of silently replacing an existing command.

Slash commands remain the canonical command syntax. For compatibility with Mudlet's generic mapper and conventional speedwalks, bare `look`/`l` and the finite cardinal, diagonal, up, and down direction names/aliases also dispatch their existing slash commands. Every other bare line remains speech; `/say <message>` explicitly speaks a reserved mapper word such as `look` or `north`.

Equipment can be removed with `/unequip <item or slot>` or `/remove <item or slot>`. The item stays in inventory, its `on_unequip()` effect runs once, and room occupants see the removal.

Runtime limits are intentionally modest: 64 total connections, 32 login connections, 32 authenticated players, 8 connections per source address, a 120-second login idle timeout, and a 256 KiB output queue per connection. Five failed logins for one address/account pair within five minutes are blocked, and one address may create at most three accounts per hour. Authenticated players receive an audible warning after ten idle hours and are saved and disconnected after twelve.

Active characters are considered for autosave every 60 seconds. The engine serializes only characters whose state lock is immediately available, compares the bounded JSON snapshot with the last submitted snapshot, and sends changed state to one coalescing persistence writer. Busy characters are retried on the next pass. Logout waits for its final queued snapshot; server shutdown gives gameplay workers and the writer one shared ten-second flush deadline and reports anything that fails to stop.

Operational events are written to standard error as bounded JSON Lines. They cover server and connection lifecycle, authentication outcomes and rate limits, persistence, room-local command triggers, NPC decision/failure metadata, and admin actions. Logs neutralize control characters, redact secret-like fields, and omit passwords, hashes, prompts, player chat/emotes, command arguments, admin reason text, NPC output text, serialized state, exception messages, and tracebacks. The explicitly enabled OpenRouter integration additionally writes full raw dialogue request payloads and response bodies to ignored, owner-only `openrouter_queries.jsonl`; authorization headers and the API key are never written. Large catalogue bodies are represented only by their byte count so they cannot crowd dialogue records out of the bounded audit. If there is not enough audit capacity for a complete request/response pair, the provider call is refused and the NPC stays on its local FSM. `BLINGMUD_SUPPRESS_OPERATIONAL_LOG=1` exists for the repository's deterministic test runner; production diagnostics are enabled by default.

The listener defaults to `0.0.0.0:4000`. Operators may set `BLINGMUD_HOST` and `BLINGMUD_PORT`; invalid values stop startup instead of silently choosing another address.

### Running and stopping

BlingMUD has no third-party Python dependency. From the repository directory, optionally create the session-admin password first:

```sh
python3 set_admin_pw.py
```

The script requires a matching password of 12–4096 characters and writes the ignored `admin.hash` file with owner-only permissions. If that file is absent or unreadable, gameplay still starts but `/admin` remains disabled.

Start the server with Python 3.11 or newer:

```sh
BLINGMUD_HOST=127.0.0.1 BLINGMUD_PORT=4000 python3 blingmud.py
```

Choose the host deliberately. `127.0.0.1` is suitable when a separately managed local frontend controls exposure; the code default remains the accepted but public `0.0.0.0`. This repository does not provide TLS, a reverse proxy, a service unit, firewall changes, or any other host configuration.

For an orderly stop, authenticate with `/admin` and use `/shutdown now [reason]`. The listener closes, queued notices receive a one-second drain opportunity, active character/world state receives its bounded final-save path, and stuck authentication workers cannot hold shutdown indefinitely. `Ctrl-C` reaches the same cleanup path. Avoid `kill -9` when state durability matters.

### Persistent files and backups

`users.sqlite` is resolved to an absolute path at startup and contains accounts, password hashes, character JSON, the single shared village-state row, and explicit bounded Knight/Val state. `admin.hash` contains only the session-admin password hash. Both are ignored by Git. `openrouter.key` is ignored, must contain only the raw local key, and must be owner-readable only. Character state is strict version-3 JSON, village state is strict version-1 JSON, NPC state is strict version-1 JSON, and account storage is schema version 4 with canonical username-key repair; startup applies known SQLite and character migrations and refuses an unknown newer database schema.

Use `/save all` or `/shutdown now`, wait for completion, and copy `users.sqlite` while BlingMUD is stopped. A raw file copy during an active SQLite transaction is not the documented backup path. Keep `admin.hash` private, and do not hand-edit serialized JSON unless you are prepared for validation to reject it and restore safe defaults.

### Administration

After `/admin`, the implemented session-only commands are:

- `/shutdown now [reason]` — announce, drain output, save, and stop.
- `/kick <player> [reason]` — announce and disconnect through normal save cleanup.
- `/heal [player] [amount|full]` — use the shared bounded health rules.
- `/save [player|all|world]` — request a focused or nonblocking bulk save.
- `/adminstatus [rooms|npcs|ai]` — show bounded runtime, activity, persistence, NPC-actor, and optional AI diagnostics.

Admin privilege is never persisted in character state. Admin reasons are shown to affected players but operational logs record only whether a reason was supplied. Disabling advisory AI globally or for one NPC prevents already queued remote speech from leaking through and restores the saved local fallback.

### NPC and failure model

Rooms with no players receive no global NPC heartbeat. Active NPCs decide through one lazy finite-mailbox actor each; one stuck callback makes only that actor inert and never creates a replacement worker. Brave Sir Knight and Val use local FSM behavior, and the possum uses a simple local state machine. Optional OpenRouter work is explicitly disabled unless `BLINGMUD_OPENROUTER_ENABLED` is set. Wrapped NPCs start and reply in FSM mode; the first validated response establishes LLM mode for that NPC. Subsequent speech emits only the bounded in-character model answer on success instead of also printing the canned FSM sentence. Admission rejection returns local output immediately; provider failure or a five-second deadline releases the exact withheld fallback on an actor tick, and late model text is discarded. Knight and Val both supply a bounded local candidate for ordinary speech, so live advisory conversation does not silently skip utterances that lack an FSM keyword. Checked-in bounded persona templates, current speaker/FSM state, and at most three recent validated exchanges provide character and continuity. Paid text models use conservative prompt reservations and a persistent one-dollar UTC-day budget before free-model fallback, with global/room/NPC request bounds.

### Tests

Run the complete suite only through the guarded runner:

```sh
python3 run_tests.py
```

It confines temporary files to `.test-tmp`, strips unsafe Python environment overrides, disables production log noise, and terminates the child suite after 30 seconds. Tests never bind the BlingMUD listener. Selector integration uses unnamed local socket pairs and fake clocks; environments that explicitly deny local socketpair writes report those tests as skipped, while ordinary hosts run them end to end. A timeout, failure, unexpected skip, or surviving test worker should be investigated before deployment.

The goal is to scale to groups of 10-20 active users at most and again to make it fun.

UI is currently plain Telnet. Telnet provides no transport encryption, so passwords and gameplay traffic can be observed or altered by anyone able to intercept the connection. Do not reuse an important password here, and do not expose the current listener directly to an untrusted network while treating it as secure.

The server suppresses password echo and never intentionally redraws hidden input, but a Telnet client may still display typed characters. That does not protect the password on the network.

The current public `0.0.0.0` listener default and lack of TLS are explicitly accepted project constraints. Operators must assess and control network exposure themselves. BlingMUD prints this warning at startup and before login; neither warning makes plaintext Telnet secure.

## Fun stuff

The 
```/bling```
 command is the most important command ever implemented in any piece of software ever.

Second to that is this:
```
/worship Gwen
```


Which makes your user do what eventually the entire human race will do - wait, i shouldn't leak my evil plans in READMEs - ignore that

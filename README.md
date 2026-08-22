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

Runtime limits are intentionally modest: 64 total connections, 32 login connections, 32 authenticated players, 8 connections per source address, a 120-second login idle timeout, and a 256 KiB output queue per connection. Five failed logins for one address/account pair within five minutes are blocked, and one address may create at most three accounts per hour. Authenticated players receive an audible warning after ten idle hours and are saved and disconnected after twelve.

Active characters are considered for autosave every 60 seconds. The engine serializes only characters whose state lock is immediately available, compares the bounded JSON snapshot with the last submitted snapshot, and sends changed state to one coalescing persistence writer. Busy characters are retried on the next pass. Logout waits for its final queued snapshot; server shutdown gives gameplay workers and the writer one shared ten-second flush deadline and reports anything that fails to stop.

The listener defaults to `0.0.0.0:4000`. Operators may set `BLINGMUD_HOST` and `BLINGMUD_PORT`; invalid values stop startup instead of silently choosing another address.

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

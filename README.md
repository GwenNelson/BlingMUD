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

Implemented in python 3.0, no real attempt at heavy optimization at least for now - it's meant for small communities of people who want a silly fun thing.

Every user session is a thread because that makes it easy to follow the logic - obviously this could be replaced with a cool async thing, but that's messier a lot of the time so won't be bothering at least at first.

The goal is to scale to groups of 10-20 active users at most and again to make it fun.

UI is just telnet, telnet is contrary to popular belief actually very secure if you don't need encryption - just don't reuse the same password here as you'd use for important stuff, that's asking to be hacked.

SSH is harder to implement and more complicated, has greater attack surface and more scope for things for stuff like buffer overflows etc and it's just a pain. If you really must have encryption, bind to localhost and run
an sshd with telnet as the shell on your server or something - but don't come crying if that opens up actual security problems.

## Fun stuff

The 
```/bling```
 command is the most important command ever implemented in any piece of software ever.

Second to that is this:
```
/worship Gwen
```


Which makes your user do what eventually the entire human race will do - wait, i shouldn't leak my evil plans in READMEs - ignore that

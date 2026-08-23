from core import CommandSpec, Room


class TempleOfSelf(Room):
    """A bounded, local safe room for reflection and recovery."""

    command_specs = (
        CommandSpec("examine", "/examine <mirror|water|book>", "Examine the Temple's reflective objects.", aliases=("inspect",)),
        CommandSpec("look", "/look mirror", "Look into the Temple mirror."),
        CommandSpec("sit", "/sit", "Sit quietly in the Temple."),
        CommandSpec("meditate", "/meditate", "Recover a small amount of health."),
        CommandSpec("read", "/read book", "Read the Tome of Indulgence."),
        CommandSpec("reforge", "/reforge self", "Review the safe self-reforging rules."),
        CommandSpec("alter", "/alter stats", "Review the safe self-reforging rules.")
    )

    def __init__(self):
        Room.__init__(
            self,
            "temple_of_self",
            "The Temple of the Self",
            "An unadorned arch opens onto a perfect still-water floor. "
            "Mirrored walls rise beneath a clear skylight, and a silver-bound "
            "book rests on a marble pedestal. The room is quiet and safe."
        )

    def on_command(self, session, command, arguments):
        target = arguments.strip().lower()
        if command in ("examine", "inspect", "look"):
            if target in ("mirror", "water", "the mirror", "the water", "examine water"):
                session.send(
                    "The water reflects {0}: health {1}/{2}, fabulousness {3}.".format(
                        session.player.name,
                        session.player.health,
                        session.player.max_health,
                        session.player.fabulousness
                    )
                )
            elif target in ("book", "tome", "the book", "tome of indulgence"):
                session.send(
                    "The Tome of Indulgence teaches that conscience belongs to "
                    "the self, and authority over one's flesh begins with taking "
                    "responsibility for it."
                )
            else:
                session.send("The Temple offers a mirror, still water, and a silver-bound book.")
            return True
        if command == "read":
            if target not in ("book", "tome", "tome of indulgence"):
                session.send("Read what?")
                return True
            return self.on_command(session, "examine", "book")
        if command in ("sit", "meditate"):
            if command == "sit" and target:
                session.send("Sit where?")
                return True
            healed = session.player.heal(5)
            session.send("You gather yourself in the still water and recover {0} health.".format(healed))
            return True
        if command in ("reforge", "alter"):
            if (command == "reforge" and target != "self") or (command == "alter" and target != "stats"):
                session.send("The Temple accepts /reforge self or /alter stats.")
                return True
            session.send("The Temple's stat respec menu is not yet unlocked for this character.")
            return True
        return False

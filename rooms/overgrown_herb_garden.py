from core import CommandSpec, Room


class OvergrownHerbGarden(Room):
    command_specs = (
        CommandSpec("examine", "/examine garden", "Examine the overgrown herb garden.", aliases=("inspect",)),
        CommandSpec("harvest", "/harvest weed", "Attempt a bounded rare-weed harvest."),
    )
    def __init__(self):
        Room.__init__(self, "overgrown_herb_garden", "The Overgrown Herb Garden", "Towering thorns, nightshades and glowing flora knot into a maze. Heavy pollen hangs in the air and every path looks almost, but not quite, familiar.")
    def on_command(self, session, command, arguments):
        target = arguments.strip().lower()
        if command in ("examine", "inspect"):
            session.send("The garden is disorienting and slightly toxic. A rare weed glows beyond the thorn wall.")
            return True
        if command == "harvest":
            if target not in ("weed", "rare weed"):
                session.send("Harvest what?")
            else:
                session.send("The thorns recoil, but the rare weed is not yet safe to carry.")
            return True
        return False

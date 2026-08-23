from core import CommandSpec, PLAYER_INVENTORY_LIMIT, Room
from items.herbs import RareWeed


class OvergrownHerbGarden(Room):
    command_specs = (
        CommandSpec("examine", "/examine garden", "Examine the overgrown herb garden.", aliases=("inspect",)),
        CommandSpec("harvest", "/harvest weed", "Attempt a bounded rare-weed harvest."),
    )
    def __init__(self):
        Room.__init__(self, "overgrown_herb_garden", "The Overgrown Herb Garden", "Towering thorns, nightshades and glowing flora knot into a maze. Heavy pollen hangs in the air and every path looks almost, but not quite, familiar.")
        self.rare_weed_available = True
    def on_command(self, session, command, arguments):
        target = arguments.strip().lower()
        if command in ("examine", "inspect"):
            if self.rare_weed_available:
                session.send("The garden is disorienting and slightly toxic. A rare weed glows beyond the thorn wall.")
            else:
                session.send(
                    "The garden is disorienting and slightly toxic. The "
                    "harvested patch beyond the thorn wall is now bare."
                )
            return True
        if command == "harvest":
            if target not in ("weed", "rare weed"):
                session.send("Harvest what?")
            else:
                if not self.rare_weed_available:
                    session.send("The rare weed has already been harvested from this patch.")
                elif len(session.player.inventory) >= PLAYER_INVENTORY_LIMIT:
                    session.send("You cannot carry the rare weed.")
                else:
                    session.player.inventory.append(RareWeed())
                    self.rare_weed_available = False
                    session.send("You harvest one rare weed without disturbing the rest of the garden.")
            return True
        return False

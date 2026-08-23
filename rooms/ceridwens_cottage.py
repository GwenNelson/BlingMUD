from core import CommandSpec, NPCAction, Room
from npcs.ceridwen import Ceridwen


class CeridwensCottage(Room):
    command_specs = (
        CommandSpec("examine", "/examine <pot|herbs|ceridwen>", "Examine Ceridwen's cottage.", aliases=("inspect",)),
        CommandSpec("buy", "/buy <salve|antitoxin>", "Ask Ceridwen about bounded remedies."),
    )
    def __init__(self):
        Room.__init__(self, "ceridwens_cottage", "Ceridwen's Cottage", "A dim earthy cottage smells of crushed mint, dried lavender, swamp root and potion fumes. Bundles hang from every beam beside a bubbling cauldron.")
        self.ceridwen = Ceridwen()
        self.add_npc(self.ceridwen)
    def on_command(self, session, command, arguments):
        target = arguments.strip().lower()
        if command in ("examine", "inspect"):
            session.send("The cottage contains hanging herbs, a bubbling pot, and Ceridwen's dangerous spoon.")
            return True
        if command == "buy":
            if target not in ("salve", "antitoxin"):
                session.send("Ceridwen offers bounded salves and antitoxins; experimental stock is locked.")
            else:
                session.send("Ceridwen taps the pot. Bring a rare weed before she sells that remedy.")
            return True
        return False

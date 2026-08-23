from core import CommandSpec, NPCAction, PLAYER_INVENTORY_LIMIT, Room
from items.drinks import HornBornSpecial
from npcs.ceridwen import Ceridwen
from items.herbs import RareWeed


class CeridwensCottage(Room):
    command_specs = (
        CommandSpec("examine", "/examine <pot|herbs|ceridwen>", "Examine Ceridwen's cottage.", aliases=("inspect",)),
        CommandSpec("buy", "/buy <salve|antitoxin|experimental>", "Ask Ceridwen about bounded remedies."),
        CommandSpec("give", "/give weed", "Offer Ceridwen a rare weed unlock."),
    )
    def __init__(self):
        Room.__init__(self, "ceridwens_cottage", "Ceridwen's Cottage", "A dim earthy cottage smells of crushed mint, dried lavender, swamp root and potion fumes. Bundles hang from every beam beside a bubbling cauldron.")
        self.ceridwen = Ceridwen()
        self.experimental_unlocked = False
        self.add_npc(self.ceridwen)
    def on_command(self, session, command, arguments):
        target = arguments.strip().lower()
        if command in ("examine", "inspect"):
            session.send("The cottage contains hanging herbs, a bubbling pot, and Ceridwen's dangerous spoon.")
            return True
        if command == "buy":
            if target == "experimental":
                if not self.experimental_unlocked:
                    session.send("Ceridwen's experimental shelf is locked.")
                elif len(session.player.inventory) >= PLAYER_INVENTORY_LIMIT:
                    session.send("You cannot carry another potion.")
                elif not session.player.spend_coins(3):
                    session.send("The experimental potion costs three coins.")
                else:
                    session.player.inventory.append(HornBornSpecial())
                    session.send("Ceridwen sells one bounded experimental potion.")
                return True
            if target not in ("salve", "antitoxin"):
                session.send("Ceridwen offers bounded salves and antitoxins; experimental stock is locked.")
            else:
                session.send("Ceridwen taps the pot. Bring a rare weed before she sells that remedy.")
            return True
        if command == "give" and target in ("weed", "rare weed"):
            weed = next((item for item in session.player.inventory if isinstance(item, RareWeed)), None)
            if weed is None:
                session.send("Ceridwen needs a rare weed before she can unlock experimental stock.")
            else:
                session.player.inventory.remove(weed)
                self.experimental_unlocked = True
                session.send("Ceridwen unlocks the experimental shelf, carefully and without making promises.")
            return True
        return False

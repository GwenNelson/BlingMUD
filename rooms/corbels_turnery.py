from core import CommandSpec, NPCAction, PLAYER_INVENTORY_LIMIT, Room
from items.drinks import AcornGoblet
from items.food import AcornMash
from items.giant_acorn import GiantAcorn
from npcs.master_corbel import MasterCorbel


class CorbelsTurnery(Room):
    command_specs = (
        CommandSpec(
            "trade",
            "/trade acorn",
            "Sell Master Corbel a giant acorn for five coins.",
            aliases=("sell",)
        ),
        CommandSpec(
            "craft",
            "/craft goblet",
            "Turn one giant acorn into a reusable acorn goblet."
        ),
        CommandSpec(
            "buy",
            "/buy <goblet|mash>",
            "Buy a fixed-price item from Master Corbel."
        ),
        CommandSpec(
            "examine",
            "/examine <corbel|lathe|wares>",
            "Inspect Master Corbel or the practical workshop.",
            aliases=("inspect",)
        )
    )

    ACORN_VALUE = 5
    GOBLET_PRICE = 8
    MASH_PRICE = 2
    CORBEL_TARGETS = ("corbel", "master corbel", "master")
    LATHE_TARGETS = ("lathe", "turning lathe", "the lathe")
    WARES_TARGETS = ("wares", "goods", "goblet", "mash")

    def __init__(self):
        Room.__init__(
            self,
            "corbels_turnery",
            "Master Corbel's Turnery",
            "A practical turnery stands at the Green's edge, warm with the "
            "smell of wood dust and linseed oil. A foot-powered lathe, tidy "
            "tools and rows of polished acorn-shell goblets show exactly "
            "what patient village craft can do."
        )
        self.corbel = MasterCorbel()
        self.add_npc(self.corbel)

    def describe_to(self, player):
        Room.describe_to(self, player)
        player.session.send(
            "Corbel buys giant acorns for five coins. Try /trade acorn, "
            "/craft goblet, or /buy goblet or mash."
        )

    def on_command(self, session, command, arguments):
        if command in ("trade", "sell"):
            return self._trade(session, arguments)
        if command == "craft":
            return self._craft(session, arguments)
        if command == "buy":
            return self._buy(session, arguments)
        if command in ("examine", "inspect"):
            return self._examine(session, arguments)
        return False

    def _trade(self, session, arguments):
        if arguments.strip().lower() not in ("acorn", "giant acorn"):
            session.send("Corbel only trades for a sound giant acorn.")
            return True

        player = session.player
        with self.lock:
            acorn = next(
                (item for item in player.inventory if isinstance(item, GiantAcorn)),
                None
            )
            if acorn is None:
                paid = 0
            else:
                paid = player.add_coins(self.ACORN_VALUE)
                if paid == self.ACORN_VALUE:
                    player.inventory.remove(acorn)
                else:
                    if paid:
                        player.spend_coins(paid)
                    paid = 0

        if not paid:
            session.send(
                "Corbel studies your hands. 'I need a giant acorn and room "
                "for the full five coins.'"
            )
            return True

        self.corbel.perform_action(
            NPCAction.say(
                "Good shell. Five coins, and do not let the Green bonk "
                "anyone while you fetch another."
            )
        )
        session.send("You receive {0} coins. Balance: {1}.".format(
            paid,
            player.coins
        ))
        return True

    def _craft(self, session, arguments):
        if arguments.strip().lower() not in ("goblet", "acorn goblet"):
            session.send("Corbel can craft an acorn goblet from a giant acorn.")
            return True

        player = session.player
        with self.lock:
            for index, item in enumerate(player.inventory):
                if isinstance(item, GiantAcorn):
                    player.inventory[index] = AcornGoblet()
                    crafted = True
                    break
            else:
                crafted = False

        if not crafted:
            session.send("You need a giant acorn before Corbel can turn it.")
            return True

        self.corbel.perform_action(
            NPCAction.emote(
                "sets the shell spinning on the lathe until it becomes a "
                "thin, gleaming acorn goblet."
            )
        )
        session.send(
            "Corbel turns your giant acorn into a reusable acorn goblet. "
            "Val can fill it at the Holler."
        )
        return True

    def _buy(self, session, arguments):
        wanted = arguments.strip().lower()
        choices = {
            "goblet": (self.GOBLET_PRICE, AcornGoblet),
            "acorn goblet": (self.GOBLET_PRICE, AcornGoblet),
            "mash": (self.MASH_PRICE, AcornMash),
            "acorn mash": (self.MASH_PRICE, AcornMash)
        }
        choice = choices.get(wanted)

        if choice is None:
            session.send("Corbel sells goblets for 8 coins and mash for 2.")
            return True

        price, factory = choice
        player = session.player

        with self.lock:
            if len(player.inventory) >= PLAYER_INVENTORY_LIMIT:
                result = "inventory_full"
            elif not player.spend_coins(price):
                result = "insufficient_coins"
            else:
                player.inventory.append(factory())
                result = "bought"

        if result == "inventory_full":
            session.send("You cannot carry another thing from the turnery.")
        elif result == "insufficient_coins":
            session.send("You do not have enough coins for that.")
        else:
            self.corbel.perform_action(
                NPCAction.say("A fair price for a useful thing.")
            )
            session.send("You buy {0}. Balance: {1}.".format(
                factory().name,
                player.coins
            ))

        return True

    def _examine(self, session, arguments):
        target = arguments.strip().lower()

        if target in self.CORBEL_TARGETS:
            session.send(
                "Master Corbel is all practical concentration, measuring "
                "twice and refusing to waste a perfectly good acorn shell."
            )
        elif target in self.LATHE_TARGETS:
            session.send(
                "The treadle lathe is old, maintained beautifully, and "
                "covered in a fine dust of giant-acorn shell."
            )
        elif target in self.WARES_TARGETS:
            session.send(
                "Goblets cost 8 coins; warm acorn mash costs 2. A giant "
                "acorn can also be crafted directly into a goblet."
            )
        else:
            session.send("Examine Corbel, the lathe, or the wares?")

        return True

import random

from core import NPCAction, PLAYER_INVENTORY_LIMIT, Room
from items.drinks import HornBornSpecial, ValHealingPotion, ValkyrieMead
from npcs.val import Val


class ValsHellaHoller(Room):
    VAL_TARGETS = ("val", "the valkyrie", "valkyrie")
    HORN_TARGETS = ("horn", "magical horn", "cow horn", "the horn")
    CAT_TARGETS = ("cat", "cats", "tavern cats", "the cats")
    BAR_TARGETS = ("bar", "tree-trunk bar", "tree trunk bar")
    MAX_ORDER_TEXT = 80
    JOKES = (
        "I left Asgard for better hours. The old job had heavenly benefits "
        "and murderous management.",
        "A warrior asked whether my mead had body. I said yes; he woke under "
        "the table beside it.",
        "I like my lovers like my battle plans: bold, flexible, and nowhere "
        "near the cats."
    )

    def __init__(self, village_state, random_source=None):
        Room.__init__(
            self,
            "vals_hella_holler",
            "Val's Hella Holler",
            "A cozy, crowded tavern fills a sturdy river-rock building "
            "beneath a tiled roof. Fireplaces and candles in glass cast warm "
            "amber light over busy tables, private wall booths and a raised "
            "bard platform. A huge carved tree-trunk bar stands before kegs "
            "and shelves of exotic bottles. Cats occupy chairs, rafters and "
            "any table whose owner looked away for a moment."
        )
        self.village_state = village_state
        self.random_source = random_source or random
        self.val = Val(village_state)
        self.add_npc(self.val)

    def describe_to(self, player):
        Room.describe_to(self, player)
        player.session.send(
            "A polished cow horn hangs behind the bar. Val serves real "
            "adventurers generously: try /order healing potion, /order mead, "
            "or ask for something impossible."
        )

    def on_command(self, session, command, arguments):
        if command == "order":
            return self._order(session, arguments)

        if command == "joke":
            return self._joke(session, arguments)

        if command == "talk":
            return self._talk(session, arguments)

        if command == "flirt":
            return self._flirt(session, arguments)

        if command == "call":
            return self._call(session, arguments)

        if command in ("examine", "inspect"):
            return self._examine(session, arguments)

        if command in ("attack", "hit"):
            return self._attack(session, arguments)

        return False

    def _val_targeted(self, arguments):
        return arguments.strip().lower() in self.VAL_TARGETS

    def _order(self, session, arguments):
        concept = arguments.strip()

        if not concept:
            session.send("Order what?")
            return True

        if len(concept) > self.MAX_ORDER_TEXT:
            session.send(
                "The horn loses interest in requests longer than eighty "
                "characters."
            )
            return True

        player = session.player

        with self.lock:
            if len(player.inventory) >= PLAYER_INVENTORY_LIMIT:
                item = None
            else:
                lowered = concept.lower()

                if any(
                    word in lowered
                    for word in ("heal", "health", "potion")
                ):
                    item = ValHealingPotion()
                elif any(
                    word in lowered
                    for word in ("mead", "ale", "beer", "cider", "wine")
                ):
                    item = ValkyrieMead()
                else:
                    item = HornBornSpecial()

                player.inventory.append(item)

        if item is None:
            session.send("You cannot carry another drink.")
            return True

        self.val.perform_action(
            NPCAction.emote(
                "tips the magical horn; impossible colours pour into a "
                "perfectly ordinary mug."
            )
        )
        self.val.perform_action(
            NPCAction.say(
                "On the house for a real adventurer. Try /drink {0}.".format(
                    item.name
                )
            )
        )
        return True

    def _joke(self, session, arguments):
        target = arguments.strip().lower()

        if target and target not in self.VAL_TARGETS:
            session.send("Ask whom for a joke?")
            return True

        self.val.perform_action(
            NPCAction.say(self.random_source.choice(self.JOKES))
        )
        return True

    def _talk(self, session, arguments):
        if not self._val_targeted(arguments):
            session.send("Talk to whom?")
            return True

        self.val.perform_action(
            NPCAction.say(
                "Val is short for Valkyrie. I fled Asgard's endless heroic "
                "dying and found honest work, warm fires and better company."
            )
        )
        return True

    def _flirt(self, session, arguments):
        if not self._val_targeted(arguments):
            session.send("Flirt with whom?")
            return True

        self.val.perform_action(
            NPCAction.say(
                "Charming. Survive the mead, impress the cats, and we shall "
                "review your application."
            )
        )
        return True

    def _call(self, session, arguments):
        if not self._val_targeted(arguments):
            session.send("Call whom?")
            return True

        self.val.perform_action(
            NPCAction.emote(
                "is suddenly at your elbow while another Val remains behind "
                "the bar, both insisting this is efficient staffing."
            )
        )
        return True

    def _examine(self, session, arguments):
        target = arguments.strip().lower()

        if target in self.HORN_TARGETS:
            session.send(
                "The polished cow horn can produce any drink concept, but "
                "Val makes every result a concrete, measurable tavern item."
            )
        elif target in self.CAT_TARGETS:
            session.send(
                "The tavern cats appear decorative until you notice that "
                "every one of them is watching your hands."
            )
        elif target in self.BAR_TARGETS:
            session.send(
                "The bar was carved from one immense fallen limb, polished "
                "smooth by stories, tankards and suspiciously many claws."
            )
        else:
            session.send("Examine what?")

        return True

    def _attack(self, session, arguments):
        if not self._val_targeted(arguments):
            session.send("Attack whom?")
            return True

        player = session.player
        old_health = player.health

        if old_health > 1:
            player.health = max(1, old_health - 5)
        self.val.perform_action(
            NPCAction.emote(
                "whistles once. Every tavern cat lands on the attacker at "
                "the same time."
            )
        )
        self.val.perform_action(
            NPCAction.say(
                "No battlefield nonsense in my tavern. The cats take that "
                "rule personally."
            )
        )
        session.send(
            "The cats enforce house policy for {0} health.".format(
                old_health - player.health
            )
        )
        return True

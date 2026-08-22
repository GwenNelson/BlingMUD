from core import Item


class Food(Item):
    """A bounded, local consumable with an explicit gameplay effect."""

    healing = 0

    def apply_to(self, player):
        return {"healed": player.heal(self.healing)}

    def consumption_message(self, result):
        return "You eat the {0}.".format(self.name)


class AcornMash(Food):
    healing = 8

    def __init__(self):
        Item.__init__(
            self,
            "acorn mash",
            "A warm bowl of humble acorn mash with a little salt, a little "
            "butter, and enough substance to keep a harvester upright."
        )

    def consumption_message(self, result):
        if result["healed"] > 0:
            return "The acorn mash restores {0} health.".format(
                result["healed"]
            )

        return "The acorn mash is comforting, if medically redundant."

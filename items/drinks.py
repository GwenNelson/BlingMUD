from core import Item, MAX_INTOXICATION


class Drink(Item):
    healing = 0
    intoxication_gain = 0

    def apply_to(self, player):
        if (
            self.intoxication_gain > 0
            and player.intoxication >= MAX_INTOXICATION
        ):
            return None

        healed = player.heal(self.healing)
        intoxication_gained = player.add_intoxication(
            self.intoxication_gain
        )
        return {
            "healed": healed,
            "intoxication_gained": intoxication_gained
        }

    def consumption_message(self, result):
        return "You finish the {0}.".format(self.name)


class ValHealingPotion(Drink):
    healing = 35
    intoxication_gain = 0

    def __init__(self):
        Item.__init__(
            self,
            "Val's healing potion",
            "A clear ruby potion drawn from Val's magical horn. It smells "
            "of clean rain and sensible decisions."
        )

    def consumption_message(self, result):
        if result["healed"] > 0:
            return (
                "Warmth knits through you, restoring {0} health.".format(
                    result["healed"]
                )
            )

        return "You feel extremely healthy and faintly overprepared."


class ValkyrieMead(Drink):
    healing = 0
    intoxication_gain = 20

    def __init__(self):
        Item.__init__(
            self,
            "Valkyrie mead",
            "Golden mead with a white head and a distant scent of thunder. "
            "Val insists this is the restrained tavern-strength version."
        )

    def consumption_message(self, result):
        return (
            "The mead tastes of honey, thunder and questionable courage. "
            "Intoxication rises by {0}.".format(
                result["intoxication_gained"]
            )
        )


class HornBornSpecial(Drink):
    healing = 10
    intoxication_gain = 8

    def __init__(self):
        Item.__init__(
            self,
            "horn-born special",
            "An impossible drink from Val's magical horn, violet at the "
            "edges and gold in the middle. Its flavour changes whenever "
            "you try to identify it."
        )

    def consumption_message(self, result):
        return (
            "The impossible flavour restores {0} health and adds {1} "
            "intoxication.".format(
                result["healed"],
                result["intoxication_gained"]
            )
        )

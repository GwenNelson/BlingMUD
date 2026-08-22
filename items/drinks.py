from core import Item, MAX_INTOXICATION


class Drink(Item):
    healing = 0
    intoxication_gain = 0

    def refusal_message(self, player):
        if (
            self.intoxication_gain > 0
            and player.intoxication >= MAX_INTOXICATION
        ):
            return "You are too intoxicated for another alcoholic drink."

        return None

    def apply_to(self, player):
        if self.refusal_message(player) is not None:
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

    def consumed_after_drinking(self, result):
        return True


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


class AcornGoblet(Drink):
    """A reusable Corbel goblet containing at most one known Val drink."""

    ALLOWED_DRINK_TYPES = (
        ValHealingPotion,
        ValkyrieMead,
        HornBornSpecial
    )

    def __init__(self, held_drink=None):
        Item.__init__(
            self,
            "acorn goblet",
            "An ornate, practical goblet turned from one giant acorn shell. "
            "Its cup is dry and ready for Val's horn."
        )
        self.held_drink = None

        if held_drink is not None and not self.fill(held_drink):
            raise ValueError("unsupported acorn goblet drink")

    def fill(self, drink):
        if self.held_drink is not None:
            return False

        if not isinstance(drink, self.ALLOWED_DRINK_TYPES):
            return False

        self.held_drink = drink
        return True

    def refusal_message(self, player):
        if self.held_drink is None:
            return "The acorn goblet is empty. Ask Val to fill it."

        return self.held_drink.refusal_message(player)

    def apply_to(self, player):
        if self.refusal_message(player) is not None:
            return None

        result = self.held_drink.apply_to(player)

        if result is None:
            return None

        self.held_drink = None
        return result

    def consumption_message(self, result):
        return "From the acorn goblet: {0}".format(
            self.held_drink.consumption_message(result)
            if self.held_drink is not None
            else "The last of Val's drink goes down very well."
        )

    def consumed_after_drinking(self, result):
        return False

    def look(self, viewer):
        if self.held_drink is None:
            return self.description

        return (
            "The acorn goblet currently holds {0}.".format(
                self.held_drink.name
            )
        )

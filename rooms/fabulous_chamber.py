from core import *

from items.pimp_hat import PimpHat

class FabulousChamber(Room):
    """Example room with custom code and state."""

    def __init__(self):
        Room.__init__(
            self,
            "fabulous_chamber",
            "The Chamber of Immeasurable Fabulousness",
            "Sequins glitter across every surface. The room appears to "
            "have been decorated by someone with unlimited confidence."
        )

    def describe_to(self, player):
        super().describe_to(player)

        hats = 0

        with self.lock:
            for item in self.items:
                if isinstance(item, PimpHat):
                    hats += 1

        if hats == 0:
            player.session.send("Sadly, there are no pimp hats in the chamber.")
        elif hats == 1:
            player.session.send("There is a pimp hat! Quickly, grab it!")
        else:
            player.session.send(
                "There are {0} magnificent pimp hats here!".format(hats)
            )



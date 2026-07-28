from core import *

class PimpHat(Item):
    def __init__(self):
        Item.__init__(
            self,
            "pimp hat",
            "An enormous and excessively fabulous pimp hat.",
            wearable=True
        )

    def on_equip(self, player):
        player.fabulousness += 10

    def on_unequip(self, player):
        player.fabulousness -= 10



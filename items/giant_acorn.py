from core import Item


class GiantAcorn(Item):
    def __init__(self):
        Item.__init__(
            self,
            "giant acorn",
            "A heavy acorn as broad as a soup bowl, with a deep brown "
            "shell sturdy enough to become something useful in a "
            "woodworker's hands."
        )

from core import Item


class RoyalPossumBottleCap(Item):
    """A harmless keepsake granted by the Suspicious Alley possum."""

    def __init__(self):
        Item.__init__(
            self,
            "royal possum bottle cap",
            "A purple bottle cap polished to a regal shine. Tiny tooth "
            "marks around its edge suggest that its previous owner chose "
            "you with considerable care."
        )

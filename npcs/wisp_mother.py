from core import NPC, SimpleRandomBehavior


class WispMother(NPC):
    def __init__(self):
        behavior = SimpleRandomBehavior(
            emotes=(
                "drifts around the stair foot in a slow blue orbit.",
                "brightens gently, and the smaller Wisps answer in kind.",
                "sends a warm ripple of light across the grass."
            ),
            minimum_delay=35.0,
            maximum_delay=70.0,
            speech_weight=0.0,
            emote_weight=1.0
        )
        NPC.__init__(
            self,
            "Wisp Mother",
            "A faint blue orb, slightly larger than the Wisps drifting "
            "through the Green, hovers beside the first impossible stair. "
            "She has no face and speaks no words, yet her light feels "
            "watchful rather than empty.",
            behavior=behavior
        )

    def look(self, viewer):
        return (
            "The Wisp Mother hovers in perfect silence. As you focus on "
            "her, a gentle pulse of blue light answers and leaves a trace "
            "of warmth across your skin."
        )

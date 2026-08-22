from core import FSMBehavior, NPC, NPCAction


def _mentions_possum(behavior, context):
    text = (context.get("text") or "").lower()
    return "possum" in text or "bin" in text


def _mentions_fabulous_food(behavior, context):
    text = (context.get("text") or "").lower()
    return any(
        word in text
        for word in ("bling", "fabulous", "hat", "snack", "food")
    )


def _mentions_friendship(behavior, context):
    text = (context.get("text") or "").lower()
    return any(
        word in text
        for word in ("friend", "possum", "thank", "hello")
    )


class BinPossumBehavior(FSMBehavior):
    STATE_WARY = "wary"
    STATE_FRIENDLY = "friendly"

    def __init__(self):
        states = {
            self.STATE_WARY: {
                "events": {
                    self.EVENT_SAY: (
                        {
                            "condition": _mentions_fabulous_food,
                            "actions": NPCAction.say(
                                "The possum fixes its bright eyes upon "
                                "anything especially fabulous."
                            )
                        },
                        {
                            "condition": _mentions_possum,
                            "actions": NPCAction.emote(
                                "peers over the bin lid and hisses with "
                                "the gravity of a minor aristocrat."
                            )
                        }
                    )
                },
                "timeout": {
                    "after": 24.0,
                    "target": self.STATE_WARY,
                    "actions": NPCAction.emote(
                        "sorts through the bin with loud, discriminating "
                        "rustles."
                    )
                }
            },
            self.STATE_FRIENDLY: {
                "events": {
                    self.EVENT_SAY: {
                        "condition": _mentions_friendship,
                        "actions": NPCAction.say(
                            "The possum chirrups proudly. The alliance "
                            "between adventurer and bin is strong."
                        )
                    }
                },
                "timeout": {
                    "after": 30.0,
                    "target": self.STATE_FRIENDLY,
                    "actions": NPCAction.emote(
                        "adjusts its magnificent hat and surveys the alley "
                        "like a tiny monarch."
                    )
                }
            }
        }

        FSMBehavior.__init__(self, states, self.STATE_WARY)


class BinPossum(NPC):
    def __init__(self):
        NPC.__init__(
            self,
            "bin possum",
            "A battle-scarred possum crouches behind the bin lid, watching "
            "you with bright eyes and formidable suspicion.",
            behavior=BinPossumBehavior()
        )

    def look(self, viewer):
        if self.behavior.current_state == BinPossumBehavior.STATE_FRIENDLY:
            return (
                "The possum wears an enormous pimp hat at a rakish angle. "
                "It regards you as a trusted subject of its tiny kingdom."
            )

        return NPC.look(self, viewer)

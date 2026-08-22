from core import FSMBehavior, NPC, NPCAction


def _corbel_arrival(behavior, context):
    return NPCAction.say(
        "Mind the shavings. Giant acorns make fine goblets, but only after "
        "a great deal of honest turning."
    )


def _corbel_acorn_reply(behavior, context):
    return NPCAction.say(
        "A sound giant acorn earns five coins. Its shell can become a "
        "goblet worth keeping."
    )


def _mentions_acorn(behavior, context):
    return "acorn" in (context.get("text") or "").lower()


class MasterCorbelBehavior(FSMBehavior):
    STATE_WORKING = "working"

    def __init__(self):
        FSMBehavior.__init__(
            self,
            {
                self.STATE_WORKING: {
                    "events": {
                        self.EVENT_PLAYER_ENTER: {"handler": _corbel_arrival},
                        self.EVENT_SAY: {
                            "condition": _mentions_acorn,
                            "handler": _corbel_acorn_reply
                        }
                    },
                    "timeout": {
                        "after": 35.0,
                        "target": self.STATE_WORKING,
                        "actions": NPCAction.emote(
                            "checks the curve of an acorn-shell goblet "
                            "against the lamplight."
                        )
                    }
                }
            },
            self.STATE_WORKING
        )


class MasterCorbel(NPC):
    def __init__(self):
        NPC.__init__(
            self,
            "Master Corbel",
            "Master Corbel is a practical village woodworker with curled "
            "shavings in their hair and the patient hands of a turner.",
            behavior=MasterCorbelBehavior()
        )

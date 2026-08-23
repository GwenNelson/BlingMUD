from core import FSMBehavior, NPC, NPCAction


class CeridwenBehavior(FSMBehavior):
    STATE_BREWING = "brewing"
    def __init__(self):
        FSMBehavior.__init__(self, {
            self.STATE_BREWING: {
                "events": {
                    self.EVENT_PLAYER_ENTER: {"actions": NPCAction.say("Mind the pot. Salves are safer than whatever is growing behind the cottage.")},
                    self.EVENT_SAY: {
                        "condition": lambda behavior, context: "weed" in (context.get("text") or "").lower(),
                        "actions": NPCAction.say("Bring me a rare weed intact and we can discuss the experimental shelf.")
                    }
                },
                "timeout": {"after": 37.0, "target": self.STATE_BREWING, "actions": NPCAction.emote("stirs the bubbling pot and swats away a green vapor face.")}
            }
        }, self.STATE_BREWING)


class Ceridwen(NPC):
    def __init__(self):
        NPC.__init__(self, "Ceridwen", "Ceridwen is an older herbalist with leaves in her hair, dirt beneath her nails, and a dangerous-looking spoon.", behavior=CeridwenBehavior())

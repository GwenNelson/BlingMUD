from core import FSMBehavior, NPC, NPCAction


class EiseleBehavior(FSMBehavior):
    STATE_WORKING = "working"
    def __init__(self):
        FSMBehavior.__init__(self, {
            self.STATE_WORKING: {
                "events": {
                    self.EVENT_PLAYER_ENTER: {"actions": NPCAction.say("Mind the sparks. I buy sound metal and sell honest work.")},
                    self.EVENT_SAY: {
                        "condition": lambda behavior, context: "scrap" in (context.get("text") or "").lower(),
                        "actions": NPCAction.say("Browse the scrap rack, then bring me metal worth weighing.")
                    }
                },
                "timeout": {"after": 32.0, "target": self.STATE_WORKING, "actions": NPCAction.emote("checks a glowing seam on the anvil.")}
            }
        }, self.STATE_WORKING)


class Eisele(NPC):
    def __init__(self):
        NPC.__init__(self, "Eisele", "Eisele is a practical blacksmith with charcoal on her sleeves and a professional eye for metal.", behavior=EiseleBehavior())


class TackdriverBehavior(FSMBehavior):
    STATE_ATTACHED = "attached"
    def __init__(self):
        FSMBehavior.__init__(self, {
            self.STATE_ATTACHED: {
                "events": {
                    self.EVENT_PLAYER_ENTER: {"actions": NPCAction.emote("vibrates in the anvil and mutters about labour.")},
                    self.EVENT_SAY: {
                        "condition": lambda behavior, context: any(word in (context.get("text") or "").lower() for word in ("society", "work", "hammer")),
                        "actions": NPCAction.say("The means of production should not be left unattended on a workbench!")
                    }
                },
                "timeout": {"after": 41.0, "target": self.STATE_ATTACHED, "actions": NPCAction.emote("gives one emphatic ideological clang.")}
            }
        }, self.STATE_ATTACHED)


class Tackdriver(NPC):
    def __init__(self):
        NPC.__init__(self, "Tackdriver", "A forged hammer with star-flecked ore and blinking eye-like inlays.", behavior=TackdriverBehavior())

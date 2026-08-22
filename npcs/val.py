from core import FSMBehavior, NPC, NPCAction


def _mentions_joke(behavior, context):
    return "joke" in (context.get("text") or "").lower()


def _mentions_drink(behavior, context):
    text = (context.get("text") or "").lower()
    return any(word in text for word in ("drink", "horn", "mead", "order"))


def _mentions_val(behavior, context):
    text = (context.get("text") or "").lower()
    return "val" in text or "hello" in text or "hail" in text


def _arrival_actions(behavior, context):
    player = context["player"]
    actions = []
    harmed_count = behavior.village_state.wisp_snapshot()["harmed_count"]

    if harmed_count > behavior.last_wisp_harm_seen:
        behavior.last_wisp_harm_seen = harmed_count
        actions.extend((
            NPCAction.say(
                "Someone harmed the Wisp Mother. The whole village knows, "
                "and my cats are taking names."
            ),
            NPCAction.emote(
                "glances towards the Green as every tavern cat goes still."
            )
        ))

    if player.health * 2 <= player.max_health:
        actions.append(
            NPCAction.say(
                "You look half-dead. Order a healing potion; that one is "
                "always on the house."
            )
        )
    elif player.intoxication >= 60:
        actions.append(
            NPCAction.say(
                "Easy there, champion. Water and a chair before more mead."
            )
        )
    else:
        actions.append(
            NPCAction.say(
                "Welcome to the Holler! Sit, shout, or order something "
                "impossible."
            )
        )

    return tuple(actions)


class ValBehavior(FSMBehavior):
    STATE_HOSTING = "hosting"

    def __init__(self, village_state):
        self.village_state = village_state
        self.last_wisp_harm_seen = 0
        states = {
            self.STATE_HOSTING: {
                "events": {
                    self.EVENT_PLAYER_ENTER: {
                        "handler": _arrival_actions
                    },
                    self.EVENT_SAY: (
                        {
                            "condition": _mentions_joke,
                            "actions": NPCAction.say(
                                "Use /joke val and I shall lower the tone "
                                "professionally."
                            )
                        },
                        {
                            "condition": _mentions_drink,
                            "actions": NPCAction.say(
                                "Tell the horn what you want with /order. "
                                "It has poor judgment and excellent range."
                            )
                        },
                        {
                            "condition": _mentions_val,
                            "actions": NPCAction.say(
                                "Hail! Val is short for Valkyrie, and tavern "
                                "work beats dying gloriously before breakfast."
                            )
                        }
                    )
                },
                "timeout": {
                    "after": 28.0,
                    "target": self.STATE_HOSTING,
                    "actions": NPCAction.emote(
                        "is behind the bar and at two tables at once; a third "
                        "Val appears briefly to rescue a tray from a cat."
                    )
                }
            }
        }
        FSMBehavior.__init__(self, states, self.STATE_HOSTING)


class Val(NPC):
    def __init__(self, village_state):
        NPC.__init__(
            self,
            "Val",
            "Val is a broad-shouldered, bright-eyed Valkyrie refugee from "
            "Asgard. She wears an apron over old battle leathers and looks "
            "far happier commanding a tavern than an endless battlefield.",
            behavior=ValBehavior(village_state)
        )

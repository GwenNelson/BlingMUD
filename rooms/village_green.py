import time

from core import CommandSpec, NPCAction, Room
from npcs.falling_acorn import FallingAcornHazard
from npcs.wisp_mother import WispMother


def _is_night_now():
    hour = time.localtime().tm_hour
    return hour < 6 or hour >= 20


class VillageGreen(Room):
    command_specs = (
        CommandSpec(
            "examine",
            "/examine wisp mother",
            "Examine a feature or being in the Village Green.",
            aliases=("inspect",)
        ),
        CommandSpec(
            "protect",
            "/protect wisp mother",
            "Place a one-hit protective ward around the Wisp Mother.",
            aliases=("guard",)
        ),
        CommandSpec(
            "attack",
            "/attack wisp mother",
            "Commit an act the village will remember.",
            aliases=("hit",)
        )
    )

    WISP_TARGETS = (
        "wisp mother",
        "the wisp mother",
        "mother wisp",
        "wisp"
    )

    def __init__(
        self,
        village_state,
        time_source=None,
        night_source=None,
        hazard_settings=None
    ):
        Room.__init__(
            self,
            "village_green",
            "The Village Green",
            "",
            time_source=time_source
        )
        self.village_state = village_state
        self.night_source = night_source or _is_night_now
        self.wisp_mother = WispMother()
        self.acorn_hazard = FallingAcornHazard(
            village_state,
            **(hazard_settings or {})
        )
        if village_state.wisp_is_present():
            self.add_npc(self.wisp_mother)

        self.add_npc(self.acorn_hazard)

    def _refresh_wisp_mother(self):
        restored = self.village_state.refresh_wisp(self.time_source())

        if (
            self.village_state.wisp_is_present()
            and self.wisp_mother.room is not self
        ):
            self.add_npc(self.wisp_mother)

        if restored:
            self.broadcast(
                "* A tiny blue spark gathers beside the stair, and the Wisp "
                "Mother slowly reforms in forgiving silence."
            )

        return restored

    def synchronize_persisted_state(self):
        """Reconcile the durable Wisp presence with the room's NPC list."""
        if self.village_state.wisp_is_present():
            if self.wisp_mother.room is not self:
                self.add_npc(self.wisp_mother)
        elif self.wisp_mother.room is self:
            self.remove_npc(self.wisp_mother)

    def description_for(self, player):
        self._refresh_wisp_mother()
        wisp_present = self.village_state.wisp_is_present()

        if self.night_source():
            if wisp_present:
                return (
                    "Night has turned the broad village commons into a sea "
                    "of blue-green light. Wisps drift above the grass like "
                    "living lanterns beneath an enormous floating tree with "
                    "no trunk, only roots hanging down around a precarious "
                    "stair into its canopy."
                )

            return (
                "The Green lies unnaturally dark. Without the Wisp Mother, "
                "only a few frightened sparks remain beneath the enormous "
                "trunkless tree, and its hanging roots resemble grasping "
                "hands around the stair."
            )

        description = (
            "A broad green commons spreads beneath an enormous floating "
            "tree. There is no trunk: only a continent of leaves overhead "
            "and impossible roots hanging down around a hand-built stair "
            "into the canopy. Villagers cross the grass between roads that "
            "will one day bind every corner of the village together."
        )

        if not wisp_present:
            description += (
                " Even in daylight the place feels diminished; the smaller "
                "Wisps hide, and word of the Wisp Mother's harm has made the "
                "commons quiet and cold."
            )

        return description

    def describe_to(self, player):
        Room.describe_to(self, player)
        tree = self.village_state.tree_snapshot()

        if tree["danger"] > 0:
            player.session.send(
                "Heavy shapes sway overhead. Harvesting in the canopy would "
                "reduce the chance of an embarrassing acorn bonking."
            )
        else:
            player.session.send(
                "The most dangerous acorns have been harvested, and the "
                "grass feels temporarily safe."
            )

    def _wisp_targeted(self, arguments):
        return arguments.strip().lower() in self.WISP_TARGETS

    def on_command(self, session, command, arguments):
        self._refresh_wisp_mother()

        if command in ("examine", "inspect"):
            return self._examine(session, arguments)

        if command in ("protect", "guard"):
            return self._protect(session, arguments)

        if command in ("attack", "hit"):
            return self._attack(session, arguments)

        return False

    def _examine(self, session, arguments):
        if not self._wisp_targeted(arguments):
            session.send("Examine what?")
            return True

        if not self.village_state.wisp_is_present():
            session.send(
                "Only a cold patch of air remains beside the stair."
            )
            return True

        self.wisp_mother.perform_action(
            NPCAction.emote(
                "answers the attention with one warm, gentle pulse of blue."
            )
        )
        session.send(
            "She says nothing, but the light feels unmistakably welcoming."
        )
        return True

    def _protect(self, session, arguments):
        if not self._wisp_targeted(arguments):
            session.send("Protect whom?")
            return True

        result = self.village_state.protect_wisp()

        if result == "absent":
            session.send("There is only darkness here to protect.")
        elif result == "already_warded":
            session.send(
                "A protective ring of smaller Wisps already surrounds her."
            )
        else:
            self.wisp_mother.perform_action(
                NPCAction.emote(
                    "glows brighter as the smaller Wisps form a warding ring."
                )
            )
            session.send(
                "Your promise takes visible shape. The ward will turn aside "
                "one act of violence."
            )

        return True

    def _attack(self, session, arguments):
        if not self._wisp_targeted(arguments):
            session.send("Attack what?")
            return True

        result = self.village_state.attack_wisp(self.time_source())

        if result == "absent":
            session.send("The darkness offers no target.")
            return True

        if result == "ward_broken":
            self.broadcast(
                "* The smaller Wisps throw themselves into the blow. Their "
                "protective ring shatters, but the Wisp Mother survives."
            )
            return True

        if self.wisp_mother.room is self:
            self.remove_npc(self.wisp_mother)

        self.broadcast(
            "* The Wisp Mother gutters out. Every blue light across the "
            "Green dims, and horrified voices carry the news into the village."
        )
        session.send(
            "The commons will remember this, and its guardian will not "
            "return for a long while."
        )
        return True

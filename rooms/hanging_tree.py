from core import CommandSpec, PLAYER_INVENTORY_LIMIT, Room
from items.giant_acorn import GiantAcorn


class HangingTreeCanopy(Room):
    command_specs = (
        CommandSpec(
            "harvest",
            "/harvest acorn",
            "Gather one giant acorn from the reachable branches.",
            aliases=("gather",)
        ),
    )

    ACORN_TARGETS = ("acorn", "acorns", "giant acorn", "giant acorns")

    def __init__(self, village_state):
        Room.__init__(
            self,
            "hanging_tree_canopy",
            "The Canopy of the Hanging Tree",
            "Broad leaves turn the sky green around a maze of hand-carved "
            "steps, rope rungs and narrow bridges. No trunk supports any "
            "of it. Roots trail down into open air while giant acorns bend "
            "the branches overhead. The route is precarious, but carefully "
            "made and plainly travelled."
        )
        self.village_state = village_state

    def describe_to(self, player):
        Room.describe_to(self, player)
        snapshot = self.village_state.tree_snapshot()

        if snapshot["supply"] <= 0:
            player.session.send(
                "The reachable branches have been picked clean for now."
            )
        elif snapshot["danger"] > 0:
            player.session.send(
                "Several dangerously heavy acorns remain overhead. "
                "Try /harvest acorn or /gather acorn."
            )
        else:
            player.session.send(
                "The worst overhanging acorns have been gathered, and the "
                "Green below is safer for it."
            )

    def on_command(self, session, command, arguments):
        if command not in ("harvest", "gather"):
            return False

        target = arguments.strip().lower()

        if target not in self.ACORN_TARGETS:
            session.send("Gather what?")
            return True

        player = session.player

        with self.lock:
            if len(player.inventory) >= PLAYER_INVENTORY_LIMIT:
                snapshot = "inventory_full"
            elif any(
                isinstance(item, GiantAcorn)
                for item in player.inventory
            ):
                snapshot = "already_carrying"
            else:
                snapshot = self.village_state.harvest_acorn()

                if snapshot is not None:
                    player.inventory.append(GiantAcorn())

        if snapshot == "inventory_full":
            session.send("You cannot carry anything else.")
            return True

        if snapshot == "already_carrying":
            session.send(
                "One giant acorn is quite enough to carry at a time."
            )
            return True

        if snapshot is None:
            session.send(
                "The reachable branches have already been picked clean."
            )
            return True

        session.send(
            "You wrestle a giant acorn free and add its considerable "
            "weight to your inventory."
        )
        self.broadcast(
            "* {0} harvests a giant acorn from a swaying branch.".format(
                player.name
            ),
            exclude=session
        )

        if snapshot["became_safe"]:
            session.send(
                "A final burden lifts from the branches. The Green below "
                "should be safe from surprise bonkings for now."
            )
        elif snapshot["danger"] == 0:
            session.send(
                "The Green below is already safe from surprise bonkings, "
                "but Corbel can still put this acorn to use."
            )
        else:
            session.send(
                "Fewer ominous shapes now hang above the Green."
            )

        return True

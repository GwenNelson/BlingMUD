from core import NPCAction, PLAYER_INVENTORY_LIMIT, Room
from items.pimp_hat import PimpHat
from items.possum_token import RoyalPossumBottleCap
from npcs.bin_possum import BinPossum, BinPossumBehavior


class SuspiciousAlley(Room):
    """A small, stateful encounter hidden behind the town-square bin."""

    BIN_TARGETS = ("bin", "the bin", "rubbish bin", "trash bin")
    POSSUM_TARGETS = (
        "possum",
        "bin possum",
        "the possum",
        "the bin possum"
    )

    def __init__(self):
        Room.__init__(
            self,
            "suspicious_alley",
            "A Suspicious Alley",
            "The alley is dark, narrow and probably needlessly dramatic. "
            "A dented rubbish bin squats beneath a gutter while something "
            "behind its lid rustles with theatrical menace."
        )
        self.possum = BinPossum()
        self.possum_revealed = False
        self.rewarded_players = set()

    def describe_to(self, player):
        Room.describe_to(self, player)

        if self.possum_revealed:
            player.session.send(
                "The bin possum is visible beside its battered kingdom."
            )
        else:
            player.session.send(
                "The bin might reward a courageous /search."
            )

    def on_command(self, session, command, arguments):
        if command in ("search", "rummage"):
            return self._search(session, arguments)

        if command == "offer":
            return self._offer(session, arguments)

        if command in ("pet", "stroke"):
            return self._pet(session, arguments)

        return False

    def _search(self, session, arguments):
        target = arguments.strip().lower()

        if not target:
            session.send("Search what?")
            return True

        if target not in self.BIN_TARGETS:
            session.send(
                "You search {0}, but the suspicious noises remain firmly "
                "bin-shaped.".format(arguments)
            )
            return True

        with self.lock:
            first_reveal = not self.possum_revealed

            if first_reveal:
                self.add_npc(self.possum)
                self.possum_revealed = True

        if first_reveal:
            self.broadcast(
                "* The bin lid erupts upwards and a furious possum rises "
                "from the rubbish like an offended monarch."
            )
            self.possum.perform_action(
                NPCAction.emote(
                    "plants both front paws upon the bin and demands tribute."
                )
            )
            session.send(
                "Its gaze keeps drifting towards objects of exceptional "
                "fabulousness. Perhaps you could /offer one."
            )
        else:
            session.send(
                "You search the bin again. The possum watches you search "
                "its throne with profound disapproval."
            )

        return True

    def _offered_item_name(self, arguments):
        item_name = arguments.strip()
        lowered = item_name.lower()

        if lowered in self.POSSUM_TARGETS:
            return ""

        for target in sorted(self.POSSUM_TARGETS, key=len, reverse=True):
            prefix = target + " "

            if lowered.startswith(prefix):
                return item_name[len(prefix):].strip()

        for target in sorted(self.POSSUM_TARGETS, key=len, reverse=True):
            suffix = " to " + target

            if lowered.endswith(suffix):
                item_name = item_name[:-len(suffix)].strip()
                break

        return item_name

    def _offer(self, session, arguments):
        if not self.possum_revealed:
            session.send("Offer what to whom? Only the bin rustles in reply.")
            return True

        item_name = self._offered_item_name(arguments)

        if not item_name:
            session.send("Offer what?")
            return True

        player = session.player
        item = player.find_item(item_name)

        if item is None:
            session.send("You are not carrying {0}.".format(item_name))
            return True

        if not isinstance(item, PimpHat):
            self.possum.perform_action(
                NPCAction.emote(
                    "sniffs the offering, then pushes it back with one paw."
                )
            )
            session.send(
                "Apparently the possum's standards are more fabulous than that."
            )
            return True

        offer_result = None

        with self.lock:
            if (
                self.possum.behavior.current_state
                == BinPossumBehavior.STATE_FRIENDLY
            ):
                offer_result = "already_friendly"
            elif item not in player.inventory:
                offer_result = "item_missing"
            else:
                for slot, equipped_item in list(player.equipment.items()):
                    if equipped_item is item:
                        item.on_unequip(player)
                        del player.equipment[slot]

                player.inventory.remove(item)
                self.possum.inventory.append(item)
                self.possum.behavior.set_state(
                    BinPossumBehavior.STATE_FRIENDLY
                )

        if offer_result == "already_friendly":
            session.send(
                "The possum already has everything it wants and declines "
                "further tribute."
            )
            return True

        if offer_result == "item_missing":
            session.send("That offering is no longer in your inventory.")
            return True

        self.possum.perform_action(
            NPCAction.emote(
                "seizes the enormous pimp hat, places it upon its head and "
                "instantly becomes royalty."
            )
        )
        self.possum.perform_action(
            NPCAction.say(
                "The possum accepts your tribute. You may now /pet possum."
            )
        )
        return True

    def _pet(self, session, arguments):
        target = arguments.strip().lower()

        if target not in self.POSSUM_TARGETS:
            session.send("Pet what?")
            return True

        if not self.possum_revealed:
            session.send(
                "You reach towards the bin. Something inside slaps your "
                "hand away with a tiny paw."
            )
            return True

        if self.possum.behavior.current_state != BinPossumBehavior.STATE_FRIENDLY:
            self.possum.perform_action(
                NPCAction.emote(
                    "bares an unreasonable number of tiny teeth. Tribute first."
                )
            )
            return True

        player = session.player
        player_key = player.name.lower()

        with self.lock:
            first_reward = player_key not in self.rewarded_players
            inventory_full = len(player.inventory) >= PLAYER_INVENTORY_LIMIT

            if first_reward and not inventory_full:
                self.rewarded_players.add(player_key)
                player.inventory.append(RoyalPossumBottleCap())

        self.possum.perform_action(
            NPCAction.emote(
                "allows {0} one solemn pat between the ears.".format(
                    player.name
                )
            )
        )

        if first_reward and inventory_full:
            session.send(
                "The possum tries to award a bottle cap, but you cannot "
                "carry anything else. It will keep the honour for later."
            )
        elif first_reward:
            session.send(
                "The possum presses a royal possum bottle cap into your hand."
            )
        else:
            session.send(
                "The possum permits another pat, but royal honours are "
                "awarded only once."
            )

        return True

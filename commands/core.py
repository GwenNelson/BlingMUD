""" Core commands go here
"""

from core import *
from items.drinks import Drink

@register_command
class HelpCommand(Command):
    name = "help"
    aliases = ("commands",)

    def execute(self, session, arguments):
        session.send("")
        session.send("BLINGMUD commands")
        session.send("-----------------")
        session.send("Anything without a slash is spoken aloud.")
        session.send("")
        session.send("/look")
        session.send("/look <object or person>")
        session.send("/north, /south, /east, /west")
        session.send("/up, /down")
        session.send("/go <direction>")
        session.send("/me <action>")
        session.send("/who")
        session.send("/inventory")
        session.send("/drink <drink>")
        session.send("/take <object>")
        session.send("/drop <object>")
        session.send("/equip <object>")
        session.send("/stats")
        session.send("/worship <person>")
        session.send("/bling")
        session.send("/quit")

@register_command
class LookCommand(Command):
    name = "look"
    aliases = ("l",)

    def execute(self, session, arguments):
        player = session.player

        if not arguments:
            player.room.describe_to(player)
            return

        target_name = arguments.strip().lower()

        with player.room.lock:
            room_items   = list(player.room.items)
            room_players = list(player.room.players)
            room_npcs    = list(player.room.npcs)

        for item in player.inventory + room_items:
            if item.name.lower() == target_name:
                session.send(item.look(player))
                return

        for other_player in room_players:
            if other_player.name.lower() == target_name:
                session.send(other_player.look(player))
                return

        for npc in room_npcs:
            if npc.name.lower() == target_name:
               session.send(npc.look(player))
               return

        session.send("You do not see {0} here.".format(arguments))


@register_command
class GoCommand(Command):
    name = "go"
    aliases = ()

    def execute(self, session, arguments):
        direction = arguments.strip().lower()

        if not direction:
            session.send("Go where?")
            return

        session.move(direction)


class DirectionCommand(Command):
    direction = None

    def execute(self, session, arguments):
        session.move(self.direction)


@register_command
class NorthCommand(DirectionCommand):
    name = "north"
    aliases = ("n",)
    direction = "north"


@register_command
class SouthCommand(DirectionCommand):
    name = "south"
    aliases = ("s",)
    direction = "south"


@register_command
class EastCommand(DirectionCommand):
    name = "east"
    aliases = ("e",)
    direction = "east"


@register_command
class WestCommand(DirectionCommand):
    name = "west"
    aliases = ("w",)
    direction = "west"


@register_command
class UpCommand(DirectionCommand):
    name = "up"
    aliases = ("u",)
    direction = "up"


@register_command
class DownCommand(DirectionCommand):
    name = "down"
    aliases = ("d",)
    direction = "down"


@register_command
class EmoteCommand(Command):
    name = "me"
    aliases = ("emote",)

    def execute(self, session, arguments):
        if not arguments:
            session.send("Do what?")
            return

        session.player.room.broadcast(
            "* {0} {1}".format(colour(session.player.name,Colour.BRIGHT_CYAN), arguments)
        )
        session.player.room.notify_player_emoted(
            session.player,
            arguments
        )

@register_command
class InventoryCommand(Command):
    name = "inventory"
    aliases = ("inv", "i")

    def execute(self, session, arguments):
        player = session.player

        if not player.inventory:
            session.send("You are carrying nothing.")
            return

        session.send("You are carrying:")
        for item in player.inventory:
            equipped = ""

            if item in player.equipment.values():
                equipped = " (equipped)"

            session.send("  {0}{1}".format(colour(item.name,Colour.BRIGHT_GREEN), equipped))


@register_command
class DrinkCommand(Command):
    name = "drink"
    aliases = ("quaff",)

    def execute(self, session, arguments):
        player = session.player
        item = player.find_item(arguments)

        if item is None:
            session.send("You are not carrying that drink.")
            return

        if not isinstance(item, Drink):
            session.send("That is not something you can drink.")
            return

        result = item.apply_to(player)

        if result is None:
            session.send(
                "You are too intoxicated for another alcoholic drink."
            )
            return

        player.inventory.remove(item)
        session.send(item.consumption_message(result))
        player.room.broadcast(
            "* {0} drinks {1}.".format(player.name, item.name),
            exclude=session
        )


@register_command
class TakeCommand(Command):
    name = "take"
    aliases = ("get",)

    def execute(self, session, arguments):
        player = session.player
        wanted = arguments.strip().lower()

        if not wanted:
            session.send("Take what?")
            return

        if player.inventory_is_full():
            session.send("You cannot carry anything else.")
            return

        item = None

        with player.room.lock:
            for candidate in player.room.items:
                if candidate.name.lower() == wanted:
                    item = candidate
                    break

            if item is not None:
                player.room.items.remove(item)

        if item is None:
            session.send("There is no {0} here.".format(arguments))
            return

        player.inventory.append(item)
        session.send("You take the {0}.".format(colour(item.name,Colour.BRIGHT_GREEN)))

        player.room.broadcast(
            "* {0} takes the {1}.".format(colour(player.name,Colour.BRIGHT_CYAN), colour(item.name,Colour.BRIGHT_GREEN)),
            exclude=session
        )


@register_command
class DropCommand(Command):
    name = "drop"
    aliases = ()

    def execute(self, session, arguments):
        player = session.player
        item = player.find_item(arguments)

        if item is None:
            session.send("You are not carrying that.")
            return

        with player.room.lock:
            if len(player.room.items) >= ROOM_ITEM_LIMIT:
                room_is_full = True
            else:
                room_is_full = False

                for slot, equipped_item in list(player.equipment.items()):
                    if equipped_item is item:
                        item.on_unequip(player)
                        del player.equipment[slot]

                player.inventory.remove(item)
                player.room.items.append(item)

        if room_is_full:
            session.send("There is no safe place to put anything else here.")
            return

        session.send("You drop the {0}.".format(colour(item.name,Colour.BRIGHT_GREEN)))

        player.room.broadcast(
            "* {0} drops the {1}.".format(colour(player.name,Colour.BRIGHT_CYAN), colour(item.name,Colour.BRIGHT_GREEN)),
            exclude=session
        )


@register_command
class EquipCommand(Command):
    name = "equip"
    aliases = ("wear",)

    def execute(self, session, arguments):
        player = session.player
        item = player.find_item(arguments)

        if item is None:
            session.send("You are not carrying that.")
            return

        if not item.wearable:
            session.send("You cannot equip that.")
            return

        old_item = player.equipment.get(item.worn_where)

        if old_item is item:
            session.send("You are already wearing it.")
            return

        if old_item is not None:
            old_item.on_unequip(player)

        player.equipment[item.worn_where] = item
        player.session.send("You equip the {0}.".format(colour(item.name,Colour.BRIGHT_GREEN)))
        item.on_equip(player)

@register_command
class StatsCommand(Command):
    name = "stats"
    aliases = ()

    def execute(self, session, arguments):
        player = session.player
        session.send("Name: {0}".format(colour(player.name,Colour.BRIGHT_CYAN)))
        session.send(
            "Fabulousness: +{0}%".format(player.fabulousness)
        )
        session.send(
            "Health: {0}/{1}".format(player.health, player.max_health)
        )
        session.send(
            "Intoxication: {0}/{1}".format(
                player.intoxication,
                MAX_INTOXICATION
            )
        )



@register_command
class QuitCommand(Command):
    name = "quit"
    aliases = ("exit",)

    def execute(self, session, arguments):
        session.send("Goodbye!")
        session.running = False

from core import *

class PimpHat(Item):
    def __init__(self):
        Item.__init__(
            self,
            "pimp hat",
            "An enormous and excessively fabulous pimp hat.",
            wearable=True,
            worn_where="Head"
        )

    def on_equip(self, player):
        player.fabulousness += 10

        player.session.send("You feel considerably more fabulous.")

        player.room.broadcast(
            "* {0} equips an enormous fabulous pimp hat.".format(player.name),
            exclude=player.session
        )
    
    def describe_look_equip(self, player):
        return "They are wearing an enormous fabulous pimp hat!"

    def on_unequip(self, player):
        player.fabulousness -= 10




@register_command
class BlingCommand(Command):
    name = "bling"
    aliases = ()

    def execute(self, session, arguments):
        player = session.player
        hat = PimpHat()

        with player.room.lock:
            player.room.items.append(hat)

        player.room.broadcast("")
        player.room.broadcast(
            "* AN ENORMOUS FABULOUS PIMP HAT FALLS FROM THE SKY *"
        )
        player.room.broadcast("")
        session.send("It lands at your feet with impossible style.")



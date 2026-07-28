import threading
import time

TICK_DELAY = 3.0

class Colour:
    UNDERLINE = "\033[4m" # i know, not a colour - but it makes sense here
    BOLD      = "\033[1m"
    DIM       = "\033[2m"

    BOLD_OFF      = "\033[22m"
    ITALIC_OFF    = "\033[23m"
    UNDERLINE_OFF = "\033[24m"
    REVERSE_OFF   = "\033[27m"
    STRIKE_OFF    = "\033[29m"

    RESET = "\033[0m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"

    BRIGHT_RED    = "\033[1;91m"
    BRIGHT_GREEN  = "\033[1;92m"
    BRIGHT_YELLOW = "\033[1;93m"
    BRIGHT_BLUE   = "\033[1;94m"
    BRIGHT_MAGENTA= "\033[1;95m"
    BRIGHT_CYAN   = "\033[1;96m"
    BRIGHT_WHITE  = "\033[1;97m"

    TITLE = "\033[1;4;97m"

def colour(text, code):
    return code + text + Colour.RESET

class Entity(object):
    """Base class for things which can exist in the world."""

    def __init__(self, name, description=""):
        self.name = name
        self.description = description

    def look(self, viewer):
        if self.description:
            return self.description
        return "You see nothing remarkable about {0}.".format(self.name)


class Item(Entity):
    """An object which may be carried or equipped."""

    def __init__(self, name, description="", wearable=False, worn_where="Head"):
        Entity.__init__(self, name, description)
        self.wearable = wearable
        self.worn_where = "Head"

    def on_equip(self, player):
        pass

    def describe_look_equip(self, player):
        """Describe the item as a piece of equipment when equipped
        """
        if self.wearable:
           return "%s: %s" % (self.name,self.worn_where)
        else:
           return self.name

    def on_unequip(self, player):
        pass

class Room(object):
    """Base class for a location.

    Rooms are code, so subclasses may add arbitrary state and behaviour.
    """

    def __init__(self, room_id, name, description):
        self.room_id = room_id
        self.name = name
        self.description = description
        self.exits = {}
        self.players = []
        self.npcs = []
        self.items = []
        self.lock = threading.RLock()

    def add_exit(self, direction, destination):
        self.exits[direction.lower()] = destination

    def add_npc(self, npc):
        with self.lock:
            if npc not in self.npcs:
                self.npcs.append(npc)
                NPCManager.instance().register(npc)
                npc.room = self

    def remove_npc(self, npc):
        with self.lock:
            if npc in self.npcs:
                self.npcs.remove(npc)
                npc.room = None

    def enter(self, player, announce=True):
        with self.lock:
            if player not in self.players:
                self.players.append(player)

        player.room = self

        for npc in self.npcs:
            npc.on_player_enter(player)

        if announce:
            self.broadcast(
                "* {0} arrives.".format(player.name),
                exclude=player.session
            )

    def leave(self, player, announce=True):
        with self.lock:
            if player in self.players:
                self.players.remove(player)

        for npc in self.npcs:
            npc.on_player_leave(player)

        if announce:
            self.broadcast(
                "* {0} leaves.".format(player.name),
                exclude=player.session
            )

    def broadcast(self, message, exclude=None):
        with self.lock:
            recipients = list(self.players)

        for player in recipients:
            session = player.session
            if session is not None and session is not exclude:
                session.send(message)

    def describe_to(self, player):
        player.session.send("")
        player.session.send(colour(self.name,Colour.TITLE))
#        player.session.send("-" * len(self.name))
        player.session.send(self.description)

        with self.lock:
            other_players = [
                colour(present.name, Colour.BRIGHT_CYAN)
                for present in self.players
                if present is not player
            ]
            item_names = [colour(item.name, Colour.BRIGHT_GREEN) for item in self.items]

            npc_names = [colour(npc.name, Colour.BRIGHT_CYAN) for npc in self.npcs]

        if npc_names:
           player.session.send("People here: {0}".format(", ".join(other_players + npc_names)) ) 
        elif other_players:
             player.session.send("People here: {0}".format(", ".join(other_players)))

        if item_names:
            player.session.send(
                "Objects here: {0}".format(", ".join(item_names))
            )

        if self.exits:
            player.session.send("Exits:")
            for e in self.exits.keys():
                player.session.send("\t %s" % colour(e,Colour.BRIGHT_WHITE))
        else:
            player.session.send("There are no obvious exits.")

    def on_command(self, session, command, arguments):
        """Allow an individual room to handle custom commands.

        Return True when the room handled the command.
        """
        return False

class Player(Entity):
    def __init__(self, name):
        Entity.__init__(self, name, "A mysterious adventurer.")
        self.session = None
        self.room = None
        self.is_admin = False
        self.inventory = []
        self.equipment = {}
        self.fabulousness = 0

    def find_item(self, name):
        wanted = name.strip().lower()

        for item in self.inventory:
            if item.name.lower() == wanted:
                return item

        return None

    def look(self, viewer):
        lines = [colour(self.name, Colour.BRIGHT_CYAN)]

        if self.fabulousness <= -20:
            lines.append(
                "They somehow make a sack of potatoes look glamorous by comparison."
            )

        elif self.fabulousness < 0:
            lines.append(
                "Fashion appears to have lost a fight with reality."
            )

        elif self.fabulousness == 0:
            lines.append(
                "They look perfectly ordinary. Nothing sparkles."
            )

        elif self.fabulousness < 10:
            lines.append(
                "They seem pleasantly well dressed."
            )

        elif self.fabulousness < 20:
            lines.append(
                "There is a definite air of fabulousness about them."
            )

        elif self.fabulousness < 40:
            lines.append(
                "They radiate fabulousness with almost supernatural confidence."
            )

        elif self.fabulousness < 75:
            lines.append(
                "Looking directly at them requires sunglasses."
            )

        elif self.fabulousness < 100:
            lines.append(
                "Nearby rainbows appear to be taking fashion advice from them."
            )

        else:
            lines.append(
                colour(
                    "WARNING: Fabulousness levels have exceeded all known safety limits.",
                    Colour.MAGENTA
                )
            )
            lines.append(
                "Reality itself seems uncertain whether it is fabulous enough to continue existing."
            )

        if self.equipment.items():
            lines.append("Equipment:")
            for k,v in self.equipment.items():
                lines.append("\t%s" % v.describe_look_equip(self))

        if viewer is self:
            lines.append("")
            lines.append(
                "You admire yourself for a moment. Entirely understandable."
            )

        return "\r\n".join(lines)

class Command(object):
    name = None
    aliases = ()
    
    admin_only = False

    def execute(self, session, arguments):
        raise NotImplementedError()


COMMANDS = {}


def register_command(command_class):
    command = command_class()
    names = [command.name]
    names.extend(command.aliases)

    for name in names:
        COMMANDS[name.lower()] = command

    return command_class




class NPCManager(object):
   _instance = None
   def __init__(self):
       self.npcs                  = []
       self.lock                  = threading.RLock()
       self._ticker_thread        = threading.Thread(target=self._run_ticker_thread)
       self._ticker_thread.daemon = True
       self.running               = False

   @classmethod
   def instance(cls):
       if cls._instance is None:
          cls._instance = cls.__new__(cls)
          cls._instance.__init__()
       return cls._instance

   def register(self, npc):
       with self.lock:
            if npc not in self.npcs:
               self.npcs.append(npc)

   def unregister(self, npc):
       with self.lock:
            self.npcs.remove(npc)

   def tick(self):
       with self.lock:
            for npc in list(self.npcs):
                npc.tick()

   def _run_ticker_thread(self):
       while self.running:
          time.sleep(TICK_DELAY)
          self.tick()

   def start(self):
       self.running = True
       self._ticker_thread.start()
   
   def stop(self):
       self.running = False
       self._ticker_thread.join()


class NPC(Entity):
    """A living non-player character."""

    def __init__(self, name, description=""):
        Entity.__init__(self, name, description)

        self.room = None
        self.flags = set()
        self.keywords = []
        self.inventory = []

    def enter(self, room):
        if self.room is not None:
            self.room.remove_npc(self)

        self.room = room
        room.add_npc(self)

    def on_player_enter(self, player):
        """Called when a player enters the room."""
        pass

    def on_player_leave(self, player):
        pass

    def on_say(self, player, text):
        """Player spoke aloud."""
        pass

    def on_emote(self, player, action):
        pass

    def tick(self):
        """Periodic update."""
        pass

    def speak(self, text):
        if self.room:
            self.room.broadcast("<{0}> {1}".format(colour(self.name,Colour.BRIGHT_CYAN), text))

    def emote(self, text):
        if self.room:
            self.room.broadcast("* {0} {1}".format(colour(self.name,Colour.BRIGHT_CYAN), text))


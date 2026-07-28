import threading
import time

TICK_DELAY = 3.0

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

    def __init__(self, name, description="", wearable=False):
        Entity.__init__(self, name, description)
        self.wearable = wearable

    def on_equip(self, player):
        pass

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
        player.session.send(self.name)
        player.session.send("-" * len(self.name))
        player.session.send(self.description)

        with self.lock:
            other_players = [
                present.name
                for present in self.players
                if present is not player
            ]
            item_names = [item.name for item in self.items]

            npc_names = [npc.name for npc in self.npcs]

        if npc_names:
           player.session.send("People here: {0}".format(", ".join(other_players + npc_names)) ) 
        elif other_players:
             player.session.send("People here: {0}".format(", ".join(other_players)))

        if item_names:
            player.session.send(
                "Objects here: {0}".format(", ".join(item_names))
            )

        if self.exits:
            player.session.send(
                "Exits: {0}".format(", ".join(sorted(self.exits.keys())))
            )
        else:
            player.session.send("There are no obvious exits.")

    def on_command(self, session, command, arguments):
        """Allow an individual room to handle custom commands.

        Return True when the room handled the command.
        """
        return False



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
            self.room.broadcast("<{0}> {1}".format(self.name, text))

    def emote(self, text):
        if self.room:
            self.room.broadcast("* {0} {1}".format(self.name, text))


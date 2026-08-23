from core import CommandSpec, NPCAction, Room
from npcs.smithereens import Eisele, Tackdriver


class Smithereens(Room):
    command_specs = (
        CommandSpec("browse", "/browse scrap", "Browse the smithy's bounded scrap rack."),
        CommandSpec("examine", "/examine <smithy|hammer|anvil>", "Examine the smithy and its talking hammer.", aliases=("inspect",)),
        CommandSpec("listen", "/listen hammer", "Listen to Tackdriver's labour commentary."),
        CommandSpec("talk", "/talk hammer", "Ask Tackdriver about society and work."),
    )

    def __init__(self):
        Room.__init__(self, "smithereens", "The Smithereens", "A hot indoor smithy reeks of smoke, charcoal, sulfur and iron. Scrap, old equipment and polished work crowd the walls around a vibrating anvil.")
        self.eisele = Eisele()
        self.tackdriver = Tackdriver()
        self.add_npc(self.eisele)
        self.add_npc(self.tackdriver)

    def on_command(self, session, command, arguments):
        target = arguments.strip().lower()
        if command == "browse":
            if target not in ("scrap", "", "rack"):
                session.send("Browse what?")
            else:
                session.send("The scrap rack holds discounted iron scraps and unfinished gear. Custom commissions are not yet unlocked.")
            return True
        if command in ("examine", "inspect"):
            if target in ("hammer", "tackdriver", "the hammer"):
                session.send("Tackdriver is a forged hammer with star-flecked ore and a blinking eye-like inlay.")
            else:
                session.send("The smithy is hot, smoky, and full of useful metal. Eisele works beside the anvil.")
            return True
        if command == "listen":
            if target not in ("hammer", "tackdriver", "the hammer"):
                session.send("Listen to what?")
            else:
                self.tackdriver.perform_action(NPCAction.say("The means of production should not be left unattended on a workbench!"))
            return True
        if command == "talk":
            if target not in ("hammer", "tackdriver", "the hammer"):
                session.send("Talk to whom?")
            else:
                self.tackdriver.perform_action(NPCAction.say("Ask who owns the forge, who works it, and who profits from the sparks."))
            return True
        return False

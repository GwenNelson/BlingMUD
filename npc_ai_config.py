"""Optional AI wiring kept separate from ordinary world construction."""

from llm_fsm import AdvisoryFSMBehavior
from npc_ai_runtime import NPCAdvisorRuntime
from openrouter_provider import OpenRouterProvider


def configure_world_ai(world, environ=None, directory=".", provider=None):
    environ = {} if environ is None else environ
    enabled = str(environ.get("BLINGMUD_OPENROUTER_ENABLED", "")).lower()
    if enabled not in ("1", "true", "yes"):
        return None
    provider = provider or OpenRouterProvider(directory)
    runtime = NPCAdvisorRuntime(provider, workers=2, queued=16)
    runtime.refresh_catalogue()
    for room_id, attribute in (
        ("crossroads", "knight"),
        ("vals_hella_holler", "val")
    ):
        npc = getattr(world.rooms[room_id], attribute)
        npc.set_behavior(AdvisoryFSMBehavior(npc.behavior, runtime))
    return runtime

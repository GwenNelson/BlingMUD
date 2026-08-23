"""Optional AI wiring kept separate from ordinary world construction."""

import os
import stat

from llm_fsm import AdvisoryFSMBehavior
from npc_ai_runtime import NPCAdvisorRuntime
from openrouter_provider import OpenRouterProvider


MAX_NPC_PROMPT_BYTES = 4096
NPC_PROMPT_FILES = {
    "Brave Sir Knight": "npcs/brave_sir_knight.llm",
    "Val": "npcs/val.llm"
}


def _load_npc_prompt(directory, relative_path):
    path = os.path.join(directory, relative_path)
    try:
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                return None
            encoded = os.read(descriptor, MAX_NPC_PROMPT_BYTES + 1)
        finally:
            os.close(descriptor)
    except OSError:
        return None
    if not encoded or len(encoded) > MAX_NPC_PROMPT_BYTES:
        return None
    try:
        text = encoded.decode("utf-8")
    except UnicodeError:
        return None
    prompt = "\n".join(
        line for line in text.splitlines()
        if not line.lstrip().startswith("#")
    ).strip()
    return prompt or None


def configure_world_ai(world, environ=None, directory=".", provider=None):
    environ = {} if environ is None else environ
    enabled = str(environ.get("BLINGMUD_OPENROUTER_ENABLED", "")).lower()
    if enabled not in ("1", "true", "yes"):
        return None
    provider = provider or OpenRouterProvider(directory)
    npc_prompts = {}
    for npc_name, relative_path in NPC_PROMPT_FILES.items():
        prompt = _load_npc_prompt(directory, relative_path)
        if prompt is not None:
            npc_prompts[npc_name] = prompt
    runtime = NPCAdvisorRuntime(
        provider, workers=2, queued=16, npc_prompts=npc_prompts
    )
    runtime.refresh_catalogue()
    for room_id, attribute in (
        ("crossroads", "knight"),
        ("vals_hella_holler", "val")
    ):
        npc = getattr(world.rooms[room_id], attribute)
        npc.set_behavior(AdvisoryFSMBehavior(npc.behavior, runtime))
    return runtime

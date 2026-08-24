import os
import shutil
import subprocess
import unittest
import xml.etree.ElementTree as ElementTree


REPOSITORY_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE_PATH = os.path.join(REPOSITORY_ROOT, "mudlet", "BlingMUD.xml")


LUA_HARNESS = r'''
local rooms = {}
local hashes = {}
local areas = {}
local handlers = {}
local timers = {}
local sent = {}
local events = {}
local nextRoomID = 100
local nextAreaID = 1
local fallbackSpeedwalkCalled = false

gmcp = {Room = {}}
gmod = {
  enableModule = function(user, module)
    assert(user == "BlingMUD")
    assert(module == "Room")
  end,
  disableModule = function() end,
}
mudlet = {}

function getAreaTable() return areas end
function addAreaName(name)
  local id = nextAreaID
  nextAreaID = nextAreaID + 1
  areas[name] = id
  return id
end
function getRoomIDbyHash(hash) return hashes[hash] or -1 end
function createRoomID()
  local id = nextRoomID
  nextRoomID = nextRoomID + 1
  return id
end
function addRoom(id, area)
  rooms[id] = {area = area, exits = {}, userdata = {}}
  return true
end
function setRoomIDbyHash(id, hash) hashes[hash] = id end
function setRoomCoordinates(id, x, y, z)
  rooms[id].x, rooms[id].y, rooms[id].z = x, y, z
end
function getRoomCoordinates(id)
  local room = rooms[id]
  return room.x, room.y, room.z
end
function setRoomName(id, name) rooms[id].name = name end
function setRoomArea(id, area) rooms[id].area = area end
function setRoomUserData(id, key, value) rooms[id].userdata[key] = value end
function setExit(from, to, direction)
  if to == -1 then
    rooms[from].exits[direction] = nil
  else
    rooms[from].exits[direction] = to
  end
  return true
end
function getRoomExits(id) return rooms[id].exits end
function centerview(id) centered = id end
function updateMap() updated = true end
function registerAnonymousEventHandler(event, callback)
  handlers[event] = callback
  return event
end
function killAnonymousEventHandler() end
function tempTimer(delay, callback)
  if delay == 0 then
    callback()
    return 0
  end
  local id = #timers + 1
  timers[id] = callback
  return id
end
function killTimer(id) timers[id] = nil end
function send(command) sent[#sent + 1] = command end
function raiseEvent(event) events[#events + 1] = event end
function cecho() end
function fallbackSpeedwalk() fallbackSpeedwalkCalled = true end
doSpeedWalk = fallbackSpeedwalk

assert(mudlet.mapper_script == true)
assert(BlingMUD.mapper.version == "1.0.0")

gmcp.Room.Info = {
  num = 1,
  name = "Town Square",
  area = "BlingMUD",
  exits = {n = 2, e = 3},
}
BlingMUD.mapper.onRoomInfo()

local room1 = hashes["BlingMUD:1"]
local room2 = hashes["BlingMUD:2"]
local room3 = hashes["BlingMUD:3"]
assert(room1 and room2 and room3)
assert(centered == room1)
assert(rooms[room1].name == "Town Square")
assert(rooms[room1].exits.n == room2)
assert(rooms[room1].exits.e == room3)
assert(rooms[room2].x == 0 and rooms[room2].y == 1)
assert(rooms[room3].x == 1 and rooms[room3].y == 0)

speedWalkDir = {"north", "e"}
speedWalkPath = {room2, room3}
doSpeedWalk()
assert(sent[1] == "/n")

gmcp.Room.Info = {
  num = 2,
  name = "North Room",
  area = "BlingMUD",
  exits = {s = 1, e = 3},
}
BlingMUD.mapper.onRoomInfo()
assert(sent[2] == "/e")

gmcp.Room.Info = {
  num = 3,
  name = "East Room",
  area = "BlingMUD",
  exits = {w = 2},
}
BlingMUD.mapper.onRoomInfo()
assert(centered == room3)
assert(events[1] == "sysSpeedwalkStarted")
assert(events[#events] == "sysSpeedwalkFinished")

local roomCount = 0
for _ in pairs(rooms) do roomCount = roomCount + 1 end
BlingMUD.mapper.onRoomInfo()
local repeatedCount = 0
for _ in pairs(rooms) do repeatedCount = repeatedCount + 1 end
assert(repeatedCount == roomCount)

local ok = BlingMUD.mapper.updateRoom({
  num = -1,
  name = "Invalid",
  area = "BlingMUD",
  exits = {},
})
assert(ok == false)

BlingMUD.mapper.onUninstall(nil, "BlingMUD")
assert(doSpeedWalk == fallbackSpeedwalk)
'''


class MudletPackageTests(unittest.TestCase):
    def test_package_is_valid_xml_with_one_mapper_script(self):
        tree = ElementTree.parse(PACKAGE_PATH)
        scripts = tree.findall(".//Script/script")

        self.assertEqual(len(scripts), 1)
        self.assertIn("BlingMUD.mapper", scripts[0].text)
        self.assertIn('send("/" .. direction, true)', scripts[0].text)

    @unittest.skipUnless(shutil.which("lua"), "Lua interpreter unavailable")
    def test_mapper_maps_gmcp_immediately_and_speedwalks_with_slashes(self):
        tree = ElementTree.parse(PACKAGE_PATH)
        script = tree.find(".//Script/script").text
        assertion_marker = "assert(mudlet.mapper_script == true)"
        prelude, assertions = LUA_HARNESS.split(assertion_marker, 1)
        completed = subprocess.run(
            ("lua", "-"),
            input=(
                prelude
                + "\n"
                + script
                + "\n"
                + script
                + "\n"
                + assertion_marker
                + assertions
            ),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=5,
            check=False,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)


if __name__ == "__main__":
    unittest.main()

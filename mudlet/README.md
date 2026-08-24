# BlingMUD mapper for Mudlet

`BlingMUD.xml` is the supported Mudlet mapper integration. It consumes the
server's authoritative `Room.Info` GMCP messages instead of trying to infer
rooms from visible text or outgoing commands.

## Install once

1. Open the BlingMUD profile in Mudlet and make sure GMCP is enabled in the
   profile preferences.
2. Open the Package Manager with `Alt+O`, choose **Install New Package**, and
   select `BlingMUD.xml` from this directory. You can also enter this in
   Mudlet, replacing the path with the absolute path to the file:

   ```text
   lua installPackage([[/absolute/path/to/BlingMUD.xml]])
   ```

3. Reconnect if the profile was already connected when the package was
   installed.

The first `Room.Info` message creates the current room, its known exits, and
placeholder destination rooms, then opens or recenters Mudlet's map. There is
no `find prompt`, `map basics`, or `start mapping` step.

The package is a replacement for Mudlet's bundled `generic_mapper` in this
profile. Remove that package, or at least leave its mapping mode stopped, to
avoid duplicate text-derived rooms. The BlingMUD package stops an already
active generic mapping session when it loads.

## Slash-command behavior

Slash commands remain canonical. Typing `/north` (or another supported
direction) updates the map when BlingMUD confirms the destination via GMCP.
Double-click speedwalking is also replaced with a bounded, confirmation-driven
walker that sends `/n`, `/e`, and so on. It waits for the expected
`Room.Info` before sending the next step and stops after three seconds or an
unexpected room change.

To verify the raw server feed independently, enter:

```text
lua display(gmcp.Room.Info)
```

If that table is absent, check that GMCP is enabled and reconnect. The mapper
requests the `Room` module on installation and each connection.

Installing the file is currently a one-time manual profile setup. Automatic
first-time package delivery from the game server requires hosting this exact
package at a stable HTTPS URL and advertising that version and URL through
`Client.GUI`; it should not point at a mutable or private development path.

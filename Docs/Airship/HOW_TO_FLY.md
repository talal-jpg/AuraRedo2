# How to fly the airship

Version 1 (2026-11-22): the controls as first built. The control iterations that follow will change the feel and
update this page.

## Try it

* Map: `/Game/Assets/MyShip/Drivable/Maps/L_AirshipTest` (start platform, walls and a ground plane for cannon and
  crash tests). In any other map, `Aura.Airship.Spawn` (server console) puts a ship 60 m in front of and 15 m above player 0.
* Walk up to the ship and press **F** (gamepad **Y**) within 12 m of the helm or 4 m of the hull to take the helm.
  **F** again leaves it; you are put 2.5 m to port of the helm. Other players can stand and walk on the deck.

## Keys

| Action | Keyboard / mouse | Gamepad |
|---|---|---|
| Throttle (S backs up slowly) | W / S | left stick up / down |
| Steer (the ship banks into the turn) | A / D | left stick left / right |
| Climb / descend (release both to hold altitude) | Space / Left Ctrl or C | right / left trigger |
| Strafe | Q / E | D-pad left / right |
| Boost (uses boost fuel; each start costs 10, forward kick every 1.5 s at most) | Left Shift | A |
| Air brake (also holds a hover); with A/D at speed: drift, with a kick when a long drift ends | X | B |
| Fire both cannons on the side the camera faces (1.5 s reload per side) | left mouse | RB |
| Tighter aim view | right mouse | LB |
| Look around (the camera recentres after 1.5 s without look input above 8 m/s) | mouse | right stick |
| Zoom the camera between 40 and 120 m | mouse wheel | D-pad up / down |
| Leave the helm | F | Y |

Cannons turn up to 20 degrees left and right and aim from -10 to +8.5 degrees of elevation. The HUD shows hull health,
boost fuel, speed, ALT (height above the ground) and the PORT / STBD reload.

## Server console commands (not in shipping builds)

`Aura.Airship.Spawn`, `Aura.Airship.Board [player]` / `Exit [player]`, `Damage <n>`, `Kill`, `Set <name> <value>` /
`Get <name>` (any ship property by name), `Input <throttle> <steer> [lift] [strafe] [boost] [brake]` / `InputClear`, `Telemetry`, `Passengers`, `Debug 1` (force and contact drawing), `RepMode`.
`Docs/Airship/CPP_NOTES.md` section 6 lists the arguments.

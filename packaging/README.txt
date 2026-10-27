LTH Overlays 0.5
================

In-house iRacing overlays for the LTH community. 27 widgets, all set up from one Control
Center window: Standings, Relative, Battle analysis, Lap history, Delta bar, Session,
Race engineer, Flags, Radar, Pit helper, Pit window, Incidents, Stint, Formation, Radio,
Fuel, Dash, Inputs, G-force, Tyres, Car setting changes, Engine warnings, Track map,
Weather, Rain Master, Connection and Performance.

Start
-----
1. Extract the whole zip to a folder (for example Documents\LTH Overlays).
   Do not run the .exe from inside the zip.
2. Run "LTH Overlays.exe". The Control Center opens with a short tutorial (pick a
   starting layout: Simple, Single monitor or Triple monitor) and the LTH icon appears
   next to the clock. On the first run the app adds itself to the Windows startup list, so it
   starts quietly with Windows and sleeps until iRacing is running.
   Turn this off in Control Center > General > Start with Windows.
3. Start iRacing. Overlays appear whenever iRacing is running: on track, in a replay,
   or spectating. Closing the Control Center does not stop the overlays. Click the
   L icon to open it again. "Quit LTH Overlays" is in the tray menu and at the bottom
   of the Control Center.

IMPORTANT: run iRacing in "Borderless window" or "Windowed" mode.
In exclusive fullscreen no overlay program can draw on top of iRacing.

Updating
--------
Quit the old version first (tray icon > Quit), then extract the new zip over the old
folder or into a new one. Your layout and settings are kept (they live in
%APPDATA%\LTH Overlays). New widgets start switched off.

Control Center
--------------
- Widgets: switch widgets on or off, search, click one for all its settings with a live
  preview. Everything applies immediately.
- Layout: all your monitors in small. Drag widgets to move them (also from one monitor
  to another), drag the corner or the edges to resize, arrows nudge by 1 px (Shift: 10 px).
  Double-click opens the settings. "Presets" gives ready layouts for one or three screens.
- Profiles: separate layouts for Race, Qualifying and Practice (switch automatically),
  plus your own. "Share" gives a short code to paste in Discord, or a .lthlayout file.
  Others use "Import layout" (or drop the file on the Control Center). It is added as a
  new profile and scaled to their screen.
- Appearance: 10 themes (incl. LTH), 19 fonts, single colours and car class colours.
- Hotkeys, General (startup, timing, track maps), Performance, Diagnostics.

On screen
---------
Ctrl+Shift+E turns edit mode on or off (also the "Edit layout" button):
- drag a widget to move it; it snaps to screen edges and other widgets;
- drag a corner to scale the whole widget;
- drag the left / right edge to change the width;
- drag the top / bottom edge to change the height. Tables (Standings, Relative,
  Lap history) then show as many rows as fit. Double-click: automatic height again;
- Ctrl + mouse wheel changes the size;
- click the Settings button on a widget (or right-click it) to open its settings;
- the bar at the top of the screen has Done and Control Center buttons.
Press Ctrl+Shift+E again to lock the layout. The mouse then passes through the
overlays to iRacing, and they never take keyboard focus.
Ctrl+Shift+H hides or shows all overlays at once.
Ctrl+Shift+R shows the next Rain Master tip. All hotkeys can be changed (Control Center >
Hotkeys).

Rain Master: short calls above the Weather widget when conditions change (WET TYRES,
HIDDEN WATER, PUDDLES ON TRACK...) and a Rain Master widget with the explanation while
driving and the full list of tips for the current conditions when you stop. Tips by
Regis / LTH Racing. The iRacing rain model changes every season, so track-specific tips
may not always match.

Standings in multiclass races show your class in full (or Top N + around you) and the
top 3 of every other class. Change both in Widgets > Standings.

Track map: the outline is recorded from your first clean lap on a track and saved, so
from then on it is there from the start. Until then cars are shown on a circle.

Windows "protected your PC" message
-----------------------------------
This build is not code-signed yet, so Windows SmartScreen may show
"Windows protected your PC" the first time. Click "More info" > "Run anyway".
It only happens once per version. The program needs no administrator rights and does
not download anything. The only thing it writes outside its own folder is your
settings (%APPDATA%\LTH Overlays) and, if "Start with Windows" is on, one standard
entry in the Windows startup list (HKEY_CURRENT_USER\...\Run, the same place Discord or
Steam use). Older versions used a small script in the Startup folder; 0.4 removes it.

Diagnostics (if gaps look wrong)
--------------------------------
Run "LTH Diagnostics.exe" (or Control Center > Diagnostics) while you are in an iRacing
session. It records 10 minutes of timing data (Ctrl+C stops earlier) and writes
lth_recording_<date>.npz and a .txt report next to the program.
Send both files to the LTH team.

Performance
-----------
Control Center > Performance shows the overlay's own CPU and RAM use. The timing engine
runs at 20 Hz, widgets only redraw when a number they show changes, each widget has its
own refresh rate, and the process runs at "Below normal" priority so iRacing always comes
first. Inputs (and Dash / Delta bar with "Smooth" on) draw straight from telemetry at up
to 60 fps; turn Smooth off or pick 30 fps on a slower PC.

Fonts: Inter, Montserrat, Saira, Barlow, Oswald, Roboto Condensed, Archivo Narrow,
IBM Plex Sans Condensed, Teko, Exo 2, Titillium Web, Kanit, Space Grotesk, Russo One,
Rajdhani, Chakra Petch, JetBrains Mono (SIL Open Font License, see
app\lth_overlays\data\fonts and app\lth_overlays\data\ui).

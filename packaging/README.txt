LTH Overlays 0.6.2
==================

In-house iRacing overlays for the LTH community. 35 widgets, all set up from one Control
Center window: Standings, Relative, Battle analysis, Lap history, Delta bar, Lap timer,
Sectors, Session, Race engineer, Flags, Radar, Overtake alert, Rejoin indicator,
Pit helper, Pit commands, Pit window, Incidents, Stint, Formation, Radio, Fuel, Dash,
Inputs, G-force, Tyres, Car setting changes, Engine warnings, Track map, Flat track map,
Weather, Rain Master, Garage cover, Stream chat, Connection and Performance.

New in 0.6.2
------------
- Inputs: the traces no longer flicker on sharp inputs, the brake line stays yellow exactly
  where ABS worked, new GT3-style wheel with a red centre mark (turns the right way) and a
  big speed readout under it. Scales with the widget size on any monitor.
- Telemetry: every practice / qualifying / race is saved automatically (last 50 sessions)
  and can be opened again from "Session". Drag across the graphs to zoom into a corner
  (like Garage61) or click a corner on the track map. ABS shown on its own strip and as an
  orange background on the brake graph.
- Weather: humidity and track usage (rubber at the start of the session, as iRacing reports
  it: words plus level of 5), bigger classic compass (north up, wind arrow, your heading).
- New Overview dashboard: laps and time this month, latest session, most driven car, laps
  per day this week.
- Records page: your all-time best lap per car and track, open it in Telemetry.
- Setups page: import LTH setup packs (.zip) and install them into
  Documents\iRacing\setups\<car>\LTH automatically when you join a session.
- Drivers: optional one-click lists for the LTH team and the Lithuanian iRacing Hub.
- Notifications in the Control Center (new personal best, setups installed).

New in 0.6.1
------------
- Fix: in practice and qualifying, drivers who went back to the garage dropped to the bottom
  of Standings (iRacing clears their best lap in telemetry). Their best lap is now kept.
- Fix: telemetry no longer drops the lap being recorded when iRacing updates session info.
- Less CPU: smooth widgets slow down to 12 fps while you stand still (garage, pits, after the
  finish), Inputs and track maps draw faster, Eco mode (Performance page) caps all smooth
  widgets at 30 or 20 fps, and the Performance page shows what each widget costs.
- Fuel strategy widget: stops needed, pit window (earliest / latest lap), fuel to add, and
  how much to save per lap to make it with one stop less. In timed races the laps to go
  follow the overall leader's pace; caution laps are left out of fuel per lap.
- Relative: Last lap and Best lap columns. Column titles are on by default.
- Blue flags: blue rows in Standings / Relative, blue ring on track maps. Friends' colours
  on track maps.
- Inputs: optional ABS light.
- Telemetry: separate graphs for throttle and brake, one colour per lap, more space
  between graphs, and a track map that shows where you are on the lap (green / red where
  lap B gains or loses). Exported laps include the track outline.
- OBS link and Copy button on every widget's page.
- "Start with Windows" is now chosen in the tutorial instead of being switched on
  silently on the first run.

New in 0.6
----------
- Standings / Relative: country flags, coloured licences, car model, status badges
  (PIT, OUT, BLUE, black flag...), optional column titles, projected iRating change,
  a header and footer bar where you pick what to show (SOF, temperatures, time left...),
  a coloured border while a flag is out, compact row heights. Narrower by default.
- Outline (stroke) around every widget: Appearance > Outline, or per widget.
- Inputs: speed, gear, a turning steering wheel and pedal percentages.
- Pit commands: click to select all tyres, fuel to the finish, fast repair, windscreen.
  No black box needed. Works only while iRacing is running on this PC.
- Smooth track map (30 or 60 fps) and a new Flat track map.
- Lap timer with your all-time personal best per car and track, Sectors (purple = new
  best), Overtake alert (faster class from behind), Rejoin indicator, incident limit taken
  from the session.
- Telemetry page: session report (lap chart, consistency, fuel) and lap-against-lap
  graphs (speed, pedals, steering, gear, time delta). Export a lap as a .lthlap file and
  send it to a friend; they open it with "Import lap" and compare it with theirs.
- Stream page: every widget as an OBS browser source, and a Stream chat widget for
  Twitch and YouTube.
- Drivers page: tag friends, teammates, rivals. Their names get your colour.
- Hotkeys for every widget and for "Next profile". Each widget can be limited to
  Practice / Qualifying / Race sessions. Garage cover hides your setup on stream.
- 14 more fonts (33 in total).

Start
-----
1. Extract the whole zip to a folder (for example Documents\LTH Overlays).
   Do not run the .exe from inside the zip.
2. Run "LTH Overlays.exe". The Control Center opens with a short tutorial (pick a
   starting layout: Simple, Single monitor or Triple monitor) and the LTH icon appears
   next to the clock. The last tutorial step asks whether to start with Windows (then it
   starts quietly and sleeps until iRacing is running). Change it any time in
   Control Center > General > Start with Windows.
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
- Appearance: 10 themes (incl. LTH), 33 fonts, outline, single colours and car class colours.
- Drivers: tag friends / teammates / rivals (by iRacing ID or from the current session), or add
  the LTH team / Lithuanian iRacing Hub lists in one click.
- Records and Setups: personal bests, LTH setup packs.
- Telemetry: session report and lap comparison, import / export .lthlap files.
- Stream: OBS browser source URLs (Copy button for each widget or the whole layout).
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

OBS
---
Control Center > Stream > Enable. Then in OBS: Sources > + > Browser, paste a URL.
"Whole layout" URLs: set the source to your monitor resolution (for example 1920 x 1080).
The server listens on 127.0.0.1 only, so nothing outside this PC can reach it.
Add ?demo=1 to a URL to see sample data while iRacing is closed.

Stream chat
-----------
Widgets > Stream chat: enter your Twitch channel and / or your YouTube live link or
@channel. Read-only, no login. Twitch uses its official anonymous chat. YouTube has no
key-free official way, so it reads the same chat feed as the youtube.com pop-out chat;
if YouTube changes it, the widget shows "YouTube: error" until the next update.

Telemetry files
---------------
Your best lap per car and track is saved automatically in
%APPDATA%\LTH Overlays\laps. Laps are recorded only for your own car while you drive
(30 Hz, or 60 Hz in Telemetry settings). A .lthlap file is a small zip (about 40 KB)
with the lap data. It contains no code.

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

Fonts: Inter, Geist, Manrope, Outfit, Sora, Figtree, Plus Jakarta Sans, Red Hat Display,
Rubik, Montserrat, Space Grotesk, Kanit, Titillium Web, Saira, Barlow, Chivo, Oswald,
Roboto Condensed, Archivo Narrow, IBM Plex Sans Condensed, Teko, Sofia Sans, Encode Sans,
Exo 2, Russo One, Rajdhani, Chakra Petch, Oxanium, JetBrains Mono (SIL Open Font License,
see app\lth_overlays\data\fonts and app\lth_overlays\data\ui).
Country flags: flag-icons by Lipis (MIT). FlairID to country table based on irDashies (MIT).

LTH Overlays
============

iRacing overlays by LTH: Standings (whole field), Relative (cars ahead and behind with
closing delta, iRating, license) and Weather. Race engineer messages are available but
off by default (tray icon > Engineer).

Start
-----
1. Extract the whole zip to a folder (for example Documents\LTH Overlays).
   Do not run the .exe from inside the zip.
2. Run "LTH Overlays.exe" once. An "L" icon appears next to the clock. On the first run
   it sets itself to start with Windows and then sleeps until iRacing is launched, so you
   never have to start it by hand. Turn this off in the tray menu: "Start with Windows".
3. Start iRacing. Overlays appear whenever iRacing is running - on track, in a replay,
   or spectating / watching an event. Optionally hide them while your own car is in
   the garage (right-click a widget in edit mode > General > Hide when my own car is
   in the garage).
   If something is not shown, send %APPDATA%\LTH Overlays\visibility.log to the LTH team.

IMPORTANT: run iRacing in "Borderless window" or "Windowed" mode.
In exclusive fullscreen no overlay program can draw on top of iRacing.

Edit the layout
---------------
Ctrl+Shift+E (or right-click the L icon > Edit layout):
- drag a widget to move it, drag the corner to change its width;
- Ctrl + mouse wheel changes the size;
- right-click a widget opens its settings (columns, filters, opacity, theme, font).
Press Ctrl+Shift+E again to lock the layout. The mouse then passes through the
overlays to iRacing, and they never take keyboard focus.

Profiles: the layout switches automatically between Race, Qualifying and
Practice. Settings are stored in %APPDATA%\LTH Overlays\config.json.

Windows "protected your PC" message
-----------------------------------
This build is not yet code-signed, so Windows SmartScreen may show
"Windows protected your PC" the first time. Click "More info" > "Run anyway".
It only happens once per version. The program needs no administrator rights,
writes nothing to the registry and does not download anything.

Diagnostics (if gaps look wrong)
--------------------------------
Run "LTH Diagnostics.exe" while you are in an iRacing session. It records
10 minutes of timing data (Ctrl+C stops earlier) and writes
lth_recording_<date>.npz and a .txt report next to the program.
Send both files to the LTH team.

Performance
-----------
Right-click the L icon > Performance shows the overlay's own CPU and RAM use.
The timing engine runs at 20 Hz, the widgets only redraw when a number changes,
and the process runs at "Below normal" priority so iRacing always comes first.

Look: the default theme is a modern dark style with the Montserrat font (Settings > Theme / Font
to switch back to the older LTH styles). Tray icon > "Save preview image" writes preview.png
to %APPDATA%\LTH Overlays.

Fonts: Montserrat, Saira Condensed, Barlow Condensed, Rajdhani, Chakra Petch
(SIL Open Font License, see app\lth_overlays\data\fonts).

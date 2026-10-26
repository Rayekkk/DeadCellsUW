Dead Cells Ultrawide (21:9)
===========================

Removes the black bars on 21:9 monitors: the game really shows more of the world (up to 960 game pixels
horizontally instead of 683). Nothing changes on 16:9.

Unofficial fan mod, not affiliated with or endorsed by Motion Twin or Evil Empire.
Source code: https://github.com/Rayekkk/DeadCellsUW

INSTALL
  Close the game and run Install.bat. It finds the game in your Steam libraries automatically.
  Other location:  Install.bat "D:\path\to\Dead Cells"
  (You can also copy this whole folder into the game folder and run Install.bat there.)

UNINSTALL
  Uninstall.bat

HOW IT WORKS
  deadcells.exe is not modified (it is Steam-DRM protected), so Steam and achievements work normally.
  The installer renames the original libhl.dll to libhl_orig.dll and puts libhl_uw.dll in its place.
  At game start it changes one value of the game code in memory and writes the result to dc_ultrawide.log.

NOTES
  - Do not copy libhl.dll alone to another PC: without libhl_orig.dll the game will not start. Use Install.bat.
  - After a game update or "Verify integrity of game files" in Steam the mod may be disabled: run Install.bat again.
  - If the game does not start after an update, run Uninstall.bat (or verify the game files in Steam).
  - A wider view is a small advantage in the Daily Challenge, which has online leaderboards.

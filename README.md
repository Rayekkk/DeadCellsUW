# Dead Cells Ultrawide (21:9)

Real 21:9 support for **Dead Cells**: the black bars on the sides are gone and the game actually renders more of the world, not a stretched picture.

> Unofficial fan mod. Not affiliated with or endorsed by Motion Twin or Evil Empire. No game files are included.

## Install

1. Download `DeadCellsUltrawide-v0.1.zip` from [Releases](https://github.com/Rayekkk/DeadCellsUW/releases) and unzip it anywhere.
2. Close the game and run **`Install.bat`**. It finds Dead Cells in your Steam libraries automatically.
   For a different location: `Install.bat "D:\path\to\Dead Cells"`.
3. Start the game normally from Steam.

To remove the mod, run **`Uninstall.bat`**.

## How it works

The game sets the stage width to `min(window width, pixelScale × Viewport.NATIVE_WIDTH)` and paints the rest of the screen black. `NATIVE_WIDTH` is 683 game pixels, slightly wider than 16:9, so on a 21:9 screen you get black bars. The mod raises it to 960, which covers any 21:9 resolution. On 16:9 it changes nothing, because the window width is the limit there.

The rest of the engine (camera, culling, parallax, cutscenes) already derives its size from the stage width, so it adapts on its own. Older shader-based fixes stretched sprites at the screen edges instead; this one doesn't.

`deadcells.exe` is protected by Steam DRM, so it is **never modified**. Instead:

- `libhl.dll` (HashLink runtime) is replaced by a small proxy (`libhl_uw.dll`). The original is kept as `libhl_orig.dll`, and all exports are forwarded to it.
- When the game calls `hl_global_init` at startup (after the DRM check, before the bytecode is loaded), the proxy finds the `Int` op that initialises `Viewport.NATIVE_WIDTH` in the embedded HashLink bytecode and points it at the value 960. That is a 2-byte change, in memory only.
- The result is written to `dc_ultrawide.log` in the game folder. If the code can't be found (for example after a game update), nothing is patched and the game runs normally with bars.

Steam, achievements and saves are untouched.

## Notes

- Don't copy `libhl.dll` alone to another PC; the game won't start without `libhl_orig.dll`. Use `Install.bat`.
- After "Verify integrity of game files" or an update that replaces `libhl.dll`, run `Install.bat` again.
- If the game fails to start after an update, run `Uninstall.bat` (or verify the game files in Steam).
- The wider view gives a small advantage in the Daily Challenge, which has online leaderboards.
- Some antivirus tools flag DLLs that patch game memory. The full source is here, so you can build it yourself.
- Tested on the Steam version (DirectX and OpenGL builds, game build from 2026-06).

## Building from source

Requirements: Windows, Python 3, and the MinGW-w64 GNU toolchain (`gcc`, `ld`, `dlltool`) with i386 support. The game is 32-bit. MSVC's x86 linker doesn't work here because it rejects `.def` export forwarders.

```bat
cd patcher
python build_proxy.py "<game dir>\libhl_orig.dll"   :: or libhl.dll if the mod is not installed
python test_scanner.py "<game dir>"
```

- `patcher/proxy/libhl_proxy.c`: the proxy, with no C runtime and only kernel32. Builds to `release/libhl_uw.dll`.
- `patcher/build_proxy.py`: generates the forwarding `.def` from the real `libhl.dll` and builds the proxy.
- `patcher/hlparse.py`: a minimal HashLink bytecode (v4) reader.
- `patcher/test_scanner.py`: checks that the proxy's byte-pattern scan finds the same op as a full by-name bytecode parse, for both exes, and that already-patched bytecode is left alone.
- `release/`: the installer (`Install.bat`, `Uninstall.bat`, `dcuw.ps1`) and the user README.

## License

[MIT](LICENSE)

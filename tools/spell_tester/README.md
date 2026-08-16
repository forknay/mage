# spell_tester

A drawing pad for the spell recognizer that runs without Godot, so a template
or spell can be tried in seconds instead of a build-and-play cycle.

```powershell
.\run.ps1
```

That compiles the tester if needed, starts it, and opens
<http://127.0.0.1:8770/>. Drag on the pad to draw a stroke; recognition runs
when the stroke ends. Each recognised feature is named where it sits on the
canvas and listed with its score in the panel, and the matched spell (if any)
is shown above the list. `C` or the button clears. Ctrl+C in the console stops
the server.

## It is the same engine

There is no second implementation here to drift out of sync:

- it compiles `mage-godot/scripts/spell_engine/*.cpp` directly -- the same
  files Jenova builds into the game;
- it loads `mage-godot/assets/spell_engine/templates/*.json` and `spells/*.json`
  through the same loader, from the same folders, which is why the tester has
  to run with the Godot project as its working directory (it finds and moves
  there itself);
- the page samples the pen with the same 4px minimum spacing and drops
  one-point strokes, like `GlyphCanvas` does, and its canvas is 800x800 to
  match `GlyphPlane.CANVAS_SIZE`.

So a shape that recognises here recognises in game. Edit a template JSON,
restart the tester, and the change is live -- templates and spells are read
once at startup.

The browser is only a pen and a screen: every recognition decision is made by
the C++ engine, reached over a tiny local HTTP server (`POST /stroke` with one
`x y` pair per line, `POST /clear`, `GET /state`). It binds to 127.0.0.1 only.
Editing `page.html` needs only a browser refresh, since the page is read from
disk per request; changing `main.cpp` or the engine needs `run.ps1` again.

## What it needs

`g++` on PATH (`scoop install gcc`), or MSVC. The build script prefers g++ and
falls back to the compiler Jenova ships in `mage-godot/Jenova/Packages/`, or a
`cl.exe` on PATH -- note that `Jenova/` is gitignored, so on a fresh clone the
MSVC path only works if you have Visual Studio's C++ tools installed.

## The two files that are not shared

- `shim/JenovaSDK.h` -- `recognizer.cpp` and `spell_engine.cpp` log through
  `jenova::sdk::Output`, which only exists inside Godot. The shim goes first on
  the include path and sends those lines to the console instead. Nothing else
  from the Jenova SDK is used by the engine sources, and the one file that
  genuinely needs it (`godot_spell_engine.cpp`, the GDScript binding) is not
  part of this build.
- `main.cpp` / `page.html` -- the server and the pad, which exist nowhere else.

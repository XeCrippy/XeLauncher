# XeLauncher

An Xbox 360 game launcher for your wrist. Pin the games you play, tap one, the
console boots it. Part of the Solace 360 family of standalone apps — small,
single-purpose, and sized for screens a desktop tool was never meant for.

Built with Flet for **Wear OS**, and it scales up cleanly on a phone.

---

## What it does

| | |
|---|---|
| **Pinned games** | A home screen of starred titles, one tap each. Long-press to reorder or unpin. |
| **Browse the console** | Drives → folders → games, the real structure exactly as the console has it. Every folder is shown; files are filtered to `.xex`, `.xbe` and `.exe`. Star anything to pin it home. |
| **Filter a folder** | The magnifier opens a filter panel: a row of the letters actually present in that folder, plus typing. Tap **S** to see only the S games. On a watch, typing opens a full-screen keypad the app draws itself — no system keyboard involved. |
| **Readable names** | Folders named as a title ID show the game (`4D5307E6` → *Halo 3*), and scene noise (`Halo.3.NTSC`, `[USA]`) is tidied off. |
| **Box art** | Covers on pinned games and game rows. The title ID is read straight out of the XEX header, so a folder called `BF3` still finds *Battlefield 3*. Cached on disk; switch it off in Settings if you would rather it never touched the internet. |
| **Campaign & multiplayer** | A folder with several entry points (`default.xex` + `default_mp.xex`, as every Call of Duty has) labels them "Campaign" and "Multiplayer" instead of two identical rows. |
| **Multiple executables** | In a folder of dev builds the row leads with the executable name, and the launch confirmation always names the exact file and folder. |
| **Console power** | Return to dashboard, cold reboot, and what is running right now. Shutdown too, where the console has an SRPC or JRPC2 plugin. |
| **Finding the console** | Auto-sweeps the Wi-Fi subnet on first run; remembers the address afterwards. Manual IP entry as a fallback. |

It talks **stock xbdm** — `dirlist`, `drivelist`, `dbgname`, `xbeinfo`,
`getfile`, `magicboot`. No memory access, no custom plugin. If your console has
a debug monitor, this works.

The single exception is **Shutdown**, which sends `consolefeatures` and so needs
an SRPC or JRPC2 plugin on the console. Everything else — browsing, launching,
dashboard, reboot, box art — is stock xbdm, and Shutdown simply reports an error
where the plugin is absent.

---

## Requirements

- An RGH/JTAG Xbox 360 with xbdm running (port 730)
- **The watch must be on the same Wi-Fi as the console.** This matters more than
  it sounds: a Wear OS watch tethered to a phone over Bluetooth proxies
  *internet* traffic through the phone, but cannot reach other devices on the
  local network. Turn on the watch's own Wi-Fi.
- Python 3.10+ and `flet==0.84.0` to run it on a desktop
- To build the APK, additionally the Flutter SDK, the Android SDK and a JDK —
  `flet build apk` drives Flutter, and will tell you which piece is missing

---

## Running it on a desktop first

```bash
cd XeLauncher
pip install -e ".[dev]"
flet run
```

The desktop window opens at **240×240** — deliberately, so what you see is the
watch layout. For the phone layout:

```bash
XELAUNCHER_PREVIEW=phone flet run     # PowerShell: $env:XELAUNCHER_PREVIEW="phone"; flet run
```

## Checking it still works

```bash
python tests/run_all.py
```

No pytest, no console, no network — the suites stub xbdm and Flet's page, then
build every screen at watch and phone sizes, drive the connect state machine,
and walk a fake drive. Worth running before `flet build apk`, where a typo costs
a ten minute rebuild and a sideload to discover.

## Building for Wear OS

```bash
flet build apk
```

The APK lands in `build/apk/`, named after `[tool.flet] product` — so
`build/apk/XeLauncher.apk`. Then install it on the watch over ADB:

```bash
# On the watch: Settings → Developer options → enable "ADB debugging"
#               and "Debug over Wi-Fi" (note the IP it shows)
adb connect 192.168.1.x:5555
adb install build/apk/XeLauncher.apk
```

That APK is debug-signed, which is enough to sideload onto your own watch. To
hand it to anyone else, zipalign and sign it with your own key:

```bash
keytool -genkey -v -keystore my-release.keystore -keyalg RSA \
        -keysize 2048 -validity 10000 -alias my-alias
zipalign -f 4 build/apk/XeLauncher.apk build/apk/aligned.apk
apksigner sign --ks my-release.keystore --ks-key-alias my-alias \
        --out build/apk/XeLauncher-signed.apk build/apk/aligned.apk
```

The app appears in the Wear OS launcher because `pyproject.toml` declares
`android.hardware.type.watch`. It is declared as *optional*, so the same APK
installs on a phone too — set it to `true` for a watch-only build.

---

## How it is put together

```
src/
├── main.py              entry point, three lines
├── xbdm/                the console protocol
│   ├── client.py          the 5 commands a launcher needs
│   ├── connection.py      buffered TCP socket
│   ├── discovery.py       subnet sweep, reports hits as they land
│   ├── protocol.py        status-line parsing
│   └── exceptions.py      errors, each with wrist-sized wording
├── core/
│   ├── session.py         the live connection; screens never see xbdm
│   ├── store.py           one JSON file: host, favourites, preferences
│   ├── library.py         directory listing, filtering and row labels
│   ├── titles.py          folder name → readable game name
│   └── title_ids.py       title ID → game name database
└── ui/
    ├── shell.py           app context, view-stack navigation
    ├── theme.py           palette and every size, resolved per screen width
    ├── widgets.py         tile, list, header, overlays
    ├── actions.py         launch / pin, shared between screens
    └── screens/           connect, home, browse, console, settings
```

**Screens are functions.** `view(app)` returns a control; `app` carries the
page, the store, the session and navigation. Console I/O runs on worker threads
via `app.run_bg()` and comes back through `app.on_ui()`; nothing touches a
control from a worker.

**Navigation is a stack of Flet views**, which is what makes Wear OS
swipe-to-dismiss and the Android back button behave natively instead of doing
nothing. Two invariants keep the Flutter navigator and `App.stack` in
agreement, and breaking either leaves an invisible route on top that swallows
every tap:

1. **Every view gets a unique route.** Flet resolves a pop by matching
   `View.route`, so three folders deep — all of them `/browse` — it matches the
   wrong view. Routes are `/browse/1`, `/browse/2`, …
2. **A pushed view is never swapped out.** Refreshing replaces its *controls*,
   so the route keeps its identity and Flutter is only ever asked to push or
   pop.

**Text input on Wear OS is not to be trusted.** Two rules, both learned the
hard way:

- **Never focus a field from code**, and never `autofocus`. On Wear OS a
  programmatically focused field takes the cursor without raising the IME — and
  because it is *already* focused, tapping it will not raise the IME either,
  leaving no way to type at all. Only the user's own tap reliably produces a
  keyboard.
- **Build each field once per screen and reuse it** across repaints. A fresh
  `TextField` per keystroke is a different widget to Flutter, so focus drops
  and the keyboard closes after the first character.

And since some watches raise no keyboard whatever you do, **the watch never
uses an inline field at all**. Tapping the filter opens `widgets.keypad()` — a
full-screen input surface that owns its own keys and hands the text back only
on Done. This is the shape Wear OS apps use for search (press search, get a
dedicated input screen) with one difference: the platform's own apps launch the
system input activity, which is a native intent Flet cannot start, so the keys
are drawn here instead. The letter picker sits alongside it for the common case
of "show me the S games", which needs no typing at all.

Anything wider than a watch keeps a real `TextField`, where the system IME
behaves normally.

### Design notes for a 200px screen

- One column, one action per row, 50px tiles — nothing smaller than a fingertip.
- Round faces clip corners, so watch mode pads the sides by a tenth of the width
  and gives the first and last list item extra room. Toggle it off in Settings
  for a square watch.
- Pure black background: nearly every Wear OS panel is OLED, and black pixels
  are switched-off pixels.
- Prompts are full-screen overlays, not Material dialogs. A dialog on a watch is
  a postage stamp with a scrollbar.
- **The real folder structure, filtered — not a clever index.** An earlier
  build swept every drive and shelved the results by folder. It looked tidy and
  it was worse: minutes to run, a depth limit, a list of folders it guessed
  were uninteresting, and a "one primary executable per folder" rule that
  quietly hid files the user owned — every Call of Duty's multiplayer, and any
  `.exe` sitting beside a `default.xex`. Browsing has none of those failure
  modes. One `dirlist` per screen, and the only filter is the file extension,
  so nothing can be hidden by a heuristic because there is no heuristic.
- Listings are cached per path for the session, so walking back up the tree is
  instant. The header's refresh button re-reads the folder from the console.

---

## Known limits

- **Installed/GOD titles cannot be launched.** They live under `HDD:\Content` as
  containers `magicboot` has no way to start. The folder is fully browsable —
  nothing is hidden — but it holds no `.xex` to tap, so it reads as "nothing to
  launch here". Disc-extracted games in `\games` work normally.
- **The filter is per-folder, not console-wide.** It narrows what is already on
  screen; it does not search other folders, because that would mean walking
  every drive over the network for each keystroke. Pinning is the answer to
  "where was that game again": browse once, star it, launch from home after.
- **Settings live wherever the platform allows.** The store proves a directory
  writable before using it, prefers wherever a settings file already exists,
  and reports the path under Settings › Storage. If a save ever fails you get
  a warning rather than a favourite that quietly disappears.
- **xbdm allows only a handful of connections.** If another tool is also
  connected to the console you may see "Too many apps connected to the
  console" — close one.
- After a launch the console tears down every xbdm socket as it switches titles.
  That is expected; the app reconnects on the next command.

---

## How box art works

Two lookups, each cached so a game only ever pays once:

1. **Path → title ID.** `getfile name="…" offset=… size=…` reads a few hundred
   bytes of the game's XEX header, finds optional header `0x00040006`
   (execution info), and takes the title ID 12 bytes in. Two ranged reads,
   about half a kilobyte — not the 20 MB executable. Matching folder names
   against the title database instead only resolves about half a real console
   (scene folders are abbreviated, misspelled, full of extra words), and gets
   the wrong game often enough to be worse than nothing.
2. **Title ID → cover.** `image.xboxlive.com/global/t.<ID>/icon/0/8000`, a
   64×64 PNG. The old `download.xboxlive.com/.../boxartlg.jpg` box art path is
   long dead; this one still answers.

Covers land in `art/` beside the settings, with an `ids.json` recording both
successes and failures — a title with no cover is asked about once, not on
every repaint. Lookups run on one background worker, strictly serial, because
every title ID costs a round trip on the single xbdm socket and browsing must
stay ahead of decoration.

Covers appear on **games, never folders**. Flet resolves a string `src`
against the bundled assets directory, which is read-only in an APK, so the
bytes have to travel inline — fine for the handful of rows in a game folder,
not for a 200-row folder listing.

---

## Roadmap ideas

- **A Wear OS Tile / complication for the top pinned game.** Not reachable from
  Flet: a Tile is a Kotlin `TileService` plus manifest entries and a
  `androidx.wear.tiles` dependency, rendered with ProtoLayout rather than
  Flutter. `flet build apk` regenerates the Android project each build and
  offers no hook for native sources, so this needs either a forked build
  template or a patch-and-gradle step outside `flet build`.
- **Rotary bezel scrolling.** Needs native Android, like the Tile above. Wear OS
  reports a bezel or crown as a rotary-encoder *motion* event, which reaches an
  Activity's `onGenericMotionEvent` — not something Flet can hook. Handling it
  as a key press does nothing on a real watch.
- Recently launched, alongside pinned
- Covers on folder rows (needs a thumbnail atlas, or Flet gaining a file-path
  image source)

---

## License

[GNU General Public License v3.0 or later](LICENSE).

You may use, study, share and modify this program freely. If you distribute a
modified version, it has to stay under the GPL and ship its source too.

The title database in `src/core/title_ids.py` is community-collected Xbox 360
title ID data. Xbox and Xbox 360 are trademarks of Microsoft; this project is
not affiliated with or endorsed by Microsoft.

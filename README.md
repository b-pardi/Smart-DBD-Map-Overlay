# DBD Smart Map Overlay

A Dead by Daylight map overlay that give you call outs so you can stop fumbling callouts. 

It watches for the map name on the Tab scoreboard, and only when you actually press Tab, then drops the matching community callout map into a little always-on-top window. That's the whole app. That's it.

Work in Progress 'smart' feature to read mouse horizontal movements to determine a relative direction faced on your map to make call outs even more brain dead easy. You'll just have to look at where your arrow is pointing.

## Why this exists

There's already a good one (LucaFontanot/dbd-map-overlay) and it inspired this. But its OCR map detection was pissing me off.It would look for the map name that appears at the start of a game on a 1 second loop and keep changing it to the wrong map. I fix that by only reading when you press Tab, from a fixed spot, with strict matching. Read once, be confident, shut up.

> [!CAUTION]
> dbd runs easy anti-cheat in menus too, technically this is illegal, but similar projects have had no issues. I guarantee nothing, but you can use your own judgement

> [!IMPORTANT]  
> This exe isn't code-signed because I'm poor and make no money off of this. Windows smartscreen will probably warn on first launch since there are packages used to read your screen and m/k input. Don't worry, `DBD Smart Map Overlay` Only looks at your tab button being pressed, two fixed locations on your screen, and horizontal mouse movement only. If you trust this humble dbd/programming enthusiast, click "more info" then "run anyway". If defender quarantines it, allow it. Or don't, I'm not your dad.

## Status

Terminal version v0.1.0 works and is in releases.
UI in progress.
Player-map direction showing is up next.

## Requirements

- Windows: It leans on win32 for the click-through overlay.
- DBD Windowed/Borderless Fullscreen: regular fullscreen causes issues with reading keypresses to trigger map detecting

### For running source code
- The conda env. tesserocr is hell to pip on Windows and conda-forge just works.
    - Python 3.11 is used in the environment because of pytesserocr deps

#### Source Code Setup
**If you want just the exe**, go to `Releases` in the right pane of this webpage
```
conda env create -f environment.yml
conda activate dbdmap-env
python -m src.scraper   # download community map callouts
python -m main.py       # starts listener for OCR read -> map overlay trigger (tab)
```

## Where the maps come from

Real people who draw these for free: hens (through hens333.com), plus EagerFace, KaiserAleex, SamoelColt and others (through allmyperks.com). Map and realm names come from the DBD wiki. Full credits in `attributions.md`. Go be nice to them.

> [!TIP]

## Roadmap (the big stuff)

- [x] Scaffold, config, attributions
- [x] Scraper: grab every creator automatically, webp-ify, index by reference map name
- [x] Event-driven OCR: read `REALM - MAP` off the Tab scoreboard, gated on a tab keypress
- [x] Map Read Gate: don't actually show/replace a map overlay if it can't identify for certain we are in the tab menu. This means looking for other consistent menu text to ensure we are in the right spot
- [x] Overlay window: transparent, click-through, always-on-top, with hotkeys to cycle creator and variation, drag-to-place, and multi-floor maps
- [x] Ship an exe for an early headless release
- [ ] Heading arrow: a compass that tracks which way you're looking (mouse-integrated, so a bit drifty, and it will need re-zeroing), plus a manual rotate key. No spinning map, no fake "you are here" dot. Those would be lies, and reading game memory to do them properly is a one-way ticket to a ban.
- [ ] Settings GUI: pick creator, opacity, size, hotkeys, and calibrate the OCR region without hand-editing JSON like it's 2004
- [ ] Update checker: add a version checker to ensure latest version on release and prompt users to update if behind

## The lawyer bit

Unofficial fan project. Not affiliated with, endorsed by, or blessed by Behaviour Interactive. It is a passive overlay that reads your screen, tab button keypresses, and horizontal mouse movement. It does not touch the game's memory and it injects / controls nothing. Run borderless windowed, behave, don't be weird. Dead by Daylight and everything in it belongs to Behaviour.

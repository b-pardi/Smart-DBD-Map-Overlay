# Smart DBD Map Overlay

A Dead by Daylight map overlay that tells you where the hell shack and main are, so you can stop alt-tabbing to a wiki mid-chase like a coward.

It watches for the map name on the Tab scoreboard, and only when you actually press Tab, then drops the matching community callout map into a little always-on-top window. That's the whole app. That's it.

## Why this exists

There's already a good one (LucaFontanot/dbd-map-overlay) and it inspired this. Its one sin: it OCRs the loading screen on a 1 second loop with very loose matching, so one half-garbled frame yeets you onto the wrong map roughly constantly. We fix that by only reading when you press Tab, from a fixed spot, with strict matching. Read once, be confident, shut up.

Second thing: the DBD wiki has lovely map outlines that politely forget to mark where shack is, which is, you know, the entire damn point of a callout. Generating our own labels was a dead end (you can't invent a landmark that isn't in the source), so we just grab the real callout maps from the people who actually draw them.

## Status

Early. Honest version:

- Done: scaffolding, config defaults, and the scraper. It auto-downloads every callout from hens333.com and allmyperks.com, converts anything weird to webp, and builds a name index for the OCR to match against.
- Not done: the OCR, the overlay window, the settings UI, the exe. So right now it downloads a pile of maps and does absolutely nothing with them. Baby steps.

## Requirements

- Windows. It leans on win32 for the click-through overlay.
- DBD in borderless windowed. Exclusive fullscreen eats overlays for breakfast. Non-negotiable, same as every overlay ever made.
- The conda env. tesserocr is hell to pip on Windows and conda-forge just works.

## Setup

```
conda env create -f environment.yml
conda activate dbdmap-env
python -m src.scraper
```

That pulls the callout maps into `data/maps/` with progress bars and writes `data/maps_index.json`. Add `--force` to refresh, or `--source hens333` if you're feeling picky.

## Where the maps come from

Real people who draw these for free: Lethia (through hens333.com), plus EagerFace, KaiserAleex, SamoelColt and others (through allmyperks.com). Map and realm names come from the DBD wiki. Full credits in `attributions.md`. Go be nice to them.

## Roadmap (the big stuff)

- [x] Scaffold, config, attributions
- [x] Scraper: grab every creator automatically, webp-ify, index by canonical map name
- [ ] Event-driven OCR: read `REALM - MAP` off the Tab scoreboard, gated on a real keypress, strict match, zero misfires
- [ ] Overlay window: transparent, click-through, always-on-top, with hotkeys to cycle creator and variation
- [ ] Heading arrow: a compass that tracks which way you're looking (mouse-integrated, so a bit drifty, and it will need re-zeroing), plus a manual rotate key. No spinning map, no fake "you are here" dot. Those would be lies, and reading game memory to do them properly is a one-way ticket to a ban.
- [ ] Settings GUI: pick creator, opacity, size, hotkeys, and calibrate the OCR region without hand-editing JSON like it's 2004
- [ ] Ship an exe plus an auto-updater so normal humans can run it. SmartScreen will scream. It screams at everything unsigned. Ignore it.
- [ ] Someday, maybe: more styles, an official Hens art toggle, smarter variation matching, multi-monitor that doesn't fall over

## Style rules (yes, for a hobby project, fight me)

Docs like this one: short, human, a little sweary, occasionally taking the piss. If a paragraph reads like a press release or an LLM padding a word count, it's wrong. Delete it and try again. No em dashes. No "seamless," no "leverage," no "robust solution."

Code: comments are short lowercase phrases about why, not what (two lines max), docstrings stay concise, nothing is padded to line up in pretty columns, and it should read like a tired human wrote it, because one did.

## The lawyer bit

Unofficial fan project. Not affiliated with, endorsed by, or blessed by Behaviour Interactive. It is a passive overlay: it reads your screen and your own keypresses, it does not touch the game's memory and it injects nothing. Run borderless windowed, behave, don't be weird. Dead by Daylight and everything in it belongs to Behaviour.

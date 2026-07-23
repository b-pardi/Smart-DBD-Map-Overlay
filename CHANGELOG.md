# Changelog

## v0.1.0

- scraper builds the map callout index from hens333.com and allmyperks.com, keyed on reference wiki names
- key watch plus screen capture read the map name off the tab menu, gated so it only reads while the menu is up
- ocr matches the read name to a callout
- controller coordinates the capture, matching, and overlay threads
- transparent click-through overlay renders the matched callout, drag to place, position remembered
- configurable delays, hotkeys, and killswitch
- tesserocr runtime wiring and frozen/dev path handling
- headless self-test and a --debug region view
- one-file terminal build, prompts to download the callout maps to appdata on first run
- one-file terminal build via pyinstaller, bundles tesseract and the callout maps, seeds them to appdata on first run

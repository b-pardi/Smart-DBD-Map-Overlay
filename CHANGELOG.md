# Changelog

## v0.2.0
- reduced exe size by removing opencv replacing its uses with pillow and numpy
- initial ui build
    - overlay page: enable/disable automode, choose map and/or creator, visualize preview, self test on shipped screenshot
        - automode was enabled by default, added routing from ui to make automode optional
    - controls page: change hotkeys, text size, and scan timing
    - calibration page: move where the ocr anchor boxes will be looking if they are set wrong, and where the map overlay shows for user preference
    - instructions page: did you really need an elaboration here?
    - about page: buttons to check for updates, view github page, report issue, and attributions to map/game creators
- map search by text or filters
    - added low res map thumbnails for viewing maps in search

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

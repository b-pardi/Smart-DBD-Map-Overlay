## Work In Progress do not use

## v0.1.0-alpha

Looping in a SWF game has never been easier. Literally hit tab once in your game and in under a second you will see a map overlay.
Scrapes map layouts from the wiki and draws either a clock layout (Hen333 style) or 3x3 grid layout (simpler KaiserAleex style)

The option to use community made maps directly exists, however new maps will not be available until creators upload their maps.
The idea of the automated overlay generation is to circumvent the wait period between a new map and a creator releasing new maps that then need to be added and updated constantly.

> notice: The map overlays are **NOT** AI generated. dbd-smart-map generates the maps from the dbd wiki, and uses deterministic algorithms (e.g. Canny edge detection, Otsu thresholding, etc.) to draw onto the wiki map. dbd-smart-map uses OCR (Optical Character Recognition) to read the map name on your screen, but that's the only AI / Machine Learning in this tool.

**To run:**
1. Download the zip folder below.
    - Under the 'Assets' drop down menu at the bottom of this page.
2. Extract the folder `dbd-smart-map` anywhere on your computer. 
    - **DO NOT** extract _only_ the exe, keep the .exe file and _internal folder together when running.
3. Run `dbdbp.exe` from whatever folder you extracted it the zip into.
4. View the 'Instructions' tab in the UI to get started.

- **See [README.md](https://github.com/b-pardi/Smart-DBD-Map-Overlay/blob/main/README.md) [FAQ.md](https://github.com/b-pardi/Smart-DBD-Map-Overlay/blob/main/FAQ.md) or [CHANGELOG.md](https://github.com/b-pardi/Smart-DBD-Map-Overlay/blob/main/CHANGELOG.md) for more details**

> notice: dbd runs easy anti-cheat in menus too, technically this is illegal, but similar projects have had no issues. So while I can't guarantee your safety, you'll live.
>
> note: run dbd in borderless (windowed fullscreen), not exclusive fullscreen. exclusive fullscreen returns black screen-captures, can swallow the synthesized clicks, and blocks the global kill-switch hotkey. borderless looks identical and makes capture, clicking, and the f7/f8 hotkeys all work.

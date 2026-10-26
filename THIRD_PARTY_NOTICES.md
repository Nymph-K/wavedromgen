# Third-party notices

WaveDromGen v2 is built on the shoulders of several open-source projects.

## WaveDrom — waveform geometry and skin symbols

The file `WaveDromGen/resources/skins.json` contains the official WaveDrom skin
symbols (20×20 SVG "bricks"), converted from the WaveDrom npm package version
3.8.0 (`skins/default.js`, `lowkey.js`, `narrow.js`, `dark.js`).

The algorithms in `WaveDromGen/wavedrom_render.py` are a Python port of
WaveDrom's `parse-wave-lane.js`, `gen-first-wave-brick.js`, `gen-wave-brick.js`,
`gen-brick.js` and `find-lane-markers.js`.

Source: <https://github.com/wavedrom/wavedrom>

```
The MIT License (MIT)

Copyright (c) 2011-2026 Aliaksei Chapyzhenka

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## PySide6 / Qt

The desktop UI is built with [PySide6](https://doc.qt.io/qtforpython/) and Qt 6.
PySide6 and Qt are available under the LGPLv3 / GPLv3 / commercial licences.
WaveDromGen imports them as dynamically linked libraries; no Qt source is
modified or included in this repository. Users who redistribute a packaged
build should comply with the applicable LGPL requirements.

## json5

Relaxed JSON parsing uses [json5](https://github.com/dpranke/pyjson5), MIT
licence. It is an optional runtime import: strict JSON continues to work if
json5 is unavailable.

## Original WaveDromGen

WaveDromGen v1 (Tkinter) was created by Henson and later improved by
blueyesess/Tony Nguyen and contributors:
<https://github.com/blueyesess/wavedromgen>.

The v2 implementation is a new Qt codebase. The original project's icon asset
(`asset/app.ico`) and name are retained for continuity.

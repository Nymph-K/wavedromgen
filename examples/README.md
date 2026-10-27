# Example diagrams

Open these with:

```bash
python main.py examples/demo.json
python main.py examples/ddr_read.json
python main.py examples/groups.json
python main.py examples/arrows.json
```

- `demo.json` — a six-lane UART-style frame with a bus, data labels, head/foot
  text and tick marks.
- `ddr_read.json` — the DDR read transaction from the WaveDrom tutorial,
  exercising `period`, `phase`, buses and data labels.
- `groups.json` — nested signal groups (`Master`/`ctrl`, `Slave`/`ctrl`), an
  empty `{}` spacer lane and array `data` labels.
- `arrows.json` — the arrows and sharp-lines tutorial example: `node` markers,
  curved and orthogonal `edge` relations, JSONML `head` text, `phase` on lanes
  without a waveform, and an unknown top-level field that is preserved.

All characters follow the WaveDrom wave syntax:
<https://wavedrom.com/tutorial.html>.
